//! Saved product configuration and semantic validation; no desktop side effects.
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use ts_rs::TS;

#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Config {
    pub format: String,
    pub schema_version: u32,
    pub settings: Settings,
    pub applications: Vec<Application>,
    pub exclusions: Vec<Exclusion>,
    pub gestures: Vec<Gesture>,
    pub rules: Vec<Rule>,
    pub workflows: Vec<Workflow>,
    pub snippets: Vec<TextRule>,
}
impl Default for Config {
    fn default() -> Self {
        Self { format: "waystroke".into(), schema_version: 1, settings: Settings::default(), applications: vec![], exclusions: vec![], gestures: vec![], rules: vec![], workflows: vec![], snippets: vec![] }
    }
}
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Settings {
    pub gestures_enabled: bool, pub trail: bool, pub feedback: bool, pub autostart: bool,
    pub similarity: f64, pub ambiguity_gap: f64, pub color: String,
    pub minimum_length: f64, pub cancel_timeout: u32,
    pub text_enabled: bool, pub terminal_text_enabled: bool,
    pub mouse_device_id: Option<String>, pub setup_complete: bool,
}
impl Default for Settings {
    fn default() -> Self {
        Self { gestures_enabled: true, trail: true, feedback: true, autostart: true, similarity: 82., ambiguity_gap: 5., color: "#6262cf".into(), minimum_length: 12., cancel_timeout: 1200, text_enabled: true, terminal_text_enabled: true, mouse_device_id: None, setup_complete: false }
    }
}
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Application { pub id: String, pub name: String }
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Exclusion { pub application_id: String, pub gestures: bool, pub text: bool }
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Sample { pub id: String, pub points: Vec<[f64; 2]> }
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Gesture { pub id: String, pub name: String, pub main_sample_id: String, pub samples: Vec<Sample> }
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct TitleCondition { pub operator: TitleOperator, pub value: String }
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
pub enum TitleOperator { #[serde(rename="包含")] Contains, #[serde(rename="等于")] Equals, #[serde(rename="不包含")] NotContains }
fn default_rule_feedback()->bool { true }
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Rule { pub id: String, pub name: String, pub enabled: bool, #[serde(default="default_rule_feedback")] pub feedback: bool, pub gesture_id: String, pub auxiliary_buttons: Vec<u16>, pub application_id: Option<String>, pub title_match: TitleCondition, pub steps: Vec<Step> }
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub enum ValueKind { Text, Number, Boolean, List, Window, Data }
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct WindowHandle { pub instance: String, pub id: String }
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
#[serde(tag="kind", content="value", rename_all="camelCase")]
pub enum Value { Text(String), Number(f64), Boolean(bool), List(Vec<Value>), Window(WindowHandle), Data(BTreeMap<String,Value>) }
impl Value {
    pub fn kind(&self) -> ValueKind { match self { Self::Text(_)=>ValueKind::Text, Self::Number(_)=>ValueKind::Number, Self::Boolean(_)=>ValueKind::Boolean, Self::List(_)=>ValueKind::List, Self::Window(_)=>ValueKind::Window, Self::Data(_)=>ValueKind::Data } }
}
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
#[serde(rename_all="camelCase", deny_unknown_fields)]
pub struct Reference { pub symbol_id: String, pub path: Vec<String>, pub kind: ValueKind }
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
#[serde(tag="mode", content="value", rename_all="camelCase")]
pub enum Binding { Literal(Value), Reference(Reference), Template(Vec<TextPart>), List(Vec<Binding>), Object(BTreeMap<String,Binding>) }
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
#[serde(tag="mode", content="value", rename_all="camelCase")]
pub enum TextPart { Text(String), Reference(Reference) }
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Symbol { pub id: String, pub name: String, pub kind: ValueKind }
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Input { pub symbol: Symbol, pub default: Option<Binding> }
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Output { pub symbol: Symbol, pub value: Binding }
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
#[serde(rename_all="camelCase", deny_unknown_fields)]
pub struct Step {
    pub id: String, pub action: String, pub enabled: bool,
    pub params: BTreeMap<String, Binding>, pub output: Option<Symbol>,
    pub on_failure: FailurePolicy, pub timeout_ms: Option<u32>,
    pub workflow_id: Option<String>, pub arguments: BTreeMap<String, Binding>,
    pub children: Vec<Step>, pub otherwise: Vec<Step>,
    pub loop_item: Option<Symbol>, pub loop_index: Option<Symbol>,
}
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
#[serde(rename_all="camelCase")]
pub enum FailurePolicy { Stop, Continue }
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Workflow { pub id: String, pub name: String, pub description: String, pub inputs: Vec<Input>, pub outputs: Vec<Output>, pub steps: Vec<Step> }
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
#[serde(rename_all="camelCase", deny_unknown_fields)]
pub struct TextRule { pub id: String, pub key: String, pub value: String, pub enabled: bool, pub application_id: Option<String>, pub trigger: TextTrigger, pub case_sensitive: bool, pub boundary: bool, pub preserve: bool }
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
#[serde(rename_all="camelCase")]
pub enum TextTrigger { Confirm, Space, Enter, Immediate }
// Execution snapshots are session data; they are never written into Config.
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
#[serde(rename_all="camelCase", deny_unknown_fields)]
pub struct StartContext {
    pub sequence: u32, pub monotonic_ms: f64, pub position: [f64; 2],
    pub window: Option<WindowHandle>, pub application_id: Option<String>,
    pub title: Option<String>, pub workspace: Option<u32>, pub monitor: Option<u32>,
    pub locked: bool,
}
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
#[serde(rename_all="camelCase")]
pub enum ExecutionState { Queued, Running, Succeeded, Failed, Canceled, TimedOut }
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
#[serde(rename_all="camelCase", deny_unknown_fields)]
pub struct StepResult {
    pub step_id: String, pub state: ExecutionState, pub started_at: Option<String>,
    pub finished_at: Option<String>, pub reason: Option<String>, pub summary: Option<String>,
}
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
#[serde(rename_all="camelCase", deny_unknown_fields)]
pub struct Execution {
    pub id: String, pub name:String, pub revision: u32, pub context: StartContext, pub state: ExecutionState,
    pub started_at: Option<String>, pub finished_at: Option<String>,
    pub reason: Option<String>, pub steps: Vec<StepResult>,
}
#[derive(Clone, Debug, Serialize, Deserialize, TS)]
pub struct ActionDefinition { pub id: String, pub group: String, pub name: String, pub description: String, pub fields: Vec<ActionField>, #[serde(default)] pub children: bool, #[serde(default)] pub note: Option<String> }
#[derive(Clone, Debug, Serialize, Deserialize, TS)]
pub struct ActionField { pub key: String, pub label: String, pub initial: String, pub kind: String, pub choices: Vec<String> }
pub fn catalog() -> Vec<ActionDefinition> { serde_json::from_str(include_str!("../action-catalog.json")).expect("compiled action catalog") }
#[derive(Clone, Debug, Serialize, Deserialize, TS, PartialEq)]
pub struct ValidationError { pub path: String, pub message: String }

pub fn validate(config: &Config) -> Vec<ValidationError> {
    let mut v=Validator { config, errors: vec![], ids: BTreeSet::new(), catalog: catalog().into_iter().map(|d|(d.id.clone(),d)).collect() };
    v.run(); v.errors
}
struct Validator<'a> { config: &'a Config, errors: Vec<ValidationError>, ids: BTreeSet<String>, catalog: BTreeMap<String,ActionDefinition> }
impl Validator<'_> {
    fn error(&mut self,p:impl Into<String>,m:impl Into<String>) { self.errors.push(ValidationError{path:p.into(),message:m.into()}); }
    fn id(&mut self,id:&str,p:&str) { if id.is_empty() || !self.ids.insert(id.into()) { self.error(p,"标识不能为空或重复"); } }
    fn name(&mut self,n:&str,p:&str) { if n.trim().is_empty() { self.error(p,"名称不能为空"); } }
    fn run(&mut self) {
        let c=self.config;
        if c.format!="waystroke" || c.schema_version!=1 { self.error("schemaVersion","配置格式或版本不受支持"); }
        let s=&c.settings;
        for (path,value,min,max) in [("similarity",s.similarity,60.,98.),("minimumLength",s.minimum_length,4.,100.),("cancelTimeout",f64::from(s.cancel_timeout),300.,5000.),("ambiguityGap",s.ambiguity_gap,0.,100.)] {
            if !value.is_finite() || value<min || value>max { self.error(format!("settings.{path}"),format!("数值应在 {min} 至 {max} 之间")); }
        }
        if s.color.len()!=7 || !s.color.starts_with('#') || !s.color[1..].chars().all(|x|x.is_ascii_hexdigit()) { self.error("settings.color","颜色格式应为 #RRGGBB"); }
        let mut apps=BTreeSet::new();
        for a in &c.applications { if a.id.trim().is_empty() || !apps.insert(&a.id) { self.error("applications","应用标识不能为空或重复"); } }
        let mut exclusions=BTreeSet::new();
        for e in &c.exclusions { if e.application_id.trim().is_empty() || !exclusions.insert(&e.application_id) { self.error("exclusions","排除应用标识不能为空或重复"); } }
        for g in &c.gestures {
            let p=format!("gestures.{}",g.id); self.id(&g.id,&p); self.name(&g.name,&p);
            if !g.samples.iter().any(|s|s.id==g.main_sample_id) { self.error(&p,"主样本不存在"); }
            for sample in &g.samples {
                self.id(&sample.id,&p);
                if sample.points.len()<2 || sample.points.iter().flatten().any(|x|!x.is_finite()) || sample.points.windows(2).all(|p|p[0]==p[1]) { self.error(&p,"需要有效的自由绘制轨迹"); }
            }
        }
        for w in &c.workflows {
            let p=format!("workflows.{}",w.id); self.id(&w.id,&p); self.name(&w.name,&p);
            let mut scope=context_scope(); let mut names=BTreeSet::new();
            if w.steps.is_empty() { self.error(format!("{p}.steps"),"至少添加一个步骤"); }
            for i in &w.inputs {
                self.symbol(&i.symbol,&p,&mut names);
                if let Some(b)=&i.default { self.binding(b,&context_scope(),Some(&i.symbol.kind),&p); }
                scope.insert(i.symbol.id.clone(),i.symbol.kind.clone());
            }
            self.steps(&w.steps,&mut scope,0,&p);
            for o in &w.outputs { self.symbol(&o.symbol,&p,&mut names); self.binding(&o.value,&scope,Some(&o.symbol.kind),&p); }
        }
        for r in &c.rules {
            let p=format!("rules.{}",r.id); self.id(&r.id,&p); self.name(&r.name,&p);
            if !c.gestures.iter().any(|g|g.id==r.gesture_id) { self.error(format!("{p}.gestureId"),"引用的手势模板不存在"); }
            if r.steps.is_empty() { self.error(format!("{p}.steps"),"至少添加一个动作"); }
            let aux:BTreeSet<_>=r.auxiliary_buttons.iter().collect();
            if aux.len()!=r.auxiliary_buttons.len() || aux.iter().any(|x|!matches!(**x,272|274|275|276)) { self.error(format!("{p}.auxiliaryButtons"),"辅助键不受支持或重复"); }
            self.steps(&r.steps,&mut context_scope(),0,&p);
            if r.enabled && c.rules.iter().any(|other|other.id!=r.id && other.enabled && other.gesture_id==r.gesture_id && other.application_id==r.application_id && other.title_match==r.title_match && BTreeSet::from_iter(other.auxiliary_buttons.iter())==aux) { self.error(&p,"已启用规则具有相同的触发条件"); }
        }
        for t in &c.snippets {
            let p=format!("snippets.{}",t.id); self.id(&t.id,&p);
            if t.key.is_empty() { self.error(&p,"关键词不能为空"); }
            if c.snippets.iter().any(|o|o.id!=t.id && o.key==t.key && o.application_id==t.application_id) { self.error(&p,"同一应用范围的关键词重复"); }
        }
        for w in &c.workflows { self.cycle(&w.id,&mut BTreeSet::new()); }
    }
    fn symbol(&mut self,s:&Symbol,p:&str,names:&mut BTreeSet<String>) { self.id(&s.id,p); self.name(&s.name,p); if !names.insert(s.name.clone()) { self.error(p,"变量或接口名称重复"); } }
    fn binding(&mut self,b:&Binding,scope:&BTreeMap<String,ValueKind>,expected:Option<&ValueKind>,p:&str) -> Option<ValueKind> {
        let kind=match b {
            Binding::Literal(v)=>Some(v.kind()),
            Binding::List(values)=>{for b in values { self.binding(b,scope,None,p); } Some(ValueKind::List)},
            Binding::Object(fields)=>{for (name,b) in fields { self.binding(b,scope,None,&format!("{p}.{name}")); } Some(ValueKind::Data)},
            Binding::Reference(r)=> {
                if !r.path.is_empty() {
                    let provider=self.config.workflows.iter().flat_map(|w|all_steps(&w.steps)).chain(self.config.rules.iter().flat_map(|r|all_steps(&r.steps))).find(|s|s.output.as_ref().is_some_and(|o|o.id==r.symbol_id) && s.action=="flow.call");
                    if let Some(provider)=provider {
                        if let Some(workflow)=provider.workflow_id.as_ref().and_then(|id|self.config.workflows.iter().find(|w|w.id==*id)) {
                            match workflow.outputs.iter().find(|o|o.symbol.id==r.path[0]) {
                                None=>self.error(p,"可复用动作的返回字段引用已失效"),
                                Some(field) if r.path.len()==1 && field.symbol.kind!=r.kind=>self.error(p,"返回字段引用类型不匹配"),
                                Some(field) if r.path.len()>1 && !matches!(field.symbol.kind,ValueKind::Data|ValueKind::List|ValueKind::Window)=>self.error(p,"该返回字段不支持嵌套路径"),
                                _=>{},
                            }
                        }
                    }
                }
                match scope.get(&r.symbol_id) {
                    None=>{self.error(p,"引用值不在当前可见作用域或尚未产生");None},
                    Some(k) if r.path.is_empty() && *k!=r.kind=>{self.error(p,"变量引用类型不匹配");None},
                    Some(k) if !r.path.is_empty() && !matches!(k,ValueKind::Data|ValueKind::List|ValueKind::Window)=>{self.error(p,"该类型不支持读取字段");None},
                    Some(_)=>Some(r.kind.clone()),
                }
            },
            Binding::Template(parts)=>{for part in parts { if let TextPart::Reference(r)=part { self.binding(&Binding::Reference(r.clone()),scope,None,p); } } Some(ValueKind::Text)},
        };
        if let (Some(got),Some(want))=(&kind,expected) { if got!=want { self.error(p,format!("参数需要 {want:?}，当前为 {got:?}")); } }
        kind
    }
    fn steps(&mut self,steps:&[Step],scope:&mut BTreeMap<String,ValueKind>,loop_depth:usize,p:&str) {
        let mut names:BTreeSet<String>=BTreeSet::new();
        for s in steps {
            let p=format!("{p}.steps.{}",s.id); self.id(&s.id,&p);
            let Some(def)=self.catalog.get(&s.action).cloned() else { self.error(&p,"未知动作类型"); continue; };
            if !def.children && !s.children.is_empty() || s.action!="condition" && !s.otherwise.is_empty() { self.error(&p,"该动作不支持嵌套步骤"); }
            if matches!(s.action.as_str(),"loop.break"|"loop.continue") && loop_depth==0 { self.error(&p,"只能放在重复或遍历内部"); }
            for (key,b) in &s.params {
                let field=def.fields.iter().find(|f|f.key==*key);
                if field.is_none() && !matches!(key.as_str(),"resultKind"|"dbusArgs"|"itemSymbol"|"indexSymbol") { self.error(format!("{p}.{key}"),"未知动作参数"); continue; }
                let expected=step_parameter_kind(s,key,field);
                if key=="dbusArgs" && s.action=="dbus.call" {
                    if let Binding::List(args)=b { for (index,arg) in args.iter().enumerate() {
                        if let Binding::Object(fields)=arg {
                            let signature=match fields.get("type") { Some(Binding::Literal(Value::Text(t)))=>Some(t.as_str()),_=>None };
                            match (signature.and_then(dbus_kind),fields.get("value")) {
                                (Some(kind),Some(value))=>{self.binding(value,scope,Some(&kind),&format!("{p}.dbusArgs.{index}.value"));},
                                _=>self.error(format!("{p}.dbusArgs.{index}"),"D-Bus 参数类型或值无效"),
                            }
                        } else { self.error(&p,"D-Bus 参数需要类型和值"); }
                    }} else { self.error(&p,"D-Bus 参数必须是类型化列表"); }
                }
                self.binding(b,scope,expected.as_ref(),&format!("{p}.{key}"));
                if let (Some(f),Binding::Literal(Value::Text(value)))=(field,b) { if f.kind=="select" && !f.choices.contains(value) { self.error(format!("{p}.{key}"),"选项不受支持"); } }
            }
            if matches!(s.action.as_str(),"repeat"|"wait") {
                if let Some(Binding::Literal(Value::Number(n)))=s.params.get("value") {
                    if !n.is_finite() || *n<0. || n.fract()!=0. { self.error(format!("{p}.value"),"次数或毫秒数应为非负整数"); }
                }
            }
            if s.action=="flow.call" {
                match s.workflow_id.as_ref().and_then(|id|self.config.workflows.iter().find(|w|w.id==*id)) {
                    None=>self.error(&p,"可复用动作引用不存在"),
                    Some(w)=>{
                        for key in s.arguments.keys() { if !w.inputs.iter().any(|i|i.symbol.id==*key) { self.error(&p,"调用参数引用已失效"); } }
                        for i in &w.inputs { if let Some(b)=s.arguments.get(&i.symbol.id) { self.binding(b,scope,Some(&i.symbol.kind),&format!("{p}.arguments.{}",i.symbol.id)); } else if i.default.is_none() { self.error(&p,format!("缺少输入参数 {}",i.symbol.name)); } }
                    }
                }
            }
            let nested_loop=loop_depth+usize::from(matches!(s.action.as_str(),"repeat"|"foreach"));
            let mut nested_scope=scope.clone();
            for sym in [&s.loop_item,&s.loop_index].into_iter().flatten() {
                self.symbol(sym,&p,&mut names);
                if !matches!(s.action.as_str(),"foreach"|"repeat") { self.error(&p,"循环局部值只能属于重复或遍历"); }
                nested_scope.insert(sym.id.clone(),sym.kind.clone());
            }
            self.steps(&s.children,&mut nested_scope,nested_loop,&p);
            self.steps(&s.otherwise,&mut scope.clone(),loop_depth,&p);
            if let Some(out)=&s.output { self.symbol(out,&p,&mut names); if let Some(kind)=step_output_kind(s) { if kind!=out.kind { self.error(&p,"步骤输出类型与动作定义不匹配"); } } if s.enabled { scope.insert(out.id.clone(),out.kind.clone()); } }
        }
    }
    fn cycle(&mut self,id:&str,stack:&mut BTreeSet<String>) {
        if !stack.insert(id.into()) { self.error(format!("workflows.{id}"),"禁止直接或间接递归调用"); return; }
        if let Some(w)=self.config.workflows.iter().find(|w|w.id==id) { for target in calls(&w.steps) { self.cycle(target,stack); } }
        stack.remove(id);
    }
}
fn all_steps(steps:&[Step])->Vec<&Step> { steps.iter().flat_map(|s|std::iter::once(s).chain(all_steps(&s.children)).chain(all_steps(&s.otherwise))).collect() }
fn calls(steps:&[Step])->Vec<&str> { steps.iter().flat_map(|s|s.workflow_id.as_deref().into_iter().chain(calls(&s.children)).chain(calls(&s.otherwise))).collect() }
pub fn context_scope()->BTreeMap<String,ValueKind> {
    [("start.applicationId",ValueKind::Text),("start.title",ValueKind::Text),("start.window",ValueKind::Window),("start.x",ValueKind::Number),("start.y",ValueKind::Number),("start.position",ValueKind::List),("pointer.position",ValueKind::List),("workspace",ValueKind::Number),("monitor",ValueKind::Number),("clipboard",ValueKind::Text),("now",ValueKind::Text),("home",ValueKind::Text)].into_iter().map(|(id,k)|(format!("context:{id}"),k)).collect()
}
pub fn parameter_kind(action:&str,key:&str,field:Option<&ActionField>)->Option<ValueKind> {
    if action=="foreach" && key=="index" { return Some(ValueKind::Text); }
    if matches!(key,"count"|"x"|"y"|"width"|"height"|"index"|"seconds"|"timeout"|"interval"|"amount"|"pid"|"minimum"|"maximum"|"min"|"max"|"left"|"right"|"duration") || key=="value" && matches!(action,"wait"|"repeat") { return Some(ValueKind::Number); }
    match field.map(|f|f.kind.as_str()) { Some("text"|"textarea"|"select")=>Some(ValueKind::Text),_=>None }
}

fn param_text<'a>(s:&'a Step,key:&str)->Option<&'a str> { match s.params.get(key) { Some(Binding::Literal(Value::Text(v)))=>Some(v),_=>None } }
fn dbus_kind(signature:&str)->Option<ValueKind> { match signature { "s"=>Some(ValueKind::Text),"i"|"d"=>Some(ValueKind::Number),"b"=>Some(ValueKind::Boolean),"as"=>Some(ValueKind::List),_=>None } }
fn named_kind(name:&str)->Option<ValueKind> { match name { "文本"=>Some(ValueKind::Text),"数字"=>Some(ValueKind::Number),"布尔值"=>Some(ValueKind::Boolean),"列表"=>Some(ValueKind::List),"窗口"=>Some(ValueKind::Window),"数据"=>Some(ValueKind::Data),_=>None } }
fn step_parameter_kind(s:&Step,key:&str,field:Option<&ActionField>)->Option<ValueKind> {
    match (s.action.as_str(),key) {
        ("dbus.property","content") if param_text(s,"operation")==Some("设置")=>param_text(s,"signature").and_then(dbus_kind),
        ("variable","value")=>param_text(s,"kind").and_then(named_kind),
        ("foreach","value")=>Some(ValueKind::List),
        ("data.field","value")=>None,
        ("condition","source"|"compare")|("wait.condition","subject"|"compare")=>None,
        ("list.change","value")=>Some(ValueKind::List),
        ("window.target","variable")=>Some(if param_text(s,"value")==Some("窗口变量") { ValueKind::Window } else { ValueKind::Text }),
        ("process.signal"|"workspace.move","value")=>Some(ValueKind::Number),
        (_,"dbusArgs"|"itemSymbol"|"indexSymbol")=>None,
        _=>parameter_kind(&s.action,key,field),
    }
}
fn step_output_kind(s:&Step)->Option<ValueKind> {
    use ValueKind::*;
    if let Some(kind)=param_text(s,"resultKind").and_then(named_kind) { return Some(kind) }
    Some(match s.action.as_str() {
        "variable"=>param_text(s,"kind").and_then(named_kind)?,
        "clipboard.read"|"selection.copy"|"date.format"|"file.read"|"dialog.input"=>Text,
        "number.calculate"|"number.random"=>Number,
        "window.find"|"launch"|"app.activate"=>Window,
        "directory.list"=>List,
        "dialog.message"=>Boolean,
        "command"|"http.request"|"flow.call"|"json.parse"=>Data,
        "text.transform"=>match param_text(s,"operation") { Some("获取长度")=>Number,Some("按分隔符拆分")=>List,_=>Text },
        "window.info"=>match param_text(s,"value") { Some("标题"|"应用 ID")=>Text,Some("工作区"|"所在显示器")=>Number,Some("是否最大化"|"是否全屏"|"是否置顶")=>Boolean,_=>Data },
        "file.info"=>match param_text(s,"property") { Some("是否存在"|"是否为目录")=>Boolean,Some("大小")=>Number,_=>Text },
        "variable.read"=>match param_text(s,"value") { Some("当前工作区"|"当前显示器")=>Number,Some("起点坐标"|"当前指针坐标")=>List,_=>Text },
        "list.change"=>match param_text(s,"operation") { Some("获取长度"|"查找")=>Number,Some("读取指定索引")=>return None,_=>List },
        _=>return None,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn step(id:&str,action:&str)->Step { Step{id:id.into(),action:action.into(),enabled:true,params:BTreeMap::new(),output:None,on_failure:FailurePolicy::Stop,timeout_ms:None,workflow_id:None,arguments:BTreeMap::new(),children:vec![],otherwise:vec![],loop_item:None,loop_index:None} }
    fn workflow(id:&str,steps:Vec<Step>)->Workflow { Workflow{id:id.into(),name:id.into(),description:String::new(),inputs:vec![],outputs:vec![],steps} }
    #[test]
    fn full_catalog_and_freeform_configuration_round_trip() {
        let defs=catalog(); assert_eq!(defs.len(),69);assert_eq!(defs.iter().map(|a|&a.id).collect::<BTreeSet<_>>().len(),69);
        let mut c=Config::default();c.gestures.push(Gesture{id:"g".into(),name:"自由曲线".into(),main_sample_id:"sample".into(),samples:vec![Sample{id:"sample".into(),points:vec![[1.2,-3.7],[5.6,8.9],[7.8,6.1]]}]});
        assert!(validate(&c).is_empty());assert_eq!(c,serde_json::from_str(&serde_json::to_string(&c).unwrap()).unwrap());
    }
    #[test]
    fn scope_types_and_local_outputs_are_checked() {
        let mut c=Config::default();
        let mut producer=step("producer","clipboard.read");producer.output=Some(Symbol{id:"text".into(),name:"剪贴板".into(),kind:ValueKind::Text});
        let mut consumer=step("consumer","wait");consumer.params.insert("value".into(),Binding::Reference(Reference{symbol_id:"text".into(),path:vec![],kind:ValueKind::Text}));
        c.workflows.push(workflow("w",vec![producer,consumer]));
        assert!(validate(&c).iter().any(|e|e.message.contains("参数需要")));
        let steps=&mut c.workflows[0].steps;
        steps[1].action="clipboard.write".into();assert!(validate(&c).is_empty());
        c.workflows[0].steps[1].action="unknown.action".into();
        assert!(validate(&c).iter().any(|e|e.path.contains("consumer")&&e.message.contains("未知动作")));
        c.workflows[0].steps[1].action="clipboard.write".into();
        let first=c.workflows[0].steps.remove(0);c.workflows[0].steps.push(first);
        assert!(validate(&c).iter().any(|e|e.message.contains("尚未产生")));
    }
    #[test]
    fn indirect_calls_cannot_recurse() {
        let mut a=step("call-a","flow.call");a.workflow_id=Some("b".into());
        let mut b=step("call-b","flow.call");b.workflow_id=Some("a".into());
        let mut c=Config::default();c.workflows=vec![workflow("a",vec![a]),workflow("b",vec![b])];
        assert!(validate(&c).iter().any(|e|e.message.contains("递归")));
    }
}
