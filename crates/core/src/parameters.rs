//! Typed declarative bindings. References use stable symbol IDs, never display names.
use std::collections::BTreeMap;
use waystroke_model::{Binding, Reference, TextPart, Value};
use waystroke_protocol::{Error, ErrorKind};
use crate::error;

pub type Values = BTreeMap<String, Value>;

pub fn reference(reference: &Reference, values: &Values) -> Result<Value, Error> {
    let mut value = values.get(&reference.symbol_id).cloned()
        .ok_or_else(|| error(ErrorKind::Validation, format!("引用值 {} 尚未产生", reference.symbol_id)))?;
    for part in &reference.path {
        value = match value {
            Value::Data(mut fields) => fields.remove(part)
                .ok_or_else(|| error(ErrorKind::Validation, format!("返回字段 {part} 不存在")))?,
            Value::List(items) => part.parse::<usize>().ok().and_then(|i| items.get(i).cloned())
                .ok_or_else(|| error(ErrorKind::Validation, format!("列表索引 {part} 不存在")))?,
            Value::Window(window) => match part.as_str() {
                "id"=>Value::Text(window.id),"instance"=>Value::Text(window.instance),
                _=>return Err(error(ErrorKind::Validation,format!("窗口句柄没有字段 {part}"))),
            },
            _ => return Err(error(ErrorKind::Validation, "该值没有可读取的字段")),
        };
    }
    if reference.kind != waystroke_model::ValueKind::Any && value.kind() != reference.kind {
        return Err(error(ErrorKind::Validation, "引用值的实际类型与声明不符"));
    }
    Ok(value)
}

pub fn display(value: &Value) -> String {
    match value {
        Value::Text(v) => v.clone(),
        Value::Number(v) => v.to_string(),
        Value::Boolean(v) => v.to_string(),
        _ => plain(value).to_string(),
    }
}

pub fn plain(value: &Value) -> serde_json::Value {
    match value {
        Value::Null => serde_json::Value::Null,
        Value::Text(v) => serde_json::json!(v),
        Value::Number(v) => serde_json::json!(v),
        Value::Boolean(v) => serde_json::json!(v),
        Value::List(v) => serde_json::Value::Array(v.iter().map(plain).collect()),
        Value::Data(v) => serde_json::Value::Object(v.iter().map(|(k,v)| (k.clone(),plain(v))).collect()),
        Value::Window(v) => serde_json::json!(v),
    }
}

pub fn from_json(value: serde_json::Value) -> Result<Value,Error> {
    Ok(match value {
        serde_json::Value::Null=>Value::Null,
        serde_json::Value::String(v)=>Value::Text(v),
        serde_json::Value::Bool(v)=>Value::Boolean(v),
        serde_json::Value::Number(v)=>Value::Number(v.as_f64().ok_or_else(||error(ErrorKind::Validation,"JSON 数字超出范围"))?),
        serde_json::Value::Array(items)=>Value::List(items.into_iter().map(from_json).collect::<Result<_,_>>()?),
        serde_json::Value::Object(fields)=>Value::Data(fields.into_iter().map(|(k,v)|Ok((k,from_json(v)?))).collect::<Result<_,Error>>()?),
    })
}

pub fn resolve(binding: &Binding, values: &Values) -> Result<Value, Error> {
    match binding {
        Binding::Literal(value) => Ok(value.clone()),
        Binding::Reference(r) => reference(r, values),
        Binding::List(items) => Ok(Value::List(items.iter().map(|b| resolve(b,values)).collect::<Result<_,_>>()?)),
        Binding::Object(fields) => Ok(Value::Data(fields.iter().map(|(k,b)| Ok((k.clone(),resolve(b,values)?))).collect::<Result<_,Error>>()?)),
        Binding::Template(parts) => {
            let mut result=String::new();
            for part in parts {
                match part {
                    TextPart::Text(text) => result.push_str(text),
                    TextPart::Reference(r) => result.push_str(&display(&reference(r,values)?)),
                }
            }
            Ok(Value::Text(result))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use waystroke_model::ValueKind;
    #[test]
    fn nested_values_and_templates_keep_types() {
        let values=Values::from([("response".into(),Value::Data(Values::from([
            ("items".into(),Value::List(vec![Value::Number(200.)]))])))]);
        let r=Reference{symbol_id:"response".into(),path:vec!["items".into(),"0".into()],kind:ValueKind::Number};
        let binding=Binding::Object(BTreeMap::from([("message".into(),Binding::Template(vec![TextPart::Text("状态=".into()),TextPart::Reference(r.clone())]))]));
        assert_eq!(plain(&resolve(&binding,&values).unwrap()),serde_json::json!({"message":"状态=200"}));
        assert!(reference(&Reference{kind:ValueKind::Text,..r},&values).is_err());
    }
}
