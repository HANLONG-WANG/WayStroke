//! Ordinary-user I/O actions. Dropping a waited command kills its own process group.
use std::{collections::BTreeMap, path::{Path,PathBuf}, process::Stdio, time::Duration};
use tokio::{fs,io::AsyncWriteExt,process::Command};
use waystroke_model::{Step,Value};
use waystroke_protocol::{Error,ErrorKind};
use crate::{error,flow::{text,integer},parameters::Values};
fn io(e:std::io::Error)->Error {error(if e.kind()==std::io::ErrorKind::PermissionDenied {ErrorKind::Permission}else{ErrorKind::Io},e.to_string())}
fn data(fields:impl IntoIterator<Item=(&'static str,Value)>)->Value {Value::Data(fields.into_iter().map(|(k,v)|(k.into(),v)).collect())}
fn encoding(label:&str)->Result<&'static encoding_rs::Encoding,Error> {
    encoding_rs::Encoding::for_label(label.as_bytes()).ok_or_else(||error(ErrorKind::Validation,format!("不支持编码 {label}")))
}
struct CommandGroup(Option<u32>);
impl Drop for CommandGroup {
    fn drop(&mut self) {if let Some(pid)=self.0 {if let Err(e)=nix::sys::signal::killpg(nix::unistd::Pid::from_raw(pid as i32),nix::sys::signal::Signal::SIGKILL) {if e!=nix::errno::Errno::ESRCH {eprintln!("command cleanup: {e}");}}}}
}
async fn command(step:&Step,values:&Values)->Result<Value,Error> {
    let mode=text(step,"mode",values)?;
    let executable=text(step,"value",values)?;
    let mut command=if mode=="通过 Shell 运行" {
        let mut command=Command::new("/bin/sh");command.args(["-c",&executable]);command
    }else if mode=="直接启动程序" {
        if executable.is_empty() {return Err(error(ErrorKind::Validation,"命令不能为空"));}
        let mut command=Command::new(&executable);
        command.args(shell_words::split(&text(step,"arguments",values)?).map_err(|e|error(ErrorKind::Validation,format!("命令参数引号错误：{e}")))?);command
    }else {return Err(error(ErrorKind::Validation,"未知命令运行方式"));};
    let directory=text(step,"directory",values)?;if !directory.is_empty(){command.current_dir(directory);}
    for line in text(step,"environment",values)?.lines().filter(|line|!line.trim().is_empty()) {
        let (key,value)=line.split_once('=').ok_or_else(||error(ErrorKind::Validation,"环境变量应为名称=值"))?;
        if key.is_empty(){return Err(error(ErrorKind::Validation,"环境变量名称不能为空"));}
        command.env(key.trim(),value);
    }
    command.process_group(0);
    command.stdin(Stdio::null());
    let wait=match text(step,"waitExit",values)?.as_str(){"是"=>true,"否"=>false,_=>return Err(error(ErrorKind::Validation,"等待结束应为是或否"))};
    if wait {command.stdout(Stdio::piped()).stderr(Stdio::piped()).kill_on_drop(true);}else {command.stdout(Stdio::null()).stderr(Stdio::null());}
    let child=command.spawn().map_err(io)?;let pid=child.id().ok_or_else(||error(ErrorKind::Io,"命令未获得进程 ID"))?;
    if !wait {
        tokio::spawn(async move {let mut child=child;if let Err(e)=child.wait().await {eprintln!("background command: {e}");}});
        return Ok(data([("pid",Value::Number(pid as f64)),("exitCode",Value::Null),("stdout",Value::Text(String::new())),("stderr",Value::Text(String::new()))]));
    }
    let mut group=CommandGroup(Some(pid));
    let timeout=integer(step,"timeout",values)?;
    let output=if timeout==0 {child.wait_with_output().await.map_err(io)?}else {
        tokio::time::timeout(Duration::from_millis(timeout),child.wait_with_output()).await.map_err(|_|error(ErrorKind::Timeout,"命令执行超时"))?.map_err(io)?
    };
    group.0=None;
    let stdout=String::from_utf8(output.stdout).map_err(|e|error(ErrorKind::Io,format!("标准输出不是 UTF-8：{e}")))?;
    let stderr=String::from_utf8(output.stderr).map_err(|e|error(ErrorKind::Io,format!("标准错误不是 UTF-8：{e}")))?;
    // Nonzero exits are data for an explicit branch, not an invented successful exit code.
    Ok(data([("pid",Value::Number(pid as f64)),("exitCode",output.status.code().map(|n|Value::Number(n as f64)).unwrap_or(Value::Null)),("stdout",Value::Text(stdout)),("stderr",Value::Text(stderr))]))
}
async fn remove(path:&Path)->Result<(),Error> {
    let info=fs::symlink_metadata(path).await.map_err(io)?;
    if info.is_dir(){fs::remove_dir_all(path).await.map_err(io)}else{fs::remove_file(path).await.map_err(io)}
}
async fn destination(source:&Path,path:PathBuf,policy:&str)->Result<PathBuf,Error> {
    if source==path {return Err(error(ErrorKind::Validation,"源路径和目标路径不能相同"));}
    let exists=match fs::symlink_metadata(&path).await {Ok(_)=>true,Err(e) if e.kind()==std::io::ErrorKind::NotFound=>false,Err(e)=>return Err(io(e))};
    if !exists {return Ok(path);}
    match policy {
        "报告失败"=>Err(error(ErrorKind::Io,"目标路径已存在")),
        "覆盖"=>{remove(&path).await?;Ok(path)},
        "自动重命名"=>{
            let parent=path.parent().unwrap_or(Path::new("."));
            let stem=path.file_stem().unwrap_or_default().to_string_lossy();let suffix=path.extension().map(|s|format!(".{}",s.to_string_lossy())).unwrap_or_default();
            let mut index=1;
            loop {let candidate=parent.join(format!("{stem} ({index}){suffix}"));
                match fs::symlink_metadata(&candidate).await {Err(e) if e.kind()==std::io::ErrorKind::NotFound=>return Ok(candidate),Err(e)=>return Err(io(e)),Ok(_)=>index+=1}
            }
        },
        _=>Err(error(ErrorKind::Validation,"未知同名处理策略")),
    }
}
async fn copy(source:PathBuf,destination:PathBuf)->Result<(),Error> {
    let mut pending=vec![(source,destination)];
    while let Some((source,destination))=pending.pop() {
        let info=fs::symlink_metadata(&source).await.map_err(io)?;
        if info.file_type().is_symlink(){fs::symlink(fs::read_link(&source).await.map_err(io)?,destination).await.map_err(io)?;}
        else if info.is_dir(){fs::create_dir(&destination).await.map_err(io)?;let mut entries=fs::read_dir(&source).await.map_err(io)?;
            while let Some(entry)=entries.next_entry().await.map_err(io)? {pending.push((entry.path(),destination.join(entry.file_name())));}
        }else if info.is_file(){fs::copy(source,destination).await.map_err(io)?;}
        else{return Err(error(ErrorKind::Io,"只支持复制普通文件、目录与符号链接"));}
    }
    Ok(())
}
pub async fn execute(step:&Step,values:&Values)->Option<Result<Option<Value>,Error>> {
    if !matches!(step.action.as_str(),"command"|"process.signal"|"uri.open"|"http.request"|"file.read"|"file.write"|"file.copy"|"file.move"|"file.trash"|"file.info"|"directory.create"|"directory.list") {return None;}
    Some(async {
        let output=match step.action.as_str() {
            "command"=>Some(command(step,values).await?),
            "process.signal"=>{
                let pid=integer(step,"value",values)?;
                if pid==0 || pid>i32::MAX as u64 {return Err(error(ErrorKind::Validation,"进程 ID 必须为正整数"));}
                let signal=match text(step,"signal",values)?.as_str(){"TERM"=>nix::sys::signal::Signal::SIGTERM,"INT"=>nix::sys::signal::Signal::SIGINT,"STOP"=>nix::sys::signal::Signal::SIGSTOP,"CONT"=>nix::sys::signal::Signal::SIGCONT,_=>return Err(error(ErrorKind::Validation,"不支持的进程信号"))};
                nix::sys::signal::kill(nix::unistd::Pid::from_raw(pid as i32),signal).map_err(|e|error(if e==nix::errno::Errno::EPERM {ErrorKind::Permission}else{ErrorKind::Io},e.to_string()))?;None
            },
            "uri.open"|"file.trash"=>{
                let status=Command::new("gio").arg(if step.action=="uri.open" {"open"}else{"trash"}).arg("--").arg(text(step,"value",values)?).kill_on_drop(true).output().await.map_err(io)?;
                if !status.status.success(){return Err(error(ErrorKind::Io,String::from_utf8_lossy(&status.stderr).trim().to_owned()));}None
            },
            "http.request"=>{
                let timeout=integer(step,"timeout",values)?;
                let mut client=reqwest::Client::builder();if timeout>0 {client=client.timeout(Duration::from_millis(timeout));}
                let client=client.build().map_err(|e|error(ErrorKind::Unavailable,e.to_string()))?;
                let method=text(step,"method",values)?.parse::<reqwest::Method>().map_err(|e|error(ErrorKind::Validation,e.to_string()))?;
                let mut request=client.request(method,text(step,"value",values)?);
                for line in text(step,"headers",values)?.lines().filter(|s|!s.trim().is_empty()) {
                    let (key,value)=line.split_once('=').ok_or_else(||error(ErrorKind::Validation,"请求头应为名称=值"))?;
                    request=request.header(key.trim(),value.trim());
                }
                let body=text(step,"body",values)?;if !body.is_empty(){request=request.body(body);}
                let response=request.send().await.map_err(http_error)?;let status=response.status().as_u16();
                let mut headers=BTreeMap::new();for (key,value) in response.headers(){let value=value.to_str().map_err(|e|error(ErrorKind::Io,e.to_string()))?;headers.entry(key.to_string()).and_modify(|old:&mut Value|{if let Value::Text(text)=old{text.push('\n');text.push_str(value);}}).or_insert(Value::Text(value.into()));}
                let body=response.text().await.map_err(http_error)?;
                Some(data([("status",Value::Number(status as f64)),("headers",Value::Data(headers)),("body",Value::Text(body))]))
            },
            "file.read"=>{
                let bytes=fs::read(text(step,"value",values)?).await.map_err(io)?;
                let (content,_,errors)=encoding(&text(step,"encoding",values)?)?.decode(&bytes);
                if errors {return Err(error(ErrorKind::Io,"文件内容不符合所选编码"));}Some(Value::Text(content.into_owned()))
            },
            "file.write"=>{
                let content=text(step,"content",values)?;let codec=encoding(&text(step,"encoding",values)?)?;
                // encoding_rs deliberately uses UTF-8 as the UTF-16 encoder output;
                // file writing must honor the requested on-disk endian encoding.
                let (bytes,errors)=if codec==encoding_rs::UTF_16LE {(std::borrow::Cow::Owned(content.encode_utf16().flat_map(u16::to_le_bytes).collect::<Vec<_>>()),false)}
                    else if codec==encoding_rs::UTF_16BE {(std::borrow::Cow::Owned(content.encode_utf16().flat_map(u16::to_be_bytes).collect::<Vec<_>>()),false)}
                    else {let (bytes,_,errors)=codec.encode(&content);(bytes,errors)};
                if errors {return Err(error(ErrorKind::Io,"文本无法使用所选编码表示"));}
                let mut options=fs::OpenOptions::new();options.write(true).create(true);
                match text(step,"mode",values)?.as_str(){"覆盖"=>{options.truncate(true);},"追加"=>{options.append(true);},_=>return Err(error(ErrorKind::Validation,"未知文件写入方式"))}
                let mut file=options.open(text(step,"value",values)?).await.map_err(io)?;file.write_all(&bytes).await.map_err(io)?;file.flush().await.map_err(io)?;None
            },
            "directory.create"=>{
                let path=text(step,"value",values)?;if text(step,"parents",values)?=="是" {fs::create_dir_all(path).await.map_err(io)?;}else{fs::create_dir(path).await.map_err(io)?;}None
            },
            "file.copy"|"file.move"=>{
                let source=PathBuf::from(text(step,"value",values)?);fs::symlink_metadata(&source).await.map_err(io)?;
                let path=PathBuf::from(text(step,"destination",values)?);
                // Canonical parents expose aliases and directory self-copy before any overwrite.
                let source_parent=fs::canonicalize(source.parent().filter(|p|!p.as_os_str().is_empty()).unwrap_or(Path::new("."))).await.map_err(io)?;
                let source_absolute=source_parent.join(source.file_name().ok_or_else(||error(ErrorKind::Validation,"源路径无文件名"))?);
                let parent=fs::canonicalize(path.parent().filter(|p|!p.as_os_str().is_empty()).unwrap_or(Path::new("."))).await.map_err(io)?;
                let target_absolute=parent.join(path.file_name().ok_or_else(||error(ErrorKind::Validation,"目标路径无文件名"))?);
                if target_absolute.starts_with(&source_absolute) {return Err(error(ErrorKind::Validation,"不能复制或移动到源路径内部"));}
                let path=destination(&source,path,&text(step,"conflict",values)?).await?;
                if step.action=="file.move" {
                    match fs::rename(&source,&path).await {
                        Ok(())=>{},Err(e) if e.raw_os_error()==Some(nix::libc::EXDEV)=>{copy(source.clone(),path).await?;remove(&source).await?;},Err(e)=>return Err(io(e)),
                    }
                }else {copy(source,path).await?;}None
            },
            "directory.list"=>{
                let filter=glob::Pattern::new(&text(step,"filter",values)?).map_err(|e|error(ErrorKind::Validation,e.to_string()))?;
                let recursive=text(step,"recursive",values)?=="是";
                let mut pending=vec![PathBuf::from(text(step,"value",values)?)];let mut paths=vec![];
                while let Some(path)=pending.pop(){let mut entries=fs::read_dir(path).await.map_err(io)?;
                    while let Some(entry)=entries.next_entry().await.map_err(io)? {
                        if filter.matches(&entry.file_name().to_string_lossy()){paths.push(entry.path());}
                        if recursive && entry.file_type().await.map_err(io)?.is_dir(){pending.push(entry.path());}
                    }
                }
                paths.sort();Some(Value::List(paths.into_iter().map(|p|Value::Text(p.to_string_lossy().into_owned())).collect()))
            },
            "file.info"=>{
                let path=PathBuf::from(text(step,"value",values)?);let property=text(step,"property",values)?;
                if property=="是否存在" {Some(Value::Boolean(fs::try_exists(path).await.map_err(io)?))}
                else {let info=fs::metadata(&path).await.map_err(io)?;Some(match property.as_str(){
                    "是否为目录"=>Value::Boolean(info.is_dir()),"文件名"=>Value::Text(path.file_name().unwrap_or_default().to_string_lossy().into_owned()),
                    "扩展名"=>Value::Text(path.extension().unwrap_or_default().to_string_lossy().into_owned()),"父目录"=>Value::Text(path.parent().unwrap_or(Path::new("")).to_string_lossy().into_owned()),
                    "大小"=>Value::Number(info.len() as f64),"修改时间"=>Value::Text(chrono::DateTime::<chrono::Utc>::from(info.modified().map_err(io)?).to_rfc3339()),
                    _=>return Err(error(ErrorKind::Validation,"未知路径信息")),
                })}
            },
            _=>unreachable!(),
        };Ok(output)
    }.await)
}
fn http_error(e:reqwest::Error)->Error {error(if e.is_timeout(){ErrorKind::Timeout}else{ErrorKind::Io},e.to_string())}
