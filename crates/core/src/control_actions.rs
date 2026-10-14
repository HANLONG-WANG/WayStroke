//! WayStroke actions use the same single-writer configuration API as the editor.
use tokio::process::Command;
use waystroke_model::{Step,Value};
use waystroke_protocol::{Error,ErrorKind,Reply,Snapshot,Commit,CORE_NAME,CORE_PATH,CORE_INTERFACE};
use crate::{error,flow::text,parameters::Values};
fn toggle(current:bool,operation:&str)->Result<bool,Error> {
    match operation {"启用"=>Ok(true),"暂停"|"停用"=>Ok(false),"切换"=>Ok(!current),_=>Err(error(ErrorKind::Validation,"未知启停操作"))}
}
pub async fn execute(step:&Step,values:&Values)->Option<Result<Option<Value>,Error>> {
    if !step.action.starts_with("waystroke."){return None;}
    Some(async {
        if step.action=="waystroke.open" {
            let page=match text(step,"value",values)?.as_str(){"手势规则"=>"rules","文本替换"=>"text","手势测试"=>"test","设置"=>"settings",_=>return Err(error(ErrorKind::Validation,"未知 WayStroke 页面"))};
            let path=std::env::current_exe().map_err(|e|error(ErrorKind::Io,e.to_string()))?.with_file_name("waystroke");
            let mut child=Command::new(path).args(["--page",page]).spawn().map_err(|e|error(ErrorKind::Io,e.to_string()))?;
            tokio::spawn(async move {if let Err(e)=child.wait().await {eprintln!("WayStroke window startup: {e}");}});
            return Ok(None);
        }
        let connection=zbus::Connection::session().await.map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
        let proxy=zbus::Proxy::new(&connection,CORE_NAME,CORE_PATH,CORE_INTERFACE).await.map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
        let reply:String=proxy.call("GetConfig",&()).await.map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
        let mut snapshot=match serde_json::from_str::<Reply<Snapshot>>(&reply).map_err(|e|error(ErrorKind::Internal,e.to_string()))? {Reply::Ok{value}=>value,Reply::Error{error}=>return Err(error)};
        let operation=text(step,"operation",values)?;
        match step.action.as_str() {
            "waystroke.toggle"=>match text(step,"value",values)?.as_str(){
                "手势"=>snapshot.config.settings.gestures_enabled=toggle(snapshot.config.settings.gestures_enabled,&operation)?,
                "文本替换"=>snapshot.config.settings.text_enabled=toggle(snapshot.config.settings.text_enabled,&operation)?,
                _=>return Err(error(ErrorKind::Validation,"未知 WayStroke 功能")),
            },
            "waystroke.rule"=>{
                let name=text(step,"value",values)?;
                let matches=snapshot.config.rules.iter().filter(|r|r.name==name).count();
                if matches!=1 {return Err(error(ErrorKind::Validation,if matches==0 {"指定规则不存在"}else{"存在同名规则，请先为规则设置唯一名称"}));}
                let rule=snapshot.config.rules.iter_mut().find(|r|r.name==name).unwrap();rule.enabled=toggle(rule.enabled,&operation)?;
            },
            _=>return Err(error(ErrorKind::Validation,"未知 WayStroke 操作")),
        }
        let commit=Commit{request_id:uuid::Uuid::new_v4().to_string(),expected_revision:snapshot.revision,config:snapshot.config};
        let reply:String=proxy.call("CommitConfig",&(serde_json::to_string(&commit).map_err(|e|error(ErrorKind::Internal,e.to_string()))?,)).await.map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
        match serde_json::from_str::<Reply<Snapshot>>(&reply).map_err(|e|error(ErrorKind::Internal,e.to_string()))? {Reply::Ok{..}=>Ok(None),Reply::Error{error}=>Err(error)}
    }.await)
}
