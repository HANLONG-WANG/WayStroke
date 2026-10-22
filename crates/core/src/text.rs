//! Shared matcher for page previews and desktop adapters. Confirmation has not
//! yet entered the application; adapters preserve or consume it after editing.
use waystroke_model::{Config, TextRule, TextTrigger};
use waystroke_protocol::{TextExpansion, TextInputTrigger, TextMatchRequest};

fn same_keyword(a:&TextRule,b:&TextRule)->bool {
    if a.case_sensitive && b.case_sensitive { a.key==b.key }
    else { a.key.to_lowercase()==b.key.to_lowercase() }
}

pub fn match_text(config:&Config, context:&TextMatchRequest)->Option<TextExpansion> {
    if !config.settings.text_enabled || context.composing
        || (context.password && !context.terminal)
        || (context.terminal && !config.settings.terminal_text_enabled)
        || config.exclusions.iter().any(|e|e.application_id==context.application_id && e.text) {
        return None;
    }
    let eligible:Vec<_>=config.snippets.iter().filter(|r|r.enabled &&
        r.application_id.as_ref().is_none_or(|app|app==&context.application_id)).collect();
    let mut rules:Vec<_>=eligible.iter().copied().filter(|rule|rule.application_id.is_some() ||
        !eligible.iter().any(|local|local.application_id.is_some() && same_keyword(rule,local))).collect();
    rules.sort_by_key(|r|(std::cmp::Reverse(r.application_id.is_some()),std::cmp::Reverse(r.key.chars().count())));
    for rule in rules {
        let triggered=matches!((&rule.trigger,&context.trigger),
            (TextTrigger::Immediate,TextInputTrigger::Commit) |
            (TextTrigger::Confirm,TextInputTrigger::Space | TextInputTrigger::Enter) |
            (TextTrigger::Space,TextInputTrigger::Space) |
            (TextTrigger::Enter,TextInputTrigger::Enter));
        if !triggered || rule.key.is_empty() {continue}
        // Compare original suffixes rather than indexing a lowercased string:
        // Unicode lowercase can change the number of scalar values.
        let start=context.before_cursor.char_indices().map(|(i,_)|i).find(|&i| {
            let suffix=&context.before_cursor[i..];
            if rule.case_sensitive {suffix==rule.key}
            else {suffix.to_lowercase()==rule.key.to_lowercase()}
        });
        let Some(start)=start else {continue};
        if rule.boundary && context.before_cursor[..start].chars().next_back()
            .is_some_and(|c|c.is_alphanumeric() || c=='_') {continue}
        return Some(TextExpansion {
            rule_id:rule.id.clone(), delete_chars:context.before_cursor[start..].chars().count() as u32,
            keyword:context.before_cursor[start..].into(), replacement:rule.value.clone(),
            confirmation:match context.trigger {TextInputTrigger::Commit=>"",TextInputTrigger::Space=>" ",TextInputTrigger::Enter=>"\n"}.into(),
            preserve:rule.preserve,
        });
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;
    fn rule(id:&str,app:Option<&str>,trigger:TextTrigger)->TextRule {
        TextRule{id:id.into(),key:";你好".into(),value:"第一行\n第二行".into(),enabled:true,
            application_id:app.map(str::to_owned),trigger,case_sensitive:true,boundary:true,preserve:true}
    }
    fn context()->TextMatchRequest {TextMatchRequest{application_id:"app".into(),before_cursor:";你好".into(),trigger:TextInputTrigger::Space,composing:false,password:false,terminal:false}}
    #[test]
    fn trigger_override_and_disabled_fallback() {
        let mut config=Config::default();config.snippets=vec![rule("global",None,TextTrigger::Confirm),rule("local",Some("app"),TextTrigger::Enter)];
        let mut q=context();assert!(match_text(&config,&q).is_none());
        q.trigger=TextInputTrigger::Enter;let expansion=match_text(&config,&q).unwrap();assert_eq!(expansion.rule_id,"local");assert_eq!(expansion.delete_chars,3);assert_eq!(expansion.confirmation,"\n");assert!(expansion.replacement.contains('\n'));
        config.snippets[1].enabled=false;q.trigger=TextInputTrigger::Space;assert_eq!(match_text(&config,&q).unwrap().rule_id,"global");
        config.snippets[0].trigger=TextTrigger::Space;q.trigger=TextInputTrigger::Enter;assert!(match_text(&config,&q).is_none());
        config.snippets[0].trigger=TextTrigger::Immediate;q.trigger=TextInputTrigger::Commit;assert!(match_text(&config,&q).is_some());
    }
    #[test]
    fn boundary_case_and_input_policy() {
        let mut config=Config::default();let mut r=rule("r",None,TextTrigger::Immediate);r.key="AbC".into();r.case_sensitive=false;r.preserve=false;config.snippets.push(r);
        let mut q=context();q.trigger=TextInputTrigger::Commit;q.before_cursor="中文abc".into();assert!(match_text(&config,&q).is_none());
        q.before_cursor="！aBc".into();assert!(!match_text(&config,&q).unwrap().preserve);
        q.composing=true;assert!(match_text(&config,&q).is_none());q.composing=false;q.password=true;assert!(match_text(&config,&q).is_none());
        q.terminal=true;assert!(match_text(&config,&q).is_some());config.settings.terminal_text_enabled=false;assert!(match_text(&config,&q).is_none());
        q.terminal=false;q.password=false;config.exclusions.push(waystroke_model::Exclusion{application_id:"app".into(),gestures:false,text:true,compatibility:false});assert!(match_text(&config,&q).is_none());
        config.exclusions.clear();config.settings.text_enabled=false;assert!(match_text(&config,&q).is_none());
    }
}
