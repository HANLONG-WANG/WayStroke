use serde::{Deserialize,Serialize};
use ts_rs::TS;
use waystroke_model::{Config, ValidationError};
pub const CORE_NAME:&str="io.github.waystroke.Core";
pub const CORE_PATH:&str="/io/github/waystroke/Core";
pub const CORE_INTERFACE:&str="io.github.waystroke.Core1";
pub const PROTOCOL_VERSION:u32=1;
#[derive(Clone,Debug,Serialize,Deserialize,TS)]
#[serde(rename_all="camelCase")]
pub struct Snapshot { pub revision:u32, pub saved_at:Option<String>, pub config:Config }
impl Default for Snapshot { fn default()->Self { Self{revision:0,saved_at:None,config:Config::default()} } }
#[derive(Clone,Debug,Serialize,Deserialize,TS)]
#[serde(rename_all="camelCase")]
pub struct Commit { pub request_id:String, pub expected_revision:u32, pub config:Config }
#[derive(Clone,Debug,Serialize,Deserialize,TS)]
#[serde(rename_all="camelCase")]
pub enum ErrorKind { Validation, Conflict, Permission, Unavailable, TargetInvalid, Timeout, Canceled, Io, Internal }
#[derive(Clone,Debug,Serialize,Deserialize,TS)]
pub struct Error { pub kind:ErrorKind, pub message:String, pub details:Vec<ValidationError> }
#[derive(Clone,Debug,Serialize,Deserialize,TS)]
#[serde(tag="status",rename_all="camelCase")]
pub enum Reply<T> { Ok { value:T }, Error { error:Error } }
impl<T> Reply<T> {
    pub fn from_result(r:Result<T,Error>)->Self { match r { Ok(value)=>Self::Ok{value},Err(error)=>Self::Error{error} } }
}
#[derive(Clone,Debug,Serialize,Deserialize,TS)]
#[serde(rename_all="camelCase")]
pub struct Status { pub protocol_version:u32, pub core_version:String, pub extension_connected:bool, pub input_connected:bool, pub execution_available:bool, pub reason:String }
