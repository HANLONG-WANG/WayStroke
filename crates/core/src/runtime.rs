//! Live desktop/input coordinator. Shape snapshots are immutable during a stroke.
use std::{sync::Arc};
use futures_util::StreamExt;
use serde_json::{Value,json};
use tokio::sync::{Mutex,mpsc,oneshot,watch,broadcast};
use waystroke_model::{StartContext,Config};
use waystroke_protocol::*;
use crate::{desktop::Desktop,input::InputClient,error,gesture};
use nix::time::{clock_gettime,ClockId};
pub fn now_ms()->f64 {let t=clock_gettime(ClockId::CLOCK_MONOTONIC).expect("Linux monotonic clock");t.tv_sec() as f64*1000.+t.tv_nsec() as f64/1e6}
struct Command {operation:Value,reply:oneshot::Sender<Result<Value,Error>>}
pub struct Driver {receiver:mpsc::Receiver<Command>}
impl Driver {
    pub fn launch(self,runtime:Arc<Runtime>,connection:zbus::Connection,config:watch::Receiver<Snapshot>){
        tokio::spawn(async move{let desktop=Desktop::new(connection.clone());if let Err(e)=runtime.clone().run(connection,config,self.receiver).await{eprintln!("WayStroke runtime stopped: {}",e.message);let _=desktop.call(json!({"operation":"release"})).await;let mut info=runtime.info.lock().await;info.status.execution_available=false;info.status.input_connected=false;info.input_armed=false;info.status.reason=e.message;drop(info);runtime.publish().await;}});
    }
}
pub struct Runtime {pub(crate) info:Mutex<RuntimeInfo>,commands:mpsc::Sender<Command>,pub events:broadcast::Sender<Value>,published:Mutex<Option<String>>}
struct Stroke {preview_text:String,points:Vec<[f64;2]>,auxiliary_buttons:Vec<u16>,sequence:u32,context:StartContext,config:Config,revision:u32,start_ms:f64,bound_ms:f64}
pub struct Job {pub id:String,pub steps:Vec<waystroke_model::Step>,pub workflows:Vec<waystroke_model::Workflow>,pub context:StartContext,pub revision:u32,pub timing:Option<GestureTiming>,pub feedback:bool,pub name:String,pub cancellation_generation:u32}
impl Runtime {
    pub fn new()->(Arc<Self>,Driver) {
        let (commands,receiver)=mpsc::channel(16);let (events,_)=broadcast::channel(256);
        let runtime=Arc::new(Self{info:Mutex::new(RuntimeInfo{status:Status{protocol_version:PROTOCOL_VERSION,core_version:env!("CARGO_PKG_VERSION").into(),extension_connected:false,input_connected:false,execution_available:false,reason:"正在连接桌面和鼠标服务".into()},devices:vec![],selected_device_id:None,input_armed:false,locked:false,recording:None,executions:vec![],timings:vec![]}),commands,events,published:Mutex::new(None)});
        (runtime,Driver{receiver})
    }
    pub async fn info(&self)->RuntimeInfo{self.info.lock().await.clone()}
    pub async fn request(&self,operation:Value)->Result<Value,Error>{if operation["operation"]=="stop"&&self.commands.is_closed(){return Ok(Value::Null);}let(sender,receiver)=oneshot::channel();self.commands.send(Command{operation,reply:sender}).await.map_err(|_|error(ErrorKind::Unavailable,"桌面协调器已停止"))?;receiver.await.map_err(|_|error(ErrorKind::Unavailable,"桌面协调器响应中断"))?}
    pub(crate) fn event(&self,event:Value){let _=self.events.send(event);}
    async fn publish(&self){let info=self.info().await;let encoded=serde_json::to_string(&info).expect("runtime state");let mut previous=self.published.lock().await;if previous.as_ref()!=Some(&encoded){*previous=Some(encoded);self.event(json!({"event":"capability","runtime":info}));}}
    async fn preview(active:&mut Stroke,desktop:&Desktop,lease_id:&str,interaction:bool)->Result<(),Error>{
        let result=gesture::recognize(&active.config,&RecognitionRequest{points:active.points.clone(),context:active.context.clone(),auxiliary_buttons:active.auxiliary_buttons.clone()});
        let text=match result.outcome {
            RecognitionOutcome::Matched=>active.config.rules.iter().find(|r|Some(&r.id)==result.rule_id.as_ref()).map(|r|r.name.as_str()).unwrap_or("未匹配"),
            RecognitionOutcome::Ambiguous=>"手势相近",
            RecognitionOutcome::TooShort=>"",
            _=>"未匹配",
        };
        if !interaction&&active.preview_text==text{return Ok(());}
        active.preview_text=text.to_string();
        desktop.call(json!({"operation":"previewGesture","leaseId":lease_id,"sequence":active.sequence,"text":text,"interaction":interaction})).await?;Ok(())
    }
    async fn release(input:&Option<InputClient>,lease:&mut Option<String>,desktop:&Desktop){if let(Some(input),Some(id))=(input,lease.take()){if let Err(e)=input.request(Some(&id),InputRequest::Release).await{eprintln!("mouse release: {}",e.message);}}if let Err(e)=desktop.call(json!({"operation":"release"})).await{eprintln!("desktop release: {}",e.message);}}
    async fn run(self:Arc<Self>,connection:zbus::Connection,mut config:watch::Receiver<Snapshot>,mut commands:mpsc::Receiver<Command>)->Result<(),Error>{
        let desktop=Desktop::new(connection.clone());
        let rule=zbus::MatchRule::builder().msg_type(zbus::message::Type::Signal).sender("io.github.waystroke.Gnome").map_err(|e|error(ErrorKind::Internal,e.to_string()))?.interface("io.github.waystroke.Gnome1").map_err(|e|error(ErrorKind::Internal,e.to_string()))?.member("Changed").map_err(|e|error(ErrorKind::Internal,e.to_string()))?.build();
        let mut signals=zbus::MessageStream::for_match_rule(rule,&connection,Some(256)).await.map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
        let lock_rule=zbus::MatchRule::builder().msg_type(zbus::message::Type::Signal).sender("org.gnome.ScreenSaver").map_err(|e|error(ErrorKind::Internal,e.to_string()))?.interface("org.gnome.ScreenSaver").map_err(|e|error(ErrorKind::Internal,e.to_string()))?.member("ActiveChanged").map_err(|e|error(ErrorKind::Internal,e.to_string()))?.build();
        let mut lock_signals=zbus::MessageStream::for_match_rule(lock_rule,&connection,Some(8)).await.map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
        let mut screen_locked=desktop.locked().await.unwrap_or(false);
        let dbus=zbus::fdo::DBusProxy::new(&connection).await.map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
        let mut owners=dbus.receive_name_owner_changed().await.map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
        let mut recording_owner:Option<String>=None;
        let mut input:Option<InputClient>=None;let mut packets:Option<broadcast::Receiver<InputPacket>>=None;let mut lease:Option<String>=None;let mut selected:Option<String>=None;let mut stroke:Option<Stroke>=None;let mut pending_finish:Option<(Stroke,Vec<[f64;2]>,f64)>=None;
        let (jobs,job_receiver)=mpsc::channel(32);let (cancel,cancel_receiver)=watch::channel(0u32);
        crate::execution::start(self.clone(),desktop.clone(),job_receiver,cancel_receiver);
        let mut connecting=tokio::task::JoinSet::new();
        let mut interval=tokio::time::interval(std::time::Duration::from_millis(500));interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
        loop {
            enum Wake {Lock(Option<zbus::Result<zbus::Message>>),Tick,Config,Packet(Result<InputPacket,broadcast::error::RecvError>),Desktop(Option<zbus::Result<zbus::Message>>),Command(Option<Command>),Owner(Option<zbus::fdo::NameOwnerChanged>),Connected(Option<Result<Result<InputClient,Error>,tokio::task::JoinError>>)}
            let wake=tokio::select!{
                _=interval.tick()=>Wake::Tick,
                _=config.changed()=>Wake::Config,
                p=async{match packets.as_mut(){Some(rx)=>rx.recv().await,None=>std::future::pending().await}}=>Wake::Packet(p),
                s=signals.next()=>Wake::Desktop(s),
                s=lock_signals.next()=>Wake::Lock(s),
                command=commands.recv()=>Wake::Command(command),
                owner=owners.next()=>Wake::Owner(owner),
                result=connecting.join_next(),if !connecting.is_empty()=>Wake::Connected(result),
            };
            match wake {
                Wake::Lock(Some(Ok(message)))=>{
                    let (locked,):(bool,)=message.body().deserialize().map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
                    screen_locked=locked;
                    if locked{Self::release(&input,&mut lease,&desktop).await;stroke=None;pending_finish=None;cancel.send_modify(|generation|*generation+=1);}
                    {let mut info=self.info.lock().await;info.locked=locked;if locked{info.input_armed=false;info.status.execution_available=false;info.status.reason="桌面已锁定".into();}}
                    self.event(json!({"event":"lock","locked":locked}));self.publish().await;
                },
                Wake::Lock(Some(Err(e)))=>return Err(error(ErrorKind::Unavailable,e.to_string())),
                Wake::Lock(None)=>return Err(error(ErrorKind::Unavailable,"锁屏状态事件连接中断")),
                Wake::Connected(Some(Ok(Ok(client))))=>{packets=Some(client.subscribe());input=Some(client);},
                Wake::Connected(Some(Ok(Err(e))))=>{self.info.lock().await.status.reason=e.message;},
                Wake::Connected(Some(Err(e)))=>return Err(error(ErrorKind::Internal,e.to_string())),
                Wake::Connected(None)=>{},
                Wake::Owner(Some(message))=>{let args=message.args().map_err(|e|error(ErrorKind::Internal,e.to_string()))?;if recording_owner.as_deref()==Some(args.name.as_str())&&args.new_owner.is_none(){recording_owner=None;self.info.lock().await.recording=None;}},
                Wake::Owner(None)=>return Err(error(ErrorKind::Unavailable,"会话身份事件连接中断")),
                Wake::Command(Some(command))=>{
                    let result=match command.operation["operation"].as_str(){
                        Some("stop")=>{Self::release(&input,&mut lease,&desktop).await;let _=cancel.send_modify(|generation|*generation+=1);let _=command.reply.send(Ok(Value::Null));return Ok(());},
                        Some("listDevices")=>match input.as_ref(){Some(client)=>match client.request(lease.as_deref(),InputRequest::ListDevices).await{Ok(InputResult::Devices{devices})=>{self.info.lock().await.devices=devices.clone();Ok(json!(devices))},Ok(_)=>Err(error(ErrorKind::Internal,"鼠标列表响应类型错误")),Err(e)=>Err(e)},None=>Err(error(ErrorKind::Unavailable,"鼠标服务未连接"))},
                        Some("windows")=>desktop.call(json!({"operation":"windows"})).await,
                        Some("getContext")=>desktop.call(json!({"operation":"getContext"})).await,
                        Some("runRule")=>async{
                            if self.info.lock().await.locked{return Err(error(ErrorKind::Unavailable,"桌面已锁定，不能执行动作"));}
                            let hello=desktop.hello().await?;
                            if hello["locked"]==true||self.info.lock().await.locked{return Err(error(ErrorKind::Unavailable,"桌面已锁定，不能执行动作"));}
                            let snapshot=config.borrow().clone();let rule=snapshot.config.rules.iter().find(|rule|Some(rule.id.as_str())==command.operation["ruleId"].as_str());
                            if let Some(rule)=rule{
                                let context=serde_json::from_value::<StartContext>(command.operation["context"].clone()).map_err(|e|error(ErrorKind::Validation,e.to_string()))?;
                                match jobs.try_reserve(){Ok(permit)=>{let id=uuid::Uuid::new_v4().to_string();let execution=waystroke_model::Execution{id:id.clone(),name:rule.name.clone(),revision:snapshot.revision,context:context.clone(),state:waystroke_model::ExecutionState::Queued,started_at:None,finished_at:None,reason:None,steps:vec![]};self.info.lock().await.executions.push(execution.clone());self.event(json!({"event":"executionQueued","execution":execution}));permit.send(Job{id:id.clone(),steps:rule.steps.clone(),workflows:snapshot.config.workflows.clone(),context,revision:snapshot.revision,timing:None,feedback:snapshot.config.settings.feedback&&rule.feedback,name:rule.name.clone(),cancellation_generation:*cancel.borrow()});Ok(json!({"executionId":id}))},Err(_)=>Err(error(ErrorKind::Unavailable,"动作队列已满"))}
                            }else{Err(error(ErrorKind::Validation,"规则不存在"))}
                        }.await,
                        Some("beginRecording")=>{let owner=command.operation["owner"].as_str().unwrap().to_string();if stroke.is_some()||pending_finish.is_some(){Err(error(ErrorKind::Conflict,"当前桌面手势尚未结束，请松开右键后重新进入录制区域"))}else if recording_owner.as_ref().is_some_and(|current|current!=&owner){Err(error(ErrorKind::Conflict,"另一个窗口正在录制手势"))}else{recording_owner=Some(owner);self.info.lock().await.recording=Some("canvas".into());Ok(Value::Null)}},
                        Some("endRecording")=>{if recording_owner.as_deref()==command.operation["owner"].as_str(){recording_owner=None;self.info.lock().await.recording=None;}Ok(Value::Null)},
                        Some("actionCapabilities")=>{let locked=self.info.lock().await.locked;Ok(json!(crate::capabilities::collect(&desktop,locked).await))},
                        Some("clearLog")=>{self.info.lock().await.executions.retain(|entry|matches!(entry.state,waystroke_model::ExecutionState::Queued|waystroke_model::ExecutionState::Running));Ok(Value::Null)},
                        Some("stopAll")=>{cancel.send_modify(|generation|*generation+=1);Ok(Value::Null)},
                        _=>Err(error(ErrorKind::Unavailable,"当前桌面操作尚未接入")),
                    };let _=command.reply.send(result);
                },
                Wake::Command(None)=>break,
                Wake::Desktop(Some(Ok(message)))=>{
                    let (text,):(String,)=message.body().deserialize().map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
                    let event:Value=serde_json::from_str(&text).map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
                    if event["event"]=="lock"&&event["locked"]==true{
                        Self::release(&input,&mut lease,&desktop).await;stroke=None;pending_finish=None;
                        let mut info=self.info.lock().await;info.locked=true;info.input_armed=false;info.status.execution_available=false;info.status.reason="桌面已锁定".into();drop(info);
                        cancel.send_modify(|generation|*generation+=1);
                    }
                    if event["event"]=="canceled"{if let(Some(client),Some(id),Some(active))=(&input,&lease,&stroke){let _=client.request(Some(id),InputRequest::Cancel{sequence:active.sequence}).await;}stroke=None;}
                    if event["event"]=="previewStroke" {
                        if let(Some(active),Some(id))=(&mut stroke,&lease){
                            if event["leaseId"].as_str()==Some(id.as_str())&&event["sequence"].as_u64()==Some(active.sequence as u64){
                                let offset=event["offset"].as_u64().ok_or_else(||error(ErrorKind::Internal,"预览轨迹缺少偏移"))? as usize;
                                if offset!=active.points.len(){return Err(error(ErrorKind::Internal,"预览轨迹顺序不一致"));}
                                let points:Vec<[f64;2]>=serde_json::from_value(event["points"].clone()).map_err(|e|error(ErrorKind::Internal,e.to_string()))?;
                                active.points.extend(points);Self::preview(active,&desktop,id,false).await?;
                            }
                        }
                    }else{self.event(event);}
                },
                Wake::Desktop(Some(Err(e)))=>return Err(error(ErrorKind::Unavailable,e.to_string())),
                Wake::Desktop(None)=>return Err(error(ErrorKind::Unavailable,"桌面事件连接中断")),
                Wake::Packet(Ok(InputPacket::Barrier{lease_id,monotonic_ms,ordinal,sequence,stage})) if lease.as_ref()==Some(&lease_id)=>{
                    let client=input.as_ref().unwrap();
                    let result:Result<(),Error>=async{
                        let barrier=desktop.wait_barrier(&lease_id,ordinal).await?;
                        match stage {
                            BarrierStage::Begin=>{
                                let snapshot=config.borrow().clone();let mut context:StartContext=serde_json::from_value(barrier["context"].clone()).map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
                                context.sequence=sequence;
                                if recording_owner.is_some()||snapshot.config.exclusions.iter().any(|e|e.gestures&&Some(&e.application_id)==context.application_id.as_ref())||!snapshot.config.settings.gestures_enabled {
                                    client.request(Some(&lease_id),InputRequest::Bypass{sequence}).await?;return Ok(());
                                }
                                desktop.call(json!({"operation":"beginGesture","leaseId":lease_id,"ordinal":ordinal,"sequence":sequence,"trail":snapshot.config.settings.trail,"color":snapshot.config.settings.color,"cancelTimeout":snapshot.config.settings.cancel_timeout,"minimumLength":snapshot.config.settings.minimum_length})).await?;
                                stroke=Some(Stroke{preview_text:String::new(),points:vec![context.position],auxiliary_buttons:vec![],sequence,context,config:snapshot.config,revision:snapshot.revision,start_ms:monotonic_ms,bound_ms:now_ms()});
                                client.request(Some(&lease_id),InputRequest::Bound{sequence}).await?;
                                self.event(json!({"event":"gestureStarted","sequence":sequence,"context":stroke.as_ref().unwrap().context}));
                            },
                            BarrierStage::Finish=>{
                                let active=stroke.take().ok_or_else(||error(ErrorKind::Canceled,"手势已取消"))?;
                                if active.sequence!=sequence{return Err(error(ErrorKind::Canceled,"结束序号已过期"));}
                                let finished=desktop.call(json!({"operation":"finishGesture","leaseId":lease_id,"ordinal":ordinal,"sequence":sequence})).await?;
                                let points=serde_json::from_value(finished["points"].clone()).map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
                                // Auxiliary state arrives in the following finish notice; defer matching.
                                self.event(json!({"event":"strokeReady","sequence":sequence,"points":points,"endContext":barrier["context"]}));
                                pending_finish=Some((active,points,monotonic_ms));
                            },
                            BarrierStage::Ready=>{},
                        }Ok(())
                    }.await;
                    if let Err(e)=result{self.event(json!({"event":"gestureError","message":e.message}));Self::release(&input,&mut lease,&desktop).await;stroke=None;pending_finish=None;}
                },
                Wake::Packet(Ok(InputPacket::Notice{lease_id,notice:InputNotice::Auxiliary{sequence,button},..})) if lease.as_ref()==Some(&lease_id)=>{
                    if let Some(active)=stroke.as_mut(){if active.sequence==sequence{
                        if !active.auxiliary_buttons.contains(&button){active.auxiliary_buttons.push(button);}
                        Self::preview(active,&desktop,&lease_id,true).await?;
                    }}
                },
                Wake::Packet(Ok(InputPacket::Notice{lease_id,notice:InputNotice::Finish{sequence,auxiliary_buttons},..})) if lease.as_ref()==Some(&lease_id)=>{
                    if let Some((active,points,released_ms))=pending_finish.take(){
                        if active.sequence!=sequence{continue;}
                        let request=RecognitionRequest{points,context:active.context.clone(),auxiliary_buttons};let result=gesture::recognize(&active.config,&request);let recognized_ms=now_ms();
                        input.as_ref().unwrap().request(Some(&lease_id),InputRequest::Decide{sequence,decision:if matches!(result.outcome,RecognitionOutcome::TooShort){StrokeDecision::Click}else{StrokeDecision::Consume}}).await?;
                        let mut timing=GestureTiming{lease_id:lease_id.clone(),sequence,start_device_ms:active.start_ms,bound_ms:active.bound_ms,release_device_ms:released_ms,recognized_ms,enqueued_ms:None,started_ms:None};
                        let permit=if result.rule_id.is_some(){match jobs.try_reserve(){Ok(permit)=>Some(permit),Err(_)=>{self.event(json!({"event":"gestureError","message":"动作队列已满"}));None}}}else{None};
                        if permit.is_some(){timing.enqueued_ms=Some(now_ms());}
                        {let mut info=self.info.lock().await;info.timings.push(timing.clone());if info.timings.len()>50{info.timings.remove(0);}}
                        if let (Some(permit),Some(rule))=(permit,result.rule_id.as_ref().and_then(|id|active.config.rules.iter().find(|r|&r.id==id))){
                            let id=uuid::Uuid::new_v4().to_string();
                            let execution=waystroke_model::Execution{id:id.clone(),name:rule.name.clone(),revision:active.revision,context:active.context.clone(),state:waystroke_model::ExecutionState::Queued,started_at:None,finished_at:None,reason:None,steps:vec![]};
                            self.info.lock().await.executions.push(execution.clone());self.event(json!({"event":"executionQueued","execution":execution}));
                            permit.send(Job{id,steps:rule.steps.clone(),workflows:active.config.workflows.clone(),context:active.context,revision:active.revision,timing:Some(timing.clone()),feedback:active.config.settings.feedback&&rule.feedback,name:rule.name.clone(),cancellation_generation:*cancel.borrow()});
                        }
                        self.event(json!({"event":"recognition","result":result,"timing":timing}));
                    }
                },
                Wake::Packet(Ok(InputPacket::Notice{notice:InputNotice::Released{reason},..}))=>{
                    Self::release(&input,&mut lease,&desktop).await;stroke=None;pending_finish=None;input=None;packets=None;self.info.lock().await.status.reason=reason;
                },
                Wake::Packet(Err(broadcast::error::RecvError::Lagged(_)))=>{Self::release(&input,&mut lease,&desktop).await;stroke=None;pending_finish=None;input=None;packets=None;self.info.lock().await.status.reason="输入事件消费过慢，鼠标已释放".into();},
                Wake::Packet(Err(broadcast::error::RecvError::Closed))=>{input=None;packets=None;lease=None;stroke=None;},
                Wake::Packet(_)=>{},
                Wake::Tick|Wake::Config=>{
                    let snapshot=config.borrow().clone();let hello=desktop.hello().await;
                    let connected=hello.is_ok();let locked=screen_locked||hello.as_ref().ok().is_some_and(|v|v["locked"]==true);
                    let desired=if connected&&!locked&&snapshot.config.settings.setup_complete&&snapshot.config.settings.gestures_enabled{snapshot.config.settings.mouse_device_id.clone()}else{None};
                    if lease.is_some()&&(desired!=selected||!connected||locked){Self::release(&input,&mut lease,&desktop).await;stroke=None;pending_finish=None;if !connected||locked{cancel.send_modify(|generation|*generation+=1);}}
                    if input.is_none()&&connecting.is_empty(){connecting.spawn(InputClient::connect());}
                    if let Some(client)=input.as_ref(){
                        if lease.is_none()&&self.info.lock().await.devices.is_empty(){if let Ok(InputResult::Devices{devices})=client.request(None,InputRequest::ListDevices).await{self.info.lock().await.devices=devices;}}
                        if let Some(id)=lease.as_deref(){if client.request(Some(id),InputRequest::Heartbeat).await.is_err(){Self::release(&input,&mut lease,&desktop).await;input=None;packets=None;}}
                    }
                    if lease.is_none(){if let(Some(client),Some(id))=(input.as_ref(),desired.as_ref()){
                        match client.request(None,InputRequest::Acquire{device_id:id.clone()}).await{
                            Ok(InputResult::Prepared{lease_id,device})=>{
                                {let mut info=self.info.lock().await;if let Some(entry)=info.devices.iter_mut().find(|entry|entry.id==device.id){*entry=device;}else{info.devices.push(device);}}
                                lease=Some(lease_id.clone());selected=Some(id.clone());
                                let prepared:Result<(),Error>=async{desktop.call(json!({"operation":"registerBarrier","leaseId":lease_id})).await?;desktop.wait_devices(&lease_id).await?;client.request(Some(&lease_id),InputRequest::Synchronize).await?;let ready=desktop.wait_barrier(&lease_id,1).await?;if ready["devicesReady"]!=true{return Err(error(ErrorKind::Unavailable,"合成鼠标尚未被桌面发现"));}client.request(Some(&lease_id),InputRequest::Activate).await?;Ok(())}.await;
                                if let Err(e)=prepared{self.info.lock().await.status.reason=e.message;Self::release(&input,&mut lease,&desktop).await;}
                            },
                            Err(e)=>self.info.lock().await.status.reason=e.message,
                            _=>{},
                        }
                    }}
                    let mut info=self.info.lock().await;info.status.extension_connected=connected;info.status.input_connected=input.is_some();info.status.execution_available=connected&&!locked;info.input_armed=lease.is_some();info.locked=locked;info.selected_device_id=snapshot.config.settings.mouse_device_id;
                    if locked{info.status.reason="桌面已锁定".into();}else if !connected{info.status.reason="GNOME 扩展未连接".into();}else if input.is_none(){info.status.reason="鼠标服务未连接或未授权".into();}else if !snapshot.config.settings.gestures_enabled{info.status.reason="手势已暂停".into();}else if info.selected_device_id.is_none(){info.status.reason="请选择用于手势的鼠标".into();}else if lease.is_some(){info.status.reason="鼠标手势已接入；具体动作能力见运行状态".into();}drop(info);self.publish().await;
                }
            }
        }
        Self::release(&input,&mut lease,&desktop).await;Ok(())
    }
}
