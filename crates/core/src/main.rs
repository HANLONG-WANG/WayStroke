use std::sync::Arc;
use tokio::sync::{Mutex,Notify};
use waystroke_core::{Repository,config_path,error};
use waystroke_protocol::*;
use zbus::{interface,object_server::SignalEmitter,object_server::ResponseDispatchNotifier};
struct Core { repository:Mutex<Repository>, quit:Arc<Notify> }
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
        if let Ok(ref snapshot)=r { if let Err(e)=Self::config_changed(&emitter,&serde_json::to_string(snapshot).unwrap()).await { eprintln!("config signal failed: {e}"); } }
        reply(r)
    }
    async fn get_status(&self,#[zbus(connection)] connection:&zbus::Connection,#[zbus(header)] header:zbus::message::Header<'_>)->String { if let Err(e)=authorize(connection,&header).await { return reply::<Status>(Err(e)) } reply(Ok(Status{protocol_version:PROTOCOL_VERSION,core_version:env!("CARGO_PKG_VERSION").into(),extension_connected:false,input_connected:false,execution_available:false,reason:"桌面扩展与鼠标服务尚未接入；配置编辑与保存可用".into()})) }
    async fn quit(&self,#[zbus(connection)] connection:&zbus::Connection,#[zbus(header)] header:zbus::message::Header<'_>)->ResponseDispatchNotifier<String> {
        let result=authorize(connection,&header).await;
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
    // D-Bus grants one owner; a second process cannot replace a running writer.
    let connection=zbus::connection::Builder::session()?.serve_at(CORE_PATH,Core{repository:Mutex::new(repo),quit:quit.clone()})?.build().await?;
    connection.request_name_with_flags(CORE_NAME,zbus::fdo::RequestNameFlags::DoNotQueue.into()).await?;
    eprintln!("WayStroke core ready ({})",env!("CARGO_PKG_VERSION"));
    tokio::select! { _=quit.notified()=>{}, _=tokio::signal::ctrl_c()=>{} }
    connection.close().await?;
    Ok(())
}
