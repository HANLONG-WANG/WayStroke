//! Desktop actions preserve explicit window identities across every step.
use serde_json::json;
use waystroke_model::{Step,Value,WindowHandle};
use waystroke_protocol::{Error,ErrorKind};
use crate::{desktop::Desktop,error,flow::{text,number,integer,parameter},parameters::{Values,from_json}};
pub fn target(step:&Step,values:&Values)->Result<WindowHandle,Error> {
    let key=match text(step,"target",values)?.as_str(){"起点窗口"=>"context:start.window","当前动作目标"=>"runtime:window.target","查找到的窗口"=>"runtime:window.found",_=>return Err(error(ErrorKind::Validation,"未知目标窗口来源"))};
    match values.get(key){Some(Value::Window(window))=>Ok(window.clone()),_=>Err(error(ErrorKind::TargetInvalid,"指定的动作目标窗口不存在"))}
}
pub async fn execute(step:&Step,desktop:&Desktop,values:&mut Values)->Option<Result<Option<Value>,Error>> {
    if !matches!(step.action.as_str(),"window"|"window.find"|"window.target"|"window.info"|"window.geometry"|"window.monitor"|"workspace.switch"|"workspace.move"|"desktop.overview"|"desktop.show"|"app.activate"|"app.quit"|"launch"){return None;}
    Some(async {
        let output=match step.action.as_str(){
            "window"=>{
                let action=match text(step,"value",values)?.as_str(){
                    "激活"=>"activate","最大化"=>"maximize","还原"=>"unmaximize","切换最大化"=>"toggleMaximize","最小化"=>"minimize","取消最小化"=>"unminimize","关闭窗口"=>"close",
                    "左半屏"=>"leftHalf","右半屏"=>"rightHalf","进入全屏"=>"fullscreen","退出全屏"=>"unfullscreen","切换全屏"=>"toggleFullscreen","置顶"=>"above","取消置顶"=>"unabove","置顶 / 取消置顶"=>"toggleAbove",
                    "所有工作区可见"=>"stick","仅当前工作区可见"=>"unstick","移至上一工作区"=>"previousWorkspace","移至下一工作区"=>"nextWorkspace",
                    _=>return Err(error(ErrorKind::Validation,"未知窗口操作")),
                };
                desktop.call(json!({"operation":"windowAction","action":action,"window":target(step,values)?})).await?;None
            },
            "window.find"=>{
                let handle=desktop.call(json!({"operation":"windowFind","applicationId":text(step,"value",values)?,"title":text(step,"title",values)?,"workspace":text(step,"workspace",values)?,"pick":text(step,"pick",values)?})).await?;
                let window:WindowHandle=serde_json::from_value(handle).map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
                values.insert("runtime:window.found".into(),Value::Window(window.clone()));Some(Value::Window(window))
            },
            "window.target"=>{
                let window=match text(step,"value",values)?.as_str(){
                    "起点窗口"=>values.get("context:start.window").cloned().ok_or_else(||error(ErrorKind::TargetInvalid,"手势起点没有窗口"))?,
                    "当前聚焦窗口"=>{
                        let handle=desktop.call(json!({"operation":"focusedWindow"})).await?;
                        if handle.is_null(){return Err(error(ErrorKind::TargetInvalid,"当前没有聚焦窗口"));}
                        Value::Window(serde_json::from_value(handle).map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?)
                    },
                    "窗口变量"=>parameter(step,"variable",values)?,_=>return Err(error(ErrorKind::Validation,"未知动作目标来源")),
                };
                let Value::Window(handle)=&window else{return Err(error(ErrorKind::Validation,"动作目标必须是窗口对象"));};
                desktop.call(json!({"operation":"windowInfo","window":handle})).await?;
                values.insert("runtime:window.target".into(),window);None
            },
            "window.info"=>{
                let key=match text(step,"value",values)?.as_str(){"标题"=>"title","应用 ID"=>"applicationId","位置与尺寸"=>"geometry","工作区"=>"workspace","所在显示器"=>"monitor","是否最大化"=>"maximized","是否全屏"=>"fullscreen","是否置顶"=>"above",_=>return Err(error(ErrorKind::Validation,"未知窗口信息"))};
                let info=desktop.call(json!({"operation":"windowInfo","window":target(step,values)?})).await?;
                Some(from_json(info.get(key).cloned().ok_or_else(||error(ErrorKind::Unavailable,"桌面未返回所需窗口信息"))?)?)
            },
            "window.geometry"=>{
                desktop.call(json!({"operation":"windowGeometry","window":target(step,values)?,"unit":text(step,"unit",values)?,"x":number(step,"x",values)?,"y":number(step,"y",values)?,"width":number(step,"width",values)?,"height":number(step,"height",values)?})).await?;None
            },
            "window.monitor"=>{let value=text(step,"value",values)?;let index=if value=="指定编号"{integer(step,"index",values)?}else{0};desktop.call(json!({"operation":"windowMonitor","window":target(step,values)?,"value":value,"index":index})).await?;None},
            "workspace.switch"=>{let value=text(step,"value",values)?;let index=if value=="指定编号"{integer(step,"index",values)?}else{0};desktop.call(json!({"operation":"workspaceSwitch","value":value,"index":index})).await?;None},
            "workspace.move"=>{desktop.call(json!({"operation":"workspaceMove","window":target(step,values)?,"index":integer(step,"value",values)?,"follow":text(step,"follow",values)?=="是"})).await?;None},
            "desktop.overview"=>{desktop.call(json!({"operation":"desktopOverview","value":text(step,"value",values)?})).await?;None},
            "desktop.show"=>{desktop.call(json!({"operation":"desktopShow","value":text(step,"value",values)?})).await?;None},
            "launch"=>{
                let application=text(step,"value",values)?;let arguments=text(step,"arguments",values)?;
                let new_window=text(step,"windowTarget",values)?=="是";
                if !new_window&&step.output.is_none(){desktop.call(json!({"operation":"launch","applicationId":application,"arguments":arguments})).await?;None}
                else{Some(Value::Window(desktop.launch_matching_window(&application,&arguments,"",new_window).await?))}
            },
            "app.activate"=>{
                let application=text(step,"value",values)?;let title=text(step,"title",values)?;let timeout=integer(step,"timeout",values)?;
                let operation=async{
                    let handle=match desktop.call(json!({"operation":"windowFind","applicationId":application,"title":title,"workspace":"所有工作区","pick":"最近使用"})).await {
                        Ok(handle)=>serde_json::from_value::<WindowHandle>(handle).map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?,
                        Err(e) if matches!(e.kind,ErrorKind::TargetInvalid)=>desktop.launch_matching(&application,"",&title).await?,
                        Err(e)=>return Err(e),
                    };
                    desktop.call(json!({"operation":"windowAction","action":"activate","window":handle})).await?;
                    Ok(Some(Value::Window(handle)))
                };
                if timeout==0 {operation.await?}else {tokio::time::timeout(std::time::Duration::from_millis(timeout),operation).await.map_err(|_|error(ErrorKind::Timeout,"等待应用窗口超时"))??}
            },
            "app.quit"=>{
                let mode=text(step,"mode",values)?;
                let window=if mode=="当前目标窗口" {Some(target(step,values)?)}else{None};
                desktop.call(json!({"operation":"applicationQuit","applicationId":text(step,"value",values)?,"mode":mode,"window":window})).await?;None
            },
            _=>unreachable!(),
        };Ok(output)
    }.await)
}
