//! Action registration is explicit and independent of the catalog display.
use serde_json::json;
use waystroke_protocol::{ActionCapability,ActionAvailability};
use crate::desktop::Desktop;
fn executor(id:&str)->Option<&'static str>{Some(match id{
    "wait"|"wait.condition"|"condition"|"repeat"|"foreach"|"loop.break"|"loop.continue"|"flow.stop"|"flow.call"=>"core:flow",
    "variable"|"variable.read"|"number.calculate"|"text.transform"|"date.format"|"number.random"|"json.parse"|"data.field"|"list.change"=>"core:data",
    "command"|"process.signal"|"uri.open"|"file.read"|"file.write"|"file.copy"|"file.move"|"file.trash"|"file.info"|"directory.create"|"directory.list"|"http.request"=>"core:io",
    "dbus.call"|"dbus.property"=>"core:dbus",
    "waystroke.toggle"|"waystroke.rule"|"waystroke.open"=>"core:control",
    "shortcut"|"key"|"mouse"|"pointer"|"scroll"|"drag"|"text"|"paste"|"clipboard.read"|"clipboard.write"|"clipboard.clear"|"selection.copy"=>"desktop:input",
    "window"|"window.find"|"window.target"|"window.info"|"window.geometry"|"window.monitor"|"workspace.switch"|"workspace.move"|"desktop.overview"|"desktop.show"|"launch"|"app.activate"|"app.quit"=>"desktop:window",
    "media"|"session"|"settings.open"=>"core:system",
    "volume"|"brightness"|"notification"|"dialog.message"|"dialog.input"|"screenshot"=>"desktop:system",
    _=>return None,
})}
pub async fn collect(desktop:&Desktop,locked:bool)->Vec<ActionCapability>{
    let hello=desktop.hello().await;
    let ready=hello.as_ref().is_ok_and(|v|v["locked"]!=true)&&!locked;
    let current=hello.as_ref().is_ok_and(|v|v["capabilities"].as_array().is_some_and(|caps|caps.iter().any(|c|c=="declarativeActionsV1")));
    let desktop_support=if ready&&current{desktop.call(json!({"operation":"actionSupport"})).await.ok()}else{None};
    let connection=zbus::Connection::session().await.ok();
    let names=if let Some(connection)=&connection{if let Ok(proxy)=zbus::fdo::DBusProxy::new(connection).await{proxy.list_names().await.unwrap_or_default().into_iter().map(|n|n.to_string()).collect::<Vec<_>>()}else{vec![]}}else{vec![]};
    waystroke_model::catalog().into_iter().map(|definition|{
        use ActionAvailability::*;
        let registered=executor(&definition.id);let mut state=Available;let mut reason="执行器已接入；具体参数、目标和权限在运行时核对".to_string();
        if registered.is_none(){state=Unavailable;reason="动作尚未注册执行器".into();}
        else if !ready{state=Unavailable;reason=if locked{"桌面已锁定".into()}else{hello.as_ref().err().map(|e|e.message.clone()).unwrap_or_else(||"桌面未就绪".into())};}
        else if registered.is_some_and(|name|name.starts_with("desktop:"))&&!current{
            state=if matches!(definition.id.as_str(),"shortcut"|"window"|"launch"){Limited}else{Unavailable};reason="当前扩展仍是旧模块，需要加载阶段 C 扩展".into();
        }else{
            match definition.id.as_str(){
                "paste"|"clipboard.write"|"clipboard.clear" if desktop_support.as_ref().is_none_or(|v|v["clipboard"]["available"]!=true)=>{state=Unavailable;reason=desktop_support.as_ref().and_then(|v|v["clipboard"]["reason"].as_str()).unwrap_or("剪贴板原生组件不可用").into();},
                "text"=>{state=Limited;reason="原生文本提交取决于目标应用；自动/临时粘贴需要剪贴板原生组件".into();},
                "volume"=>{let output=desktop_support.as_ref().is_some_and(|v|v["audio"]["output"]==true);let input=desktop_support.as_ref().is_some_and(|v|v["audio"]["input"]==true);if !output&&!input{state=Unavailable;reason="没有可用的默认音频设备".into();}else if !output||!input{state=Limited;reason=if output{"仅默认输出可用"}else{"仅默认输入可用"}.into();}},
                "brightness" if desktop_support.as_ref().is_none_or(|v|v["brightness"]!=true)=>{state=Unavailable;reason="GNOME 没有可控制的显示器背光".into();},
                "media"=>{if !names.iter().any(|n|n.starts_with("org.mpris.MediaPlayer2.")){state=Unavailable;reason="没有 MPRIS 播放器".into();}else{state=Limited;reason="具体播放和定位操作由所选播放器的能力决定".into();}},
                "session"=>{state=Limited;reason="锁屏使用 GNOME 服务；注销和挂起另需会话服务及系统权限".into();},
                "dbus.call"|"dbus.property"=>{state=Limited;reason="按目标服务的接口和访问权限执行".into();},
                _=>{},
            }
        }
        ActionCapability{action_id:definition.id,executor:registered.map(str::to_owned),state,reason}
    }).collect()
}
