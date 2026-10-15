//! Fixed desktop setup operations. No arbitrary command, path or UID from the webview.
use std::{collections::HashMap,fs,path::{Path,PathBuf},os::unix::fs::{DirBuilderExt,PermissionsExt},process::Command};
use serde_json::{Value,json};
const UUID:&str="waystroke@local";
const FILES:&[(&str,&[u8])]=&[
    ("metadata.json",include_bytes!("../../../../extension/metadata.json")),
    ("extension.js",include_bytes!("../../../../extension/extension.js")),
    ("clipboard.js",include_bytes!("../../../../extension/clipboard.js")),
    ("dialogs.js",include_bytes!("../../../../extension/dialogs.js")),
    ("system.js",include_bytes!("../../../../extension/system.js")),
    ("text.js",include_bytes!("../../../../extension/text.js")),
    ("terminal.js",include_bytes!("../../../../extension/terminal.js")),
];
fn data_home()->Result<PathBuf,String>{
    if let Some(path)=std::env::var_os("XDG_DATA_HOME").filter(|p|Path::new(p).is_absolute()){return Ok(path.into())}
    Ok(PathBuf::from(std::env::var_os("HOME").ok_or("缺少用户主目录")?).join(".local/share"))
}
fn install_extension(base:&Path)->Result<(),String>{
    let path=base.join("gnome-shell/extensions").join(UUID);fs::create_dir_all(&path).map_err(|e|e.to_string())?;
    for (name,bytes) in FILES{fs::write(path.join(name),bytes).map_err(|e|e.to_string())?;}Ok(())
}
async fn extension()->Result<Value,String>{
    let connection=zbus::Connection::session().await.map_err(|e|e.to_string())?;
    let proxy=zbus::Proxy::new(&connection,"org.gnome.Shell.Extensions","/org/gnome/Shell/Extensions","org.gnome.Shell.Extensions").await.map_err(|e|e.to_string())?;
    let version:String=proxy.get_property("ShellVersion").await.map_err(|e|format!("无法读取 GNOME 版本：{e}"))?;
    if version!="50.5"{return Err(format!("需要 GNOME Shell 50.5，当前为 {version}"))}
    let info:HashMap<String,zbus::zvariant::OwnedValue>=proxy.call("GetExtensionInfo",&(UUID,)).await.map_err(|e|e.to_string())?;
    if info.is_empty(){
        install_extension(&data_home()?)?;
        // GNOME 50 cannot dynamically discover a previously unknown local extension.
        return Ok(json!({"message":"扩展文件已安装。GNOME 首次发现本地扩展需要重新登录；请保存工作后重新登录，再点击连接扩展。","restartRequired":true}));
    }
    let enabled:bool=proxy.get_property("UserExtensionsEnabled").await.map_err(|e|e.to_string())?;
    if !enabled{return Err("GNOME 已全局禁用用户扩展，请先在扩展应用中启用用户扩展后重试。".into())}
    let accepted:bool=proxy.call("EnableExtension",&(UUID,)).await.map_err(|e|e.to_string())?;
    if !accepted{return Err("GNOME 未能启用 WayStroke 扩展；请检查扩展错误后重试。".into())}
    Ok(json!({"message":"已请求 GNOME 启用 WayStroke 扩展，正在读取实际连接状态。","restartRequired":false}))
}
fn input()->Result<Value,String>{
    let binary=std::env::current_exe().map_err(|e|e.to_string())?.with_file_name("waystroke-inputd");
    if !binary.is_file(){return Err("缺少配套 waystroke-inputd，请安装完整应用或先构建鼠标服务。".into())}
    let stage=std::env::temp_dir().join(format!("waystroke-setup-{}-{}",std::process::id(),std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_err(|e|e.to_string())?.as_nanos()));
    fs::DirBuilder::new().mode(0o700).create(&stage).map_err(|e|e.to_string())?;
    let result=(||{
        fs::copy(&binary,stage.join("waystroke-inputd")).map_err(|e|e.to_string())?;
        fs::set_permissions(stage.join("waystroke-inputd"),fs::Permissions::from_mode(0o700)).map_err(|e|e.to_string())?;
        fs::write(stage.join("install.sh"),include_bytes!("../../../../packaging/setup-input.sh")).map_err(|e|e.to_string())?;
        fs::write(stage.join("waystroke-inputd.service"),include_bytes!("../../../../packaging/systemd/waystroke-inputd.service")).map_err(|e|e.to_string())?;
        let output=Command::new("pkexec").arg("/usr/bin/bash").arg(stage.join("install.sh")).output().map_err(|e|format!("无法请求管理员授权：{e}"))?;
        if !output.status.success(){return Err(match output.status.code(){Some(126)=>"管理员授权已取消，可以重试。".into(),Some(127)=>format!("管理员授权未通过：{}",String::from_utf8_lossy(&output.stderr).trim()),_=>format!("鼠标服务安装失败：{}",String::from_utf8_lossy(&output.stderr).trim())})}
        Ok(json!({"message":String::from_utf8_lossy(&output.stdout).trim(),"restartRequired":false}))
    })();
    if let Err(e)=fs::remove_dir_all(&stage){return Err(format!("安装临时文件清理失败：{e}"))}result
}
#[tauri::command]
pub async fn setup_operation(operation:String)->Result<Value,String>{
    match operation.as_str(){"extension"=>extension().await,"input"=>tauri::async_runtime::spawn_blocking(input).await.map_err(|e|e.to_string())?,_=>Err("不支持的接入操作".into())}
}
#[cfg(test)]
mod tests{
    use super::*;
    #[test]fn installs_current_extension_resources(){let root=std::env::temp_dir().join(format!("waystroke-extension-test-{}",std::process::id()));install_extension(&root).unwrap();for(name,bytes)in FILES{assert_eq!(fs::read(root.join("gnome-shell/extensions").join(UUID).join(name)).unwrap(),*bytes);}fs::remove_dir_all(root).unwrap();}
}
