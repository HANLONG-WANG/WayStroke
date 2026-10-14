//! Input sequences are serial and release only the virtual device's own held inputs.
use serde_json::json;
use waystroke_model::{Step,Value};
use waystroke_protocol::{Error,ErrorKind};
use crate::{desktop::Desktop,error,flow::{text,number,integer},parameters::Values,window_actions::target};
fn button(name:&str)->Result<u32,Error>{match name{"左键"=>Ok(1),"中键"=>Ok(2),"右键"=>Ok(3),"侧键 1"=>Ok(8),"侧键 2"=>Ok(9),_=>Err(error(ErrorKind::Validation,"未知鼠标按钮"))}}
fn coordinates(value:&str)->Result<[f64;2],Error>{
    let values=value.split(',').map(|v|v.trim().parse::<f64>()).collect::<Result<Vec<_>,_>>().map_err(|_|error(ErrorKind::Validation,"坐标应为 X, Y"))?;
    if values.len()!=2||!values.iter().all(|v|v.is_finite()){return Err(error(ErrorKind::Validation,"坐标需要两个有效数字"));}Ok([values[0],values[1]])
}
async fn move_pointer(desktop:&Desktop,position:[f64;2])->Result<(),Error>{desktop.call(json!({"operation":"pointerMove","mode":"屏幕绝对坐标","x":position[0],"y":position[1]})).await?;Ok(())}
async fn mouse(desktop:&Desktop,button:u32,pressed:bool)->Result<(),Error>{desktop.call(json!({"operation":"mouseInput","button":button,"pressed":pressed})).await?;Ok(())}
pub async fn execute(step:&Step,desktop:&Desktop,values:&Values)->Option<Result<Option<Value>,Error>> {
    if !matches!(step.action.as_str(),"key"|"mouse"|"pointer"|"scroll"|"drag"|"text"|"paste"|"clipboard.read"|"clipboard.write"|"clipboard.clear"|"selection.copy"){return None;}
    Some(async {
        match step.action.as_str(){
            "key"=>{desktop.call(json!({"operation":"keyInput","window":target(step,values)?,"key":text(step,"value",values)?,"value":text(step,"operation",values)?})).await?;},
            "mouse"=>{
                match text(step,"position",values)?.as_str(){
                    "当前位置"=>{},"指定坐标"=>move_pointer(desktop,[number(step,"x",values)?,number(step,"y",values)?]).await?,
                    "手势起点"=>{
                        let point=match (values.get("context:start.x"),values.get("context:start.y")){(Some(Value::Number(x)),Some(Value::Number(y)))=>[*x,*y],_=>return Err(error(ErrorKind::TargetInvalid,"没有手势起点坐标"))};
                        move_pointer(desktop,point).await?;
                    },_=>return Err(error(ErrorKind::Validation,"未知点击位置")),
                }
                let button=button(&text(step,"value",values)?)?;
                match text(step,"operation",values)?.as_str(){
                    "按下"=>mouse(desktop,button,true).await?,"释放"=>mouse(desktop,button,false).await?,
                    "单击"|"双击"=>{mouse(desktop,button,true).await?;mouse(desktop,button,false).await?;if text(step,"operation",values)?=="双击"{tokio::time::sleep(std::time::Duration::from_millis(80)).await;mouse(desktop,button,true).await?;mouse(desktop,button,false).await?;}},
                    _=>return Err(error(ErrorKind::Validation,"未知鼠标操作")),
                }
            },
            "pointer"=>{
                let mode=text(step,"value",values)?;let window=if mode=="目标窗口内"{Some(target(step,values)?)}else{None};
                desktop.call(json!({"operation":"pointerMove","mode":mode,"window":window,"x":number(step,"x",values)?,"y":number(step,"y",values)?})).await?;
            },
            "scroll"=>{
                let window=target(step,values)?;let direction=text(step,"value",values)?;
                for _ in 0..integer(step,"amount",values)?{desktop.call(json!({"operation":"scrollInput","window":window,"direction":direction})).await?;tokio::task::yield_now().await;}
            },
            "drag"=>{
                let window=target(step,values)?;desktop.call(json!({"operation":"windowAction","action":"activate","window":window})).await?;
                let start=coordinates(&text(step,"start",values)?)?;let end=coordinates(&text(step,"end",values)?)?;let duration=integer(step,"duration",values)?;
                let button=button(&text(step,"value",values)?)?;move_pointer(desktop,start).await?;mouse(desktop,button,true).await?;
                let began=tokio::time::Instant::now();
                loop{
                    let fraction=if duration==0 {1.}else{(began.elapsed().as_secs_f64()*1000./duration as f64).min(1.)};
                    move_pointer(desktop,[start[0]+(end[0]-start[0])*fraction,start[1]+(end[1]-start[1])*fraction]).await?;
                    if fraction>=1. {break;}tokio::time::sleep(std::time::Duration::from_millis(16)).await;
                }
                mouse(desktop,button,false).await?;
            },
            "clipboard.read"=>{let value=desktop.call(json!({"operation":"clipboardRead"})).await?;return Ok(Some(Value::Text(value.as_str().ok_or_else(||error(ErrorKind::Unavailable,"剪贴板文本格式错误"))?.into())));},
            "clipboard.write"=>{desktop.call(json!({"operation":"clipboardWrite","text":text(step,"value",values)?})).await?;},
            "clipboard.clear"=>{desktop.call(json!({"operation":"clipboardClear"})).await?;},
            "selection.copy"=>{
                let result=desktop.clipboard_transaction(json!({"operation":"clipboardCopyStart","window":target(step,values)?}),false,integer(step,"timeout",values)?).await?;
                return Ok(Some(Value::Text(result["text"].as_str().ok_or_else(||error(ErrorKind::Unavailable,"复制结果未返回文本"))?.into())));
            },
            "paste"=>{
                let restore=match text(step,"restore",values)?.as_str(){"恢复原内容"=>true,"保留本次内容"=>false,_=>return Err(error(ErrorKind::Validation,"未知剪贴板恢复策略"))};
                desktop.clipboard_transaction(json!({"operation":"clipboardPasteStart","window":target(step,values)?,"text":text(step,"value",values)?,"restore":restore}),true,5000).await?;
            },
            "text"=>{
                let method=text(step,"method",values)?;let window=target(step,values)?;let content=text(step,"value",values)?;
                match method.as_str(){
                    "模拟文本输入"=>{desktop.call(json!({"operation":"textInput","window":window,"text":content})).await?;},
                    "自动"|"临时剪贴板粘贴"=>{
                        desktop.clipboard_transaction(json!({"operation":"clipboardPasteStart","window":window,"text":content,"restore":true}),true,5000).await?;
                    },
                    _=>return Err(error(ErrorKind::Validation,"未知文本输入方式")),
                }
            },
            _=>unreachable!(),
        };Ok(None)
    }.await)
}
