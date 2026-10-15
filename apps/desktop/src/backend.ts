import { invoke } from '@tauri-apps/api/core';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { listen } from '@tauri-apps/api/event';
import { toConfig, fromConfig, setCatalog, type EditorDocument } from './adapter';
import definitions from '../../../crates/model/action-catalog.json';
import type { Snapshot, Reply, Status, RuntimeInfo, ActionCapability, MouseDevice, RecognitionRequest, RecognitionResult, ConfigurationRequest } from './generated/protocol';
import { PROTOCOL_VERSION } from './generated/protocol';
import type { TextMatchRequest, TextExpansion } from './generated/protocol';
export class Backend {
 revision=0;connected=false;lastError='';pendingWrites=0;
 onError=(message:string)=>console.error(message);
 onConnection=(_connected:boolean)=>{};
 onPage=(_page:string)=>{};
 async setup(operation:'extension'|'input'){const result=await invoke<{message:string,restartRequired:boolean}>('setup_operation',{operation});await this.reconnect();return result;}
 async launchPage(){return invoke<string|null>('launch_page');}
 onRuntime=(_event:Record<string,unknown>)=>{};
 runtime:RuntimeInfo|null=null;
 capabilities:ActionCapability[]=[];
 private capabilityGeneration=0;
 async getCapabilities(){const generation=++this.capabilityGeneration;const capabilities=await this.call<ActionCapability[]>('get_action_capabilities');if(generation===this.capabilityGeneration)this.capabilities=capabilities;return this.capabilities;}
 onConfig=(_document:EditorDocument)=>false;
 private writing=false;
 private tail:Promise<unknown>=Promise.resolve();
 async call<T>(method:string,payload:unknown=''):Promise<T> {
  const raw=await invoke<string>('core_call',{method,payload:typeof payload==='string'?payload:JSON.stringify(payload)});
  const reply=JSON.parse(raw) as Reply<T>;
  if(reply.status==='error')throw new Error(reply.error.message+'\n'+reply.error.details.map(d=>d.path+'：'+d.message).join('\n'));
  return reply.value;
 }
 async snapshot():Promise<Snapshot>{const status=await this.getStatus();if(status.protocolVersion!==PROTOCOL_VERSION)throw new Error('后台协议版本不兼容，请使用配套版本');return this.call<Snapshot>('get_config');}
 async initialize():Promise<EditorDocument> {
  setCatalog(definitions);
  await listen<string>('navigate-request',event=>this.onPage(event.payload));
  await listen<boolean>('core-connected',event=>{if(event.payload)this.reconnect().catch(error=>{this.connected=false;this.lastError=String(error);this.onConnection(false)});else{this.connected=false;this.runtime=null;this.capabilityGeneration++;this.capabilities=[];this.lastError='后台连接已中断，请重新连接后保存。';this.onConnection(false)}});
  await listen<string>('config-changed',event=>{if(!this.connected)return;const snapshot=JSON.parse(event.payload) as Snapshot;if(!this.writing&&snapshot.revision>this.revision&&this.onConfig(fromConfig(snapshot.config)))this.revision=snapshot.revision;});
  await listen<string>('runtime-changed',event=>{if(!this.connected)return;const update=JSON.parse(event.payload);if(update.event==='capability'){const previous=this.runtime;this.runtime=update.runtime;if(previous?.status.extensionConnected!==this.runtime?.status.extensionConnected||previous?.locked!==this.runtime?.locked){this.capabilities=[];this.getCapabilities().then(()=>{if(this.connected&&this.runtime)this.onRuntime({event:'capability',runtime:this.runtime});}).catch(error=>{if(this.connected)this.onError('无法取得动作能力：'+String(error));});}}this.onRuntime(update)});
  try{this.runtime=await this.call<RuntimeInfo>('get_runtime');await this.getCapabilities().catch(()=>{});const snapshot=await this.snapshot();this.revision=snapshot.revision;this.connected=true;return fromConfig(snapshot.config);}
  catch(error){this.lastError=String(error);this.connected=false;const fallback=JSON.parse(await invoke<string>('default_config')) as Snapshot;return fromConfig(fallback.config);}
 }

 save(document:EditorDocument):Promise<EditorDocument> {
  this.pendingWrites++;const task=this.tail.catch(()=>{}).then(async()=>{
   try{if(!this.connected)throw new Error(this.lastError||'后台未连接，请重新连接后保存。');this.writing=true;const snapshot=await this.call<Snapshot>('commit_config',{requestId:crypto.randomUUID(),expectedRevision:this.revision,config:toConfig(document)});this.revision=snapshot.revision;return fromConfig(snapshot.config);}
   catch(error){this.onError(String(error));throw error;}finally{this.writing=false;this.pendingWrites--;}
  });this.tail=task;return task;
 }
 async configuration<T=unknown>(operation:string,fields:Record<string,unknown>={}){await this.flush();return this.call<T>('configuration',{operation,...fields} as ConfigurationRequest);}
 async applyConfiguration(operation:string,fields:Record<string,unknown>){await this.flush();this.writing=true;try{const snapshot=await this.configuration<Snapshot>(operation,{...fields,expectedRevision:this.revision});this.revision=snapshot.revision;return fromConfig(snapshot.config);}finally{this.writing=false;}}
 async exportFile(operation:string,id?:string){const result=operation==='export_diagnostics'?await this.call<{content:string}>('export_diagnostics'):await this.configuration<{content:string}>(operation,id?{id}:{});return invoke<boolean>('save_file',{content:result.content,name:operation==='export_diagnostics'?'diagnostics':id?'backup':'config'});}
 async validate(document:EditorDocument){return this.call<{path:string,message:string}[]>('validate_document',toConfig(document));}
 async runRule(ruleId:string,context:RecognitionRequest['context']){return this.call<{executionId:string}>('run_rule',{ruleId,context});}
 async control(operation:string){return this.call('runtime_control',{operation});}
 async recognize(request:RecognitionRequest){return this.call<RecognitionResult>('recognize_stroke',request);}
 async compare(points:number[][],samples:number[][][]){return this.call<number[]>('compare_strokes',{points,samples});}
 async testTextRule(request:TextMatchRequest){await this.flush();return this.call<TextExpansion|null>('test_text_rule',request);}
 async getRuntime(){this.runtime=await this.call<RuntimeInfo>('get_runtime');this.onRuntime({event:'capability',runtime:this.runtime});return this.runtime;}
 async listDevices(){return this.call<MouseDevice[]>('list_devices');}
 async listWindows(){return this.call<{handle:{instance:string,id:string},title:string,applicationId:string}[]>('list_windows');}
 async getStatus(){return this.call<Status>('get_status');}
 async reconnect(){const snapshot=await this.snapshot();if(snapshot.revision!==this.revision&&this.onConfig(fromConfig(snapshot.config)))this.revision=snapshot.revision;this.connected=true;this.lastError='';await this.getRuntime();await this.getCapabilities().catch(()=>{});this.onConnection(true);}
 async flush(){if(this.pendingWrites>0)await this.tail;}
 async windowAction(action:string){const window=getCurrentWindow();if(action==='minimize')await window.minimize();else if(action==='close')await window.destroy();else if(action==='quit'){await this.call('quit');await window.destroy();}}
}
