//! Phase B serial executors. Other action types fail explicitly until phase C.
use std::{sync::Arc,collections::BTreeMap};
use serde_json::json;
use tokio::sync::{mpsc,watch};
use waystroke_model::{Binding,Value,WindowHandle,Execution,ExecutionState,StepResult,FailurePolicy};
use waystroke_protocol::{Error,ErrorKind};
use crate::{desktop::Desktop,error,runtime::{Runtime,Job,now_ms}};
fn timestamp()->String{chrono::Utc::now().to_rfc3339()}
fn resolve(binding:&Binding,values:&BTreeMap<String,Value>)->Result<Value,Error>{
    match binding{
        Binding::Literal(value)=>Ok(value.clone()),
        Binding::Reference(reference)=>{
            let mut value=values.get(&reference.symbol_id).cloned().ok_or_else(||error(ErrorKind::Validation,"动作引用值不可用"))?;
            for part in &reference.path{value=match value{Value::Data(fields)=>fields.get(part).cloned().ok_or_else(||error(ErrorKind::Validation,"返回字段不存在"))?,_=>return Err(error(ErrorKind::Validation,"该值没有数据字段"))};}Ok(value)
        },
        _=>Err(error(ErrorKind::Unavailable,"复合参数求值将在声明式执行阶段接入")),
    }
}
fn text(step:&waystroke_model::Step,key:&str,values:&BTreeMap<String,Value>)->Result<String,Error>{match step.params.get(key).map(|b|resolve(b,values)).transpose()?{Some(Value::Text(v))=>Ok(v),None=>Ok(String::new()),_=>Err(error(ErrorKind::Validation,format!("{key} 必须是文本")))}}
fn window(step:&waystroke_model::Step,values:&BTreeMap<String,Value>)->Result<WindowHandle,Error>{let target=text(step,"target",values)?;let key=if target=="当前动作目标"&&values.contains_key("runtime:window.target"){"runtime:window.target"}else if target=="查找到的窗口"{"runtime:window.found"}else{"context:start.window"};match values.get(key){Some(Value::Window(w))=>Ok(w.clone()),_=>Err(error(ErrorKind::TargetInvalid,"起点没有可操作窗口"))}}
async fn execute(step:&waystroke_model::Step,desktop:&Desktop,values:&BTreeMap<String,Value>)->Result<Option<Value>,Error>{
    match step.action.as_str(){
        "shortcut"=>{
            let count=match step.params.get("count").map(|b|resolve(b,values)).transpose()?{Some(Value::Number(n)) if n>=1.&&n.fract()==0.=>n as u32,None=>1,_=>return Err(error(ErrorKind::Validation,"快捷键次数必须是正整数"))};
            let keys=text(step,"value",values)?;let target=window(step,values)?;for _ in 0..count{desktop.call(json!({"operation":"shortcut","keys":keys,"window":target})).await?;}Ok(None)
        },
        "window"=>{
            let operation=text(step,"value",values)?;let action=match operation.as_str(){"激活"=>"activate","最大化"=>"maximize","还原"=>"unmaximize","切换最大化"=>"toggleMaximize","最小化"=>"minimize","关闭窗口"=>"close",_=>return Err(error(ErrorKind::Unavailable,"该窗口操作将在完整窗口执行阶段接入"))};
            desktop.call(json!({"operation":"windowAction","action":action,"window":window(step,values)?})).await?;Ok(None)
        },
        "launch"=>{
            if !text(step,"arguments",values)?.is_empty(){return Err(error(ErrorKind::Unavailable,"非空启动参数将在完整应用执行阶段接入"));}
            Ok(Some(Value::Window(desktop.launch_window(&text(step,"value",values)?).await?)))
        },
        "wait"=>{let delay=match step.params.get("value").map(|b|resolve(b,values)).transpose()?{Some(Value::Number(n)) if n>=0.=>n as u64,_=>return Err(error(ErrorKind::Validation,"等待时间必须是非负数字"))};tokio::time::sleep(std::time::Duration::from_millis(delay)).await;Ok(None)},
        _=>Err(error(ErrorKind::Unavailable,format!("动作 {} 尚未提供执行器",step.action))),
    }
}
pub fn start(runtime:Arc<Runtime>,desktop:Desktop,mut jobs:mpsc::Receiver<Job>,mut cancellation:watch::Receiver<u32>){
    tokio::spawn(async move{
        let definitions=waystroke_model::catalog();
        while let Some(job)=jobs.recv().await{
            let generation=*cancellation.borrow_and_update();
            let canceled=generation!=job.cancellation_generation||cancellation.has_changed().is_err();
            let id=job.id.clone();let mut execution=Execution{id:id.clone(),name:job.name.clone(),revision:job.revision,context:job.context.clone(),state:if canceled{ExecutionState::Canceled}else{ExecutionState::Running},started_at:if canceled{None}else{Some(timestamp())},finished_at:None,reason:if canceled{Some("排队动作已取消".into())}else{None},steps:vec![]};
            if !canceled{
                let mut timing=job.timing.clone();if let Some(timing)=timing.as_mut(){timing.started_ms=Some(now_ms());let mut info=runtime.info.lock().await;if let Some(entry)=info.timings.iter_mut().find(|entry|entry.sequence==timing.sequence&&entry.lease_id==timing.lease_id){entry.started_ms=timing.started_ms;}}
                {let mut info=runtime.info.lock().await;if let Some(entry)=info.executions.iter_mut().find(|entry|entry.id==id){*entry=execution.clone();}}
                runtime.event(json!({"event":"executionStarted","execution":execution,"timing":timing}));
                execution.state=ExecutionState::Succeeded;
            }
            let mut values=BTreeMap::new();if let Some(window)=job.context.window{values.insert("context:start.window".into(),Value::Window(window));}if let Some(app)=job.context.application_id{values.insert("context:start.applicationId".into(),Value::Text(app));}if let Some(title)=job.context.title{values.insert("context:start.title".into(),Value::Text(title));}
            for step in &job.steps{
                if execution.state==ExecutionState::Canceled{break;}if *cancellation.borrow()!=generation||cancellation.has_changed().is_err(){execution.state=ExecutionState::Canceled;execution.reason=Some("动作已停止".into());break;}if !step.enabled{continue;}let began=timestamp();
                let operation=async{match step.timeout_ms.filter(|timeout|*timeout>0){Some(timeout)=>tokio::time::timeout(std::time::Duration::from_millis(timeout.into()),execute(step,&desktop,&values)).await.map_err(|_|error(ErrorKind::Timeout,"步骤超时"))?,None=>execute(step,&desktop,&values).await}};
                let result=tokio::select!{result=operation=>result,_=cancellation.changed()=>Err(error(ErrorKind::Canceled,"动作已停止"))};
                let (state,reason)=match result{Ok(value)=>{if step.action=="launch"&&text(step,"windowTarget",&values).ok().as_deref()==Some("是"){if let Some(value)=&value{values.insert("runtime:window.target".into(),value.clone());}}if let(Some(symbol),Some(value))=(&step.output,value){values.insert(symbol.id.clone(),value);}(ExecutionState::Succeeded,None)},Err(e)=>{let state=match e.kind{ErrorKind::Canceled=>ExecutionState::Canceled,ErrorKind::Timeout=>ExecutionState::TimedOut,_=>ExecutionState::Failed};(state,Some(e.message))}};
                let stop=state!=ExecutionState::Succeeded&&(step.on_failure==FailurePolicy::Stop||state==ExecutionState::Canceled);
                execution.steps.push(StepResult{step_id:step.id.clone(),state:state.clone(),started_at:Some(began),finished_at:Some(timestamp()),reason:reason.clone(),summary:definitions.iter().find(|entry|entry.id==step.action).map(|entry|entry.name.clone())});
                if state!=ExecutionState::Succeeded{execution.state=state;execution.reason=reason;}if stop{break;}
            }
            execution.finished_at=Some(timestamp());{let mut info=runtime.info.lock().await;if let Some(entry)=info.executions.iter_mut().find(|entry|entry.id==id){*entry=execution.clone();}else{info.executions.push(execution.clone());}while info.executions.len()>50{if let Some(index)=info.executions.iter().position(|entry|!matches!(entry.state,ExecutionState::Queued|ExecutionState::Running)){info.executions.remove(index);}else{break;}}}
            runtime.event(json!({"event":"executionFinished","execution":execution}));
            if job.feedback&&!canceled{let message=if execution.state==ExecutionState::Succeeded{format!("{} · 已执行",job.name)}else{execution.reason.clone().unwrap_or_else(||"动作未完成".into())};if let Err(e)=desktop.call(json!({"operation":"feedback","text":message,"monitor":job.context.monitor})).await{eprintln!("gesture feedback: {}",e.message);}}
        }
    });
}
