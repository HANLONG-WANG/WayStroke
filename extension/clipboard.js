import Gio from 'gi://Gio';
import Meta from 'gi://Meta';
import GLib from 'gi://GLib';

// The small native source preserves arbitrary MIME bytes; GJS cannot implement
// Meta.SelectionSource.read_async, whose vfunc takes an async callback.
let native=null;
async function source(contents,onRead=null){
    native??=(await import('gi://WayStrokeClipboard?version=1.0')).default;
    const bytes=Object.fromEntries([...contents].map(([name,bytes])=>[name,bytes.toArray()]));
    const value=native.source_new(new GLib.Variant('a{say}',bytes));
    if(onRead)value.connect('read',(_source,mimetype)=>onRead(mimetype));return value;
}
export const clipboardSource=source;
// X11 advertises selection-management targets alongside data formats. These
// are queries/commands, not content to back up (some even change the source).
const selectionTargets=new Set(['TARGETS','TIMESTAMP','MULTIPLE','SAVE_TARGETS','DELETE','INSERT_SELECTION','INSERT_PROPERTY']);
export async function snapshot(selection,cancellable){
    const contents=new Map();
    for(const mimetype of selection.get_mimetypes(Meta.SelectionType.SELECTION_CLIPBOARD)||[]){
        if(selectionTargets.has(mimetype))continue;
        const stream=Gio.MemoryOutputStream.new_resizable();
        await new Promise((resolve,reject)=>selection.transfer_async(Meta.SelectionType.SELECTION_CLIPBOARD,mimetype,-1,stream,cancellable,(object,result)=>{try{object.transfer_finish(result);resolve()}catch(error){reject(error)}}));
        stream.close(null);contents.set(mimetype,stream.steal_as_bytes());
    }
    return contents;
}

const TYPE=Meta.SelectionType.SELECTION_CLIPBOARD;
function canceled(){return Object.assign(Error('剪贴板操作已取消'),{kind:'canceled'})}
function textContents(text){const bytes=new GLib.Bytes(new TextEncoder().encode(text));return new Map([['text/plain;charset=utf-8',bytes],['text/plain',bytes]])}
export class ClipboardBridge {
    constructor(selection,changed){
        this.selection=selection;this.changed=changed;this.version=0;this.owner=null;this.pending=new Set();this.paste=null;
        this.signal=selection.connect('owner-changed',(_selection,type,owner)=>{if(type===TYPE){this.owner=owner;this.version++;changed({event:'clipboardChanged',version:this.version})}});
    }
    async task(operation){
        const cancel=new Gio.Cancellable();this.pending.add(cancel);
        try{return await operation(cancel)}catch(error){if(cancel.is_cancelled())throw canceled();throw error}finally{this.pending.delete(cancel)}
    }
    async read(){return this.task(cancel=>this.readText(cancel))}
    async readText(cancel){
        const types=this.selection.get_mimetypes(TYPE)||[];
        if(!types.length)return '';
        const mime=['text/plain;charset=utf-8','text/plain','UTF8_STRING'].find(type=>types.includes(type));
        if(!mime)throw Object.assign(Error('当前剪贴板不包含可读取的文本'),{kind:'unavailable'});
        const stream=Gio.MemoryOutputStream.new_resizable();
        await new Promise((resolve,reject)=>this.selection.transfer_async(TYPE,mime,-1,stream,cancel,(selection,result)=>{try{selection.transfer_finish(result);resolve()}catch(error){reject(error)}}));
        stream.close(null);return new TextDecoder('utf-8',{fatal:true}).decode(stream.steal_as_bytes().toArray());
    }
    async readSelection(send){return this.task(async cancel=>{
        if(this.paste||this.copy)throw Object.assign(Error('已有临时剪贴板操作'),{kind:'conflict'});
        const copy={owner:null};this.copy=copy;
        let original,empty,signal=0,canceledSignal=0,timeout=0;
        try{
            const version=this.version,contents=await snapshot(this.selection,cancel);
            original=await clipboardSource(contents);empty=contents.size===0;
            if(this.version!==version)throw Object.assign(Error('剪贴板在准备读取选区时发生变化'),{kind:'conflict'});
            // Only the client's copy is bounded; a slow backup of the user's
            // clipboard must not count as a window that exports nothing.
            timeout=GLib.timeout_add(GLib.PRIORITY_DEFAULT,300,()=>{timeout=0;cancel.cancel();return GLib.SOURCE_REMOVE});
            const changed=new Promise((resolve,reject)=>{
                signal=this.selection.connect('owner-changed',(_selection,type,owner)=>{if(type===TYPE&&owner&&!copy.owner){copy.owner=owner;resolve()}});
                canceledSignal=cancel.connect(()=>reject(canceled()));
            });
            await Promise.all([send(),changed]);
            const text=await this.readText(cancel);
            return this.owner===copy.owner?text:null;
        }catch(error){if(cancel.is_cancelled())return null;throw error}
        finally{
            if(signal)this.selection.disconnect(signal);
            if(canceledSignal)cancel.disconnect(canceledSignal);
            // Restore every saved MIME format, including on timeout/read failure.
            // A later owner change belongs to the user and wins over restoration.
            if(copy.owner&&this.owner===copy.owner&&original){this.selection.set_owner(TYPE,original);if(empty)this.selection.unset_owner(TYPE,original)}
            this.copy=null;
            if(timeout)GLib.source_remove(timeout);
        }
    })}
    async write(text){return this.writeFormats(textContents(text))}
    async writeFormats(contents){return this.task(async cancel=>{
        if(this.paste)throw Object.assign(Error('临时粘贴尚未结束'),{kind:'conflict'});
        const source=await clipboardSource(contents);if(cancel.is_cancelled())throw canceled();this.selection.set_owner(TYPE,source);return null;
    })}
    async clear(){return this.task(async cancel=>{if(this.paste)throw Object.assign(Error('临时粘贴尚未结束'),{kind:'conflict'});const empty=await clipboardSource(new Map());if(cancel.is_cancelled())throw canceled();this.selection.set_owner(TYPE,empty);this.selection.unset_owner(TYPE,empty);return null})}
    async beginPaste(text,restore,send){return this.task(async cancel=>{
        if(this.paste||this.copy)throw Object.assign(Error('已有临时剪贴板操作'),{kind:'conflict'});
        const version=this.version,contents=await snapshot(this.selection,cancel);
        const original=await clipboardSource(contents);
        const source=await clipboardSource(textContents(text));
        if(cancel.is_cancelled())throw canceled();
        if(this.version!==version)throw Object.assign(Error('剪贴板在准备粘贴时发生变化，请重试'),{kind:'conflict'});
        const paste={token:GLib.uuid_string_random(),source,original,empty:contents.size===0,restore,reads:0,signal:0};
        paste.signal=source.connect('read',()=>{if(this.paste===paste){paste.reads++;this.changed({event:'clipboardPasteRead',token:paste.token})}});
        this.paste=paste;this.selection.set_owner(TYPE,source);
        // Mutter 50.5 synchronously prefetches the selection during owner-changed.
        // That cache read is not the application paste request.
        paste.reads=0;
        try{await send()}catch(error){this.finishPaste(true);throw error}
        return {token:paste.token};
    })}
    pasteStatus(token){
        if(this.paste?.token!==token)throw Object.assign(Error('粘贴会话已失效'),{kind:'targetInvalid'});
        return {read:this.paste.reads>0};
    }
    finishPaste(aborted=false){
        const paste=this.paste;if(!paste)return;
        this.paste=null;paste.source.disconnect(paste.signal);
        // A new user copy wins over restoration of our temporary clipboard.
        if((aborted||paste.restore)&&this.owner===paste.source){
            this.selection.set_owner(TYPE,paste.original);
            if(paste.empty)this.selection.unset_owner(TYPE,paste.original);
        }
    }
    cancel(){for(const cancel of this.pending)cancel.cancel();this.finishPaste(true)}
    disable(){this.cancel();this.selection.disconnect(this.signal)}
}

export async function clipboardCapability(){
    const paths=[...(GLib.getenv('GI_TYPELIB_PATH')||'').split(':').filter(Boolean),'/usr/lib64/girepository-1.0'];
    if(!paths.some(path=>Gio.File.new_for_path(path+'/WayStrokeClipboard-1.0.typelib').query_exists(null)))return {available:false,reason:'未安装 WayStroke 剪贴板原生组件'};
    try{await clipboardSource(new Map());return {available:true,reason:''}}catch(error){return {available:false,reason:error.message}}
}
