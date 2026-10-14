//! Session/system actions run as the desktop user; host capabilities are explicit.
use serde_json::json;
use waystroke_model::{Step,Value};
use waystroke_protocol::{Error,ErrorKind};
use crate::{desktop::Desktop,error,flow::{text,number},parameters::{Values,from_json}};
fn bus(e:zbus::Error)->Error {error(if matches!(&e,zbus::Error::MethodError(name,_,_) if name.as_str().contains("AccessDenied")||name.as_str().contains("Auth")){ErrorKind::Permission}else{ErrorKind::Unavailable},e.to_string())}
async fn media(step:&Step,values:&Values)->Result<(),Error>{
    let connection=zbus::Connection::session().await.map_err(bus)?;
    let dbus=zbus::fdo::DBusProxy::new(&connection).await.map_err(bus)?;
    let requested=text(step,"player",values)?;
    let mut names=dbus.list_names().await.map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?.into_iter().map(|v|v.to_string()).filter(|v|v.starts_with("org.mpris.MediaPlayer2.")).collect::<Vec<_>>();names.sort();
    if names.is_empty(){return Err(error(ErrorKind::Unavailable,"没有可用的 MPRIS 播放器"));}
    let auto=requested.is_empty()||requested=="当前活动播放器";
    let mut candidates=vec![];
    for name in names {
        let root=zbus::Proxy::new(&connection,name.as_str(),"/org/mpris/MediaPlayer2","org.mpris.MediaPlayer2").await.map_err(bus)?;
        let identity:String=root.get_property("Identity").await.map_err(bus)?;
        let player=zbus::Proxy::new(&connection,name.as_str(),"/org/mpris/MediaPlayer2","org.mpris.MediaPlayer2.Player").await.map_err(bus)?;
        if auto||requested==name||requested==identity||name.strip_prefix("org.mpris.MediaPlayer2.")==Some(&requested){
            let status:String=player.get_property("PlaybackStatus").await.map_err(bus)?;
            let entry:Option<String>=root.get_property("DesktopEntry").await.ok();
            let origin=values.get("context:start.applicationId");
            let origin_match=matches!((entry,origin),(Some(entry),Some(Value::Text(app))) if entry.trim_end_matches(".desktop")==app.trim_end_matches(".desktop"));
            candidates.push((name,status=="Playing",origin_match));
        }
    }
    if candidates.is_empty(){return Err(error(ErrorKind::Unavailable,"指定播放器没有提供可用的 MPRIS 服务"));}
    if !auto&&candidates.len()>1{return Err(error(ErrorKind::Validation,"播放器名称对应多个实例，请使用完整 MPRIS 服务名"));}
    candidates.sort_by_key(|(name,playing,origin)|(!*origin,!*playing,name.clone()));
    let name=&candidates[0].0;
    let proxy=zbus::Proxy::new(&connection,name.as_str(),"/org/mpris/MediaPlayer2","org.mpris.MediaPlayer2.Player").await.map_err(bus)?;
    let operation=text(step,"value",values)?;
    let (method,capability)=match operation.as_str(){"播放"=>("Play","CanPlay"),"暂停"=>("Pause","CanPause"),"播放 / 暂停"=>("PlayPause",if proxy.get_property::<String>("PlaybackStatus").await.map_err(bus)?=="Playing" {"CanPause"}else{"CanPlay"}),"停止"=>("Stop","CanControl"),"上一首"=>("Previous","CanGoPrevious"),"下一首"=>("Next","CanGoNext"),"快进"|"快退"=>("Seek","CanSeek"),_=>return Err(error(ErrorKind::Validation,"未知媒体操作"))};
    if !proxy.get_property::<bool>("CanControl").await.map_err(bus)?||!proxy.get_property::<bool>(capability).await.map_err(bus)?{return Err(error(ErrorKind::Unavailable,format!("播放器不支持 {operation}")));}
    if method=="Seek"{
        let seconds=number(step,"seconds",values)?;
        if seconds<0.||seconds>i64::MAX as f64/1_000_000. {return Err(error(ErrorKind::Validation,"快进或快退时长无效"));}
        let offset=(seconds*1_000_000.).round() as i64 * if operation=="快退" {-1}else{1};
        let _:()=proxy.call(method,&(offset,)).await.map_err(bus)?;
    }else{let _:()=proxy.call(method,&()).await.map_err(bus)?;}
    Ok(())
}
pub async fn execute(step:&Step,desktop:&Desktop,values:&Values)->Option<Result<Option<Value>,Error>>{
    if !matches!(step.action.as_str(),"volume"|"brightness"|"media"|"notification"|"dialog.message"|"dialog.input"|"screenshot"|"session"|"settings.open"){return None;}
    Some(async {
        match step.action.as_str(){
            "volume"=>{desktop.call(json!({"operation":"volume","value":text(step,"value",values)?,"amount":number(step,"amount",values)?,"device":text(step,"device",values)?})).await?;},
            "brightness"=>{desktop.call(json!({"operation":"brightness","value":text(step,"value",values)?,"amount":number(step,"amount",values)?})).await?;},
            "media"=>media(step,values).await?,
            "notification"=>{desktop.call(json!({"operation":"notification","title":text(step,"value",values)?,"body":text(step,"body",values)?})).await?;},
            "dialog.message"=>return Ok(Some(from_json(desktop.call(json!({"operation":"dialogMessage","title":text(step,"value",values)?,"content":text(step,"body",values)?,"buttons":text(step,"buttons",values)?})).await?)?)),
            "dialog.input"=>return Ok(Some(from_json(desktop.call(json!({"operation":"dialogInput","prompt":text(step,"value",values)?,"defaultValue":text(step,"default",values)?,"buttons":"确定 / 取消"})).await?)?)),
            "screenshot"=>{
                let window=if text(step,"value",values)?=="目标窗口"{match values.get("runtime:window.target"){Some(Value::Window(window))=>Some(window),_=>return Err(error(ErrorKind::TargetInvalid,"没有可截图的动作目标窗口"))}}else{None};
                let destination=text(step,"destination",values)?;
                let path=if destination=="文件"{text(step,"path",values)?}else{String::new()};
                return Ok(Some(from_json(desktop.call(json!({"operation":"screenshot","value":text(step,"value",values)?,"destination":destination,"path":path,"window":window})).await?)?));
            },
            "session"=>{
                let operation=text(step,"value",values)?;
                let confirm=text(step,"confirm",values)?;if !matches!(confirm.as_str(),"是"|"否"){return Err(error(ErrorKind::Validation,"执行前确认应为是或否"));}
                if confirm=="是"{desktop.call(json!({"operation":"dialogMessage","title":"确认会话操作","content":format!("确定要{operation}吗？"),"buttons":"确定 / 取消"})).await?;}
                let connection=zbus::Connection::session().await.map_err(bus)?;
                match operation.as_str(){
                    "锁屏"=>{let proxy=zbus::Proxy::new(&connection,"org.gnome.ScreenSaver","/org/gnome/ScreenSaver","org.gnome.ScreenSaver").await.map_err(bus)?;let _:()=proxy.call("Lock",&()).await.map_err(bus)?;},
                    "注销"=>{let proxy=zbus::Proxy::new(&connection,"org.gnome.SessionManager","/org/gnome/SessionManager","org.gnome.SessionManager").await.map_err(bus)?;let _:()=proxy.call("Logout",&(0u32,)).await.map_err(bus)?;},
                    "挂起"=>{let connection=zbus::Connection::system().await.map_err(bus)?;let proxy=zbus::Proxy::new(&connection,"org.freedesktop.login1","/org/freedesktop/login1","org.freedesktop.login1.Manager").await.map_err(bus)?;let capability:String=proxy.call("CanSuspend",&()).await.map_err(bus)?;if !matches!(capability.as_str(),"yes"|"challenge"){return Err(error(ErrorKind::Unavailable,format!("当前系统不能挂起：{capability}")));}let _:()=proxy.call("Suspend",&(true,)).await.map_err(bus)?;},
                    _=>return Err(error(ErrorKind::Validation,"未知会话操作")),
                }
            },
            "settings.open"=>{
                let panel=match text(step,"value",values)?.as_str(){"显示器"=>"display","声音"=>"sound","键盘"=>"keyboard","鼠标与触摸板"=>"mouse","网络"=>"network","蓝牙"=>"bluetooth","电源"=>"power","外观"=>"background",_=>return Err(error(ErrorKind::Validation,"未知设置页面"))};
                desktop.launch_window_arguments("org.gnome.Settings",panel).await?;
            },_=>unreachable!(),
        };Ok(None)
    }.await)
}
