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

/// Privileged input service protocol. It carries mouse routing only, never actions.
pub const INPUT_PROTOCOL_VERSION:u32=1;
pub const INPUT_SOCKET:&str="/run/waystroke/control.sock";
pub const INPUT_LEASE_MS:u32=3000;
pub const START_BINDING_MS:u32=250;
#[derive(Clone,Debug,Serialize,Deserialize,TS,PartialEq)]
#[serde(rename_all="camelCase",deny_unknown_fields)]
pub struct MouseDevice { pub id:String, pub name:String, pub path:String, pub physical_path:Option<String> }
#[derive(Clone,Debug,Serialize,Deserialize,TS,PartialEq)]
#[serde(rename_all="camelCase",deny_unknown_fields)]
pub struct MouseEvent { pub kind:u16, pub code:u16, pub value:i32, pub monotonic_ms:f64 }
#[derive(Clone,Debug,Serialize,Deserialize,TS,PartialEq)]
#[serde(rename_all="camelCase")]
pub enum StrokeDecision { Click, Consume }
#[derive(Clone,Debug,Serialize,Deserialize,TS)]
#[serde(tag="type",rename_all="camelCase",rename_all_fields="camelCase")]
pub enum InputRequest {
    Hello { version:u32 }, ListDevices, Synchronize, Activate,
    Acquire { device_id:String }, Heartbeat,
    Bound { sequence:u32 }, Bypass { sequence:u32 }, Decide { sequence:u32, decision:StrokeDecision },
    Cancel { sequence:u32 }, Release,
}
#[derive(Clone,Debug,Serialize,Deserialize,TS,PartialEq)]
#[serde(tag="type",rename_all="camelCase",rename_all_fields="camelCase")]
pub enum InputNotice {
    Begin { sequence:u32 }, Motion { sequence:u32, dx:i32, dy:i32 },
    Auxiliary { sequence:u32, button:u16 }, Finish { sequence:u32, auxiliary_buttons:Vec<u16> },
    Released { reason:String },
}

#[derive(Clone,Debug,Serialize,Deserialize,TS)]
#[serde(rename_all="camelCase",deny_unknown_fields)]
pub struct InputCommand { pub request_id:u32, pub lease_id:Option<String>, pub request:InputRequest }
#[derive(Clone,Debug,Serialize,Deserialize,TS)]
#[serde(tag="type",rename_all="camelCase",rename_all_fields="camelCase")]
pub enum InputResult { Hello { version:u32,lease_ms:u32 }, Devices { devices:Vec<MouseDevice> }, Prepared { device:MouseDevice,lease_id:String }, Ack }
#[derive(Clone,Debug,Serialize,Deserialize,TS)]
#[serde(rename_all="camelCase")]
pub enum BarrierStage { Ready, Begin, Finish }
#[derive(Clone,Debug,Serialize,Deserialize,TS)]
#[serde(tag="type",rename_all="camelCase",rename_all_fields="camelCase")]
pub enum InputPacket {
    Reply { request_id:u32, result:Reply<InputResult> }, Notice { lease_id:String,monotonic_ms:f64,notice:InputNotice },
    Barrier { lease_id:String,monotonic_ms:f64,ordinal:u32, sequence:u32, stage:BarrierStage },
}

#[derive(Clone,Debug,Serialize,Deserialize,TS)]
#[serde(rename_all="camelCase",deny_unknown_fields)]
pub struct RecognitionRequest { pub points:Vec<[f64;2]>, pub context:waystroke_model::StartContext, pub auxiliary_buttons:Vec<u16> }
#[derive(Clone,Debug,Serialize,Deserialize,TS,PartialEq)]
#[serde(rename_all="camelCase")]
pub enum RecognitionOutcome { Matched, NoMatch, Ambiguous, TooShort, Excluded, Disabled }
#[derive(Clone,Debug,Serialize,Deserialize,TS)]
#[serde(rename_all="camelCase")]
pub struct Candidate { pub rule_id:String, pub rule_name:String, pub gesture_id:String, pub sample_id:String, pub score:f64, pub priority:u8 }
#[derive(Clone,Debug,Serialize,Deserialize,TS)]
#[serde(rename_all="camelCase")]
pub struct RecognitionResult { pub outcome:RecognitionOutcome, pub rule_id:Option<String>, pub candidates:Vec<Candidate>, pub length:f64, pub reason:String }

#[derive(Clone,Debug,Serialize,Deserialize,TS)]
#[serde(rename_all="camelCase")]
pub struct GestureTiming {
    pub lease_id:String,pub sequence:u32,pub start_device_ms:f64,pub bound_ms:f64,pub release_device_ms:f64,
    pub recognized_ms:f64,pub enqueued_ms:Option<f64>,pub started_ms:Option<f64>,
}
#[derive(Clone,Debug,Serialize,Deserialize,TS)]
#[serde(rename_all="camelCase")]
pub struct RuntimeInfo {
    pub status:Status,pub devices:Vec<MouseDevice>,pub selected_device_id:Option<String>,
    pub input_armed:bool,pub locked:bool,pub recording:Option<String>,
    pub executions:Vec<waystroke_model::Execution>,pub timings:Vec<GestureTiming>,
}
