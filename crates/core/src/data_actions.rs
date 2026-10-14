//! Pure actions run with the same typed bindings as desktop and I/O actions.
use waystroke_model::{Step, Value};
use waystroke_protocol::{Error, ErrorKind};
use crate::{error, parameters::{Values, resolve, display}};

fn parameter(step: &Step, key: &str, values: &Values) -> Result<Value, Error> {
    resolve(step.params.get(key).ok_or_else(|| error(ErrorKind::Validation,format!("缺少参数 {key}")))?,values)
}
fn text(step: &Step, key: &str, values: &Values) -> Result<String, Error> {
    match parameter(step,key,values)? {Value::Text(v)=>Ok(v),_=>Err(error(ErrorKind::Validation,format!("{key} 必须为文本")))}
}
fn number(step: &Step, key: &str, values: &Values) -> Result<f64, Error> {
    match parameter(step,key,values)? {Value::Number(v) if v.is_finite()=>Ok(v),_=>Err(error(ErrorKind::Validation,format!("{key} 必须为有效数字")))}
}

pub fn execute(step: &Step, values: &Values) -> Option<Result<Value,Error>> {
    match step.action.as_str() {
        "json.parse" => Some((|| {
            let json=serde_json::from_str(&text(step,"value",values)?).map_err(|e|error(ErrorKind::Validation,format!("JSON 无法解析：{e}")))?;
            crate::parameters::from_json(json)
        })()),
        "date.format" => Some((|| {
            let format=text(step,"value",values)?;
            let format=if format.contains('%') {format}else {
                let mut result=format;
                for (token,code) in [("YYYY","%Y"),("YY","%y"),("MM","%m"),("DD","%d"),("HH","%H"),("mm","%M"),("ss","%S")] {result=result.replace(token,code);}
                result
            };
            if chrono::format::StrftimeItems::new(&format).any(|v|matches!(v,chrono::format::Item::Error)) {return Err(error(ErrorKind::Validation,"日期格式无效"));}
            let zone=text(step,"timezone",values)?;
            let output=match zone.as_str() {
                "本地时区"=>chrono::Local::now().format(&format).to_string(),
                _=>chrono::Utc::now().with_timezone(&zone.parse::<chrono_tz::Tz>().map_err(|_|error(ErrorKind::Validation,"时区应为 UTC 或 IANA 名称"))?).format(&format).to_string(),
            };
            Ok(Value::Text(output))
        })()),
        "number.random" => Some((|| {
            let minimum=number(step,"min",values)?;let maximum=number(step,"max",values)?;
            if minimum>maximum {return Err(error(ErrorKind::Validation,"随机数最小值不能大于最大值"));}
            let mut bytes=[0u8;8];getrandom::fill(&mut bytes).map_err(|e|error(ErrorKind::Io,e.to_string()))?;
            let fraction=(u64::from_ne_bytes(bytes)>>11) as f64/(1u64<<53) as f64;
            let value=if minimum.fract()==0. && maximum.fract()==0. {(minimum+fraction*(maximum-minimum+1.)).floor().min(maximum)}else {minimum+fraction*(maximum-minimum)};
            if !value.is_finite() {return Err(error(ErrorKind::Validation,"随机数范围过大"));}
            Ok(Value::Number(value))
        })()),
        "list.change" => Some((|| {
            let Value::List(mut items)=parameter(step,"value",values)? else{return Err(error(ErrorKind::Validation,"列表操作需要列表"));};
            let operation=text(step,"operation",values)?;
            if operation=="获取长度" {return Ok(Value::Number(items.len() as f64));}
            let argument=parameter(step,"argument",values)?;
            match operation.as_str() {
                "追加"=>{items.push(argument);Ok(Value::List(items))},
                "查找"=>Ok(Value::Number(items.iter().position(|v|v==&argument).map(|i|i as f64).unwrap_or(-1.))),
                "读取指定索引"|"移除指定索引"=>{
                    let index=match argument {Value::Number(v)=>v,Value::Text(v)=>v.parse().map_err(|_|error(ErrorKind::Validation,"列表索引应为非负整数"))?,_=>return Err(error(ErrorKind::Validation,"列表索引应为数字"))};
                    if index<0. || index.fract()!=0. || index>=items.len() as f64 {return Err(error(ErrorKind::Validation,"列表索引越界"));}
                    if operation=="读取指定索引" {Ok(items[index as usize].clone())}else {items.remove(index as usize);Ok(Value::List(items))}
                },
                _=>Err(error(ErrorKind::Validation,"未知列表操作")),
            }
        })()),
        "variable" => Some(parameter(step,"value",values)),
        "number.calculate" => Some((|| {
            let left=number(step,"left",values)?;
            let operation=text(step,"value",values)?;
            let right=if operation=="四舍五入"{0.}else{number(step,"right",values)?};
            let result=match operation.as_str() {
                "加"=>left+right,"减"=>left-right,"乘"=>left*right,
                "除" if right!=0.=>left/right,"取余" if right!=0.=>left%right,
                "最小值"=>left.min(right),"最大值"=>left.max(right),"四舍五入"=>left.round(),
                "除"|"取余"=>return Err(error(ErrorKind::Validation,"不能除以零")),
                _=>return Err(error(ErrorKind::Validation,"未知数字运算")),
            };
            if !result.is_finite() {return Err(error(ErrorKind::Validation,"数字运算结果超出范围"));}
            Ok(Value::Number(result))
        })()),
        "text.transform" => Some((|| {
            let value=parameter(step,"value",values)?;
            let operation=text(step,"operation",values)?;
            let argument=if matches!(operation.as_str(),"替换"|"截取"|"按分隔符拆分"|"按分隔符合并"){text(step,"argument",values)?}else{String::new()};
            let replacement=if matches!(operation.as_str(),"替换"|"连接"){text(step,"replacement",values)?}else{String::new()};
            if operation=="按分隔符合并" {
                let Value::List(items)=value else{return Err(error(ErrorKind::Validation,"合并需要列表"));};
                return Ok(Value::Text(items.iter().map(display).collect::<Vec<_>>().join(&argument)));
            }
            let Value::Text(value)=value else{return Err(error(ErrorKind::Validation,"文本处理需要文本"));};
            Ok(match operation.as_str() {
                "去首尾空白"=>Value::Text(value.trim().into()),
                "转大写"=>Value::Text(value.to_uppercase()),"转小写"=>Value::Text(value.to_lowercase()),
                "替换"=>Value::Text(value.replace(&argument,&replacement)),
                "连接"=>Value::Text(value+&replacement),
                "获取长度"=>Value::Number(value.chars().count() as f64),
                "按分隔符拆分"=>Value::List(value.split(&argument).map(|v|Value::Text(v.into())).collect()),
                "截取"=>{
                    let mut range=argument.split(',');
                    let start=range.next().unwrap_or_default().trim().parse::<usize>().map_err(|_|error(ErrorKind::Validation,"截取位置应为非负整数"))?;
                    let length=range.next().map(|v|v.trim().parse::<usize>()).transpose().map_err(|_|error(ErrorKind::Validation,"截取长度应为非负整数"))?;
                    Value::Text(value.chars().skip(start).take(length.unwrap_or(usize::MAX)).collect())
                },
                _=>return Err(error(ErrorKind::Validation,"未知文本处理操作")),
            })
        })()),
        "data.field" => Some((|| {
            let mut value=parameter(step,"value",values)?;
            for field in text(step,"path",values)?.split('.').filter(|s|!s.is_empty()) {
                value=match value {
                    Value::Data(mut fields)=>fields.remove(field),
                    Value::List(items)=>field.parse::<usize>().ok().and_then(|i|items.get(i).cloned()),
                    _=>None,
                }.ok_or_else(||error(ErrorKind::Validation,format!("字段 {field} 不存在")))?;
            }
            Ok(value)
        })()),
        _=>None,
    }
}
