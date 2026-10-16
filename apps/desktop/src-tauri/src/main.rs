mod setup;
mod rendering;
use futures_util::StreamExt;
use std::{process::{Command,Stdio},time::Duration};
use tauri::{Emitter,Manager};
use waystroke_protocol::{CORE_NAME,CORE_PATH,CORE_INTERFACE};
use zbus::names::OwnedBusName;

#[tauri::command]
fn default_config()->String { serde_json::to_string(&waystroke_protocol::Snapshot::default()).expect("default snapshot") }

fn requested_page(args:&[String])->Option<String> {
    args.windows(2).find(|pair|pair[0]=="--page" && ["rules","text","test","settings"].contains(&pair[1].as_str())).map(|pair|pair[1].clone())
}
#[tauri::command]
fn launch_page()->Option<String> {requested_page(&std::env::args().collect::<Vec<_>>())}

#[tauri::command]
fn list_applications()->Vec<serde_json::Value> {
    use gtk::gio::prelude::*;
    let mut apps=gtk::gio::AppInfo::all().into_iter().filter(|app|app.should_show())
        .filter_map(|app|app.id().map(|id|serde_json::json!({"id":id.as_str(),"name":app.display_name().as_str()}))).collect::<Vec<_>>();
    apps.sort_by(|a,b|a["id"].as_str().cmp(&b["id"].as_str()));
    apps.dedup_by(|a,b|a["id"]==b["id"]);
    apps
}

static CORE_CONNECTION:tokio::sync::OnceCell<zbus::Connection>=tokio::sync::OnceCell::const_new();
#[tauri::command]
async fn core_call(method:String,payload:String)->Result<String,String> {
    let connection=CORE_CONNECTION.get_or_try_init(zbus::Connection::session).await.map_err(|e|e.to_string())?;
    let proxy=zbus::Proxy::new(connection,CORE_NAME,CORE_PATH,CORE_INTERFACE).await.map_err(|e|e.to_string())?;
    let result:zbus::Result<String>=match method.as_str() {
        "configuration"=>proxy.call("Configuration",&(payload,)).await,
        "export_diagnostics"=>proxy.call("ExportDiagnostics",&()).await,
        "get_config"=>proxy.call("GetConfig",&()).await,
        "validate_document"=>proxy.call("ValidateDocument",&(payload,)).await,
        "commit_config"=>proxy.call("CommitConfig",&(payload,)).await,
        "get_action_capabilities"=>proxy.call("GetActionCapabilities",&()).await,
        "get_runtime"=>proxy.call("GetRuntime",&()).await,
        "list_devices"=>proxy.call("ListDevices",&()).await,
        "list_windows"=>proxy.call("ListWindows",&()).await,
        "get_context"=>proxy.call("GetContext",&()).await,
        "run_rule"=>proxy.call("RunRule",&(payload,)).await,
        "runtime_control"=>proxy.call("RuntimeControl",&(payload,)).await,
        "compare_strokes"=>proxy.call("CompareStrokes",&(payload,)).await,
        "test_text_rule"=>proxy.call("TestTextRule",&(payload,)).await,
        "recognize_stroke"=>proxy.call("RecognizeStroke",&(payload,)).await,
        "get_status"=>proxy.call("GetStatus",&()).await,
        "quit"=>proxy.call("Quit",&()).await,
        _=>return Err("不支持的本地操作".into()),
    };
    result.map_err(|e|e.to_string())
}
/// The desktop owns file selection; the webview cannot select an output path.
#[tauri::command]
async fn save_file(app:tauri::AppHandle,content:String,name:String)->Result<bool,String>{
    let (sender,receiver)=tokio::sync::oneshot::channel();let handle=app.clone();
    app.run_on_main_thread(move ||{
        use gtk::prelude::*;
        let window=match handle.get_webview_window("main").ok_or("设置窗口已关闭".to_string()).and_then(|window|window.gtk_window().map_err(|e|e.to_string())){
            Ok(window)=>window,Err(error)=>{let _=sender.send(Err(error));return;},
        };
        let dialog=gtk::FileChooserDialog::new(Some("保存 WayStroke 文件"),Some(&window),gtk::FileChooserAction::Save);
        dialog.add_buttons(&[("取消",gtk::ResponseType::Cancel),("保存",gtk::ResponseType::Accept)]);
        dialog.set_modal(true);dialog.set_destroy_with_parent(true);dialog.set_do_overwrite_confirmation(true);dialog.set_default_response(gtk::ResponseType::Accept);
        dialog.set_current_name(match name.as_str(){"diagnostics"=>"waystroke-diagnostics.json","backup"=>"waystroke-backup.json",_=>"waystroke-config.json"});
        let filter=gtk::FileFilter::new();filter.set_name(Some("JSON"));filter.add_pattern("*.json");dialog.add_filter(filter);
        let sender=std::cell::RefCell::new(Some(sender));
        dialog.connect_response(move |dialog,response|{
            let result=if response==gtk::ResponseType::Accept{dialog.filename().map(Some).ok_or("没有选择保存位置".to_string())}else{Ok(None)};
            let reply=sender.borrow_mut().take();
            // No child widgets or references escape this main-thread dialog.
            unsafe{dialog.destroy();}if let Some(reply)=reply{let _=reply.send(result);}
        });
        dialog.show_all();
    }).map_err(|e|e.to_string())?;
    let Some(path)=receiver.await.map_err(|_|"文件对话框已关闭")?? else{return Ok(false)};
    tauri::async_runtime::spawn_blocking(move ||{
        let parent=path.parent().ok_or("保存路径没有父目录")?;
        use std::io::Write;use std::os::unix::fs::OpenOptionsExt;
        let temporary=parent.join(format!(".waystroke-export-{}.tmp",std::process::id()));
        let result=(||{let mut file=std::fs::OpenOptions::new().write(true).create_new(true).mode(0o600).open(&temporary)?;file.write_all(content.as_bytes())?;file.sync_all()?;std::fs::rename(&temporary,&path)?;std::fs::File::open(parent)?.sync_all()})();
        if result.is_err(){let _=std::fs::remove_file(&temporary);}result.map_err(|e:std::io::Error|e.to_string())?;Ok(true)
    }).await.map_err(|e|e.to_string())?
}
async fn ensure_core()->Result<(),Box<dyn std::error::Error>> {
    let connection=zbus::Connection::session().await?;
    let dbus=zbus::fdo::DBusProxy::new(&connection).await?;
    let name=OwnedBusName::try_from(CORE_NAME)?;
    if dbus.name_has_owner(name.clone().into()).await? { return Ok(()) }
    let path=std::env::current_exe()?.with_file_name("waystroke-core");
    if path == std::path::Path::new("/usr/bin/waystroke-core") {
        dbus.start_service_by_name(zbus::names::WellKnownName::try_from(CORE_NAME)?, 0).await?;
    } else {
    Command::new(path).stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::inherit()).spawn()?;
    }
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
        .plugin(tauri_plugin_single_instance::init(|app,args,_| {
            if let Some(page)=requested_page(&args) {let _=app.emit("navigate-request",page);}
            if let Some(w)=app.get_webview_window("main") {
                // xdg-shell has no unminimize request; GTK deiconify alone does not
                // restore a minimized surface on GNOME Wayland. Remap this same
                // window before presenting it, preserving its editor/webview.
                let _=w.hide();
                let _=w.show();let _=w.unminimize();let _=w.set_focus();
            }
        }))
        .setup(|app| {
            app.get_webview_window("main").expect("main window")
                .with_webview(|webview| rendering::configure(&webview.inner()))?;
            if let Err(e)=tauri::async_runtime::block_on(ensure_core()) { eprintln!("WayStroke: {e}"); }
            let handle=app.handle().clone();
            tauri::async_runtime::spawn(async move {
                let subscription=async {
                    let connection=zbus::Connection::session().await?;
                    let proxy=zbus::Proxy::new(&connection,CORE_NAME,CORE_PATH,CORE_INTERFACE).await?;
                    let dbus=zbus::fdo::DBusProxy::new(&connection).await?;
                    let mut config=proxy.receive_signal("ConfigChanged").await?;
                    let mut runtime=proxy.receive_signal("RuntimeChanged").await?;
                    let mut owners=dbus.receive_name_owner_changed().await?;
                    loop {
                        tokio::select! {
                            message=config.next()=>match message {
                                Some(m)=>{let (snapshot,):(String,)=m.body().deserialize()?;let _=handle.emit("config-changed",snapshot);},
                                None=>break,
                            },
                            message=runtime.next()=>match message {
                                Some(m)=>{let (event,):(String,)=m.body().deserialize()?;let _=handle.emit("runtime-changed",event);},
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
        .invoke_handler(tauri::generate_handler![core_call,default_config,launch_page,list_applications,save_file,setup::setup_operation])
        .run(tauri::generate_context!()).expect("WayStroke desktop startup failed");
}
