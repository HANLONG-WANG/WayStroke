use std::{fs, path::Path};
use ts_rs::TS;
use waystroke_model::*;
fn main() {
    let dest=Path::new("apps/desktop/src/generated/model.ts");
    let types=vec![Config::decl(),Settings::decl(),Application::decl(),Exclusion::decl(),Sample::decl(),Gesture::decl(),TitleCondition::decl(),TitleOperator::decl(),Rule::decl(),ValueKind::decl(),WindowHandle::decl(),Value::decl(),Reference::decl(),Binding::decl(),TextPart::decl(),Symbol::decl(),Input::decl(),Output::decl(),Step::decl(),FailurePolicy::decl(),Workflow::decl(),TextRule::decl(),TextTrigger::decl(),StartContext::decl(),ExecutionState::decl(),StepResult::decl(),Execution::decl(),ActionDefinition::decl(),ActionField::decl(),ValidationError::decl()];
    fs::create_dir_all(dest.parent().unwrap()).unwrap();
    fs::write(dest,format!("// Generated from waystroke-model; do not edit.\n{}\n",types.into_iter().map(|t|format!("export {t}")).collect::<Vec<_>>().join("\n"))).unwrap();
}
