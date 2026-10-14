//! Shell marks the real input origin before replaying a rule's final character.
//! AT-SPI then confirms the matching committed insertion at that exact node.
use std::{collections::HashMap,sync::Arc,time::{Duration,Instant}};
use futures_util::StreamExt;
use serde_json::json;
use tokio::sync::{mpsc,watch};
use zbus::zvariant::OwnedValue;
use crate::{atspi::{Adapter,Context,Guard,Request,Reference,bus_error},runtime::Runtime};
use waystroke_protocol::{Snapshot,Error,ErrorKind,TextInputTrigger};
pub(super) struct Intent {text:Option<String>,guard:Guard,before:Context,created:Instant}
fn wanted(snapshot:&Snapshot)->bool{snapshot.config.settings.text_enabled&&snapshot.config.snippets.iter().any(|rule|rule.enabled&&rule.trigger==waystroke_model::TextTrigger::Immediate)}
impl Adapter {
    pub async fn note_input(&self,session:&zbus::Connection,guard:Guard,text:Option<String>)->Result<bool,Error>{
        if text.as_ref().is_some_and(|text|text.chars().count()!=1)||text.is_none()&&!guard.composing{return Err(crate::error(ErrorKind::Validation,"输入来源须为一个字符，或当前组合的确认"))}
        Self::guard_input(&crate::desktop::Desktop::new(session.clone()),&guard,text.is_none()).await?;
        let bus=self.connect(session).await?;
        let Some(context)=self.focused(&bus,&guard).await? else{return Ok(false)};
        let sender=self.input_sender.lock().await.clone();
        let Some(sender)=sender else{return Ok(false)};
        sender.try_send(Intent{text,guard,before:context,created:Instant::now()}).map_err(|_|crate::error(ErrorKind::Unavailable,"输入来源处理队列不可用"))?;
        self.input_keys.fetch_add(1,std::sync::atomic::Ordering::Relaxed);Ok(true)
    }
    pub fn launch_input(self:Arc<Self>,session:zbus::Connection,mut config:watch::Receiver<Snapshot>,runtime:Arc<Runtime>){
        tokio::spawn(async move{
            loop {
                while !wanted(&config.borrow()){if config.changed().await.is_err(){return}}
                let result=self.monitor(&session,&mut config,&runtime).await;
                self.input_ready(false);*self.input_sender.lock().await=None;
                if let Err(error)=&result{self.input_error(Some(error.message.clone())).await;eprintln!("AT-SPI 输入来源接入：{}",error.message);runtime.event(json!({"event":"textCapability","adapter":"atspi","state":"limited","reason":error.message}));}
                if config.has_changed().is_err(){return}
                if result.is_err(){tokio::select!{changed=config.changed()=>{if changed.is_err(){return}},_=tokio::time::sleep(Duration::from_secs(2))=>{}}}
            }
        });
    }
    async fn monitor(self:&Arc<Self>,session:&zbus::Connection,config:&mut watch::Receiver<Snapshot>,runtime:&Runtime)->Result<(),Error>{
        let bus=self.connect(session).await?;
        let rule=zbus::MatchRule::builder().msg_type(zbus::message::Type::Signal).interface("org.a11y.atspi.Event.Object").map_err(bus_error)?.member("TextChanged").map_err(bus_error)?.build();
        let mut events=zbus::MessageStream::for_match_rule(rule,&bus,Some(64)).await.map_err(bus_error)?;
        let owner_rule=zbus::MatchRule::builder().msg_type(zbus::message::Type::Signal).sender("org.freedesktop.DBus").map_err(bus_error)?.interface("org.freedesktop.DBus").map_err(bus_error)?.member("NameOwnerChanged").map_err(bus_error)?.arg(0,"org.a11y.atspi.Registry").map_err(bus_error)?.build();
        let mut owners=zbus::MessageStream::for_match_rule(owner_rule,&bus,Some(8)).await.map_err(bus_error)?;
        let registry=zbus::Proxy::new(&bus,"org.a11y.atspi.Registry","/org/a11y/atspi/registry","org.a11y.atspi.Registry").await.map_err(bus_error)?;
        let _:()=registry.call("RegisterEvent",&("object:text-changed:insert",Vec::<String>::new(),"")).await.map_err(bus_error)?;
        let (sender,mut keys)=mpsc::channel(16);*self.input_sender.lock().await=Some(sender);
        self.input_error(None).await;self.input_ready(true);
        runtime.event(json!({"event":"textCapability","adapter":"atspi","state":"available","reason":"输入起点与实际提交事件已连接"}));
        let mut intent:Option<Intent>=None;
        let result=async {
            loop {
                let expires=intent.as_ref().map(|note|note.created+Duration::from_millis(500)).unwrap_or_else(Instant::now);
                tokio::select!{
                    _=tokio::time::sleep_until(tokio::time::Instant::from_std(expires)),if intent.is_some()=>{intent=None;},
                    changed=config.changed()=>{if changed.is_err()||!wanted(&config.borrow()){return Ok(())}intent=None;},
                    owner=owners.next()=>{
                        let message=match owner{Some(Ok(message))=>message,Some(Err(error))=>return Err(bus_error(error)),None=>return Err(crate::error(ErrorKind::Unavailable,"AT-SPI 注册服务监听已断开"))};
                        let (_,previous,_):(String,String,String)=message.body().deserialize().map_err(bus_error)?;
                        if !previous.is_empty(){self.input_ready(false);bus.clone().close().await.map_err(bus_error)?;return Err(crate::error(ErrorKind::Unavailable,"AT-SPI 注册服务已重启，正在重新连接"))}
                    },
                    key=keys.recv()=>{intent=key;if intent.is_none(){return Err(crate::error(ErrorKind::Unavailable,"AT-SPI 输入来源连接中断"))}},
                    event=events.next()=>{
                        let message=match event{Some(Ok(message))=>message,Some(Err(error))=>return Err(bus_error(error)),None=>return Err(crate::error(ErrorKind::Unavailable,"AT-SPI 文本事件连接中断"))};
                        // Notes were queued before Shell released the original input.
                        while let Ok(note)=keys.try_recv(){intent=Some(note);}
                        let Some(note)=intent.as_ref() else{continue};
                        if note.created.elapsed()>Duration::from_millis(500){intent=None;continue}
                        let header=message.header();
                        if header.sender().map(|s|s.as_str())!=Some(note.before.node.0.as_str())||header.path().map(|p|p.as_str())!=Some(note.before.node.1.as_str()){continue}
                        let Some(context)=Self::read(&bus,&note.before.node).await? else{intent=None;continue};
                        let details=match message.body().signature().to_string().as_str(){
                            "siiva{sv}"|"(siiva{sv})"=>message.body().deserialize::<(String,i32,i32,OwnedValue,HashMap<String,OwnedValue>)>().map(|(kind,start,count,_,_)|(kind,start,count)),
                            _=>message.body().deserialize::<(String,i32,i32,OwnedValue,Reference)>().map(|(kind,start,count,_,_)|(kind,start,count)),
                        }.map_err(bus_error)?;
                        if !details.0.starts_with("insert")||details.2<1||details.1!=note.before.cursor{continue}
                        let inserted=context.text.chars().skip(details.1 as usize).take(details.2 as usize).collect::<String>();
                        if note.text.as_ref().is_some_and(|text|*text!=inserted){continue}
                        let expected=note.before.text.chars().take(details.1 as usize).chain(inserted.chars()).chain(note.before.text.chars().skip(details.1 as usize)).collect::<String>();
                        if context.text!=expected{intent=None;continue}
                        let expected=Context{cursor:details.1+details.2,..context};
                        let composition=note.text.is_none();let mut guard=note.guard.clone();guard.composing=false;
                        let node=note.before.node.clone();intent=None;
                        let snapshot=config.borrow().clone();
                        let response=tokio::time::timeout(Duration::from_millis(400),async {
                            if composition {
                                let desktop=crate::desktop::Desktop::new(session.clone());
                                loop {
                                    let mut actual:Guard=serde_json::from_value(desktop.call(json!({"operation":"textGuard"})).await?).map_err(bus_error)?;
                                    let composing=actual.composing;actual.composing=false;
                                    if actual!=guard{return Err(crate::error(ErrorKind::TargetInvalid,"组合提交的原焦点已变化，取消替换"))}
                                    if !composing{break}
                                    tokio::time::sleep(Duration::from_millis(5)).await;
                                }
                            }
                            self.clone().expand(session,&snapshot.config,Request{guard,trigger:TextInputTrigger::Commit,node:Some(node),expected:Some(expected)}).await
                        }).await;
                        match response{
                            Ok(Ok(result)) if result["matched"]==true=>runtime.event(json!({"event":"textExpansion","adapter":"atspi","state":"succeeded","ruleId":result["ruleId"],"undoToken":result["undoToken"]})),
                            Ok(Ok(_))=>{},Ok(Err(error))=>runtime.event(json!({"event":"textExpansion","adapter":"atspi","state":"failed","reason":error.message})),
                            Err(_)=>runtime.event(json!({"event":"textExpansion","adapter":"atspi","state":"failed","reason":"AT-SPI 立即匹配超时"})),
                        }
                    }
                }
            }
        }.await;
        if !bus.is_closed(){let _:()=registry.call("DeregisterEvent",&("object:text-changed:insert",)).await.map_err(bus_error)?;}
        result
    }
}
