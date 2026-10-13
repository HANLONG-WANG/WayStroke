//! Authorized mouse transport; no configuration, keyboard capture or user actions.
use evdev::{Device,InputEvent,KeyCode,AttributeSet,raw_stream::{RawDevice,EventStream},uinput::VirtualDevice};
use std::{io,os::{fd::AsRawFd,unix::fs::{PermissionsExt,FileTypeExt}},path::Path,time::Duration};
use tokio::{io::{AsyncBufReadExt,AsyncWriteExt,BufReader},net::{UnixListener,UnixStream},time::Instant};
use waystroke_inputd::{Router,Effect,devices};
use waystroke_protocol::*;

nix::ioctl_write_ptr!(set_event_clock,b'E',0xa0,libc::c_int);
fn monotonic_ms()->f64 {let mut t=libc::timespec{tv_sec:0,tv_nsec:0};unsafe{libc::clock_gettime(libc::CLOCK_MONOTONIC,&mut t)};t.tv_sec as f64*1000.+t.tv_nsec as f64/1e6}

struct Capture {
    lease_id:String, prepared:Option<RawDevice>, stream:Option<EventStream>,
    pointer:VirtualDevice, source_keys:VirtualDevice, router:Router,
    frame:Vec<InputEvent>, key_frame:Vec<InputEvent>, ordinal:u32, last_event_ms:f64, lease:Instant, binding:Option<Instant>, deciding:Option<Instant>,
}
impl Capture {
    fn prepare(device:MouseDevice)->io::Result<Self> {
        let source=Device::open(&device.path)?;
        if !devices::eligible(&source) { return Err(io::Error::other("所选设备不再是相对鼠标")); }
        let lease_id=uuid::Uuid::new_v4().to_string();
        let pointer_name=format!("WayStroke Virtual Pointer {lease_id}");
        // One kernel event queue orders pointer frames and the private F24 marker.
        // Advertise a keyboard layout for udev classification; emit only the
        // source mouse capabilities and F24, never read a physical keyboard.
        let mut keys=AttributeSet::<KeyCode>::new();
        for key in source.supported_keys().unwrap().iter(){keys.insert(key);}
        for key in [KeyCode::KEY_A,KeyCode::KEY_B,KeyCode::KEY_C,KeyCode::KEY_D,KeyCode::KEY_E,KeyCode::KEY_F,KeyCode::KEY_G,KeyCode::KEY_H,KeyCode::KEY_I,KeyCode::KEY_J,KeyCode::KEY_K,KeyCode::KEY_L,KeyCode::KEY_M,KeyCode::KEY_N,KeyCode::KEY_O,KeyCode::KEY_P,KeyCode::KEY_Q,KeyCode::KEY_R,KeyCode::KEY_S,KeyCode::KEY_T,KeyCode::KEY_U,KeyCode::KEY_V,KeyCode::KEY_W,KeyCode::KEY_X,KeyCode::KEY_Y,KeyCode::KEY_Z,KeyCode::KEY_SPACE,KeyCode::KEY_ENTER,KeyCode::KEY_F24] {keys.insert(key);}
        let mut builder=VirtualDevice::builder()?.name(&pointer_name)
            .input_id(source.input_id()).with_keys(&keys)?
            .with_relative_axes(source.supported_relative_axes().unwrap())?;
        builder=builder.with_properties(source.properties())?;
        if let Some(misc)=source.misc_properties() { builder=builder.with_msc(misc)?; }
        if source.supported_absolute_axes().is_some() {
            for (axis,info) in source.get_absinfo()? { builder=builder.with_absolute_axis(&evdev::UinputAbsSetup::new(axis,info))?; }
        }
        let pointer=builder.build()?;
        let source_keys=VirtualDevice::builder()?.name(&format!("WayStroke Virtual Source Keys {lease_id}")).with_keys(&keys)?.build()?;
        let raw=RawDevice::open(&device.path)?;
        unsafe{set_event_clock(raw.as_raw_fd(),&libc::CLOCK_MONOTONIC)}.map_err(io::Error::from)?;
        let prepared=Some(raw);
        Ok(Self{lease_id,prepared,stream:None,pointer,source_keys,router:Router::default(),frame:vec![],key_frame:vec![],ordinal:0,last_event_ms:monotonic_ms(),lease:Instant::now()+Duration::from_millis(INPUT_LEASE_MS.into()),binding:None,deciding:None})
    }
    fn activate(&mut self)->io::Result<()> {
        if self.stream.is_some() { return Err(io::Error::other("鼠标已接管")); }
        let mut source=self.prepared.take().ok_or_else(||io::Error::other("鼠标准备状态失效"))?;
        if source.get_key_state()?.iter().next().is_some() { return Err(io::Error::other("请松开所有鼠标按键后重试")); }
        source.grab()?;
        if source.get_key_state()?.iter().next().is_some() { return Err(io::Error::other("接管期间按键状态改变，请重试")); }
        self.stream=Some(source.into_event_stream()?);Ok(())
    }
    fn emit(&mut self,event:MouseEvent)->io::Result<()> {
        if event.kind==0 && event.code==0 { self.pointer.emit(&self.frame)?;self.frame.clear();if !self.key_frame.is_empty(){self.source_keys.emit(&self.key_frame)?;self.key_frame.clear();} }
        else if event.kind==1&&!(272..288).contains(&event.code){self.key_frame.push(InputEvent::new(event.kind,event.code,event.value));}
        else { self.frame.push(InputEvent::new(event.kind,event.code,event.value)); }
        Ok(())
    }
    async fn marker(&mut self,writer:&mut tokio::net::unix::OwnedWriteHalf,stage:BarrierStage,sequence:u32)->io::Result<()> {
        self.ordinal+=1;
        // The receiver observes the kernel event after previously forwarded motion.
        // A cached Shell snapshot handles marker-before-D-Bus notification races.
        packet(writer,&InputPacket::Barrier{lease_id:self.lease_id.clone(),monotonic_ms:self.last_event_ms,ordinal:self.ordinal,sequence,stage}).await?;
        self.pointer.emit(&[InputEvent::new(evdev::EventType::KEY.0,KeyCode::KEY_F24.code(),1),InputEvent::new(evdev::EventType::KEY.0,KeyCode::KEY_F24.code(),0)])
    }
    async fn effects(&mut self,effects:Vec<Effect>,writer:&mut tokio::net::unix::OwnedWriteHalf)->io::Result<()> {
        for effect in effects { match effect {
            Effect::Forward(e)=>self.emit(e)?,
            Effect::Notify(notice,monotonic_ms)=>{
                self.last_event_ms=monotonic_ms;
                match &notice {
                    InputNotice::Begin{sequence}=>{self.binding=Some(Instant::now()+Duration::from_millis(START_BINDING_MS.into()));self.marker(writer,BarrierStage::Begin,*sequence).await?;},
                    InputNotice::Finish{sequence,..}=>{self.deciding=Some(Instant::now()+Duration::from_millis(START_BINDING_MS.into()));self.marker(writer,BarrierStage::Finish,*sequence).await?;},
                    _=>{},
                }
                packet(writer,&InputPacket::Notice{lease_id:self.lease_id.clone(),monotonic_ms:self.last_event_ms,notice}).await?;
            }
        }}Ok(())
    }
    fn release(&mut self) { let mut effects=self.router.recover_completed_click();effects.extend(self.router.release());for effect in effects { if let Effect::Forward(e)=effect { if let Err(e)=self.emit(e) { eprintln!("释放合成鼠标按键失败：{e}");break; } } }self.stream.take();self.prepared.take(); }
    fn deadline(&self)->Instant { [Some(self.lease),self.binding,self.deciding].into_iter().flatten().min().unwrap() }
}
impl Drop for Capture { fn drop(&mut self){self.release()} }
async fn packet(writer:&mut tokio::net::unix::OwnedWriteHalf,p:&InputPacket)->io::Result<()> {
    let mut bytes=serde_json::to_vec(p)?;bytes.push(b'\n');
    tokio::time::timeout(Duration::from_millis(100),writer.write_all(&bytes)).await.map_err(|_|io::Error::new(io::ErrorKind::TimedOut,"控制器未读取输入事件"))?
}
fn failure(message:impl Into<String>)->Error { Error{kind:ErrorKind::Unavailable,message:message.into(),details:vec![]} }
async fn session(socket:UnixStream)->io::Result<()> {
    let (reader,mut writer)=socket.into_split();let mut reader=BufReader::new(reader);let mut line=String::new();
    let mut hello=false;let mut capture:Option<Capture>=None;
    let mut term=tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())?;
    loop {
        enum Wake { Command(io::Result<usize>),Event(io::Result<InputEvent>),Timeout,Quit }
        let deadline=capture.as_ref().map(Capture::deadline);
        let wake=tokio::select! {
            r=reader.read_line(&mut line)=>Wake::Command(r),
            e=async { match capture.as_mut().and_then(|c|c.stream.as_mut()) { Some(stream)=>stream.next_event().await,None=>std::future::pending().await } }=>Wake::Event(e),
            _=async { match deadline { Some(d)=>tokio::time::sleep_until(d).await,None=>std::future::pending().await } }=>Wake::Timeout,
            _=term.recv()=>Wake::Quit,
            _=tokio::signal::ctrl_c()=>Wake::Quit,
        };
        match wake {
            Wake::Quit=>return Ok(()),
            Wake::Timeout=>{let lease_id=capture.take().unwrap().lease_id.clone();packet(&mut writer,&InputPacket::Notice{lease_id,monotonic_ms:monotonic_ms(),notice:InputNotice::Released{reason:"控制租期或起点/结果确认超时".into()}}).await?;},
            Wake::Event(result)=>{
                let result=result.and_then(|e|{let active=capture.as_mut().unwrap();active.last_event_ms=e.timestamp().duration_since(std::time::UNIX_EPOCH).map_err(io::Error::other)?.as_secs_f64()*1000.;active.router.feed(MouseEvent{kind:e.event_type().0,code:e.code(),value:e.value(),monotonic_ms:active.last_event_ms}).map_err(io::Error::other)});
                match result {
                    Ok(effects)=>capture.as_mut().unwrap().effects(effects,&mut writer).await?,
                    Err(e)=>{let lease_id=capture.take().unwrap().lease_id.clone();packet(&mut writer,&InputPacket::Notice{lease_id,monotonic_ms:monotonic_ms(),notice:InputNotice::Released{reason:e.to_string()}}).await?;},
                }
            }
            Wake::Command(result)=>{
                if result?==0 { return Ok(()); }
                if line.len()>65536 { return Err(io::Error::other("输入请求过大")); }
                let command:InputCommand=serde_json::from_str(&line)?;line.clear();
                let result:Result<InputResult,Error>=async {
                    if let InputRequest::Hello{version}=command.request {
                        if version!=INPUT_PROTOCOL_VERSION { return Err(failure("输入协议版本不兼容")); }
                        hello=true;return Ok(InputResult::Hello{version:INPUT_PROTOCOL_VERSION,lease_ms:INPUT_LEASE_MS});
                    }
                    if !hello { return Err(failure("请先完成版本握手")); }
                    match command.request {
                        InputRequest::Hello{..}=>unreachable!(),
                        InputRequest::ListDevices=>Ok(InputResult::Devices{devices:devices::enumerate().map_err(|e|failure(e.to_string()))?}),
                        InputRequest::Acquire{device_id}=>{
                            if capture.is_some() { return Err(failure("请先释放原鼠标")); }
                            let device=devices::enumerate().map_err(|e|failure(e.to_string()))?.into_iter().find(|d|d.id==device_id).ok_or_else(||failure("所选鼠标已断开，未改选其他设备"))?;
                            let next=Capture::prepare(device.clone()).map_err(|e|failure(e.to_string()))?;
                            let lease_id=next.lease_id.clone();capture=Some(next);Ok(InputResult::Prepared{device,lease_id})
                        },
                        InputRequest::Release=>{if capture.as_ref().is_some_and(|c|Some(&c.lease_id)!=command.lease_id.as_ref()){return Err(failure("控制租期已失效"));}capture.take();Ok(InputResult::Ack)},
                        request=>{
                            let active=capture.as_mut().ok_or_else(||failure("鼠标未准备或已释放"))?;
                            if Some(&active.lease_id)!=command.lease_id.as_ref(){return Err(failure("控制租期已失效"));}
                            let effects=match request {
                                InputRequest::Synchronize=>{active.marker(&mut writer,BarrierStage::Ready,0).await.map_err(|e|failure(e.to_string()))?;vec![]},
                                InputRequest::Activate=>{active.activate().map_err(|e|failure(e.to_string()))?;vec![]},
                                InputRequest::Heartbeat=>{active.lease=Instant::now()+Duration::from_millis(INPUT_LEASE_MS.into());vec![]},
                                InputRequest::Bound{sequence}=>{let out=active.router.bound(sequence).map_err(failure)?;active.binding=None;out},
                                InputRequest::Bypass{sequence}=>{let out=active.router.bypass(sequence).map_err(failure)?;active.binding=None;out},
                                InputRequest::Decide{sequence,decision}=>{let out=active.router.decide(sequence,decision).map_err(failure)?;active.deciding=None;out},
                                InputRequest::Cancel{sequence}=>{let out=active.router.cancel(sequence).map_err(failure)?;active.binding=None;active.deciding=None;out},
                                _=>unreachable!(),
                            };
                            active.effects(effects,&mut writer).await.map_err(|e|failure(e.to_string()))?;Ok(InputResult::Ack)
                        }
                    }
                }.await;
                packet(&mut writer,&InputPacket::Reply{request_id:command.request_id,result:Reply::from_result(result)}).await?;
            }
        }
    }
}
#[tokio::main]
async fn main()->Result<(),Box<dyn std::error::Error>> {
    let args=std::env::args().skip(1).collect::<Vec<_>>();
    if args.len()!=2||args[0]!="--uid" { return Err("用法：waystroke-inputd --uid 安装时授权的UID".into()); }
    let uid:u32=args[1].parse()?;if uid==0 { return Err("必须授权普通桌面用户".into()); }
    if unsafe{libc::geteuid()}!=0 { return Err("鼠标服务由 systemd 以 root 运行；普通界面不提权".into()); }
    let path=Path::new(INPUT_SOCKET);let parent=path.parent().unwrap();std::fs::create_dir_all(parent)?;
    std::fs::set_permissions(parent,std::fs::Permissions::from_mode(0o711))?;
    if path.exists() {
        if !std::fs::symlink_metadata(path)?.file_type().is_socket() { return Err("控制路径被非socket文件占用".into()); }
        if UnixStream::connect(path).await.is_ok() { return Err("鼠标服务已经运行".into()); }
        std::fs::remove_file(path)?;
    }
    let listener=UnixListener::bind(path)?;std::fs::set_permissions(path,std::fs::Permissions::from_mode(0o600))?;
    let cpath=std::ffi::CString::new(INPUT_SOCKET)?;if unsafe{libc::chown(cpath.as_ptr(),uid,u32::MAX)}!=0 { return Err(io::Error::last_os_error().into()); }
    eprintln!("WayStroke input service ready; idle, no device grabbed");
    let mut term=tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())?;
    loop { tokio::select! {
        r=listener.accept()=>{let (stream,_)=r?;if stream.peer_cred()?.uid()!=uid { continue; }if let Err(e)=session(stream).await { eprintln!("控制会话结束：{e}"); }},
        _=term.recv()=>break,
        _=tokio::signal::ctrl_c()=>break,
    }}
    std::fs::remove_file(path)?;Ok(())
}
