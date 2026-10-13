//! Direction/order/aspect preserving freeform recognition; no rotation fitting.
use waystroke_model::{Config,TitleOperator};
use waystroke_protocol::{RecognitionRequest,RecognitionResult,RecognitionOutcome,Candidate};
const SAMPLES:usize=64;
pub fn length(points:&[[f64;2]])->f64 { points.windows(2).map(|p|(p[1][0]-p[0][0]).hypot(p[1][1]-p[0][1])).sum() }
pub fn normalized(points:&[[f64;2]])->Option<[[f64;2];SAMPLES]> {
    if points.len()<2||points.iter().flatten().any(|n|!n.is_finite()) {return None;}
    let total=length(points);if total<=0. {return None;}
    let mut result=[[0.;2];SAMPLES];let mut segment=1;let mut covered=0.;
    for (i,point) in result.iter_mut().enumerate() {
        let distance=total*i as f64/(SAMPLES-1) as f64;
        while segment<points.len()-1 {
            let part=(points[segment][0]-points[segment-1][0]).hypot(points[segment][1]-points[segment-1][1]);
            if covered+part>=distance {break;}covered+=part;segment+=1;
        }
        let a=points[segment-1];let b=points[segment];let part=(b[0]-a[0]).hypot(b[1]-a[1]);let t=if part>0. {(distance-covered)/part}else{0.};
        *point=[a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t];
    }
    let min_x=result.iter().map(|p|p[0]).fold(f64::INFINITY,f64::min);let max_x=result.iter().map(|p|p[0]).fold(f64::NEG_INFINITY,f64::max);
    let min_y=result.iter().map(|p|p[1]).fold(f64::INFINITY,f64::min);let max_y=result.iter().map(|p|p[1]).fold(f64::NEG_INFINITY,f64::max);
    let scale=(max_x-min_x).max(max_y-min_y);if scale<=0. {return None;}
    let center=[result.iter().map(|p|p[0]).sum::<f64>()/SAMPLES as f64,result.iter().map(|p|p[1]).sum::<f64>()/SAMPLES as f64];
    for point in &mut result {*point=[(point[0]-center[0])/scale,(point[1]-center[1])/scale];}Some(result)
}
pub fn similarity(a:&[[f64;2]],b:&[[f64;2]])->f64 {
    let (Some(a),Some(b))=(normalized(a),normalized(b)) else{return 0.;};
    let distance=a.iter().zip(&b).map(|(a,b)|(a[0]-b[0]).hypot(a[1]-b[1])).sum::<f64>()/SAMPLES as f64;
    (-4.*distance).exp()*100.
}
pub fn recognize(config:&Config,request:&RecognitionRequest)->RecognitionResult {
    let length=length(&request.points);let result=|outcome,reason:&str,candidates,rule_id|RecognitionResult{outcome,rule_id,candidates,length,reason:reason.into()};
    if !config.settings.gestures_enabled||request.context.locked{return result(RecognitionOutcome::Disabled,"手势已暂停",vec![],None);}
    if config.exclusions.iter().any(|e|e.gestures&&Some(&e.application_id)==request.context.application_id.as_ref()){return result(RecognitionOutcome::Excluded,"起点应用已排除，原始鼠标操作透传",vec![],None);}
    if length<config.settings.minimum_length||normalized(&request.points).is_none(){return result(RecognitionOutcome::TooShort,"未达到最小逻辑像素长度",vec![],None);}
    let mut buttons=request.auxiliary_buttons.clone();buttons.sort_unstable();buttons.dedup();
    let mut candidates=vec![];
    for rule in &config.rules {
        if !rule.enabled {continue;}
        let mut expected=rule.auxiliary_buttons.clone();expected.sort_unstable();expected.dedup();if expected!=buttons {continue;}
        if rule.application_id.is_some()&&rule.application_id!=request.context.application_id {continue;}
        let condition=&rule.title_match;let has_title=!condition.value.is_empty();
        if has_title {
            let Some(title)=request.context.title.as_deref() else {continue;};
            let matches=match condition.operator{TitleOperator::Contains=>title.contains(&condition.value),TitleOperator::Equals=>title==condition.value,TitleOperator::NotContains=>!title.contains(&condition.value)};
            if !matches {continue;}
        }
        let Some(gesture)=config.gestures.iter().find(|g|g.id==rule.gesture_id) else {continue;};
        let Some((sample,score))=gesture.samples.iter().map(|s|(s,similarity(&request.points,&s.points))).max_by(|a,b|a.1.total_cmp(&b.1)) else {continue;};
        let priority=match(rule.application_id.is_some(),has_title){(true,true)=>3,(true,false)=>2,(false,true)=>1,(false,false)=>0};
        candidates.push(Candidate{rule_id:rule.id.clone(),rule_name:rule.name.clone(),gesture_id:gesture.id.clone(),sample_id:sample.id.clone(),score,priority});
    }
    candidates.sort_by(|a,b|b.priority.cmp(&a.priority).then(b.score.total_cmp(&a.score)).then(a.rule_id.cmp(&b.rule_id)));
    let eligible=candidates.iter().filter(|c|c.score>=config.settings.similarity).collect::<Vec<_>>();
    let Some(first)=eligible.first() else{return result(RecognitionOutcome::NoMatch,"没有候选达到识别阈值",candidates,None);};
    if eligible.get(1).is_some_and(|second|second.priority==first.priority&&first.score-second.score<config.settings.ambiguity_gap){return result(RecognitionOutcome::Ambiguous,"同级候选分差不足，不执行动作",candidates,None);}
    let id=first.rule_id.clone();result(RecognitionOutcome::Matched,"已按起点窗口范围和辅助键匹配",candidates,Some(id))
}
#[cfg(test)]
mod tests {
    use super::*;
    use waystroke_model::*;
    fn stroke()->Vec<[f64;2]>{vec![[0.,0.],[120.,0.],[120.,80.]]}
    #[test]
    fn normalization_preserves_direction_order_and_aspect() {
        let points=stroke();let scaled=points.iter().map(|p|[p[0]*3.+50.,p[1]*3.-25.]).collect::<Vec<_>>();
        assert!((similarity(&points,&scaled)-100.).abs()<1e-9);
        let reverse=points.iter().rev().copied().collect::<Vec<_>>();let rotate=points.iter().map(|p|[-p[1],p[0]]).collect::<Vec<_>>();let distorted=points.iter().map(|p|[p[0]*3.,p[1]]).collect::<Vec<_>>();
        assert!(similarity(&points,&reverse)<82.);assert!(similarity(&points,&rotate)<82.);assert!(similarity(&points,&distorted)<similarity(&points,&scaled));
        assert_eq!(normalized(&[[1.,1.],[1.,1.]]),None);
    }
    fn request()->RecognitionRequest {RecognitionRequest{points:stroke(),auxiliary_buttons:vec![],context:StartContext{sequence:1,monotonic_ms:1.,position:[1.,1.],window:None,application_id:Some("app".into()),title:Some("Editor".into()),workspace:Some(0),monitor:Some(0),locked:false}}}
    fn rule(id:&str,app:Option<String>)->Rule{Rule{id:id.into(),name:id.into(),enabled:true,feedback:true,gesture_id:"g".into(),auxiliary_buttons:vec![],application_id:app,title_match:TitleCondition{operator:TitleOperator::Contains,value:String::new()},steps:vec![]}}
    #[test]
    fn priority_fallback_ambiguity_and_exclusions() {
        let mut c=Config::default();c.gestures.push(Gesture{id:"g".into(),name:"g".into(),main_sample_id:"s".into(),samples:vec![Sample{id:"s".into(),points:stroke()}]});
        c.rules=vec![rule("global",None),rule("app",Some("app".into()))];assert_eq!(recognize(&c,&request()).rule_id.as_deref(),Some("app"));
        c.rules[1].enabled=false;assert_eq!(recognize(&c,&request()).rule_id.as_deref(),Some("global"));
        c.rules.push(rule("another-global",None));assert_eq!(recognize(&c,&request()).outcome,RecognitionOutcome::Ambiguous);
        c.exclusions.push(Exclusion{application_id:"app".into(),gestures:true,text:false});assert_eq!(recognize(&c,&request()).outcome,RecognitionOutcome::Excluded);
        c.exclusions.clear();let mut r=request();r.points=vec![[0.,0.],[11.9,0.]];assert_eq!(recognize(&c,&r).outcome,RecognitionOutcome::TooShort);
    }
}
