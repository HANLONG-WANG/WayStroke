//! Serial, scoped execution of the declarative step tree.
use std::{collections::BTreeMap, future::Future, pin::Pin, sync::Arc, time::Duration};
use serde_json::json;
use waystroke_model::{Execution, ExecutionState, FailurePolicy, Step, StepResult, Value, Workflow};
use waystroke_protocol::{Error, ErrorKind};
use crate::{desktop::Desktop, error, parameters::{Values, resolve}, runtime::Runtime};

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Control { Next, Break, Continue, Stop }
pub struct Runner {
    pub execution: Execution,
    pub failure: Option<Error>,
    pub desktop: Desktop,
    pub runtime: Arc<Runtime>,
    pub workflows: Vec<Workflow>,
    pub names: BTreeMap<String,String>,
}
fn timestamp() -> String { chrono::Utc::now().to_rfc3339() }
pub fn parameter(step: &Step, key: &str, values: &Values) -> Result<Value, Error> {
    resolve(step.params.get(key).ok_or_else(|| error(ErrorKind::Validation,format!("缺少参数 {key}")))?,values)
}
pub fn text(step: &Step, key: &str, values: &Values) -> Result<String, Error> {
    match parameter(step,key,values)? {Value::Text(v)=>Ok(v),_=>Err(error(ErrorKind::Validation,format!("{key} 必须是文本")))}
}
pub fn number(step: &Step, key: &str, values: &Values) -> Result<f64, Error> {
    match parameter(step,key,values)? {Value::Number(v) if v.is_finite()=>Ok(v),_=>Err(error(ErrorKind::Validation,format!("{key} 必须是有效数字")))}
}
pub fn integer(step: &Step, key: &str, values: &Values) -> Result<u64, Error> {
    let n=number(step,key,values)?;
    if n<0. || n.fract()!=0. || n>=u64::MAX as f64 {return Err(error(ErrorKind::Validation,format!("{key} 必须是非负整数")));}
    Ok(n as u64)
}
pub fn state(error: &Error) -> ExecutionState {
    match error.kind {ErrorKind::Canceled=>ExecutionState::Canceled,ErrorKind::Timeout=>ExecutionState::TimedOut,_=>ExecutionState::Failed}
}
fn propagate_targets(source: &Values, destination: &mut Values) {
    for key in ["runtime:window.target","runtime:window.found"] {
        if let Some(v)=source.get(key) {destination.insert(key.into(),v.clone());}
    }
}
pub fn compare(left: &Value, operator: &str, right: &Value) -> Result<bool,Error> {
    let empty=match left {Value::Null=>true,Value::Text(v)=>v.is_empty(),Value::List(v)=>v.is_empty(),Value::Data(v)=>v.is_empty(),_=>false};
    Ok(match operator {
        "等于"=>left==right,"不等于"=>left!=right,
        "为空"=>empty,"不为空"=>!empty,
        "为真"=>matches!(left,Value::Boolean(true)),"为假"=>matches!(left,Value::Boolean(false)),
        "包含"|"不包含"=>{
            let found=match (left,right) {
                (Value::Text(a),Value::Text(b))=>a.contains(b),
                (Value::List(a),b)=>a.contains(b),
                _=>return Err(error(ErrorKind::Validation,"包含比较需要文本或列表")),
            };if operator=="包含" {found}else{!found}
        },
        "大于"|"小于"=>{
            let (Value::Number(a),Value::Number(b))=(left,right) else{return Err(error(ErrorKind::Validation,"大小比较需要数字"));};
            if operator=="大于" {a>b}else{a<b}
        },
        _=>return Err(error(ErrorKind::Validation,"未知比较方式")),
    })
}
impl Runner {
    pub async fn publish(&self, event: &str) {
        {let mut info=self.runtime.info.lock().await;
            if let Some(entry)=info.executions.iter_mut().find(|e|e.id==self.execution.id) {*entry=self.execution.clone();}
        }
        self.runtime.event(json!({"event":event,"execution":self.execution}));
    }
    pub fn close_running(&mut self, error: &Error) { self.close_running_from(0,error); }
    fn close_running_from(&mut self, index: usize, error: &Error) {
        for step in &mut self.execution.steps[index..] {
            if step.state==ExecutionState::Running {step.state=state(error);step.finished_at=Some(timestamp());step.reason=Some(error.message.clone());}
        }
    }
    pub fn sequence<'a>(&'a mut self, steps: &'a [Step], values: &'a mut Values) -> Pin<Box<dyn Future<Output=Result<Control,Error>>+Send+'a>> {
        Box::pin(async move {
            for step in steps {
                if !step.enabled {continue;}
                // Yield even a tree of pure actions, so cancellation and desktop input keep progressing.
                tokio::task::yield_now().await;
                let index=self.execution.steps.len();
                self.execution.steps.push(StepResult{step_id:step.id.clone(),state:ExecutionState::Running,started_at:Some(timestamp()),finished_at:None,reason:None,summary:self.names.get(&step.action).cloned(),output:None});
                self.publish("executionStepStarted").await;
                let result=match step.timeout_ms.filter(|v|*v>0) {
                    Some(ms)=>tokio::time::timeout(Duration::from_millis(ms.into()),self.step(step,values)).await.unwrap_or_else(|_|Err(error(ErrorKind::Timeout,"步骤超时"))),
                    None=>self.step(step,values).await,
                };
                let control=match result {
                    Ok((control,output))=>{
                        self.execution.steps[index].output=output.clone();
                        if let (Some(symbol),Some(value))=(&step.output,output) {
                            if symbol.kind!=waystroke_model::ValueKind::Any && symbol.kind!=value.kind() {
                                Err(error(ErrorKind::Validation,format!("输出 {} 的实际类型与声明不符",symbol.name)))
                            }else {values.insert(symbol.id.clone(),value);Ok(control)}
                        }else {Ok(control)}
                    },
                    Err(e)=>Err(e),
                };
                let entry=&mut self.execution.steps[index];
                entry.finished_at=Some(timestamp());
                match &control {Ok(_)=>entry.state=ExecutionState::Succeeded,Err(e)=>{entry.state=state(e);entry.reason=Some(e.message.clone());}}
                if let Err(e)=&control {self.close_running_from(index+1,e);self.failure=Some(e.clone());if let Err(release)=self.desktop.call(json!({"operation":"releaseInputs"})).await {eprintln!("input cleanup: {}",release.message);}}
                self.publish("executionStepFinished").await;
                match control {
                    Ok(Control::Next)=>{},Ok(other)=>return Ok(other),
                    Err(e) if step.on_failure==FailurePolicy::Continue && !matches!(e.kind,ErrorKind::Canceled)=>{},
                    Err(e)=>return Err(e),
                }
            }
            Ok(Control::Next)
        })
    }
    async fn step(&mut self, step: &Step, values: &mut Values) -> Result<(Control,Option<Value>),Error> {
        let mut contexts=std::collections::BTreeSet::new();
        for (key,binding) in &step.params {if waystroke_model::parameter_active(step,key){context_references(binding,&mut contexts);}}
        for binding in step.arguments.values(){context_references(binding,&mut contexts);}
        if step.action=="variable.read" {
            let key=match text(step,"value",values)?.as_str() {
                "起点应用 ID"=>"context:start.applicationId","起点窗口标题"=>"context:start.title","起点坐标"=>"context:start.position",
                "当前指针坐标"=>"context:pointer.position","当前工作区"=>"context:workspace","当前显示器"=>"context:monitor",
                "剪贴板文本"=>"context:clipboard","当前日期时间"=>"context:now","用户主目录"=>"context:home",
                _=>return Err(error(ErrorKind::Validation,"未知上下文来源")),
            };
            contexts.insert(key.to_owned());self.hydrate(&contexts,values).await?;
            return Ok((Control::Next,Some(values.get(key).cloned().ok_or_else(||error(ErrorKind::TargetInvalid,"所选上下文不存在"))?)));
        }
        self.hydrate(&contexts,values).await?;
        match step.action.as_str() {
            "loop.break"=>Ok((Control::Break,None)),"loop.continue"=>Ok((Control::Continue,None)),
            "flow.stop"=>{self.execution.reason=Some(text(step,"value",values)?);Ok((Control::Stop,None))},
            "condition"=>{
                let yes=self.condition(step,values).await?;
                let mut scope=values.clone();
                let result=self.sequence(if yes {&step.children}else{&step.otherwise},&mut scope).await;
                propagate_targets(&scope,values);
                Ok((result?,None))
            },
            "repeat"|"foreach"=>{
                let items=if step.action=="foreach" {
                    match parameter(step,"value",values)? {Value::List(v)=>Some(v),_=>return Err(error(ErrorKind::Validation,"遍历需要列表"))}
                }else {None};
                let count=match &items {Some(items)=>items.len() as u64,None=>integer(step,"value",values)?};
                for index in 0..count {
                    let mut scope=values.clone();
                    if let Some(symbol)=&step.loop_index {scope.insert(symbol.id.clone(),Value::Number(index as f64));}
                    if let (Some(symbol),Some(items))=(&step.loop_item,&items) {
                        let value=items[index as usize].clone();
                        if symbol.kind!=waystroke_model::ValueKind::Any && value.kind()!=symbol.kind {return Err(error(ErrorKind::Validation,format!("当前遍历项类型与 {} 的声明不符",symbol.name)));}
                        scope.insert(symbol.id.clone(),value);
                    }
                    let result=self.sequence(&step.children,&mut scope).await;
                    propagate_targets(&scope,values);
                    match result? {Control::Break=>break,Control::Stop=>return Ok((Control::Stop,None)),Control::Next|Control::Continue=>{}}
                }
                Ok((Control::Next,None))
            },
            "flow.call"=>{
                let workflow=self.workflows.iter().find(|w|Some(&w.id)==step.workflow_id.as_ref()).cloned().ok_or_else(||error(ErrorKind::Validation,"可复用动作不存在"))?;
                let mut scope:Values=values.iter().filter(|(key,_)|key.starts_with("context:")||key.starts_with("runtime:")).map(|(k,v)|(k.clone(),v.clone())).collect();
                for input in &workflow.inputs {
                    let binding=step.arguments.get(&input.symbol.id).or(input.default.as_ref()).ok_or_else(||error(ErrorKind::Validation,format!("缺少输入 {}",input.symbol.name)))?;
                    let mut contexts=std::collections::BTreeSet::new();context_references(binding,&mut contexts);self.hydrate(&contexts,&mut scope).await?;
                    let value=resolve(binding,if step.arguments.contains_key(&input.symbol.id){values}else{&scope})?;
                    if input.symbol.kind!=waystroke_model::ValueKind::Any && value.kind()!=input.symbol.kind {return Err(error(ErrorKind::Validation,format!("输入 {} 类型不符",input.symbol.name)));}
                    scope.insert(input.symbol.id.clone(),value);
                }
                let control=self.sequence(&workflow.steps,&mut scope).await?;
                if matches!(control,Control::Break|Control::Continue) {return Err(error(ErrorKind::Validation,"循环控制不能跨越动作调用"));}
                if control==Control::Stop {return Ok((Control::Stop,None));}
                let mut outputs=BTreeMap::new();
                for output in &workflow.outputs {
                    let mut contexts=std::collections::BTreeSet::new();context_references(&output.value,&mut contexts);self.hydrate(&contexts,&mut scope).await?;
                    let value=resolve(&output.value,&scope)?;
                    if output.symbol.kind!=waystroke_model::ValueKind::Any && value.kind()!=output.symbol.kind {return Err(error(ErrorKind::Validation,format!("返回值 {} 类型不符",output.symbol.name)));}
                    outputs.insert(output.symbol.id.clone(),value);
                }
                propagate_targets(&scope,values);
                Ok((Control::Next,Some(Value::Data(outputs))))
            },
            "wait.condition"=>{
                let timeout=integer(step,"timeout",values)?;
                let interval=integer(step,"interval",values)?;
                if interval==0 {return Err(error(ErrorKind::Validation,"检查间隔必须大于零"));}
                let operation=async {
                    loop {
                        if self.wait_condition(step,values).await? {return Ok((Control::Next,None));}
                        tokio::time::sleep(Duration::from_millis(interval)).await;
                    }
                };
                if timeout==0 {operation.await}else {tokio::time::timeout(Duration::from_millis(timeout),operation).await.map_err(|_|error(ErrorKind::Timeout,"等待条件超时"))?}
            },
            _=>{
                let output=match crate::window_actions::execute(step,&self.desktop,values).await {
                    Some(result)=>result?,None=>match crate::input_actions::execute(step,&self.desktop,values).await {Some(result)=>result?,None=>crate::execution::execute_leaf(step,&self.desktop,values).await?},
                };
                if step.action=="launch" && text(step,"windowTarget",values)?=="是" {
                    if let Some(value)=&output {values.insert("runtime:window.target".into(),value.clone());}
                }
                Ok((Control::Next,output))
            },
        }
    }
    async fn condition(&self,step:&Step,values:&Values)->Result<bool,Error> {
        let source=match text(step,"value",values)?.as_str() {
            "应用名称"=>values.get("context:start.applicationId").cloned().unwrap_or(Value::Text(String::new())),
            "窗口标题"=>values.get("context:start.title").cloned().unwrap_or(Value::Text(String::new())),
            "变量"=>parameter(step,"source",values)?,
            "命令退出码"=>{
                match parameter(step,"source",values)? {Value::Data(mut fields)=>fields.remove("exitCode").ok_or_else(||error(ErrorKind::Validation,"命令尚无退出码"))?,Value::Number(n)=>Value::Number(n),_=>return Err(error(ErrorKind::Validation,"需要命令结果"))}
            },
            "文件是否存在"=>Value::Boolean(tokio::fs::try_exists(text(step,"source",values)?).await.map_err(|e|error(ErrorKind::Io,e.to_string()))?),
            "剪贴板"=>Value::Text(self.clipboard().await?),
            _=>return Err(error(ErrorKind::Validation,"未知条件对象")),
        };
        let operator=text(step,"operator",values)?;
        let right=if matches!(operator.as_str(),"为空"|"不为空"|"为真"|"为假"){Value::Null}else{parameter(step,"compare",values)?};
        compare(&source,&operator,&right)
    }
    async fn clipboard(&self)->Result<String,Error> {
        self.desktop.call(json!({"operation":"clipboardRead"})).await?.as_str().map(str::to_owned).ok_or_else(||error(ErrorKind::Unavailable,"剪贴板未返回文本"))
    }
    async fn hydrate(&self,keys:&std::collections::BTreeSet<String>,values:&mut Values)->Result<(),Error> {
        if keys.contains("context:now") {values.insert("context:now".into(),Value::Text(chrono::Local::now().to_rfc3339()));}
        if keys.contains("context:home") {values.insert("context:home".into(),Value::Text(std::env::var("HOME").map_err(|_|error(ErrorKind::Unavailable,"无法读取用户主目录"))?));}
        if keys.contains("context:clipboard") {values.insert("context:clipboard".into(),Value::Text(self.clipboard().await?));}
        if keys.iter().any(|key|matches!(key.as_str(),"context:pointer.position"|"context:workspace"|"context:monitor")) {
            let context:waystroke_model::StartContext=serde_json::from_value(self.desktop.call(json!({"operation":"getContext"})).await?).map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
            values.insert("context:pointer.position".into(),Value::List(context.position.into_iter().map(Value::Number).collect()));
            if let Some(workspace)=context.workspace {values.insert("context:workspace".into(),Value::Number(workspace as f64+1.));}
            if let Some(monitor)=context.monitor {values.insert("context:monitor".into(),Value::Number(monitor as f64+1.));}
        }
        Ok(())
    }
    async fn wait_condition(&self,step:&Step,values:&Values)->Result<bool,Error> {
        let compare_value=parameter(step,"compare",values)?;
        match text(step,"value",values)?.as_str() {
            "变量等于"=>Ok(parameter(step,"subject",values)?==compare_value),
            "文件存在"=>tokio::fs::try_exists(text(step,"subject",values)?).await.map_err(|e|error(ErrorKind::Io,e.to_string())),
            "剪贴板包含"=>compare(&Value::Text(self.clipboard().await?),"包含",&compare_value),
            kind @ ("窗口出现"|"窗口消失"|"窗口标题包含")=>{
                let app=text(step,"subject",values)?;
                let windows=self.desktop.call(json!({"operation":"windows"})).await?;
                let found=windows.as_array().ok_or_else(||error(ErrorKind::Unavailable,"窗口列表格式错误"))?.iter().any(|w|{
                    (app.is_empty()||w["applicationId"].as_str()==Some(&app)) && (kind!="窗口标题包含" || w["title"].as_str().is_some_and(|title|matches!(&compare_value,Value::Text(value) if title.contains(value))))
                });
                Ok(if kind=="窗口消失" {!found}else{found})
            },
            _=>Err(error(ErrorKind::Validation,"未知等待条件")),
        }
    }
}

fn context_references(binding:&waystroke_model::Binding,keys:&mut std::collections::BTreeSet<String>) {
    use waystroke_model::{Binding,TextPart};
    match binding {
        Binding::Reference(r)=>{if r.symbol_id.starts_with("context:"){keys.insert(r.symbol_id.clone());}},
        Binding::Template(parts)=>for part in parts {if let TextPart::Reference(r)=part {if r.symbol_id.starts_with("context:"){keys.insert(r.symbol_id.clone());}}},
        Binding::List(items)=>for item in items {context_references(item,keys);},
        Binding::Object(fields)=>for item in fields.values() {context_references(item,keys);},
        Binding::Literal(_)=>{},
    }
}
