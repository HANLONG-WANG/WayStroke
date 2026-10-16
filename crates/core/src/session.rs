//! The login preference takes effect only after explicit setup completion.
use std::{fs,path::PathBuf};
use waystroke_model::Settings;
use waystroke_protocol::{Error,ErrorKind};
use crate::{error,io_error,write_atomic};
pub struct Autostart {pub path:PathBuf,pub executable:PathBuf}
impl Autostart {
    pub fn content(&self,settings:&Settings)->Result<Option<Vec<u8>>,Error>{
        if !settings.setup_complete||!settings.autostart{return Ok(None)}
        let executable=self.executable.to_str().ok_or_else(||error(ErrorKind::Io,"登录启动路径不是有效文本"))?;
        if executable.contains(['\n','\r','=']){return Err(error(ErrorKind::Io,"登录启动路径含不支持的字符"))}
        // Desktop Entry Specification, Exec key: quote arguments, then escape string values.
        // https://specifications.freedesktop.org/desktop-entry-spec/latest/exec-variables.html
        let quoted=executable.replace('\\',"\\\\").replace('"',"\\\"").replace('`',"\\`").replace('$',"\\$").replace('%',"%%");
        let quoted=quoted.replace('\\',"\\\\");
        let launch=if self.executable == std::path::Path::new("/usr/bin/waystroke-core") {
            "/usr/bin/systemctl --user start waystroke-core.service".to_string()
        } else {format!("\"{quoted}\"")};
        Ok(Some(format!("[Desktop Entry]\nType=Application\nName=WayStroke\nExec={launch}\nTryExec={quoted}\nOnlyShowIn=GNOME;\nTerminal=false\nNoDisplay=true\nX-GNOME-Autostart-enabled=true\n").into_bytes()))
    }
    pub fn read(&self)->Result<Option<Vec<u8>>,Error>{match fs::read(&self.path){Ok(bytes)=>Ok(Some(bytes)),Err(e) if e.kind()==std::io::ErrorKind::NotFound=>Ok(None),Err(e)=>Err(io_error(e))}}
    pub fn write(&self,content:Option<&[u8]>)->Result<(),Error>{
        match content{Some(bytes)=>write_atomic(&self.path,bytes),None=>match fs::remove_file(&self.path){Ok(())=>fs::File::open(self.path.parent().expect("autostart parent")).and_then(|f|f.sync_all()).map_err(io_error),Err(e) if e.kind()==std::io::ErrorKind::NotFound=>Ok(()),Err(e)=>Err(io_error(e))}}
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::Repository;
    use waystroke_protocol::Commit;
    #[test]
    fn setup_gates_login_and_failed_save_rolls_it_back(){
        let root=std::env::temp_dir().join(format!("waystroke-login-{}",uuid::Uuid::new_v4()));let path=root.join("waystroke/config.json");
        let login=root.join("autostart/waystroke.desktop");let mut repo=Repository::open(path.clone()).unwrap();
        repo.attach_autostart(Autostart{path:login.clone(),executable:PathBuf::from("/usr/bin/waystroke-core")}).unwrap();assert!(!login.exists());
        let mut config=repo.snapshot().config;config.settings.setup_complete=true;
        repo.commit(Commit{request_id:"setup".into(),expected_revision:0,config:config.clone()}).unwrap();assert!(fs::read_to_string(&login).unwrap().contains("Exec=/usr/bin/systemctl --user start waystroke-core.service"));
        config.settings.autostart=false;repo.commit(Commit{request_id:"off".into(),expected_revision:1,config:config.clone()}).unwrap();assert!(!login.exists());let before=fs::read(&path).unwrap();
        let blocked=root.join(format!("waystroke/.config-{}.tmp",std::process::id()));fs::create_dir(&blocked).unwrap();
        config.settings.autostart=true;assert!(repo.commit(Commit{request_id:"failure".into(),expected_revision:2,config:config.clone()}).is_err());assert!(!login.exists());assert_eq!(fs::read(&path).unwrap(),before);assert_eq!(repo.snapshot().revision,2);fs::remove_dir(&blocked).unwrap();
        fs::write(root.join("not-a-directory"),b"blocked").unwrap();repo.autostart.as_mut().unwrap().path=root.join("not-a-directory/waystroke.desktop");
        assert!(repo.commit(Commit{request_id:"login-failure".into(),expected_revision:2,config}).is_err());assert_eq!(fs::read(&path).unwrap(),before);fs::remove_dir_all(root).unwrap();
    }
}
