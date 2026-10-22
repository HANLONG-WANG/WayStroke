import type { Config, Step, Binding, Value, ValueKind, Symbol, Reference } from './generated/model';
// The editor retains the reviewed field layout; this boundary converts it to typed saved data.
export type EditorDocument = Record<string, any>;
const kinds:Record<string,ValueKind>={'文本':'text','数字':'number','布尔值':'boolean','列表':'list','窗口':'window','数据':'data','自动':'any'};
const labels=Object.fromEntries(Object.entries(kinds).map(([label,kind])=>[kind,label]));
const contexts:Record<string,[string,ValueKind]>={ '起点窗口':['context:start.window','window'],'起点应用':['context:start.applicationId','text'],'窗口标题':['context:start.title','text'],'起点X':['context:start.x','number'],'起点Y':['context:start.y','number'],'当前工作区':['context:workspace','number'],'起点坐标':['context:start.position','list'],'当前指针坐标':['context:pointer.position','list'],'当前显示器':['context:monitor','number'],'剪贴板文本':['context:clipboard','text'],'当前时间':['context:now','text'],'主目录':['context:home','text'] };
const modifiers:Record<string,number>={'左键':272,'中键':274,'侧键 1':275,'侧键 2':276};
let source:Config;
let catalog:EditorDocument[]=[];
const aliases=new Map<string,Symbol>();
export function setCatalog(value:EditorDocument[]) { catalog=value; }
function flatValue(v:Value):any { return v.kind==='null'?null:v.kind==='list'?v.value.map(flatValue):v.kind==='data'?Object.fromEntries(Object.entries(v.value).map(([k,v])=>[k,flatValue(v!)])):v.value; }
function value(v:any):Value {
 if(v===null)return {kind:'null'};
 if(typeof v==='number')return {kind:'number',value:v};if(typeof v==='boolean')return {kind:'boolean',value:v};
 if(Array.isArray(v))return {kind:'list',value:v.map(value)};
 if(v && typeof v==='object')return {kind:'data',value:Object.fromEntries(Object.entries(v).map(([k,v])=>[k,value(v)]))};
 return {kind:'text',value:String(v??'')};
}
function allSymbols(c:Config):Map<string,Symbol> {
 const symbols=new Map<string,Symbol>();
 for(const [name,[id,kind]] of Object.entries(contexts))symbols.set(id,{id,name,kind});
 function steps(list:Step[]) { for(const s of list) { for(const sym of [s.output,s.loopItem,s.loopIndex])if(sym)symbols.set(sym.id,sym);steps(s.children);steps(s.otherwise); } }
 for(const w of c.workflows){for(const x of [...w.inputs,...w.outputs])symbols.set(x.symbol.id,x.symbol);steps(w.steps)}
 for(const r of c.rules)steps(r.steps);
 return symbols;
}
export function fromConfig(c:Config):EditorDocument {
 source=structuredClone(c);aliases.clear();const symbols=allSymbols(c);const producers=new Map<string,Step>();function collect(list:Step[]){for(const step of list){if(step.output)producers.set(step.output.id,step);collect(step.children);collect(step.otherwise)}}for(const owner of [...c.rules,...c.workflows])collect(owner.steps);for(const symbol of symbols.values())aliases.set(symbol.name,symbol);
 function token(r:Reference) { const provider=producers.get(r.symbolId);const workflow=c.workflows.find(w=>w.id===provider?.workflowId);const path=r.path.map((part,index)=>index===0?(workflow?.outputs.find(o=>o.symbol.id===part)?.symbol.name??part):part);return (symbols.get(r.symbolId)?.name??r.symbolId)+(path.length?'.'+path.join('.'):''); }
 function unbind(b:Binding):any { if(b.mode==='list')return b.value.map(unbind);if(b.mode==='object')return Object.fromEntries(Object.entries(b.value).map(([k,v])=>[k,unbind(v!)]));if(b.mode==='literal')return flatValue(b.value);if(b.mode==='reference')return '${'+token(b.value)+'}';return b.value.map(p=>p.mode==='text'?p.value:'${'+token(p.value)+'}').join(''); }
 function steps(list:Step[]):EditorDocument[] {return list.map(s=>{
  const out:EditorDocument={uid:s.id,type:s.action,enabled:s.enabled,onFailure:s.onFailure==='stop'?'停止序列':'记录失败并继续',timeoutMs:s.timeoutMs,...Object.fromEntries(Object.entries(s.params).map(([k,v])=>[k,unbind(v!)]))};
  if(s.output){out.outputId=s.output.id;out.output=s.output.name;out.resultKind=labels[s.output.kind];if(s.action==='variable')out.name=s.output.name;}
  if(s.workflowId){out.workflowId=s.workflowId;out.value=c.workflows.find(w=>w.id===s.workflowId)?.name??'';const w=c.workflows.find(w=>w.id===s.workflowId);out.inputIds=Object.fromEntries(Object.entries(s.arguments).map(([id,b])=>[id,unbind(b!)]));out.inputValues=Object.fromEntries(Object.entries(s.arguments).map(([id,b])=>[w?.inputs.find(i=>i.symbol.id===id)?.symbol.name??id,unbind(b!)]));}
  if(s.children.length||catalog.find(d=>d.id===s.action)?.children)out.children=steps(s.children);
  if(s.action==='condition')out.otherwise=steps(s.otherwise);
  if(s.loopItem){out.item=s.loopItem.name;out.itemKind=labels[s.loopItem.kind];out.loopItemId=s.loopItem.id;}if(s.loopIndex){out.index=s.loopIndex.name;out.loopIndexId=s.loopIndex.id;}
  if(out.dbusArgs)for(const arg of out.dbusArgs)if(typeof arg.value!=='string')arg.value=Array.isArray(arg.value)?arg.value.join('\n'):String(arg.value);
  out.bindingAnchors=structuredClone(s.params);out.bindingLabels=Object.fromEntries(Object.keys(s.params).map(key=>[key,structuredClone(out[key])]));out.argumentAnchors=structuredClone(s.arguments);out.argumentLabels=structuredClone(out.inputIds??{});
  if(s.action==='variable')delete out.output;
  return out;
 })}
 const apps=c.applications;const scope=(id:string|null)=>id?apps.find(a=>a.id===id)?.name??id:'全局';
 return {settings:{...c.settings},applications:structuredClone(apps),exclusions:structuredClone(c.exclusions),
  gestures:c.gestures.map(g=>({id:g.id,name:g.name,mainSampleId:g.mainSampleId,samples:structuredClone([...g.samples.filter(s=>s.id===g.mainSampleId),...g.samples.filter(s=>s.id!==g.mainSampleId)])})),
  rules:c.rules.map(r=>({id:r.id,name:r.name,enabled:r.enabled,feedback:r.feedback,gestureId:r.gestureId,path:structuredClone(c.gestures.find(g=>g.id===r.gestureId)?.samples.find(s=>s.id===c.gestures.find(g=>g.id===r.gestureId)?.mainSampleId)?.points??[]),modifier:r.auxiliaryButtons.length?Object.entries(modifiers).find(([,code])=>code===r.auxiliaryButtons[0])?.[0]??'无':'无',auxiliaryButtons:r.auxiliaryButtons,originalModifier:r.auxiliaryButtons.length?Object.entries(modifiers).find(([,code])=>code===r.auxiliaryButtons[0])?.[0]??'无':'无',applicationId:r.applicationId??'',scope:scope(r.applicationId),titleMatch:r.titleMatch,steps:steps(r.steps)})),
  workflows:c.workflows.map(w=>({id:w.id,name:w.name,description:w.description,inputs:w.inputs.map(i=>({uid:i.symbol.id,name:i.symbol.name,kind:labels[i.symbol.kind],default:i.default?unbind(i.default):'',defaultAnchor:i.default,defaultLabel:i.default?unbind(i.default):'',originalKind:labels[i.symbol.kind]})),outputs:w.outputs.map(o=>({uid:o.symbol.id,name:o.symbol.name,kind:labels[o.symbol.kind],value:unbind(o.value),valueAnchor:o.value,valueLabel:unbind(o.value),originalKind:labels[o.symbol.kind]})),steps:steps(w.steps)})),
  snippets:c.snippets.map(t=>({id:t.id,key:t.key,value:t.value,enabled:t.enabled,applicationId:t.applicationId??'',scope:scope(t.applicationId),trigger:t.trigger,caseSensitive:t.caseSensitive,boundary:t.boundary,keepDelimiter:t.preserve}))};
}
export function parameterActive(step:EditorDocument,key:string):boolean {
 switch(step.type){
  case 'text.transform':if(key==='argument')return ['替换','截取','按分隔符拆分','按分隔符合并'].includes(step.operation);if(key==='replacement')return ['替换','连接'].includes(step.operation);break;
  case 'condition':if(key==='source')return ['变量','文件是否存在','命令退出码'].includes(step.value);if(key==='compare')return !['为空','不为空','为真','为假'].includes(step.operator);break;
  case 'wait.condition':if(key==='subject')return step.value!=='剪贴板包含';if(key==='compare')return ['窗口标题包含','变量等于','剪贴板包含'].includes(step.value);break;
  case 'mouse':if(['x','y'].includes(key))return step.position==='指定坐标';break;
  case 'command':if(key==='arguments')return step.mode!=='通过 Shell 运行';break;
  case 'window.target':if(key==='variable')return step.value==='窗口变量';break;
  case 'workspace.switch':case 'window.monitor':if(key==='index')return step.value==='指定编号';break;
  case 'media':if(key==='seconds')return ['快进','快退'].includes(step.value);break;
  case 'screenshot':if(key==='path')return step.destination==='文件';break;
  case 'number.calculate':if(key==='right')return step.value!=='四舍五入';break;
  case 'list.change':if(key==='argument')return step.operation!=='获取长度';break;
  case 'dbus.property':if(['content','signature'].includes(key))return step.operation==='设置';break;
  case 'dbus.call':if(key==='arguments')return !step.dbusArgs;break;
 }
 return true;
}
export function toConfig(d:EditorDocument):Config {
 const base=structuredClone(source);const outputWorkflows=new Map<string,string>();const context=new Map<string,Symbol>(Object.entries(contexts).map(([name,[id,kind]])=>[name,{id,name,kind}]));
 const kind=(label:string):ValueKind=>kinds[label]??'data';
 const scopedId=(parent:string,id:any)=>String(id).startsWith(parent+':')?String(id):parent+':'+String(id??crypto.randomUUID());
 function bind(raw:any,scope:Map<string,Symbol>,expected:ValueKind='text',plain=false):Binding {
  const text=String(raw??'');
  function ref(name:string):Reference {
   const root=[...new Set([...scope.keys(),...aliases.keys()])].filter(key=>name===key||name.startsWith(key+'.')).sort((a,b)=>b.length-a.length)[0];
   const sym=scope.get(root)??aliases.get(root);if(!sym||![...scope.values()].some(s=>s.id===sym.id))throw new Error('引用值不可用：'+name);
   const path=name===root?[]:name.slice(root.length+1).split('.');let resultKind:ValueKind=path.length?(['status','exitCode','pid','width','height'].includes(path.at(-1)??'')?'number':path.at(-1)==='headers'?'data':'text'):sym.kind;
   const workflowId=outputWorkflows.get(sym.id);
   if(workflowId&&path.length){const workflow=d.workflows.find((w:EditorDocument)=>w.id===workflowId);const previous=source.workflows.find(w=>w.id===workflowId)?.outputs.find(o=>o.symbol.name===path[0]);const field=workflow?.outputs.find((o:EditorDocument)=>o.name===path[0]||o.uid===path[0]||o.uid===previous?.symbol.id);if(!field)throw new Error('可复用动作的返回字段已失效：'+name);path[0]=String(field.uid);resultKind=kind(field.kind);}
   return {symbolId:sym.id,path,kind:resultKind};
  }
  if(plain&&[...scope.keys()].some(name=>text===name||text.startsWith(name+'.')))return {mode:'reference',value:ref(text)};
  const parts=[...text.matchAll(/\$\{([^}]+)\}/g)];
  if(parts.length===1 && parts[0][0]===text)return {mode:'reference',value:ref(parts[0][1])};
  if(parts.length){const segments:any[]=[];let offset=0;for(const match of parts){if(match.index>offset)segments.push({mode:'text',value:text.slice(offset,match.index)});segments.push({mode:'reference',value:ref(match[1])});offset=match.index+match[0].length;}if(offset<text.length)segments.push({mode:'text',value:text.slice(offset)});return {mode:'template',value:segments};}
  if(expected==='number'){const n=Number(raw);if(!Number.isFinite(n))throw new Error('请输入数字或数字变量：'+text);return {mode:'literal',value:{kind:'number',value:n}};}
  if(expected==='boolean'){if(!['true','false',true,false].includes(raw))throw new Error('请输入布尔值：'+text);return {mode:'literal',value:{kind:'boolean',value:raw===true||raw==='true'}};}
  if(expected==='list'){let items=raw;if(!Array.isArray(items)){if(text.trim().startsWith('[')){try{items=JSON.parse(text)}catch{throw new Error('列表 JSON 无法解析')}}else items=text.split('\n')}if(!Array.isArray(items))throw new Error('请输入列表或列表变量');return {mode:'literal',value:value(items)};}
  if(expected==='data'){let data=raw;if(typeof data!=='object'){try{data=JSON.parse(text)}catch{throw new Error('请输入 JSON 对象或数据变量')}}const result=value(data);if(!['data','null'].includes(result.kind))throw new Error('数据值需要 JSON 对象，列表请选择列表类型');return {mode:'literal',value:result};}
  return {mode:'literal',value:value(text)};
 }
 function dbusKind(signature:string):ValueKind { const kind=({s:'text',i:'number',d:'number',b:'boolean',as:'list'} as Record<string,ValueKind>)[signature];if(!kind)throw new Error('D-Bus 类型不受支持：'+signature);return kind; }
 function outputKind(s:EditorDocument):ValueKind {
  if(s.type==='variable')return kind(s.kind??'数字');
  if(s.type==='text.transform')return s.operation==='获取长度'?'number':s.operation==='按分隔符拆分'?'list':'text';
  if(s.resultKind&&s.resultKind!=='自动')return kind(s.resultKind);
  if(['data.field','json.parse'].includes(s.type)||s.type==='list.change'&&s.operation==='读取指定索引')return 'any';
  if(['clipboard.read','selection.copy','date.format','file.read','dialog.input'].includes(s.type))return 'text';
  if(['number.calculate','number.random'].includes(s.type))return 'number';
  if(['launch','app.activate','window.find'].includes(s.type))return 'window';
  if(s.type==='directory.list')return 'list';if(s.type==='dialog.message')return 'boolean';
  if(s.type==='window.info'){if(['标题','应用 ID'].includes(s.value))return 'text';if(['工作区','所在显示器'].includes(s.value))return 'number';if(['是否最大化','是否全屏','是否置顶'].includes(s.value))return 'boolean';}
  if(s.type==='file.info')return ['是否存在','是否为目录'].includes(s.property)?'boolean':s.property==='大小'?'number':'text';
  if(s.type==='variable.read')return ['当前工作区','当前显示器'].includes(s.value)?'number':['起点坐标','当前指针坐标'].includes(s.value)?'list':'text';
  if(s.type==='list.change')return ['获取长度','查找'].includes(s.operation)?'number':s.operation==='读取指定索引'?'data':'list';
  return 'data';
 }
 function referenceKind(raw:any,scope:Map<string,Symbol>):ValueKind {
  const binding=bind(raw,scope,'text',true);return binding.mode==='reference'?binding.value.kind:'text';
 }
 function paramKind(s:EditorDocument,key:string,scope:Map<string,Symbol>):ValueKind {
  if(s.type==='dbus.property'&&key==='content'&&s.operation==='设置')return dbusKind(s.signature);
  if(s.type==='condition'&&key==='compare'&&['为空','不为空','为真','为假'].includes(s.operator))return 'text';
  if(s.type==='condition'&&key==='compare')return s.value==='文件是否存在'?'boolean':s.value==='命令退出码'?'number':referenceKind(s.source,scope);
  if(s.type==='wait.condition'&&s.value==='变量等于'&&key==='compare')return referenceKind(s.subject,scope);
  if(s.type==='variable'&&key==='value')return kind(s.kind??'数字');
  if(s.type==='text.transform'&&key==='value'&&s.operation==='按分隔符合并')return 'list';
  if(['foreach','list.change'].includes(s.type)&&key==='value')return 'list';
  if(s.type==='window.target'&&key==='variable'&&s.value==='窗口变量')return 'window';
  if(s.type==='foreach'&&key==='index')return 'text';
  if(['x','y','width','height','count','index','duration','timeout','interval','amount','seconds','left','right','min','max'].includes(key)||key==='value'&&['wait','repeat','process.signal','workspace.move'].includes(s.type))return 'number';
  return 'text';
 }
 function steps(list:EditorDocument[],scope:Map<string,Symbol>):Step[] { return list.map(s=>{
  try {
  s.uid??=crypto.randomUUID();const def=catalog.find(a=>a.id===s.type);if(!def)throw new Error('未知动作：'+s.type);
  const outputName=s.type==='variable'?s.name:s.output;
  const out:Step={id:s.uid,action:s.type,enabled:s.enabled!==false,params:{},output:outputName?{id:s.outputId??s.uid+':output',name:outputName,kind:outputKind(s)}:null,onFailure:s.onFailure==='记录失败并继续'?'continue':'stop',timeoutMs:s.timeoutMs??null,workflowId:s.workflowId??null,arguments:{},children:[],otherwise:[],loopItem:null,loopIndex:null};
  for(const field of def.fields){if(field.key==='output'||s.type==='flow.call'&&['value','arguments'].includes(field.key))continue;const raw=s[field.key]??field.initial;const anchor=s.bindingAnchors?.[field.key];if(!parameterActive(s,field.key)){out.params[field.key]=anchor&&JSON.stringify(raw)===JSON.stringify(s.bindingLabels?.[field.key])?structuredClone(anchor):{mode:'literal',value:value(raw)};continue;}out.params[field.key]=anchor&&['kind','operation','signature'].every(key=>s[key]===s.bindingLabels?.[key])&&JSON.stringify(raw)===JSON.stringify(s.bindingLabels?.[field.key])?structuredClone(anchor):bind(raw,scope,paramKind(s,field.key,scope),field.key==='variable'||field.key==='source'&&s.type==='condition'&&['变量','命令退出码'].includes(s.value)||field.key==='subject'&&s.type==='wait.condition'&&s.value==='变量等于'||field.key==='value'&&['foreach','list.change','data.field'].includes(s.type));}
  if(s.resultKind)out.params.resultKind=bind(s.resultKind,scope);
  if(s.dbusArgs)out.params.dbusArgs=s.bindingAnchors?.dbusArgs&&JSON.stringify(s.dbusArgs)===JSON.stringify(s.bindingLabels?.dbusArgs)?structuredClone(s.bindingAnchors.dbusArgs):{mode:'list',value:s.dbusArgs.map((arg:EditorDocument)=>({mode:'object',value:{type:{mode:'literal',value:value(arg.type)},value:bind(arg.value,scope,dbusKind(arg.type))}}))};
  if(s.workflowId){const w=d.workflows.find((w:EditorDocument)=>w.id===s.workflowId);if(!w)throw new Error('可复用动作引用不存在');for(const i of w.inputs) { const raw=s.inputValues?.[i.name]??s.inputIds?.[i.uid]??i.default;if(raw!==undefined){const id=String(i.uid??crypto.randomUUID());const anchor=s.argumentAnchors?.[id];out.arguments[id]=anchor&&['kind','operation','signature'].every(key=>s[key]===s.bindingLabels?.[key])&&JSON.stringify(raw)===JSON.stringify(s.argumentLabels?.[id])?structuredClone(anchor):bind(raw,scope,kind(i.kind));} }}
  const nested=new Map(scope);
  if(s.type==='foreach'){out.loopItem={id:s.loopItemId??s.uid+':item',name:s.item||'当前项',kind:kind(s.itemKind??'文本')};out.loopIndex={id:s.loopIndexId??s.uid+':index',name:s.index||'索引',kind:'number'};nested.set(out.loopItem.name,out.loopItem);nested.set(out.loopIndex.name,out.loopIndex);}
  if(s.type==='repeat'){out.loopIndex={id:s.loopIndexId??s.uid+':index',name:'循环序号',kind:'number'};nested.set(out.loopIndex.name,out.loopIndex);}
  out.children=steps(s.children??[],nested);out.otherwise=steps(s.otherwise??[],new Map(scope));
  if(out.output&&out.enabled){scope.set(out.output.name,out.output);aliases.set(out.output.name,out.output);if(out.workflowId)outputWorkflows.set(out.output.id,out.workflowId);}
  return out;
  }catch(error){
   if(error instanceof Error&&!('stepId' in error))Object.assign(error,{stepId:s.uid});
   throw error;
  }
 }) }
 base.settings={...base.settings,...Object.fromEntries(Object.keys(base.settings).map(k=>[k,d.settings[k]??(base.settings as any)[k]]))};
 base.applications=d.applications.map((a:EditorDocument)=>({id:a.id,name:a.name}));base.exclusions=d.exclusions.map((e:EditorDocument)=>({applicationId:e.applicationId,gestures:e.gestures,text:e.text,compatibility:!!e.compatibility}));
 base.gestures=d.gestures.map((g:EditorDocument)=>{const original=source.gestures.find(item=>item.id===g.id);const samples=g.samples.map((s:EditorDocument)=>({id:original?.samples.some(item=>item.id===s.id)?String(s.id):scopedId(g.id,s.id),points:s.points}));return {id:String(g.id),name:g.name,mainSampleId:samples[0]?.id??'',samples:original?samples.sort((a:{id:string},b:{id:string})=>original.samples.findIndex(s=>s.id===a.id)-original.samples.findIndex(s=>s.id===b.id)):samples};});
 base.workflows=d.workflows.map((w:EditorDocument)=>{const scope=new Map(context);const inputs=w.inputs.map((i:EditorDocument)=>{i.uid=String(i.uid??crypto.randomUUID());const symbol={id:i.uid,name:i.name,kind:kind(i.kind)};scope.set(i.name,symbol);aliases.set(i.name,symbol);return {symbol,default:i.kind===i.originalKind&&JSON.stringify(i.default)===JSON.stringify(i.defaultLabel)?structuredClone(i.defaultAnchor):i.default!==''?bind(i.default,context,symbol.kind):null};});const body=steps(w.steps,scope);return {id:String(w.id),name:w.name,description:w.description??'',inputs,outputs:w.outputs.map((o:EditorDocument)=>({symbol:{id:String(o.uid??crypto.randomUUID()),name:o.name,kind:kind(o.kind)},value:o.kind===o.originalKind&&JSON.stringify(o.value)===JSON.stringify(o.valueLabel)?structuredClone(o.valueAnchor):bind(o.value,scope,kind(o.kind))})),steps:body};});
 base.rules=d.rules.map((r:EditorDocument)=>({id:String(r.id),name:r.name,enabled:r.enabled,feedback:r.feedback!==false,gestureId:r.gestureId,auxiliaryButtons:r.modifier===r.originalModifier?structuredClone(r.auxiliaryButtons):r.modifier==='无'?[]:[modifiers[r.modifier]],applicationId:r.applicationId||null,titleMatch:r.titleMatch,steps:steps(r.steps,new Map(context))}));
 base.snippets=d.snippets.map((t:EditorDocument)=>({id:String(t.id),key:t.key,value:t.value,enabled:t.enabled,applicationId:t.applicationId||null,trigger:t.trigger,caseSensitive:t.caseSensitive!==false,boundary:t.boundary!==false,preserve:t.keepDelimiter!==false}));
 return base;
}
