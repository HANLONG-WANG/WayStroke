use std::sync::Arc;
use tokio::sync::{Mutex,Notify,watch};
use waystroke_core::{Repository,config_path,error};
use waystroke_protocol::*;
use zbus::{interface,object_server::SignalEmitter,object_server::ResponseDispatchNotifier};
struct Core { atspi:Arc<waystroke_core::atspi::Adapter>,repository:Arc<Mutex<Repository>>,runtime:Arc<waystroke_core::runtime::Runtime>,config_events:watch::Sender<Snapshot>,quit:Arc<Notify> }
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
    async fn configuration(&self,request:&str,#[zbus(signal_emitter)] emitter:SignalEmitter<'_>,#[zbus(connection)] connection:&zbus::Connection,#[zbus(header)] header:zbus::message::Header<'_>)->String {
        if let Err(e)=authorize(connection,&header).await{return reply::<serde_json::Value>(Err(e));}
        let r=match serde_json::from_str::<serde_json::Value>(request){
            Ok(q)=>{let mut repository=self.repository.lock().await;let previous=repository.snapshot().revision;let result=repository.configuration(q);if result.is_ok()&&repository.snapshot().revision!=previous{let snapshot=repository.snapshot();self.config_events.send_replace(snapshot.clone());if let Err(e)=Self::config_changed(&emitter,&serde_json::to_string(&snapshot).unwrap()).await{eprintln!("config signal failed: {e}");}}result},
            Err(e)=>Err(error(ErrorKind::Validation,e.to_string())),
        };reply(r)
    }
    async fn export_diagnostics(&self,#[zbus(connection)] connection:&zbus::Connection,#[zbus(header)] header:zbus::message::Header<'_>)->String {
        if let Err(e)=authorize(connection,&header).await{return reply::<serde_json::Value>(Err(e));}
        let info=self.runtime.info().await;
        // Allowlist component state only: no configuration, window titles, outputs or input text.
        let capabilities=self.runtime.request(serde_json::json!({"operation":"actionCapabilities"})).await;
        reply(Ok(serde_json::json!({"content":serde_json::to_string_pretty(&serde_json::json!({"format":"waystroke-diagnostics","version":env!("CARGO_PKG_VERSION"),"protocolVersion":PROTOCOL_VERSION,"createdAt":chrono::Utc::now().to_rfc3339(),"components":info.status,"locked":info.locked,"inputArmed":info.input_armed,"timings":info.timings,"text":{"state":info.text.state,"connected":info.text.connected,"adapter":info.text.adapter},"capabilities":Reply::from_result(capabilities),"executions":info.executions.iter().map(|e|serde_json::json!({"state":e.state,"revision":e.revision,"finishedAt":e.finished_at,"steps":e.steps.iter().map(|s|serde_json::json!({"stepId":s.step_id,"state":s.state})).collect::<Vec<_>>()})).collect::<Vec<_>>()})).unwrap()})))
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
    async fn test_text_rule(&self,request:&str,#[zbus(connection)] connection:&zbus::Connection,#[zbus(header)] header:zbus::message::Header<'_>)->String {
        if let Err(e)=authorize(connection,&header).await{return reply::<Option<TextExpansion>>(Err(e));}
        match serde_json::from_str::<TextMatchRequest>(request) {
            Ok(context)=>reply(Ok(waystroke_core::text::match_text(&self.repository.lock().await.snapshot().config,&context))),
            Err(e)=>reply::<Option<TextExpansion>>(Err(error(ErrorKind::Validation,e.to_string()))),
        }
    }
    async fn expand_accessible_text(&self,request:&str,#[zbus(connection)] connection:&zbus::Connection,#[zbus(header)] header:zbus::message::Header<'_>)->String {
        if let Err(e)=authorize(connection,&header).await{return reply::<serde_json::Value>(Err(e));}
        let request=match serde_json::from_str::<waystroke_core::atspi::Request>(request){Ok(request)=>request,Err(e)=>return reply::<serde_json::Value>(Err(error(ErrorKind::Validation,e.to_string())))};
        let config=self.repository.lock().await.snapshot().config;
        reply(self.atspi.clone().expand(connection,&config,request).await)
    }
    async fn note_accessible_input(&self,request:&str,#[zbus(connection)] connection:&zbus::Connection,#[zbus(header)] header:zbus::message::Header<'_>)->String {
        if let Err(e)=authorize(connection,&header).await{return reply::<bool>(Err(e));}
        #[derive(serde::Deserialize)]struct Note{guard:waystroke_core::atspi::Guard,text:Option<String>}
        let request=match serde_json::from_str::<Note>(request){Ok(request)=>request,Err(e)=>return reply::<bool>(Err(error(ErrorKind::Validation,e.to_string())))};
        match tokio::time::timeout(std::time::Duration::from_millis(400),self.atspi.note_input(connection,request.guard,request.text)).await{Ok(result)=>reply(result),Err(_)=>reply::<bool>(Err(error(ErrorKind::Timeout,"AT-SPI 输入起点确认超时")))}
    }
    async fn get_accessible_text_status(&self,#[zbus(connection)] connection:&zbus::Connection,#[zbus(header)] header:zbus::message::Header<'_>)->String {
        if let Err(e)=authorize(connection,&header).await{return reply::<serde_json::Value>(Err(e));}reply(Ok(self.atspi.status().await))
    }
    async fn undo_accessible_text(&self,request:&str,#[zbus(connection)] connection:&zbus::Connection,#[zbus(header)] header:zbus::message::Header<'_>)->String {
        if let Err(e)=authorize(connection,&header).await{return reply::<serde_json::Value>(Err(e));}
        let request=match serde_json::from_str::<waystroke_core::atspi::UndoRequest>(request){Ok(request)=>request,Err(e)=>return reply::<serde_json::Value>(Err(error(ErrorKind::Validation,e.to_string())))};
        reply(self.atspi.undo(connection,request).await)
    }
    async fn clear_accessible_text(&self,token:&str,#[zbus(connection)] connection:&zbus::Connection,#[zbus(header)] header:zbus::message::Header<'_>)->String {
        if let Err(e)=authorize(connection,&header).await{return reply::<()>(Err(e));}
        #[derive(serde::Deserialize)]struct Clear{token:String}
        match serde_json::from_str::<Clear>(token){Ok(request)=>{self.atspi.clear(&request.token).await;reply(Ok(()))},Err(e)=>reply::<()>(Err(error(ErrorKind::Validation,e.to_string())))}
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
    async fn get_action_capabilities(&self,#[zbus(connection)] connection:&zbus::Connection,#[zbus(header)] header:zbus::message::Header<'_>)->String{if let Err(e)=authorize(connection,&header).await{return reply::<serde_json::Value>(Err(e));}reply(self.runtime.request(serde_json::json!({"operation":"actionCapabilities"})).await)}
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
    let repo=Repository::open(path.clone()).map_err(|e|e.message)?;
    let quit=Arc::new(Notify::new());
    let (config_events,config_receiver)=watch::channel(repo.snapshot());let(runtime,driver)=waystroke_core::runtime::Runtime::new();
    let mut runtime_events=runtime.events.subscribe();
    let atspi=Arc::new(waystroke_core::atspi::Adapter::default());
    // D-Bus grants one owner; a second process cannot replace a running writer.
    let repository=Arc::new(Mutex::new(repo));
    let connection=zbus::connection::Builder::session()?.serve_at(CORE_PATH,Core{atspi:atspi.clone(),repository:repository.clone(),runtime:runtime.clone(),config_events,quit:quit.clone()})?.build().await?;
    let mut writer=repository.lock().await;
    connection.request_name_with_flags(CORE_NAME,zbus::fdo::RequestNameFlags::DoNotQueue.into()).await?;
    writer.attach_autostart(waystroke_core::session::Autostart{path:path.parent().unwrap().parent().unwrap().join("autostart/waystroke.desktop"),executable:std::env::current_exe()?}).map_err(|e|e.message)?;
    drop(writer);
    atspi.launch_input(connection.clone(),config_receiver.clone(),runtime.clone());
    driver.launch(runtime.clone(),connection.clone(),config_receiver);
    let text_runtime=runtime.clone();
    let event_connection=connection.clone();tokio::spawn(async move{let emitter=SignalEmitter::new(&event_connection,CORE_PATH).expect("core path");while let Ok(event)=runtime_events.recv().await{text_runtime.observe_text(&event).await;if let Err(e)=Core::runtime_changed(&emitter,&event.to_string()).await{eprintln!("runtime signal: {e}");}}});
    eprintln!("WayStroke core ready ({})",env!("CARGO_PKG_VERSION"));
    let mut terminate=tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())?;
    tokio::select! { _=quit.notified()=>{}, _=tokio::signal::ctrl_c()=>{}, _=terminate.recv()=>{} }
    if let Err(e)=runtime.request(serde_json::json!({"operation":"stop"})).await{eprintln!("runtime shutdown: {}",e.message);}
    connection.close().await?;
    Ok(())
}
