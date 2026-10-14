//! Typed D-Bus integration using the five argument types exposed by the reviewed UI.
use std::{collections::BTreeMap,time::Duration};
use zbus::zvariant::{Value as BusValue,Structure,StructureBuilder};
use waystroke_model::{Step,Value};
use waystroke_protocol::{Error,ErrorKind};
use crate::{error,flow::{text,integer,parameter},parameters::Values};
fn bus_error(e:zbus::Error)->Error {
    let permission=matches!(&e,zbus::Error::MethodError(name,_,_) if name.as_str().contains("AccessDenied")||name.as_str().contains("Auth"));
    error(if permission{ErrorKind::Permission}else{ErrorKind::Unavailable},e.to_string())
}
fn typed(signature:&str,value:Value)->Result<BusValue<'static>,Error> {
    Ok(match (signature,value) {
        ("s",Value::Text(v))=>v.into(),("b",Value::Boolean(v))=>v.into(),
        ("d",Value::Number(v)) if v.is_finite()=>v.into(),
        ("i",Value::Number(v)) if v.fract()==0. && v>=i32::MIN as f64 && v<=i32::MAX as f64=>(v as i32).into(),
        ("as",Value::List(items))=>{
            let strings=items.into_iter().map(|v|match v {Value::Text(v)=>Ok(v),_=>Err(error(ErrorKind::Validation,"D-Bus 文本列表只能包含文本"))}).collect::<Result<Vec<_>,_>>()?;
            BusValue::new(strings)
        },
        _=>return Err(error(ErrorKind::Validation,format!("D-Bus 值不符合类型 {signature}"))),
    })
}
fn from_bus(value:&BusValue<'_>)->Result<Value,Error> {
    Ok(match value {
        BusValue::U8(v)=>Value::Number(*v as f64),BusValue::I16(v)=>Value::Number(*v as f64),BusValue::U16(v)=>Value::Number(*v as f64),
        BusValue::I32(v)=>Value::Number(*v as f64),BusValue::U32(v)=>Value::Number(*v as f64),
        BusValue::I64(v)=>{if v.unsigned_abs()>9_007_199_254_740_991{return Err(error(ErrorKind::Validation,"D-Bus 整数超出精确数字范围"));}Value::Number(*v as f64)},
        BusValue::U64(v)=>{if *v>9_007_199_254_740_991{return Err(error(ErrorKind::Validation,"D-Bus 整数超出精确数字范围"));}Value::Number(*v as f64)},
        BusValue::F64(v)=>Value::Number(*v),BusValue::Bool(v)=>Value::Boolean(*v),
        BusValue::Str(v)=>Value::Text(v.to_string()),BusValue::ObjectPath(v)=>Value::Text(v.to_string()),BusValue::Signature(v)=>Value::Text(v.to_string()),
        BusValue::Value(v)=>from_bus(v)?,
        BusValue::Array(v)=>Value::List(v.inner().iter().map(from_bus).collect::<Result<_,_>>()?),
        BusValue::Structure(v)=>Value::List(v.fields().iter().map(from_bus).collect::<Result<_,_>>()?),
        BusValue::Dict(v)=>{
            let mut fields=BTreeMap::new();for (key,value) in v.iter() {
                let key=match key {BusValue::Str(v)=>v.to_string(),_=>return Err(error(ErrorKind::Validation,"D-Bus 字典键必须是文本"))};
                fields.insert(key,from_bus(value)?);
            }Value::Data(fields)
        },
        _=>return Err(error(ErrorKind::Unavailable,"D-Bus 返回了无法在编排中使用的类型")),
    })
}
pub async fn execute(step:&Step,values:&Values)->Option<Result<Option<Value>,Error>> {
    if !matches!(step.action.as_str(),"dbus.call"|"dbus.property"){return None;}
    Some(async {
        let connection=match text(step,"bus",values)?.as_str(){"会话总线"=>zbus::Connection::session().await,"系统总线"=>zbus::Connection::system().await,_=>return Err(error(ErrorKind::Validation,"未知 D-Bus 总线"))}.map_err(bus_error)?;
        let service=text(step,"service",values)?;let path=text(step,"path",values)?;let interface=text(step,"interface",values)?;let method=text(step,"value",values)?;
        let operation=async {
            if step.action=="dbus.property" {
                let proxy=zbus::Proxy::new(&connection,service.as_str(),path.as_str(),"org.freedesktop.DBus.Properties").await.map_err(bus_error)?;
                match text(step,"operation",values)?.as_str() {
                    "读取"=>{
                        let value:zbus::zvariant::OwnedValue=proxy.call("Get",&(interface.as_str(),method.as_str())).await.map_err(bus_error)?;
                        Ok(Some(Value::Data(BTreeMap::from([("value".into(),from_bus(&value)?)]))))
                    },
                    "设置"=>{
                        let value=typed(&text(step,"signature",values)?,parameter(step,"content",values)?)?;
                        let _:()=proxy.call("Set",&(interface.as_str(),method.as_str(),value)).await.map_err(bus_error)?;
                        Ok(Some(Value::Data(BTreeMap::from([("written".into(),Value::Boolean(true))]))))
                    },
                    _=>Err(error(ErrorKind::Validation,"未知 D-Bus 属性操作")),
                }
            }else {
                let mut builder=StructureBuilder::new();let mut generated=String::new();let mut count=0;
                let args=if step.params.contains_key("dbusArgs") {
                    match parameter(step,"dbusArgs",values)? {Value::List(v)=>v,_=>return Err(error(ErrorKind::Validation,"需要类型化 D-Bus 参数列表"))}
                }else if text(step,"arguments",values)?.trim().is_empty()||text(step,"arguments",values)?.trim()=="[]" {vec![]}
                else{return Err(error(ErrorKind::Validation,"请使用类型化 D-Bus 参数表"));};
                for arg in args {
                    let Value::Data(mut fields)=arg else{return Err(error(ErrorKind::Validation,"D-Bus 参数缺少类型和值"));};
                    let Some(Value::Text(signature))=fields.remove("type") else{return Err(error(ErrorKind::Validation,"D-Bus 参数类型无效"));};
                    let value=fields.remove("value").ok_or_else(||error(ErrorKind::Validation,"D-Bus 参数值缺失"))?;
                    builder=builder.append_field(typed(&signature,value)?);generated+=&signature;count+=1;
                }
                let signature=text(step,"signature",values)?;
                if !signature.is_empty() && signature!=generated {return Err(error(ErrorKind::Validation,"D-Bus 参数签名与参数表不一致"));}
                let proxy=zbus::Proxy::new(&connection,service.as_str(),path.as_str(),interface.as_str()).await.map_err(bus_error)?;
                let reply=if count==0 {proxy.call_method(method.as_str(),&()).await.map_err(bus_error)?}else {proxy.call_method(method.as_str(),&builder.build().map_err(|e|error(ErrorKind::Validation,e.to_string()))?).await.map_err(bus_error)?};
                let body=reply.body();
                let output=if body.signature().to_string().is_empty() {vec![]}else {body.deserialize::<Structure>().map_err(bus_error)?.fields().iter().map(from_bus).collect::<Result<Vec<_>,_>>()?};
                Ok(Some(Value::Data(BTreeMap::from([("values".into(),Value::List(output))]))))
            }
        };
        let timeout=if step.action=="dbus.call" {integer(step,"timeout",values)?}else{5000};
        if timeout==0 {operation.await}else {tokio::time::timeout(Duration::from_millis(timeout),operation).await.map_err(|_|error(ErrorKind::Timeout,"D-Bus 调用超时"))?}
    }.await)
}
