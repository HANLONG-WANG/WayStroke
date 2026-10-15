//! Portable configuration migration and device-local, durable backups.
use std::{collections::{BTreeMap,BTreeSet}, fs, path::PathBuf};
use serde::{Deserialize, Serialize};
use waystroke_model::{Binding, Config, Reference, Step, TextPart, Workflow};
use waystroke_protocol::{BackupSummary, Commit, ConfigCounts, Error, ErrorKind, ImportPreview, ImportMode};
use crate::{Repository, error, io_error, write_atomic};

#[derive(Clone, Serialize, Deserialize)]
#[serde(rename_all="camelCase", deny_unknown_fields)]
pub struct Backup { pub id:String, pub created_at:String, pub reason:String, pub config:Config }
#[derive(Clone)]
pub struct Inspection { pub token:String, pub revision:u32, pub config:Config }

fn checked(config:Config)->Result<Config,Error> {
    let details=waystroke_model::validate(&config);
    if details.is_empty(){Ok(config)}else{Err(Error{kind:ErrorKind::Validation,message:"配置校验失败，未修改当前配置".into(),details})}
}
/// Setup/authorization stay local; stable device selection is a saved preference.
pub fn portable(mut config:Config)->Config {config.settings.setup_complete=false;config}
fn counts(c:&Config)->ConfigCounts {ConfigCounts{rules:c.rules.len(),gestures:c.gestures.len(),workflows:c.workflows.len(),snippets:c.snippets.len(),applications:c.applications.len(),exclusions:c.exclusions.len()}}
fn fresh()->String {uuid::Uuid::new_v4().to_string()}
fn map_id(id:&mut String,ids:&BTreeMap<String,String>){if let Some(next)=ids.get(id){*id=next.clone();}}
fn reference(r:&mut Reference,ids:&BTreeMap<String,String>,returned:&BTreeSet<String>){if returned.contains(&r.symbol_id){if let Some(field)=r.path.first_mut(){map_id(field,ids);}}map_id(&mut r.symbol_id,ids);}
fn binding(b:&mut Binding,ids:&BTreeMap<String,String>,returned:&BTreeSet<String>){match b {
    Binding::Reference(r)=>reference(r,ids,returned),Binding::Template(parts)=>for p in parts{if let TextPart::Reference(r)=p{reference(r,ids,returned)}},
    Binding::List(items)=>for b in items{binding(b,ids,returned)},Binding::Object(fields)=>for b in fields.values_mut(){binding(b,ids,returned)},Binding::Literal(_)=>{},
}}
fn collect_steps(steps:&[Step],ids:&mut BTreeMap<String,String>,returned:&mut BTreeSet<String>){for s in steps{if s.action=="flow.call"{if let Some(output)=&s.output{returned.insert(output.id.clone());}}ids.insert(s.id.clone(),fresh());for symbol in [&s.output,&s.loop_item,&s.loop_index].into_iter().flatten(){ids.insert(symbol.id.clone(),fresh());}collect_steps(&s.children,ids,returned);collect_steps(&s.otherwise,ids,returned);}}
fn steps(items:&mut [Step],ids:&BTreeMap<String,String>,returned:&BTreeSet<String>){for s in items{
    map_id(&mut s.id,ids);for symbol in [&mut s.output,&mut s.loop_item,&mut s.loop_index].into_iter().flatten(){map_id(&mut symbol.id,ids);}
    if let Some(id)=&mut s.workflow_id{map_id(id,ids)}
    for b in s.params.values_mut(){binding(b,ids,returned)}
    s.arguments=std::mem::take(&mut s.arguments).into_iter().map(|(mut id,mut b)|{map_id(&mut id,ids);binding(&mut b,ids,returned);(id,b)}).collect();
    steps(&mut s.children,ids,returned);steps(&mut s.otherwise,ids,returned);
}}
fn workflow(w:&mut Workflow,ids:&BTreeMap<String,String>,returned:&BTreeSet<String>){map_id(&mut w.id,ids);for i in &mut w.inputs{map_id(&mut i.symbol.id,ids);if let Some(b)=&mut i.default{binding(b,ids,returned)}}for o in &mut w.outputs{map_id(&mut o.symbol.id,ids);binding(&mut o.value,ids,returned)}steps(&mut w.steps,ids,returned);}
fn unique_name(name:&mut String,existing:impl Iterator<Item=String>){let names:Vec<_>=existing.collect();if names.contains(name){name.push_str(" 副本");while names.contains(name){name.push_str(" 副本");}}}
fn identity_set(c:&Config)->BTreeSet<String>{
    let mut ids=BTreeSet::new();
    for g in &c.gestures{ids.insert(g.id.clone());for sample in &g.samples{ids.insert(sample.id.clone());}}
    for w in &c.workflows{ids.insert(w.id.clone());for input in &w.inputs{ids.insert(input.symbol.id.clone());}for output in &w.outputs{ids.insert(output.symbol.id.clone());}step_identity_set(&w.steps,&mut ids);}
    for rule in &c.rules{ids.insert(rule.id.clone());step_identity_set(&rule.steps,&mut ids);}
    for snippet in &c.snippets{ids.insert(snippet.id.clone());}ids
}
fn step_identity_set(steps:&[Step],ids:&mut BTreeSet<String>){for step in steps{ids.insert(step.id.clone());for symbol in [&step.output,&step.loop_item,&step.loop_index].into_iter().flatten(){ids.insert(symbol.id.clone());}step_identity_set(&step.children,ids);step_identity_set(&step.otherwise,ids);}}
/// Preserve independent identities. Conflicting entities and their copied local IDs
/// are remapped; application IDs remain desktop identities and text stays literal.
pub fn merge(current:&Config,mut incoming:Config)->Result<Config,Error>{
    let mut out=current.clone();let mut ids=BTreeMap::new();let mut returned=BTreeSet::new();
    for g in &incoming.gestures{ids.insert(g.id.clone(),fresh());for s in &g.samples{ids.insert(s.id.clone(),fresh());}}
    for w in &incoming.workflows{ids.insert(w.id.clone(),fresh());for i in &w.inputs{ids.insert(i.symbol.id.clone(),fresh());}for o in &w.outputs{ids.insert(o.symbol.id.clone(),fresh());}collect_steps(&w.steps,&mut ids,&mut returned);}
    for r in &incoming.rules{ids.insert(r.id.clone(),fresh());collect_steps(&r.steps,&mut ids,&mut returned);}
    let occupied=identity_set(current);let mut copied_locals=BTreeSet::new();
    for g in &incoming.gestures{if occupied.contains(&g.id){copied_locals.extend(g.samples.iter().map(|s|s.id.clone()));}}
    for w in &incoming.workflows{if occupied.contains(&w.id){copied_locals.extend(w.inputs.iter().map(|i|i.symbol.id.clone()));copied_locals.extend(w.outputs.iter().map(|o|o.symbol.id.clone()));step_identity_set(&w.steps,&mut copied_locals);}}
    for r in &incoming.rules{if occupied.contains(&r.id){step_identity_set(&r.steps,&mut copied_locals);}}
    ids.retain(|id,_|occupied.contains(id)||copied_locals.contains(id));
    for a in incoming.applications{if !out.applications.iter().any(|e|e.id==a.id){out.applications.push(a)}}
    for e in incoming.exclusions{if !out.exclusions.iter().any(|old|old.application_id==e.application_id){out.exclusions.push(e)}}
    for g in &mut incoming.gestures{map_id(&mut g.id,&ids);map_id(&mut g.main_sample_id,&ids);for s in &mut g.samples{map_id(&mut s.id,&ids)}unique_name(&mut g.name,out.gestures.iter().map(|g|g.name.clone()));out.gestures.push(g.clone());}
    for mut w in incoming.workflows{workflow(&mut w,&ids,&returned);unique_name(&mut w.name,out.workflows.iter().map(|w|w.name.clone()));out.workflows.push(w);}
    for mut r in incoming.rules{
        // Detect equivalent triggers against original geometry as well as IDs.
        let source=incoming.gestures.iter().find(|g|g.id==*ids.get(&r.gesture_id).unwrap_or(&r.gesture_id));
        let conflict=current.rules.iter().any(|old|old.application_id==r.application_id&&old.title_match==r.title_match&&{
            let mut a=old.auxiliary_buttons.clone();let mut b=r.auxiliary_buttons.clone();a.sort();b.sort();a==b
        }&&(old.gesture_id==r.gesture_id||source.is_some_and(|g|current.gestures.iter().find(|g|g.id==old.gesture_id).is_some_and(|old|old.samples.iter().any(|a|g.samples.iter().any(|b|crate::gesture::similarity(&a.points,&b.points)>99.9))))));
        if conflict||current.rules.iter().any(|old|old.id==r.id){r.enabled=false;}
        map_id(&mut r.id,&ids);map_id(&mut r.gesture_id,&ids);steps(&mut r.steps,&ids,&returned);unique_name(&mut r.name,out.rules.iter().map(|r|r.name.clone()));out.rules.push(r);
    }
    for mut t in incoming.snippets{if out.snippets.iter().any(|old|old.key==t.key&&old.application_id==t.application_id){continue}if occupied.contains(&t.id){t.id=fresh();}out.snippets.push(t);}
    checked(out)
}
impl Repository {
    fn backup_path(&self,id:&str)->Result<PathBuf,Error>{uuid::Uuid::parse_str(id).map_err(|_|error(ErrorKind::Validation,"备份标识无效"))?;Ok(self.backup_path.join(format!("{id}.json")))}
    pub fn list_backups(&self)->Result<Vec<Backup>,Error>{
        if !self.backup_path.exists(){return Ok(vec![])}
        let mut entries=vec![];
        for entry in fs::read_dir(&self.backup_path).map_err(io_error)?{let path=entry.map_err(io_error)?.path();if path.extension().is_some_and(|e|e=="json"){let b=self.read_backup(path.file_stem().and_then(|s|s.to_str()).unwrap_or(""))?;entries.push(b);}}
        entries.sort_by(|a,b|b.created_at.cmp(&a.created_at).then_with(||b.id.cmp(&a.id)));Ok(entries)
    }
    fn read_backup(&self,id:&str)->Result<Backup,Error>{let b:Backup=serde_json::from_slice(&fs::read(self.backup_path(id)?).map_err(io_error)?).map_err(|e|error(ErrorKind::Validation,format!("备份无法读取：{e}")))?;if b.id!=id{return Err(error(ErrorKind::Validation,"备份身份不符"))}checked(b.config.clone())?;Ok(b)}
    pub fn create_backup(&self,reason:&str)->Result<Backup,Error>{
        let b=Backup{id:fresh(),created_at:chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Nanos,true),reason:reason.into(),config:portable(self.snapshot.config.clone())};
        write_atomic(&self.backup_path(&b.id)?,&serde_json::to_vec_pretty(&b).map_err(|e|error(ErrorKind::Internal,e.to_string()))?)?;
        // Verify the durable file before permitting any destructive commit.
        self.read_backup(&b.id)?;
        for old in self.list_backups()?.into_iter().skip(5){fs::remove_file(self.backup_path(&old.id)?).map_err(io_error)?;}
        Ok(b)
    }
    fn apply_portable(&mut self,mut config:Config,expected_revision:u32,reason:&str)->Result<waystroke_protocol::Snapshot,Error>{
        if expected_revision!=self.snapshot.revision{return Err(error(ErrorKind::Conflict,"配置已改变，请重新检查文件"))}
        config.settings.setup_complete=self.snapshot.config.settings.setup_complete;
        checked(config.clone())?;self.create_backup(reason)?;
        let snapshot=self.commit(Commit{request_id:fresh(),expected_revision,config})?;
        self.inspection=None;Ok(snapshot)
    }
    pub fn configuration(&mut self,request:serde_json::Value)->Result<serde_json::Value,Error>{
        use serde_json::json;
        use waystroke_protocol::ConfigurationRequest::*;
        let request=serde_json::from_value::<waystroke_protocol::ConfigurationRequest>(request).map_err(|e|error(ErrorKind::Validation,e.to_string()))?;
        match request{
            ExportConfig=>Ok(json!({"content":serde_json::to_string_pretty(&portable(self.snapshot.config.clone())).unwrap()})),
            InspectImport{content}=>{
                let config=checked(serde_json::from_str::<Config>(&content).map_err(|e|error(ErrorKind::Validation,format!("配置文件无法读取：{e}")))?)?;
                let merged=merge(&self.snapshot.config,config.clone())?;let token=fresh();
                let preview=ImportPreview{token:token.clone(),revision:self.snapshot.revision,source:counts(&config),merge:counts(&merged),disabled_rules:merged.rules.iter().skip(self.snapshot.config.rules.len()).filter(|r|!r.enabled).count(),skipped_snippets:config.snippets.len()+self.snapshot.config.snippets.len()-merged.snippets.len()};
                self.inspection=Some(Inspection{token,revision:self.snapshot.revision,config});Ok(json!(preview))
            },
            ApplyImport{token,mode,expected_revision}=>{
                let inspection=self.inspection.as_ref().filter(|i|i.token==token&&i.revision==self.snapshot.revision).ok_or_else(||error(ErrorKind::Conflict,"导入检查已过期，请重新选择文件"))?;
                let config=match mode{ImportMode::Merge=>merge(&self.snapshot.config,inspection.config.clone())?,ImportMode::Replace=>inspection.config.clone()};
                Ok(json!(self.apply_portable(config,expected_revision,"导入前自动备份")?))
            },
            RestoreBackup{id,expected_revision}=>{let config=self.read_backup(&id)?.config;Ok(json!(self.apply_portable(config,expected_revision,"恢复前自动备份")?))},
            CreateBackup=>{let b=self.create_backup("手动备份")?;Ok(json!({"id":b.id}))},
            ListBackups=>Ok(json!(self.list_backups()?.iter().map(|b|BackupSummary{id:b.id.clone(),created_at:b.created_at.clone(),reason:b.reason.clone(),rules:b.config.rules.len(),gestures:b.config.gestures.len()}).collect::<Vec<_>>())),
            DeleteBackup{id}=>{fs::remove_file(self.backup_path(&id)?).map_err(io_error)?;fs::File::open(&self.backup_path).and_then(|f|f.sync_all()).map_err(io_error)?;Ok(json!(null))},
            ExportBackup{id}=>Ok(json!({"content":serde_json::to_string_pretty(&self.read_backup(&id)?.config).unwrap()})),
        }
    }

}
pub fn state_path()->Result<PathBuf,Error>{
    let base=match std::env::var_os("XDG_STATE_HOME"){Some(p) if std::path::Path::new(&p).is_absolute()=>PathBuf::from(p),_=>PathBuf::from(std::env::var_os("HOME").ok_or_else(||error(ErrorKind::Io,"缺少用户主目录"))?).join(".local/state")};
    Ok(base.join("waystroke/backups"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use waystroke_model::*;
    fn fixture()->Config {
        let mut c=Config::default();
        let variable=Symbol{id:"symbol".into(),name:"结果".into(),kind:ValueKind::Text};
        let mut step=Step{id:"step".into(),action:"variable".into(),enabled:true,params:BTreeMap::from([("kind".into(),Binding::Literal(Value::Text("文本".into()))),("value".into(),Binding::Literal(Value::Text("symbol".into())))]),output:Some(variable.clone()),on_failure:FailurePolicy::Stop,timeout_ms:None,workflow_id:None,arguments:BTreeMap::new(),children:vec![],otherwise:vec![],loop_item:None,loop_index:None};
        let workflow=Workflow{id:"workflow".into(),name:"动作".into(),description:String::new(),inputs:vec![],outputs:vec![Output{symbol:Symbol{id:"return".into(),name:"返回".into(),kind:ValueKind::Text},value:Binding::Reference(Reference{symbol_id:variable.id,path:vec![],kind:ValueKind::Text})}],steps:vec![step.clone()]};
        step.id="call".into();step.action="flow.call".into();step.params.clear();step.output=None;step.workflow_id=Some(workflow.id.clone());
        c.workflows.push(workflow);c.gestures.push(Gesture{id:"gesture".into(),name:"手势".into(),main_sample_id:"sample".into(),samples:vec![Sample{id:"sample".into(),points:vec![[0.,0.],[20.,30.]]}]});
        c.rules.push(Rule{id:"rule".into(),name:"规则".into(),enabled:true,feedback:true,gesture_id:"gesture".into(),auxiliary_buttons:vec![],application_id:None,title_match:TitleCondition{operator:TitleOperator::Contains,value:String::new()},steps:vec![step]});
        c.snippets.push(TextRule{id:"snippet".into(),key:";hello".into(),value:"private text".into(),enabled:true,application_id:None,trigger:TextTrigger::Confirm,case_sensitive:false,boundary:true,preserve:true});
        assert!(validate(&c).is_empty(),"{:?}",validate(&c));c
    }
    #[test]
    fn merge_remaps_internal_references_and_preserves_preferences_and_text(){
        let mut current=fixture();current.settings.feedback=false;
        let incoming=fixture();let c=merge(&current,incoming).unwrap();
        assert!(!c.settings.feedback);assert_eq!(c.snippets.len(),1);assert_eq!(c.gestures.len(),2);assert_eq!(c.workflows.len(),2);assert!(!c.rules[1].enabled);
        assert_ne!(c.workflows[0].id,c.workflows[1].id);assert_eq!(c.rules[1].steps[0].workflow_id.as_ref(),Some(&c.workflows[1].id));
        assert_eq!(c.rules[1].gesture_id,c.gestures[1].id);assert_eq!(c.gestures[1].main_sample_id,c.gestures[1].samples[0].id);
        let Binding::Reference(r)=&c.workflows[1].outputs[0].value else{panic!()};assert_eq!(r.symbol_id,c.workflows[1].steps[0].output.as_ref().unwrap().id);
        assert_eq!(c.workflows[1].steps[0].params["value"],Binding::Literal(Value::Text("symbol".into())));
    }
    #[test]
    fn merge_preserves_call_arguments_and_return_paths(){
        let mut incoming=fixture();
        incoming.workflows[0].inputs.push(Input{symbol:Symbol{id:"input".into(),name:"输入".into(),kind:ValueKind::Text},default:None});
        incoming.rules[0].steps[0].arguments.insert("input".into(),Binding::Literal(Value::Text("input".into())));
        incoming.rules[0].steps[0].output=Some(Symbol{id:"call-output".into(),name:"调用结果".into(),kind:ValueKind::Data});
        let mut consumer=incoming.workflows[0].steps[0].clone();consumer.id="consumer".into();consumer.output=None;
        consumer.params.insert("value".into(),Binding::Reference(Reference{symbol_id:"call-output".into(),path:vec!["return".into()],kind:ValueKind::Text}));
        incoming.rules[0].steps.push(consumer);
        let independent=merge(&Config::default(),incoming.clone()).unwrap();assert_eq!(independent.workflows[0].id,incoming.workflows[0].id);
        let merged=merge(&fixture(),incoming).unwrap();let workflow=&merged.workflows[1];let call=&merged.rules[1].steps[0];
        assert_eq!(call.arguments[&workflow.inputs[0].symbol.id],Binding::Literal(Value::Text("input".into())));
        let Binding::Reference(r)=&merged.rules[1].steps[1].params["value"] else{panic!()};
        assert_eq!(r.symbol_id,call.output.as_ref().unwrap().id);assert_eq!(r.path[0],workflow.outputs[0].symbol.id);
        // Ordinary structured data keys are user data, even when equal to another entity ID.
        let mut ordinary=Reference{symbol_id:"data-output".into(),path:vec!["return".into()],kind:ValueKind::Text};
        reference(&mut ordinary,&BTreeMap::from([("return".into(),"new-return".into()),("data-output".into(),"new-data".into())]),&BTreeSet::from(["call-output".into()]));
        assert_eq!(ordinary.symbol_id,"new-data");assert_eq!(ordinary.path[0],"return");
    }
    #[test]
    fn import_backup_restore_restart_and_failure_are_atomic(){
        let root=std::env::temp_dir().join(format!("waystroke-migration-{}",fresh()));fs::create_dir_all(&root).unwrap();
        let path=root.join("config.json");let mut repo=Repository::open(path.clone()).unwrap();repo.backup_path=root.join("state/backups");
        let mut original=fixture();original.settings.mouse_device_id=Some("local-device".into());original.settings.setup_complete=true;
        repo.commit(Commit{request_id:"test".into(),expected_revision:0,config:original.clone()}).unwrap();
        let export=repo.configuration(json!({"operation":"export_config"})).unwrap();let portable_config:Config=serde_json::from_str(export["content"].as_str().unwrap()).unwrap();assert_eq!(portable_config.settings.mouse_device_id,original.settings.mouse_device_id);assert!(!portable_config.settings.setup_complete);
        let before=fs::read(&path).unwrap();let mut invalid=fixture();invalid.schema_version=900;
        assert!(repo.configuration(json!({"operation":"inspect_import","content":serde_json::to_string(&invalid).unwrap()})).is_err());assert_eq!(fs::read(&path).unwrap(),before);
        let mut unknown=fixture();unknown.rules[0].steps[0].action="unknown.action".into();
        let mut missing=fixture();missing.rules[0].gesture_id="missing".into();
        let mut recursive=fixture();let mut call=recursive.rules[0].steps[0].clone();call.id="recursive-call".into();recursive.workflows[0].steps=vec![call];recursive.workflows[0].outputs.clear();
        for invalid in [unknown,missing,recursive]{assert!(repo.configuration(json!({"operation":"inspect_import","content":serde_json::to_string(&invalid).unwrap()})).is_err());assert_eq!(fs::read(&path).unwrap(),before);}
        let inspect=repo.configuration(json!({"operation":"inspect_import","content":serde_json::to_string(&Config::default()).unwrap()})).unwrap();
        assert!(repo.configuration(json!({"operation":"apply_import","token":inspect["token"],"mode":"replace","expectedRevision":0})).is_err());
        fs::write(root.join("blocked"),b"file").unwrap();let backup_path=repo.backup_path.clone();repo.backup_path=root.join("blocked/backups");
        assert!(repo.configuration(json!({"operation":"apply_import","token":inspect["token"],"mode":"replace","expectedRevision":1})).is_err());assert_eq!(repo.snapshot.revision,1);assert_eq!(fs::read(&path).unwrap(),before);
        repo.backup_path=backup_path.clone();repo.configuration(json!({"operation":"apply_import","token":inspect["token"],"mode":"replace","expectedRevision":1})).unwrap();assert!(repo.snapshot.config.rules.is_empty());assert_eq!(repo.snapshot.config.settings.mouse_device_id,None);
        let list=repo.list_backups().unwrap();assert_eq!(list.len(),1);let backup_id=list[0].id.clone();assert_eq!(list[0].config.rules,original.rules);
        let mut restarted=Repository::open(path).unwrap();restarted.backup_path=backup_path;assert_eq!(restarted.list_backups().unwrap()[0].id,backup_id);
        restarted.configuration(json!({"operation":"restore_backup","id":backup_id,"expectedRevision":2})).unwrap();assert_eq!(restarted.snapshot.config,original);assert_eq!(restarted.list_backups().unwrap().len(),2);
        for _ in 0..5{restarted.create_backup("manual").unwrap();}assert_eq!(restarted.list_backups().unwrap().len(),5);
        let id=restarted.list_backups().unwrap()[0].id.clone();let exported=restarted.configuration(json!({"operation":"export_backup","id":id})).unwrap();assert_eq!(serde_json::from_str::<Config>(exported["content"].as_str().unwrap()).unwrap().rules,original.rules);
        restarted.configuration(json!({"operation":"delete_backup","id":id})).unwrap();assert_eq!(restarted.list_backups().unwrap().len(),4);fs::remove_dir_all(root).unwrap();
    }
}
