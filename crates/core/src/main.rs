use std::sync::Arc;
use tokio::sync::{Mutex,Notify,watch};
use waystroke_core::{Repository,config_path,error};
use waystroke_protocol::*;
use zbus::{interface,object_server::SignalEmitter,object_server::ResponseDispatchNotifier};
struct Core { repository:Arc<Mutex<Repository>>,runtime:Arc<waystroke_core::runtime::Runtime>,config_events:watch::Sender<Snapshot>,quit:Arc<Notify> }
fn reply<T:serde::Serialize>(r:Result<T,Error>)->String { serde_json::to_string(&Reply::from_result(r)).expect("serializable protocol reply") }
async fn authorize(connection:&zbus::Connection,header:&zbus::message::Header<'_>)->Result<(),Error> {
    let sender=header.sender().ok_or_else(||error(ErrorKind::Permission,"缺少会话调用身份"))?;
    let own=connection.unique_name().ok_or_else(||error(ErrorKind::Permission,"缺少服务会话身份"))?;
    let dbus=zbus::fdo::DBusProxy::new(connection).await.map_err(|e|error(ErrorKind::Permission,e.to_string()))?;
    let caller=dbus.get_connection_unix_user(sender.clone().into()).await.map_err(|e|error(ErrorKind::Permission,e.to_string()))?;
    let user=dbus.get_connection_unix_user(own.clone().into()).await.map_err(|e|error(ErrorKind::Permission,e.to_string()))?;
    if caller!=user { return Err(error(ErrorKind::Permission,"仅允许同一用户会话访问")) } Ok(())
}
#[interface(name="io.github.waystroke.Core1")]
impl Core {
    async fn get_config(&self,#[zbus(connection)] connection:&zbus::Connection,#[zbus(header)] header:zbus::message::Header<'_>)->String { if let Err(e)=authorize(connection,&header).await { return reply::<Snapshot>(Err(e)) } reply(Ok(self.repository.lock().await.snapshot())) }
    async fn validate_document(&self,config:&str,#[zbus(connection)] connection:&zbus::Connection,#[zbus(header)] header:zbus::message::Header<'_>)->String {
        if let Err(e)=authorize(connection,&header).await { return reply::<Vec<waystroke_model::ValidationError>>(Err(e)) }
        match serde_json::from_str::<waystroke_model::Config>(config) { Ok(c)=>reply(Ok(waystroke_model::validate(&c))),Err(e)=>reply::<Vec<waystroke_model::ValidationError>>(Err(error(ErrorKind::Validation,e.to_string()))) }
    }
    async fn commit_config(&self,request:&str,#[zbus(signal_emitter)] emitter:SignalEmitter<'_>,#[zbus(connection)] connection:&zbus::Connection,#[zbus(header)] header:zbus::message::Header<'_>)->String {
        if let Err(e)=authorize(connection,&header).await { return reply::<Snapshot>(Err(e)) }
        let r=match serde_json::from_str::<Commit>(request) { Ok(c)=>self.repository.lock().await.commit(c),Err(e)=>Err(error(ErrorKind::Validation,e.to_string())) };
        if let Ok(ref snapshot)=r {self.config_events.send_replace(snapshot.clone());if let Err(e)=Self::config_changed(&emitter,&serde_json::to_string(snapshot).unwrap()).await { eprintln!("config signal failed: {e}"); } }
        reply(r)
    }
    async fn recognize_stroke(&self,request:&str,#[zbus(connection)] connection:&zbus::Connection,#[zbus(header)] header:zbus::message::Header<'_>)->String {
        if let Err(e)=authorize(connection,&header).await{return reply::<RecognitionResult>(Err(e));}
        match serde_json::from_str::<RecognitionRequest>(request){
            Ok(request)=>reply(Ok(waystroke_core::gesture::recognize(&self.repository.lock().await.snapshot().config,&request))),
            Err(e)=>reply::<RecognitionResult>(Err(error(ErrorKind::Validation,e.to_string()))),
        }
    }
    async fn compare_strokes(&self,request:&str,#[zbus(connection)] connection:&zbus::Connection,#[zbus(header)] header:zbus::message::Header<'_>)->String {
        if let Err(e)=authorize(connection,&header).await{return reply::<Vec<f64>>(Err(e));}
        #[derive(serde::Deserialize)]struct Comparison{points:Vec<[f64;2]>,samples:Vec<Vec<[f64;2]>>}
        match serde_json::from_str::<Comparison>(request){Ok(q)=>reply(Ok(q.samples.iter().map(|sample|waystroke_core::gesture::similarity(&q.points,sample)).collect::<Vec<_>>())),Err(e)=>reply::<Vec<f64>>(Err(error(ErrorKind::Validation,e.to_string())))}
    }
    async fn run_rule(&self,request:&str,#[zbus(connection)] connection:&zbus::Connection,#[zbus(header)] header:zbus::message::Header<'_>)->String {
        if let Err(e)=authorize(connection,&header).await{return reply::<serde_json::Value>(Err(e));}
        #[derive(serde::Deserialize)]#[serde(rename_all="camelCase")]struct Run{rule_id:String,context:waystroke_model::StartContext}
        match serde_json::from_str::<Run>(request){Ok(q)=>reply(self.runtime.request(serde_json::json!({"operation":"runRule","ruleId":q.rule_id,"context":q.context})).await),Err(e)=>reply::<serde_json::Value>(Err(error(ErrorKind::Validation,e.to_string())))}
    }
    async fn runtime_control(&self,request:&str,#[zbus(connection)] connection:&zbus::Connection,#[zbus(header)] header:zbus::message::Header<'_>)->String {
        if let Err(e)=authorize(connection,&header).await{return reply::<serde_json::Value>(Err(e));}
        #[derive(serde::Deserialize)]struct Control{operation:String}
        match serde_json::from_str::<Control>(request){Ok(q) if ["beginRecording","endRecording","stopAll","clearLog"].contains(&q.operation.as_str())=>reply(self.runtime.request(serde_json::json!({"operation":q.operation,"owner":header.sender().unwrap().as_str()})).await),Ok(_)=>reply::<serde_json::Value>(Err(error(ErrorKind::Validation,"不支持的运行控制"))),Err(e)=>reply::<serde_json::Value>(Err(error(ErrorKind::Validation,e.to_string())))}
    }
    async fn get_status(&self,#[zbus(connection)] connection:&zbus::Connection,#[zbus(header)] header:zbus::message::Header<'_>)->String { if let Err(e)=authorize(connection,&header).await { return reply::<Status>(Err(e)) } reply(Ok(self.runtime.info().await.status)) }
    async fn get_runtime(&self,#[zbus(connection)] connection:&zbus::Connection,#[zbus(header)] header:zbus::message::Header<'_>)->String{if let Err(e)=authorize(connection,&header).await{return reply::<RuntimeInfo>(Err(e));}reply(Ok(self.runtime.info().await))}
    async fn list_devices(&self,#[zbus(connection)] connection:&zbus::Connection,#[zbus(header)] header:zbus::message::Header<'_>)->String{if let Err(e)=authorize(connection,&header).await{return reply::<serde_json::Value>(Err(e));}reply(self.runtime.request(serde_json::json!({"operation":"listDevices"})).await)}
    async fn list_windows(&self,#[zbus(connection)] connection:&zbus::Connection,#[zbus(header)] header:zbus::message::Header<'_>)->String{if let Err(e)=authorize(connection,&header).await{return reply::<serde_json::Value>(Err(e));}reply(self.runtime.request(serde_json::json!({"operation":"windows"})).await)}
    async fn get_context(&self,#[zbus(connection)] connection:&zbus::Connection,#[zbus(header)] header:zbus::message::Header<'_>)->String{if let Err(e)=authorize(connection,&header).await{return reply::<serde_json::Value>(Err(e));}reply(self.runtime.request(serde_json::json!({"operation":"getContext"})).await)}
    #[zbus(signal)]
    async fn runtime_changed(emitter:&SignalEmitter<'_>,event:&str)->zbus::Result<()>;
    async fn quit(&self,#[zbus(connection)] connection:&zbus::Connection,#[zbus(header)] header:zbus::message::Header<'_>)->ResponseDispatchNotifier<String> {
        let result=authorize(connection,&header).await;
        if result.is_ok(){if let Err(e)=self.runtime.request(serde_json::json!({"operation":"stop"})).await{eprintln!("runtime cleanup before quit: {}",e.message);}}
        let allowed=result.is_ok();let (response,sent)=ResponseDispatchNotifier::new(reply(result));
        let quit=self.quit.clone();tokio::spawn(async move { sent.await;if allowed { quit.notify_one(); } });response
    }
    #[zbus(signal)]
    async fn config_changed(emitter:&SignalEmitter<'_>,snapshot:&str)->zbus::Result<()>;
}
#[tokio::main]
async fn main()->Result<(),Box<dyn std::error::Error>> {
    let path=match config_path() { Ok(p)=>p,Err(e)=>return Err(e.message.into()) };
    let repo=Repository::open(path).map_err(|e|e.message)?;
    let quit=Arc::new(Notify::new());
    let (config_events,config_receiver)=watch::channel(repo.snapshot());let(runtime,driver)=waystroke_core::runtime::Runtime::new();
    let mut runtime_events=runtime.events.subscribe();
    // D-Bus grants one owner; a second process cannot replace a running writer.
    let connection=zbus::connection::Builder::session()?.serve_at(CORE_PATH,Core{repository:Arc::new(Mutex::new(repo)),runtime:runtime.clone(),config_events,quit:quit.clone()})?.build().await?;
    connection.request_name_with_flags(CORE_NAME,zbus::fdo::RequestNameFlags::DoNotQueue.into()).await?;
    driver.launch(runtime.clone(),connection.clone(),config_receiver);
    let event_connection=connection.clone();tokio::spawn(async move{let emitter=SignalEmitter::new(&event_connection,CORE_PATH).expect("core path");while let Ok(event)=runtime_events.recv().await{if let Err(e)=Core::runtime_changed(&emitter,&event.to_string()).await{eprintln!("runtime signal: {e}");}}});
    eprintln!("WayStroke core ready ({})",env!("CARGO_PKG_VERSION"));
    tokio::select! { _=quit.notified()=>{}, _=tokio::signal::ctrl_c()=>{} }
    if let Err(e)=runtime.request(serde_json::json!({"operation":"stop"})).await{eprintln!("runtime shutdown: {}",e.message);}
    connection.close().await?;
    Ok(())
}
