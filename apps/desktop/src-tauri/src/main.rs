use futures_util::StreamExt;
use std::{process::{Command,Stdio},time::Duration};
use tauri::{Emitter,Manager};
use waystroke_protocol::{CORE_NAME,CORE_PATH,CORE_INTERFACE};
use zbus::names::OwnedBusName;

#[tauri::command]
fn default_config()->String { serde_json::to_string(&waystroke_protocol::Snapshot::default()).expect("default snapshot") }

#[tauri::command]
async fn core_call(method:String,payload:String)->Result<String,String> {
    let connection=zbus::Connection::session().await.map_err(|e|e.to_string())?;
    let proxy=zbus::Proxy::new(&connection,CORE_NAME,CORE_PATH,CORE_INTERFACE).await.map_err(|e|e.to_string())?;
    let result:zbus::Result<String>=match method.as_str() {
        "get_config"=>proxy.call("GetConfig",&()).await,
        "validate_document"=>proxy.call("ValidateDocument",&(payload,)).await,
        "commit_config"=>proxy.call("CommitConfig",&(payload,)).await,
        "get_status"=>proxy.call("GetStatus",&()).await,
        "quit"=>proxy.call("Quit",&()).await,
        _=>return Err("不支持的本地操作".into()),
    };
    result.map_err(|e|e.to_string())
}
async fn ensure_core()->Result<(),Box<dyn std::error::Error>> {
    let connection=zbus::Connection::session().await?;
    let dbus=zbus::fdo::DBusProxy::new(&connection).await?;
    let name=OwnedBusName::try_from(CORE_NAME)?;
    if dbus.name_has_owner(name.clone().into()).await? { return Ok(()) }
    let path=std::env::current_exe()?.with_file_name("waystroke-core");
    Command::new(path).stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::inherit()).spawn()?;
    for _ in 0..30 { if dbus.name_has_owner(name.clone().into()).await? { return Ok(()) } tokio::time::sleep(Duration::from_millis(100)).await; }
    Err("后台未能启动，请查看启动错误".into())
}
fn main() {
    // Set before GTK starts or any application worker threads are created.
    unsafe {
        std::env::set_var("GDK_BACKEND","wayland");
        // Verified on this host: WebKitGTK fails Wayland explicit sync with NVIDIA.
        // Keep compositing/DMABUF enabled and honor an explicit user override.
        if std::path::Path::new("/sys/module/nvidia").exists() && std::env::var_os("__NV_DISABLE_EXPLICIT_SYNC").is_none() {
            std::env::set_var("__NV_DISABLE_EXPLICIT_SYNC","1");
        }
    }
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app,_,_| {
            if let Some(w)=app.get_webview_window("main") {
                // xdg-shell has no unminimize request; GTK deiconify alone does not
                // restore a minimized surface on GNOME Wayland. Remap this same
                // window before presenting it, preserving its editor/webview.
                let _=w.hide();
                let _=w.show();let _=w.unminimize();let _=w.set_focus();
            }
        }))
        .setup(|app| {
            if let Err(e)=tauri::async_runtime::block_on(ensure_core()) { eprintln!("WayStroke: {e}"); }
            let handle=app.handle().clone();
            tauri::async_runtime::spawn(async move {
                let subscription=async {
                    let connection=zbus::Connection::session().await?;
                    let proxy=zbus::Proxy::new(&connection,CORE_NAME,CORE_PATH,CORE_INTERFACE).await?;
                    let dbus=zbus::fdo::DBusProxy::new(&connection).await?;
                    let mut config=proxy.receive_signal("ConfigChanged").await?;
                    let mut owners=dbus.receive_name_owner_changed().await?;
                    loop {
                        tokio::select! {
                            message=config.next()=>match message {
                                Some(m)=>{let (snapshot,):(String,)=m.body().deserialize()?;let _=handle.emit("config-changed",snapshot);},
                                None=>break,
                            },
                            message=owners.next()=>match message {
                                Some(m)=>{let args=m.args()?;if args.name.as_str()==CORE_NAME { let _=handle.emit("core-connected",args.new_owner.is_some()); }},
                                None=>break,
                            },
                        }
                    }
                    Ok::<(),zbus::Error>(())
                }.await;
                if let Err(error)=subscription { eprintln!("WayStroke event subscription: {error}"); }
                let _=handle.emit("core-connected",false);
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![core_call,default_config])
        .run(tauri::generate_context!()).expect("WayStroke desktop startup failed");
}
