//! Configuration writes are serialized here, never in the desktop webview.
pub mod configuration;
pub mod session;
pub mod gesture;
pub mod text;
pub mod atspi;
pub mod xselection;
mod atspi_input;
pub mod input;
pub mod desktop;
pub mod runtime;
pub mod execution;
pub mod parameters;
pub mod data_actions;
pub mod flow;
pub mod io_actions;
pub mod dbus_actions;
pub mod control_actions;
pub mod window_actions;
pub mod input_actions;
pub mod system_actions;
pub mod capabilities;
use std::{fs, io::Write, path::{Path,PathBuf}};
use std::os::unix::fs::{OpenOptionsExt,PermissionsExt};
use waystroke_model::validate;
use waystroke_protocol::{Commit,Snapshot,Error,ErrorKind};

pub struct Repository { path:PathBuf, snapshot:Snapshot, backup_path:PathBuf, inspection:Option<configuration::Inspection>, autostart:Option<session::Autostart> }
impl Repository {
    pub fn open(path:PathBuf)->Result<Self,Error> {
        let snapshot=if path.exists() { serde_json::from_slice(&fs::read(&path).map_err(io_error)?).map_err(|e|error(ErrorKind::Validation,format!("配置无法读取：{e}")))? } else { Snapshot::default() };
        let errors=validate(&snapshot.config);
        if !errors.is_empty() { return Err(Error{kind:ErrorKind::Validation,message:"配置校验失败，原文件保持不变".into(),details:errors}); }
        Ok(Self{path,snapshot,backup_path:configuration::state_path()?,inspection:None,autostart:None})
    }
    pub fn attach_autostart(&mut self,autostart:session::Autostart)->Result<(),Error>{
        let desired=autostart.content(&self.snapshot.config.settings)?;
        if autostart.read()?!=desired {autostart.write(desired.as_deref())?;}
        self.autostart=Some(autostart);Ok(())
    }
    pub fn snapshot(&self)->Snapshot { self.snapshot.clone() }
    pub fn commit(&mut self,request:Commit)->Result<Snapshot,Error> {
        if request.expected_revision!=self.snapshot.revision { return Err(error(ErrorKind::Conflict,"配置已改变，请保留草稿并重新加载")); }
        let details=validate(&request.config);
        if !details.is_empty() { return Err(Error{kind:ErrorKind::Validation,message:"配置校验失败".into(),details}); }
        let revision=self.snapshot.revision.checked_add(1).ok_or_else(||error(ErrorKind::Internal,"配置版本计数已耗尽"))?;
        let next=Snapshot{revision,saved_at:Some(chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Millis,true)),config:request.config};
        let bytes=serde_json::to_vec_pretty(&next).map_err(|e|error(ErrorKind::Internal,e.to_string()))?;
        let login_changed=self.snapshot.config.settings.autostart!=next.config.settings.autostart||self.snapshot.config.settings.setup_complete!=next.config.settings.setup_complete;
        let previous=if login_changed {if let Some(login)=&self.autostart{let previous=login.read()?;login.write(login.content(&next.config.settings)?.as_deref())?;Some(previous)}else{None}}else{None};
        if let Err(failure)=write_atomic(&self.path,&bytes){
            if let (Some(login),Some(previous))=(&self.autostart,previous){if let Err(rollback)=login.write(previous.as_deref()){return Err(error(ErrorKind::Io,format!("{}；登录启动恢复失败：{}",failure.message,rollback.message)))}}
            return Err(failure)
        }
        self.snapshot=next;
        Ok(self.snapshot())
    }
}
pub fn config_path()->Result<PathBuf,Error> {
    let base=match std::env::var_os("XDG_CONFIG_HOME") {
        Some(p) if Path::new(&p).is_absolute()=>PathBuf::from(p),
        _=>PathBuf::from(std::env::var_os("HOME").ok_or_else(||error(ErrorKind::Io,"缺少用户主目录"))?).join(".config"),
    };
    Ok(base.join("waystroke/config.json"))
}
fn write_atomic(path:&Path,bytes:&[u8])->Result<(),Error> {
    let parent=path.parent().ok_or_else(||error(ErrorKind::Io,"配置路径没有父目录"))?;
    fs::create_dir_all(parent).map_err(io_error)?;
    fs::set_permissions(parent,fs::Permissions::from_mode(0o700)).map_err(io_error)?;
    let temp=parent.join(format!(".config-{}.tmp",std::process::id()));
    let result=(|| {
        let mut file=fs::OpenOptions::new().write(true).create_new(true).mode(0o600).open(&temp)?;
        file.write_all(bytes)?; file.sync_all()?;
        fs::rename(&temp,path)?;
        fs::File::open(parent)?.sync_all()?;
        Ok::<_,std::io::Error>(())
    })();
    if result.is_err() { let _=fs::remove_file(&temp); }
    result.map_err(io_error)
}
pub fn error(kind:ErrorKind,message:impl Into<String>)->Error { Error{kind,message:message.into(),details:vec![]} }
fn io_error(e:std::io::Error)->Error { error(ErrorKind::Io,e.to_string()) }

#[cfg(test)]
mod tests {
    use super::*;
    use waystroke_model::Config;
    #[test]
    fn saved_revision_survives_restart_and_failed_changes_preserve_file() {
        let dir=std::env::temp_dir().join(format!("waystroke-config-test-{}",std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        let path=dir.join("config.json");
        let mut repo=Repository::open(path.clone()).unwrap();
        let mut config=Config::default();config.settings.feedback=false;
        let request=Commit{request_id:"test".into(),expected_revision:0,config:config.clone()};
        assert_eq!(repo.commit(request.clone()).unwrap().revision,1);
        let before=fs::read(&path).unwrap();
        assert!(matches!(repo.commit(request).unwrap_err().kind,ErrorKind::Conflict));
        config.settings.similarity=200.;
        assert!(matches!(repo.commit(Commit{request_id:"bad".into(),expected_revision:1,config}).unwrap_err().kind,ErrorKind::Validation));
        assert_eq!(fs::read(&path).unwrap(),before);
        let blocked_temp=dir.join(format!(".config-{}.tmp",std::process::id()));
        fs::create_dir(&blocked_temp).unwrap();
        let failed=repo.commit(Commit{request_id:"io-failure".into(),expected_revision:1,config:Config::default()});
        fs::remove_dir(blocked_temp).unwrap();
        assert!(matches!(failed.unwrap_err().kind,ErrorKind::Io));
        assert_eq!(repo.snapshot().revision,1);
        assert_eq!(fs::read(&path).unwrap(),before);
        let restarted=Repository::open(path).unwrap();
        assert_eq!(restarted.snapshot().revision,1);
        assert!(!restarted.snapshot().config.settings.feedback);
        fs::remove_dir_all(dir).unwrap();
    }
}
