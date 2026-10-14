//! FIFO execution queue with immutable configuration snapshots.
use std::{sync::Arc,collections::BTreeMap};
use serde_json::json;
use tokio::sync::{mpsc,watch};
use waystroke_model::{Value,Execution,ExecutionState};
use waystroke_protocol::{Error,ErrorKind};
use crate::{desktop::Desktop,error,runtime::{Runtime,Job,now_ms}};
fn timestamp()->String{chrono::Utc::now().to_rfc3339()}
use crate::parameters::resolve;
fn text(step:&waystroke_model::Step,key:&str,values:&BTreeMap<String,Value>)->Result<String,Error>{match step.params.get(key).map(|b|resolve(b,values)).transpose()?{Some(Value::Text(v))=>Ok(v),None=>Ok(String::new()),_=>Err(error(ErrorKind::Validation,format!("{key} 必须是文本")))}}
pub(crate) async fn execute_leaf(step:&waystroke_model::Step,desktop:&Desktop,values:&BTreeMap<String,Value>)->Result<Option<Value>,Error>{
    if let Some(result)=crate::data_actions::execute(step,values){return result.map(Some);}
    if let Some(result)=crate::io_actions::execute(step,values).await{return result;}
    if let Some(result)=crate::dbus_actions::execute(step,values).await{return result;}
    if let Some(result)=crate::control_actions::execute(step,values).await{return result;}
    if let Some(result)=crate::system_actions::execute(step,desktop,values).await{return result;}
    match step.action.as_str(){
        "shortcut"=>{
            let count=match step.params.get("count").map(|b|resolve(b,values)).transpose()?{Some(Value::Number(n)) if n>=1.&&n.fract()==0.=>n as u32,None=>1,_=>return Err(error(ErrorKind::Validation,"快捷键次数必须是正整数"))};
            let keys=text(step,"value",values)?;let target=crate::window_actions::target(step,values)?;for _ in 0..count{desktop.call(json!({"operation":"shortcut","keys":keys,"window":target})).await?;}Ok(None)
        },
        "wait"=>{let delay=match step.params.get("value").map(|b|resolve(b,values)).transpose()?{Some(Value::Number(n)) if n>=0.=>n as u64,_=>return Err(error(ErrorKind::Validation,"等待时间必须是非负数字"))};tokio::time::sleep(std::time::Duration::from_millis(delay)).await;Ok(None)},
        _=>Err(error(ErrorKind::Unavailable,format!("动作 {} 尚未提供执行器",step.action))),
    }
}
pub fn start(runtime:Arc<Runtime>,desktop:Desktop,mut jobs:mpsc::Receiver<Job>,mut cancellation:watch::Receiver<u32>){
    tokio::spawn(async move{
        while let Some(job)=jobs.recv().await{
            let generation=*cancellation.borrow_and_update();
            let canceled=generation!=job.cancellation_generation||cancellation.has_changed().is_err();
            let id=job.id.clone();let mut execution=Execution{id:id.clone(),name:job.name.clone(),revision:job.revision,context:job.context.clone(),state:if canceled{ExecutionState::Canceled}else{ExecutionState::Running},started_at:if canceled{None}else{Some(timestamp())},finished_at:None,reason:if canceled{Some("排队动作已取消".into())}else{None},steps:vec![]};
            if !canceled{
                let mut timing=job.timing.clone();if let Some(timing)=timing.as_mut(){timing.started_ms=Some(now_ms());let mut info=runtime.info.lock().await;if let Some(entry)=info.timings.iter_mut().find(|entry|entry.sequence==timing.sequence&&entry.lease_id==timing.lease_id){entry.started_ms=timing.started_ms;}}
                {let mut info=runtime.info.lock().await;if let Some(entry)=info.executions.iter_mut().find(|entry|entry.id==id){*entry=execution.clone();}}
                runtime.event(json!({"event":"executionStarted","execution":execution,"timing":timing}));
            }
            let mut values=BTreeMap::new();if let Some(window)=job.context.window{values.insert("context:start.window".into(),Value::Window(window.clone()));values.insert("runtime:window.target".into(),Value::Window(window));}if let Some(app)=job.context.application_id{values.insert("context:start.applicationId".into(),Value::Text(app));}if let Some(title)=job.context.title{values.insert("context:start.title".into(),Value::Text(title));}
            if !canceled {
                values.insert("context:start.x".into(),Value::Number(job.context.position[0]));
                values.insert("context:start.y".into(),Value::Number(job.context.position[1]));
                values.insert("context:start.position".into(),Value::List(job.context.position.iter().map(|n|Value::Number(*n)).collect()));
                if let Some(workspace)=job.context.workspace {values.insert("context:workspace".into(),Value::Number(workspace as f64+1.));}
                if let Some(monitor)=job.context.monitor {values.insert("context:monitor".into(),Value::Number(monitor as f64+1.));}
                let mut runner=crate::flow::Runner{execution,failure:None,desktop:desktop.clone(),runtime:runtime.clone(),workflows:job.workflows,names:waystroke_model::catalog().into_iter().map(|d|(d.id,d.name)).collect()};
                let result=tokio::select! {
                    biased;
                    _=cancellation.changed()=>Err(error(ErrorKind::Canceled,"动作已停止")),
                    result=runner.sequence(&job.steps,&mut values)=>result,
                };
                match result {
                    Err(e)=>{runner.close_running(&e);runner.execution.state=crate::flow::state(&e);runner.execution.reason=Some(e.message);},
                    Ok(crate::flow::Control::Break|crate::flow::Control::Continue)=>{runner.execution.state=ExecutionState::Failed;runner.execution.reason=Some("循环控制不在循环内部".into());},
                    Ok(_)=>{runner.execution.state=ExecutionState::Succeeded;if let Some(e)=runner.failure {runner.execution.state=crate::flow::state(&e);runner.execution.reason=Some(e.message);}},
                }
                execution=runner.execution;
            }
            if !canceled {if let Err(e)=desktop.call(json!({"operation":"releaseInputs"})).await {eprintln!("input cleanup: {}",e.message);}}
            execution.finished_at=Some(timestamp());{let mut info=runtime.info.lock().await;if let Some(entry)=info.executions.iter_mut().find(|entry|entry.id==id){*entry=execution.clone();}else{info.executions.push(execution.clone());}while info.executions.len()>50{if let Some(index)=info.executions.iter().position(|entry|!matches!(entry.state,ExecutionState::Queued|ExecutionState::Running)){info.executions.remove(index);}else{break;}}}
            runtime.event(json!({"event":"executionFinished","execution":execution}));
            if job.feedback&&!canceled{let message=if execution.state==ExecutionState::Succeeded{format!("{} · 已执行",job.name)}else{execution.reason.clone().unwrap_or_else(||"动作未完成".into())};if let Err(e)=desktop.call(json!({"operation":"feedback","text":message,"monitor":job.context.monitor})).await{eprintln!("gesture feedback: {}",e.message);}}
        }
    });
}
