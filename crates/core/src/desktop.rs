//! Same-session GNOME adapter; all effects remain in the ordinary user session.
use serde_json::{Value,json};
use futures_util::StreamExt;
use waystroke_protocol::{Reply,Error,ErrorKind,START_BINDING_MS};
use crate::error;
#[derive(Clone)]
pub struct Desktop { connection:zbus::Connection }
impl Desktop {
    pub fn new(connection:zbus::Connection)->Self{Self{connection}}
    pub async fn call(&self,request:Value)->Result<Value,Error> {
        let proxy=zbus::Proxy::new(&self.connection,"io.github.waystroke.Gnome","/io/github/waystroke/Gnome","io.github.waystroke.Gnome1").await.map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
        let text:String=proxy.call("Call",&(request.to_string(),)).await.map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
        match serde_json::from_str::<Reply<Value>>(&text).map_err(|e|error(ErrorKind::Unavailable,format!("桌面协议错误：{e}")))? {Reply::Ok{value}=>Ok(value),Reply::Error{error}=>Err(error)}
    }
    pub async fn locked(&self)->Result<bool,Error>{
        let proxy=zbus::Proxy::new(&self.connection,"org.gnome.ScreenSaver","/org/gnome/ScreenSaver","org.gnome.ScreenSaver").await.map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
        proxy.call("GetActive",&()).await.map_err(|e|error(ErrorKind::Unavailable,e.to_string()))
    }
    /// Subscribe before initiating a clipboard transaction, then query cached
    /// progress on actual selection events. No fixed delay guesses paste readiness.
    pub async fn clipboard_transaction(&self,start:Value,paste:bool,timeout:u64)->Result<Value,Error> {
        let proxy=zbus::Proxy::new(&self.connection,"io.github.waystroke.Gnome","/io/github/waystroke/Gnome","io.github.waystroke.Gnome1").await.map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
        let mut events=proxy.receive_signal("Changed").await.map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
        let started=self.call(start).await?;
        let request=if paste {json!({"operation":"clipboardPasteStatus","token":started["token"]})}else{json!({"operation":"clipboardCopyResult","version":started["version"]})};
        let operation=async {
            loop {
                let result=self.call(request.clone()).await?;
                if if paste {result["read"]==true}else{result["changed"]==true} {return Ok(result);}
                if events.next().await.is_none(){return Err(error(ErrorKind::Unavailable,"剪贴板事件连接中断"));}
            }
        };
        let result=if timeout==0 {operation.await}else{tokio::time::timeout(std::time::Duration::from_millis(timeout),operation).await.map_err(|_|error(ErrorKind::Timeout,if paste {"目标应用没有读取粘贴内容"}else{"未获取到新的选中文本；未使用旧剪贴板"}))?};
        if paste {self.call(json!({"operation":"clipboardPasteFinish","token":started["token"]})).await?;}
        result
    }
    pub async fn launch_window(&self,application_id:&str)->Result<waystroke_model::WindowHandle,Error> {self.launch_window_arguments(application_id,"").await}
    pub async fn launch_window_arguments(&self,application_id:&str,arguments:&str)->Result<waystroke_model::WindowHandle,Error> {self.launch_matching(application_id,arguments,"").await}
    pub async fn launch_matching(&self,application_id:&str,arguments:&str,title:&str)->Result<waystroke_model::WindowHandle,Error> {
        self.launch_matching_window(application_id,arguments,title,false).await
    }
    pub async fn launch_matching_window(&self,application_id:&str,arguments:&str,title:&str,new_window:bool)->Result<waystroke_model::WindowHandle,Error> {
        let proxy=zbus::Proxy::new(&self.connection,"io.github.waystroke.Gnome","/io/github/waystroke/Gnome","io.github.waystroke.Gnome1").await.map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
        let mut signals=proxy.receive_signal("Changed").await.map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
        let previous=if new_window {self.call(json!({"operation":"windows"})).await?.as_array().map(|windows|windows.iter().map(|window|window["handle"].clone()).collect::<Vec<_>>()).unwrap_or_default()}else{vec![]};
        let launched=self.call(json!({"operation":"launch","applicationId":application_id,"arguments":arguments,"newWindow":new_window})).await?;
        let app=launched["applicationId"].as_str().unwrap_or(application_id);
        let find=|windows:Value|->Result<Option<waystroke_model::WindowHandle>,Error>{
            let window=windows.as_array().and_then(|windows|windows.iter().find(|window|window["applicationId"]==app&&window["title"].as_str().is_some_and(|value|value.contains(title))&&!previous.contains(&window["handle"])));
            window.map(|window|serde_json::from_value(window["handle"].clone()).map_err(|e|error(ErrorKind::Unavailable,e.to_string()))).transpose()
        };
        if let Some(window)=find(self.call(json!({"operation":"windows"})).await?)?{return Ok(window);}
        tokio::time::timeout(std::time::Duration::from_secs(5),async {
            while signals.next().await.is_some(){if let Some(window)=find(self.call(json!({"operation":"windows"})).await?)?{return Ok(window);}}
            Err(error(ErrorKind::Unavailable,"应用启动后桌面事件连接中断"))
        }).await.map_err(|_|error(ErrorKind::Timeout,"应用已请求启动，但没有出现可返回的窗口"))?
    }
    pub async fn wait_devices(&self,lease_id:&str)->Result<(),Error> {
        let proxy=zbus::Proxy::new(&self.connection,"io.github.waystroke.Gnome","/io/github/waystroke/Gnome","io.github.waystroke.Gnome1").await.map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
        let mut signals=proxy.receive_signal("Changed").await.map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
        let request=json!({"operation":"devicesReady","leaseId":lease_id});
        if self.call(request.clone()).await?==true{return Ok(());}
        tokio::time::timeout(std::time::Duration::from_secs(2),async {
            while let Some(message)=signals.next().await{
                let (text,):(String,)=message.body().deserialize().map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
                let event:Value=serde_json::from_str(&text).map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
                if event["event"]=="deviceAdded"&&self.call(request.clone()).await?==true{return Ok(());}
            }Err(error(ErrorKind::Unavailable,"合成设备就绪事件连接中断"))
        }).await.map_err(|_|error(ErrorKind::Timeout,"合成设备未被桌面发现，未接管鼠标"))?
    }
    pub async fn wait_barrier(&self,lease_id:&str,ordinal:u32)->Result<Value,Error> {
        let proxy=zbus::Proxy::new(&self.connection,"io.github.waystroke.Gnome","/io/github/waystroke/Gnome","io.github.waystroke.Gnome1").await.map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
        // Subscribe before checking the cache, so marker/notification races do
        // not become a fixed sleep or miss a previously completed barrier.
        let mut signals=proxy.receive_signal("Changed").await.map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
        let request=json!({"operation":"barrierSnapshot","leaseId":lease_id,"ordinal":ordinal});
        match self.call(request.clone()).await {Ok(value)=>return Ok(value),Err(e) if matches!(e.kind,ErrorKind::Timeout)=>{},Err(e)=>return Err(e)}
        tokio::time::timeout(std::time::Duration::from_millis(START_BINDING_MS.into()),async {
            while let Some(message)=signals.next().await {
                let (text,):(String,)=message.body().deserialize().map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
                let signal:Value=serde_json::from_str(&text).map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
                if signal["event"]=="barrier"&&signal["leaseId"]==lease_id&&signal["ordinal"]==ordinal{return self.call(request).await;}
            }
            Err(error(ErrorKind::Unavailable,"桌面事件订阅已断开"))
        }).await.map_err(|_|error(ErrorKind::Timeout,"合成器未确认输入屏障，释放鼠标"))?
    }
    pub async fn hello(&self)->Result<Value,Error> {
        let value=self.call(json!({"operation":"hello"})).await?;
        if value["protocolVersion"]!=1||value["shellVersion"]!="50.5" {return Err(error(ErrorKind::Unavailable,"桌面扩展版本不兼容"));}Ok(value)
    }
}
