//! Event-driven authorized mouse connection. Replies and push events share one stream.
use std::{collections::HashMap,sync::{Arc,atomic::{AtomicU32,Ordering}},time::Duration};
use tokio::{io::{AsyncBufReadExt,AsyncWriteExt,BufReader},net::UnixStream,sync::{Mutex,broadcast,oneshot}};
use waystroke_protocol::*;
use crate::error;
type Pending=Arc<Mutex<HashMap<u32,oneshot::Sender<Result<InputResult,Error>>>>>;
pub struct InputClient {
    writer:Mutex<tokio::net::unix::OwnedWriteHalf>,pending:Pending,next:AtomicU32,
    reader:tokio::task::JoinHandle<()>,events:broadcast::Sender<InputPacket>,
}
impl InputClient {
    pub async fn connect()->Result<Self,Error> {
        let socket=UnixStream::connect(INPUT_SOCKET).await.map_err(|e|error(ErrorKind::Unavailable,format!("鼠标服务未连接：{e}")))?;
        if socket.peer_cred().map_err(|e|error(ErrorKind::Permission,e.to_string()))?.uid()!=0 {return Err(error(ErrorKind::Permission,"鼠标服务不是系统服务"));}
        let (reader,writer)=socket.into_split();let pending:Pending=Arc::new(Mutex::new(HashMap::new()));let (events,_)=broadcast::channel(256);
        let reader_pending=pending.clone();let reader_events=events.clone();
        let reader=tokio::spawn(async move {
            let mut lines=BufReader::new(reader).lines();
            let failure=loop {
                let text=match lines.next_line().await {Ok(Some(s))=>s,Ok(None)=>break "鼠标服务断开".to_owned(),Err(e)=>break e.to_string()};
                let message:InputPacket=match serde_json::from_str(&text) {Ok(m)=>m,Err(e)=>break format!("鼠标服务协议错误：{e}")};
                match message {
                    InputPacket::Reply{request_id,result}=>{if let Some(sender)=reader_pending.lock().await.remove(&request_id){let _=sender.send(match result {Reply::Ok{value}=>Ok(value),Reply::Error{error}=>Err(error)});}},
                    message=>{let _=reader_events.send(message);},
                }
            };
            for (_,sender) in reader_pending.lock().await.drain(){let _=sender.send(Err(error(ErrorKind::Unavailable,failure.clone())));}
            let _=reader_events.send(InputPacket::Notice{lease_id:String::new(),monotonic_ms:0.,notice:InputNotice::Released{reason:failure}});
        });
        let client=Self{writer:Mutex::new(writer),pending,next:AtomicU32::new(1),reader,events};
        match client.request(None,InputRequest::Hello{version:INPUT_PROTOCOL_VERSION}).await? {
            InputResult::Hello{version,..} if version==INPUT_PROTOCOL_VERSION=>Ok(client),
            _=>Err(error(ErrorKind::Unavailable,"鼠标服务协议版本不兼容")),
        }
    }
    pub fn subscribe(&self)->broadcast::Receiver<InputPacket>{self.events.subscribe()}
    pub async fn request(&self,lease_id:Option<&str>,request:InputRequest)->Result<InputResult,Error> {
        let request_id=self.next.fetch_add(1,Ordering::Relaxed);let (sender,receiver)=oneshot::channel();
        let command=InputCommand{request_id,lease_id:lease_id.map(str::to_owned),request};
        let mut bytes=serde_json::to_vec(&command).map_err(|e|error(ErrorKind::Internal,e.to_string()))?;bytes.push(b'\n');
        self.pending.lock().await.insert(request_id,sender);
        if let Err(e)=self.writer.lock().await.write_all(&bytes).await {self.pending.lock().await.remove(&request_id);return Err(error(ErrorKind::Unavailable,e.to_string()));}
        let result=tokio::time::timeout(Duration::from_secs(1),receiver).await;
        self.pending.lock().await.remove(&request_id);
        match result {Ok(Ok(value))=>value,Ok(Err(_))=>Err(error(ErrorKind::Unavailable,"鼠标服务响应通道关闭")),Err(_)=>Err(error(ErrorKind::Timeout,"鼠标服务响应超时"))}
    }
}
impl Drop for InputClient {fn drop(&mut self){self.reader.abort();}}
