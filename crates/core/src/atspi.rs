//! AT-SPI editing runs in core, on this user's accessibility bus. Window binding
//! is checked against the Shell handle and the accessible owner's actual PID.
use std::{collections::{VecDeque,HashMap},sync::{Arc,atomic::{AtomicBool,AtomicU64,Ordering}}};
use futures_util::StreamExt;
use serde::{Deserialize,Serialize};
use serde_json::json;
use tokio::sync::Mutex;
use waystroke_model::{Config,WindowHandle};
use waystroke_protocol::{Error,ErrorKind,TextInputTrigger,TextMatchRequest};
use zbus::zvariant::{OwnedObjectPath,OwnedValue};
use crate::{desktop::Desktop,error};
const ACCESSIBLE:&str="org.a11y.atspi.Accessible";
const TEXT:&str="org.a11y.atspi.Text";
const EDITABLE:&str="org.a11y.atspi.EditableText";
pub(super) type Reference=(String,OwnedObjectPath);
#[derive(Clone,Debug,Deserialize,Serialize,PartialEq)]
#[serde(rename_all="camelCase",deny_unknown_fields)]
pub struct Guard {pub instance:String,pub generation:u32,pub window:WindowHandle,pub application_id:String,pub pid:u32,pub client_type:u32,pub composing:bool,pub ime_known:bool,pub locked:bool,pub enabled:bool,#[serde(default)]pub wm_class:String}
#[derive(Deserialize)]
#[serde(rename_all="camelCase",deny_unknown_fields)]
pub struct Request {pub guard:Guard,pub trigger:TextInputTrigger,#[serde(default)]pub node:Option<Reference>,#[serde(skip)]pub(super) expected:Option<Context>,
    /// An immediate rule's final character, held back by Shell when no
    /// accessible input source exists; only the selection fallback uses it.
    #[serde(default)]pub literal:Option<String>}
/// What AT-SPI reports for the focused window. Only `Absent` permits the
/// selection fallback: a password or unusable text node is never selected.
pub(super) enum Focus {Editable(Context),Other,Absent}
#[derive(Clone,Debug)]
pub(super) struct Context {pub node:Reference,pub text:String,pub cursor:i32,pub serial:u32}
impl PartialEq for Context {fn eq(&self,other:&Self)->bool{self.node==other.node&&self.text==other.text&&self.cursor==other.cursor}}
#[derive(Default)]
pub struct Adapter {roots:Mutex<Vec<Reference>>,pub(super) input_sender:Mutex<Option<tokio::sync::mpsc::Sender<crate::atspi_input::Intent>>>,pub(super) input_keys:Arc<AtomicU64>,input_error:Mutex<Option<String>>,input_ready:AtomicBool,connection:Mutex<Option<zbus::Connection>>,undo:Arc<Mutex<Option<Undo>>>,editing:Mutex<()>}
struct Undo {token:String,guard:Guard,before:Context,after:Context,start:i32,confirmation:String,confirmed:bool}
#[derive(Deserialize)]
#[serde(rename_all="camelCase",deny_unknown_fields)]
pub struct UndoRequest {pub guard:Guard,pub token:String}
pub(super) fn bus_error(e:impl std::fmt::Display)->Error {error(ErrorKind::Unavailable,format!("AT-SPI 接入失败：{e}"))}
/// zbus stops reading the whole connection while any stream's queue is full,
/// so a consumer that awaits replies on the same bus must not drain the stream
/// itself: a burst of events would leave the reply unread forever.
pub(super) async fn events(bus:&zbus::Connection,rule:zbus::MatchRule<'static>)->Result<tokio::sync::mpsc::UnboundedReceiver<zbus::Result<zbus::Message>>,Error>{
    let mut stream=zbus::MessageStream::for_match_rule(rule,bus,Some(64)).await.map_err(bus_error)?;
    let (sender,receiver)=tokio::sync::mpsc::unbounded_channel();
    tokio::spawn(async move{while let Some(message)=stream.next().await{if sender.send(message).is_err(){return}}});
    Ok(receiver)
}
fn partial_error(mut error:Error)->Error {
    error.details.push(waystroke_model::ValidationError{path:"text.partialEdit".into(),message:"文本可能已改变；停止重放确认键".into()});error
}
// A timed-out read must not be confused with a timed-out write. Once a write
// was sent, its result is uncertain even if its D-Bus future was canceled.
async fn checked_edit(edited:&AtomicBool,operation:impl std::future::Future<Output=Result<serde_json::Value,Error>>)->Result<serde_json::Value,Error>{
    let result=tokio::time::timeout(std::time::Duration::from_millis(350),operation).await
        .unwrap_or_else(|_|Err(error(ErrorKind::Timeout,"AT-SPI 编辑超时")));
    result.map_err(|mut error|{
        if edited.load(Ordering::Relaxed){
            if !error.details.iter().any(|detail|detail.path=="text.partialEdit"){error=partial_error(error)}
        }else{error.details.push(waystroke_model::ValidationError{path:"text.unmodified".into(),message:"尚未发出编辑请求，可恢复原确认键".into()})}
        error
    })
}
impl Adapter {
    pub async fn status(&self)->serde_json::Value {json!({"immediateReady":self.input_ready.load(Ordering::Relaxed),"undoAvailable":self.undo.lock().await.is_some(),"inputError":self.input_error.lock().await.clone(),"inputKeys":self.input_keys.load(Ordering::Relaxed)})}
    pub(super) async fn input_error(&self,error:Option<String>){*self.input_error.lock().await=error;}
    pub(super) fn input_ready(&self,ready:bool){self.input_ready.store(ready,Ordering::Relaxed)}
    pub(super) async fn connect(&self,session:&zbus::Connection)->Result<zbus::Connection,Error> {
        let mut cached=self.connection.lock().await;
        if let Some(connection)=cached.as_ref(){if !connection.is_closed(){return Ok(connection.clone())}*cached=None;*self.undo.lock().await=None;}
        let proxy=zbus::Proxy::new(session,"org.a11y.Bus","/org/a11y/bus","org.a11y.Bus").await.map_err(bus_error)?;
        let address:String=proxy.call("GetAddress",&()).await.map_err(bus_error)?;
        let connection=zbus::connection::Builder::address(address.as_str()).map_err(bus_error)?.build().await.map_err(bus_error)?;
        self.watch_undo(&connection,session).await?;*cached=Some(connection.clone());Ok(connection)
    }
    async fn watch_undo(&self,bus:&zbus::Connection,session:&zbus::Connection)->Result<(),Error>{
        let rule=zbus::MatchRule::builder().msg_type(zbus::message::Type::Signal).interface("org.a11y.atspi.Event.Object").map_err(bus_error)?.build();
        let mut events=events(bus,rule).await?;
        let registry=zbus::Proxy::new(bus,"org.a11y.atspi.Registry","/org/a11y/atspi/registry","org.a11y.atspi.Registry").await.map_err(bus_error)?;
        for event in ["object:text-caret-moved","object:state-changed:focused"]{let _:()=registry.call("RegisterEvent",&(event,Vec::<String>::new(),"")).await.map_err(bus_error)?;}
        let undo=self.undo.clone();let bus=bus.clone();let desktop=Desktop::new(session.clone());
        tokio::spawn(async move{
            while let Some(message)=events.recv().await{
                let message=match message{Ok(message)=>message,Err(error)=>{eprintln!("AT-SPI 撤销事件连接中断：{error}");*undo.lock().await=None;return}};
                let header=message.header();let member=header.member().map(|m|m.as_str());
                if !matches!(member,Some("TextCaretMoved"|"StateChanged")){continue}
                let details=match message.body().signature().to_string().as_str(){
                    "siiva{sv}"|"(siiva{sv})"=>message.body().deserialize::<(String,i32,i32,OwnedValue,HashMap<String,OwnedValue>)>().map(|(kind,first,_,_,_)|(kind,first)),
                    _=>message.body().deserialize::<(String,i32,i32,OwnedValue,Reference)>().map(|(kind,first,_,_,_)|(kind,first)),
                };
                if member==Some("StateChanged")&&details.as_ref().is_ok_and(|(kind,_)|kind=="focused") {
                    if let Some(sender)=header.sender() {
                        let dbus=zbus::Proxy::new(&bus,"org.freedesktop.DBus","/org/freedesktop/DBus","org.freedesktop.DBus").await;
                        if let Ok(dbus)=dbus {
                            if let Ok(pid)=dbus.call::<_,_,u32>("GetConnectionUnixProcessID",&(sender.as_str(),)).await {
                                if let Err(error)=desktop.call(json!({"operation":"textFocusChanged","pid":pid})).await{eprintln!("AT-SPI 焦点通知失败：{}",error.message)}
                            }
                        }
                    }
                }
                let mut slot=undo.lock().await;let Some(entry)=slot.as_mut() else{continue};
                if header.sender().map(|s|s.as_str())!=Some(entry.after.node.0.as_str())||header.path().map(|p|p.as_str())!=Some(entry.after.node.1.as_str())||message.primary_header().serial_num().get()<=entry.after.serial{continue}
                let token=entry.token.clone();
                match details{Ok((kind,first))=>{
                    if member==Some("StateChanged")&&kind=="focused"&&first==0{*slot=None}
                    else if member==Some("TextCaretMoved"){
                        let confirmation=entry.confirmation.chars().count() as i32;
                        let expected=entry.after.cursor+if entry.confirmed{confirmation}else{0};
                        if first!=expected{if !entry.confirmed&&confirmation>0&&first==entry.after.cursor+confirmation{entry.confirmed=true}else{*slot=None}}
                    }
                },Err(error)=>{eprintln!("AT-SPI 撤销事件无法解析：{error}");*slot=None}}
                let invalidated=slot.is_none();drop(slot);
                if invalidated{if let Err(error)=desktop.call(json!({"operation":"textUndoInvalidated","token":token})).await{eprintln!("AT-SPI 撤销状态通知失败：{}",error.message)}}
            }
            *undo.lock().await=None;
        });Ok(())
    }
    async fn proxy<'a>(bus:&'a zbus::Connection,node:&'a Reference,interface:&'static str)->Result<zbus::Proxy<'a>,Error>{zbus::Proxy::new(bus,node.0.as_str(),node.1.as_str(),interface).await.map_err(bus_error)}
    // Chromium lists children it has not created yet as the AT-SPI null reference.
    async fn children(bus:&zbus::Connection,node:&Reference)->Result<Vec<Reference>,Error>{
        let children:Vec<Reference>=Self::proxy(bus,node,ACCESSIBLE).await?.call("GetChildren",&()).await.map_err(bus_error)?;
        Ok(children.into_iter().filter(|child|child.1.as_str()!="/org/a11y/atspi/null").collect())
    }
    pub(super) async fn read(bus:&zbus::Connection,node:&Reference)->Result<Option<Context>,Error>{
        let accessible=Self::proxy(bus,node,ACCESSIBLE).await?;
        let role:u32=accessible.call("GetRole",&()).await.map_err(bus_error)?;
        // Never read password text; terminal editing uses its separate adapter.
        if role==40||role==60{return Ok(None)}
        let states:Vec<u32>=accessible.call("GetState",&()).await.map_err(bus_error)?;
        let has=|bit:u32|states.get((bit/32) as usize).is_some_and(|word|word&(1<<(bit%32))!=0);
        if !has(12)||!has(7){return Ok(None)}
        let interfaces:Vec<String>=accessible.call("GetInterfaces",&()).await.map_err(bus_error)?;
        if !interfaces.iter().any(|i|i==TEXT)||!interfaces.iter().any(|i|i==EDITABLE){return Ok(None)}
        let proxy=Self::proxy(bus,node,TEXT).await?;
        let selections:i32=proxy.call("GetNSelections",&()).await.map_err(bus_error)?;
        if selections!=0{return Ok(None)}
        let cursor:i32=proxy.get_property("CaretOffset").await.map_err(bus_error)?;
        let reply=proxy.call_method("GetText",&(0i32,-1i32)).await.map_err(bus_error)?;
        let text:String=reply.body().deserialize().map_err(bus_error)?;let serial=reply.primary_header().serial_num().get();
        if cursor<0||cursor as usize>text.chars().count(){return Err(error(ErrorKind::TargetInvalid,"AT-SPI 光标超出文本范围"))}
        Ok(Some(Context{node:node.clone(),text,cursor,serial}))
    }
    pub(super) async fn focused(&self,bus:&zbus::Connection,guard:&Guard)->Result<Option<Context>,Error>{
        Ok(match self.locate(bus,guard).await?{Focus::Editable(context)=>Some(context),_=>None})
    }
    pub(super) async fn locate(&self,bus:&zbus::Connection,guard:&Guard)->Result<Focus,Error>{
        let root=("org.a11y.atspi.Registry".into(),OwnedObjectPath::try_from("/org/a11y/atspi/accessible/root").unwrap());
        let dbus=zbus::fdo::DBusProxy::new(bus).await.map_err(bus_error)?;
        let registered=Self::children(bus,&root).await?;
        let live=dbus.list_names().await.map_err(bus_error)?;
        let roots={
            let mut remembered=self.roots.lock().await;
            remembered.retain(|reference|live.iter().any(|name|name.as_str()==reference.0));
            let mut roots=registered;
            for reference in remembered.iter(){if !roots.contains(reference){roots.push(reference.clone());}}
            *remembered=roots.clone();roots
        };
        // A registry restart can lose application entries while those clients
        // still export their accessible roots. Revalidate identity and focus on
        // every access; only references, never text, survive the restart.
        for application in roots {
            let name=zbus::names::BusName::try_from(application.0.as_str()).map_err(bus_error)?;
            if dbus.get_connection_unix_process_id(name).await.map_err(bus_error)?!=guard.pid{continue}
            let mut queue=VecDeque::from([application]);
            while let Some(node)=queue.pop_front(){
                let accessible=Self::proxy(bus,&node,ACCESSIBLE).await?;
                let states:Vec<u32>=accessible.call("GetState",&()).await.map_err(bus_error)?;
                if states.first().is_some_and(|word|word&(1<<12)!=0){
                    let role:u32=accessible.call("GetRole",&()).await.map_err(bus_error)?;
                    if role==40||role==60{return Ok(Focus::Other)}
                    if let Some(context)=Self::read(bus,&node).await?{return Ok(Focus::Editable(context))}
                    let interfaces:Vec<String>=accessible.call("GetInterfaces",&()).await.map_err(bus_error)?;
                    if interfaces.iter().any(|i|i==TEXT){return Ok(Focus::Other)}
                }
                queue.extend(Self::children(bus,&node).await?);
            }
        }
        Ok(Focus::Absent)
    }
    /// Whether the focused window exposes no accessible text at all.
    pub async fn absent(&self,session:&zbus::Connection,guard:&Guard)->Result<bool,Error>{
        let bus=self.connect(session).await?;Ok(matches!(self.locate(&bus,guard).await?,Focus::Absent))
    }
    pub(super) async fn guard(desktop:&Desktop,expected:&Guard)->Result<(),Error>{
        Self::guard_input(desktop,expected,false).await
    }
    pub(super) async fn guard_input(desktop:&Desktop,expected:&Guard,allow_composing:bool)->Result<(),Error>{
        let actual:Guard=serde_json::from_value(desktop.call(json!({"operation":"textGuard"})).await?).map_err(bus_error)?;
        if actual!=*expected||actual.locked||actual.composing&&!allow_composing||!actual.ime_known||!actual.enabled||actual.client_type!=1{return Err(error(ErrorKind::TargetInvalid,"焦点、输入法或文本接入状态已变化，取消 AT-SPI 操作"))}
        Ok(())
    }
    pub async fn clear(&self,token:&str){let mut undo=self.undo.lock().await;if undo.as_ref().is_some_and(|entry|entry.token==token){*undo=None;}}
    pub async fn undo(&self,session:&zbus::Connection,request:UndoRequest)->Result<serde_json::Value,Error>{
        let edited=AtomicBool::new(false);
        checked_edit(&edited,self.undo_inner(session,request,&edited)).await
    }
    async fn undo_inner(&self,session:&zbus::Connection,request:UndoRequest,edited:&AtomicBool)->Result<serde_json::Value,Error>{
        let _editing=self.editing.lock().await;
        let mut slot=self.undo.lock().await;
        if !slot.as_ref().is_some_and(|entry|entry.token==request.token){return Ok(json!({"matched":false}))}
        let entry=slot.take().unwrap();drop(slot);
        let desktop=Desktop::new(session.clone());Self::guard(&desktop,&request.guard).await?;
        if entry.guard!=request.guard{return Ok(json!({"matched":false}))}
        let bus=self.connect(session).await?;
        let Some(actual)=Self::read(&bus,&entry.after.node).await? else{return Ok(json!({"matched":false}))};
        let confirmation=if actual==entry.after{String::new()}else{
            let expected=entry.after.text.chars().take(entry.after.cursor as usize).chain(entry.confirmation.chars()).chain(entry.after.text.chars().skip(entry.after.cursor as usize)).collect::<String>();
            if entry.confirmation.is_empty()||actual.text!=expected||actual.cursor!=entry.after.cursor+entry.confirmation.chars().count() as i32{return Ok(json!({"matched":false}))}
            entry.confirmation
        };
        Self::guard(&desktop,&request.guard).await?;
        let editable=Self::proxy(&bus,&actual.node,EDITABLE).await?;
        edited.store(true,Ordering::Relaxed);
        let deleted:bool=editable.call("DeleteText",&(entry.start,actual.cursor)).await.map_err(bus_error).map_err(partial_error)?;
        if !deleted{return Err(partial_error(error(ErrorKind::Unavailable,"应用拒绝撤销替换的删除操作")))}
        Self::guard(&desktop,&request.guard).await.map_err(partial_error)?;
        let after_delete=actual.text.chars().take(entry.start as usize).chain(actual.text.chars().skip(actual.cursor as usize)).collect::<String>();
        if !Self::read(&bus,&actual.node).await.map_err(partial_error)?.is_some_and(|context|context.text==after_delete){return Err(partial_error(error(ErrorKind::TargetInvalid,"焦点或文本在撤销中改变，停止插入")))}
        let replacement=entry.before.text.chars().skip(entry.start as usize).take((entry.before.cursor-entry.start) as usize).chain(confirmation.chars()).collect::<String>();
        let inserted:bool=editable.call("InsertText",&(entry.start,replacement.as_str(),replacement.len() as i32)).await.map_err(bus_error).map_err(partial_error)?;
        if !inserted{return Err(partial_error(error(ErrorKind::Unavailable,"应用拒绝恢复关键词")))}
        let cursor=entry.start+replacement.chars().count() as i32;
        let moved:bool=Self::proxy(&bus,&actual.node,TEXT).await.map_err(partial_error)?.call("SetCaretOffset",&(cursor,)).await.map_err(bus_error).map_err(partial_error)?;
        if !moved{return Err(partial_error(error(ErrorKind::Unavailable,"应用拒绝恢复撤销后的光标")))}
        let expected=entry.before.text.chars().take(entry.before.cursor as usize).chain(confirmation.chars()).chain(entry.before.text.chars().skip(entry.before.cursor as usize)).collect::<String>();
        if !Self::read(&bus,&actual.node).await.map_err(partial_error)?.is_some_and(|context|context.text==expected&&context.cursor==cursor){return Err(partial_error(error(ErrorKind::Unavailable,"应用未确认撤销结果")))}
        Ok(json!({"matched":true,"adapter":"atspi"}))
    }
    pub async fn expand(self:Arc<Self>,session:&zbus::Connection,config:&Config,request:Request)->Result<serde_json::Value,Error>{
        let edited=AtomicBool::new(false);
        checked_edit(&edited,self.expand_inner(session,config,request,&edited)).await
    }
    async fn expand_inner(&self,session:&zbus::Connection,config:&Config,request:Request,edited:&AtomicBool)->Result<serde_json::Value,Error>{
        let _editing=self.editing.lock().await;
        let desktop=Desktop::new(session.clone());
        Self::guard(&desktop,&request.guard).await?;
        let bus=self.connect(session).await?;
        let context=match self.locate(&bus,&request.guard).await? {
            Focus::Editable(context)=>context,
            Focus::Other=>return Ok(json!({"matched":false,"reason":"当前焦点属于密码字段或暂不可编辑的 AT-SPI 文本"})),
            Focus::Absent=>return Ok(json!({"matched":false,"fallback":true})),
        };
        if request.node.as_ref().is_some_and(|node|node!=&context.node){return Err(error(ErrorKind::TargetInvalid,"AT-SPI 输入起点已失效，不改用其他编辑区域"))}
        if request.expected.as_ref().is_some_and(|expected|expected!=&context){return Err(error(ErrorKind::TargetInvalid,"实际提交后的范围或光标已变化，取消替换"))}
        let matched=crate::text::match_text(config,&TextMatchRequest{application_id:request.guard.application_id.clone(),before_cursor:context.text.chars().take(context.cursor as usize).collect(),trigger:request.trigger,composing:false,password:false,terminal:false});
        let Some(expansion)=matched else{return Ok(json!({"matched":false}))};
        Self::guard(&desktop,&request.guard).await?;
        if Self::read(&bus,&context.node).await?.as_ref()!=Some(&context){return Err(error(ErrorKind::TargetInvalid,"AT-SPI 焦点或文本范围已变化"))}
        let start=context.cursor-expansion.delete_chars as i32;
        let editable=Self::proxy(&bus,&context.node,EDITABLE).await?;
        edited.store(true,Ordering::Relaxed);
        let deleted:bool=editable.call("DeleteText",&(start,context.cursor)).await.map_err(bus_error).map_err(partial_error)?;
        if !deleted{return Err(partial_error(error(ErrorKind::Unavailable,"应用拒绝删除关键词")))}
        Self::guard(&desktop,&request.guard).await.map_err(partial_error)?;
        let after_delete=context.text.chars().take(start as usize).chain(context.text.chars().skip(context.cursor as usize)).collect::<String>();
        if !Self::read(&bus,&context.node).await.map_err(partial_error)?.is_some_and(|actual|actual.text==after_delete){return Err(partial_error(error(ErrorKind::TargetInvalid,"AT-SPI 焦点或文字在删除后改变；停止插入")))}
        let inserted:bool=editable.call("InsertText",&(start,expansion.replacement.as_str(),expansion.replacement.len() as i32)).await.map_err(bus_error).map_err(partial_error)?;
        if !inserted{return Err(partial_error(error(ErrorKind::Unavailable,"应用拒绝插入替换文本；关键词已删除")))}
        let cursor=start+expansion.replacement.chars().count() as i32;
        let moved:bool=Self::proxy(&bus,&context.node,TEXT).await.map_err(partial_error)?.call("SetCaretOffset",&(cursor,)).await.map_err(bus_error).map_err(partial_error)?;
        if !moved{return Err(partial_error(error(ErrorKind::Unavailable,"应用拒绝设置替换后的光标")))}
        let expected=context.text.chars().take(start as usize).chain(expansion.replacement.chars()).chain(context.text.chars().skip(context.cursor as usize)).collect::<String>();
        let verified=Self::read(&bus,&context.node).await.map_err(partial_error)?;
        let after=verified.filter(|actual|actual.text==expected&&actual.cursor==cursor).ok_or_else(||partial_error(error(ErrorKind::Unavailable,"应用未确认 AT-SPI 替换结果")))?;
        let token=uuid::Uuid::new_v4().to_string();
        *self.undo.lock().await=Some(Undo{token:token.clone(),guard:request.guard,before:context.clone(),after,start,confirmation:if expansion.preserve{expansion.confirmation}else{String::new()},confirmed:false});
        Ok(json!({"matched":true,"preserve":expansion.preserve,"ruleId":expansion.rule_id,"adapter":"atspi","undoToken":token}))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[tokio::test]
    async fn timeout_reports_whether_an_edit_was_sent(){
        let edited=AtomicBool::new(false);
        let before=checked_edit(&edited,std::future::pending()).await.unwrap_err();
        assert!(matches!(before.kind,ErrorKind::Timeout));
        assert!(before.details.iter().any(|detail|detail.path=="text.unmodified"));
        let after=checked_edit(&edited,async{edited.store(true,Ordering::Relaxed);std::future::pending().await}).await.unwrap_err();
        assert!(after.details.iter().any(|detail|detail.path=="text.partialEdit"));
        assert!(!after.details.iter().any(|detail|detail.path=="text.unmodified"));
    }
}
