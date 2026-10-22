import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GObject from 'gi://GObject';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import {TerminalAdapter} from './terminal.js';
import * as IBusManager from 'resource:///org/gnome/shell/misc/ibusManager.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

// GNOME reports the physical Super modifier as MOD4 on native IM events;
// accept both MOD4 and the virtual SUPER flag when identifying shortcuts.
// Text never leaves this user's session bus and is never written to a log.
export class TextBridge {
    constructor(extension) {
        this.extension=extension;this.im=Main.inputMethod;this.enabled=false;this.generation=0;
        this.grabs=new Map();this.candidates=new Map();this.deliveredPresses=new Set();this.keyQueue=[];this.transaction=0;this.processing=false;this.signals=[];this.timers=new Set();this.frames=new Set();this.immediateCharacters=[];
        this.cancellable=new Gio.Cancellable();this.alive=true;this.terminal=new TerminalAdapter(this);this.coreEpoch=0;this.selectionPrepared=false;
        // Mirrors core's built-in X11 terminal names for the status text.
        this.terminalClasses=new Set(['xterm','uxterm','urxvt','rxvt','st','st-256color','alacritty','kitty','terminator','xfce4-terminal','gnome-terminal','gnome-terminal-server','konsole','tilix','sakura','guake','tilda','termite','wezterm','org.wezfurlong.wezterm','foot','eterm','aterm','mlterm','lxterminal','mate-terminal','qterminal','cool-retro-term','terminology','yakuake','ptyxis','org.gnome.ptyxis','kgx','org.gnome.console','ghostty','com.mitchellh.ghostty','contour','zutty','tabby','hyper','deepin-terminal','x-terminal-emulator']);
        this.ibusManager=IBusManager.getIBusManager();this.panelSignals=[];this.panel=null;this.panelComposing=false;this.connect(this.ibusManager,'ready',()=>{this.reset();this.trackPanel();this.updateGrabs()});this.trackPanel();
        this.connect(this.im._ibus,'disconnected',()=>this.reset());
        this.calibrateKeyboard();
        this.originalNotify=this.im.notify_key_event;
        this.notify=(event,handled)=>{
            if(!this.alive)return this.originalNotify.call(this.im,event,handled);
            if(this.calibration&&event.type()===Clutter.EventType.KEY_PRESS&&event.get_key_symbol()===this.calibrationKey){this.keyboardKnown(event.get_source_device());return this.originalNotify.call(this.im,event,true)}
            if(event.get_source_device()===this.ownedKeyboard){
                if(event.type()===Clutter.EventType.KEY_PRESS)this.reset();
                return this.originalNotify.call(this.im,event,handled);
            }
            const code=event.get_key_code()||event.get_key_symbol();
            // Releases for presses already delivered/consumed must not wait for
            // an edit acknowledgement. Queue complete later key pairs instead.
            if(event.type()===Clutter.EventType.KEY_RELEASE&&this.deliveredPresses.delete(code))return this.originalNotify.call(this.im,event,handled);
            if(this.processing){const copy=event.copy();this.enqueue(()=>this.notify(copy,handled));return this.originalNotify.call(this.im,event,true)}
            if(event.type()===Clutter.EventType.KEY_PRESS){
                this.deliveredPresses.add(code);
                const key=event.get_key_symbol(),modifiers=event.get_state();
                if(!handled&&!this.composing()&&(key===Clutter.KEY_z||key===Clutter.KEY_Z)&&modifiers&Clutter.ModifierType.CONTROL_MASK&&!(modifiers&(Clutter.ModifierType.MOD1_MASK|Clutter.ModifierType.SUPER_MASK|Clutter.ModifierType.MOD4_MASK))&&this.undoLast())return this.originalNotify.call(this.im,event,true);
                if(![Clutter.KEY_Control_L,Clutter.KEY_Control_R,Clutter.KEY_Shift_L,Clutter.KEY_Shift_R].includes(key))this.undo=null;
                this.generation++;this.lastInput=null;
                if(!handled&&(modifiers&(Clutter.ModifierType.CONTROL_MASK|Clutter.ModifierType.MOD1_MASK|Clutter.ModifierType.SUPER_MASK|Clutter.ModifierType.MOD4_MASK)))this.clearNativeInput();
                if(this.terminal.key(event,handled))return this.originalNotify.call(this.im,event,true);
                if(!handled&&!this.composing()&&!(modifiers&(Clutter.ModifierType.CONTROL_MASK|Clutter.ModifierType.MOD1_MASK|Clutter.ModifierType.SUPER_MASK|Clutter.ModifierType.MOD4_MASK))){
                    if(key===Clutter.KEY_space||key===Clutter.KEY_Return){
                        const snapshot=this.snapshot();
                        this.candidates.set(event.get_time(),{snapshot});
                        if(this.candidates.size>32)this.candidates.delete(this.candidates.keys().next().value);
                        if(snapshot){
                            const grab={key,code:event.get_key_code(),trigger:key===Clutter.KEY_space?'space':'enter'};
                            this.run(async()=>{const ready=await this.waitNativeInput();this.candidates.set(event.get_time(),{snapshot:ready?this.snapshot():null});return this.confirm(grab,event.get_time())}).catch(e=>this.failure(e));
                            return this.originalNotify.call(this.im,event,true);
                        }
                    }else if(Clutter.keysym_to_unicode(key)>=32){this.noteNativeInput(String.fromCodePoint(Clutter.keysym_to_unicode(key)));this.lastInput=this.generation}else this.clearNativeInput();
                }
            }
            return this.originalNotify.call(this.im,event,handled);
        };
        this.im.notify_key_event=this.notify;
        this.originalCommit=this.im.commit;
        this.commit=text=>{
            if(!this.alive)return this.originalCommit.call(this.im,text);
            if(this.processing&&!this.applying){this.enqueue(()=>this.commit(text));return}
            this.terminal.committed(text);
            if(this.enabled&&!this.applying&&!this.terminal.focused())this.noteNativeInput(text);
            if(this.enabled&&!this.applying&&!this.extension.locked())this.lastInput=this.generation;
            return this.originalCommit.call(this.im,text);
        };
        this.im.commit=this.commit;
        this.originalPreedit=this.im.set_preedit_text;
        this.preedit=(...args)=>{
            const result=this.originalPreedit.apply(this.im,args);
            // IBus commits before clearing its preedit flags. Resume only after
            // the caller has cleared them and the client reports committed text.
            if(this.alive&&!args[0]&&(this.nativeExpected||this.terminal.commitContext))this.later(0,()=>{this.surroundingChanged();this.terminal.resumeCommitted()});
            return result;
        };
        this.im.set_preedit_text=this.preedit;
        this.originalReset=this.im._fullReset;
        this.fullReset=(...args)=>{this.reset();return this.originalReset.apply(this.im,args)};
        this.im._fullReset=this.fullReset;
        this.connect(this.im,'surrounding-text-set',()=>this.surroundingChanged());
        this.connect(global.display,'notify::focus-window',()=>{this.accessibleBlockedWindow=null;this.reset();this.prepareSelection();if(this.calibration)this.later(0,()=>this.sendCalibration());for(const grab of this.grabs.values())Main.wm.allowKeybinding(grab.binding,this.bindingMode())});
        this.connect(Main.sessionMode,'updated',()=>{this.reset();this.updateGrabs();this.prepareSelection()});
        this.connect(global.display,'accelerator-activated',(_display,id,device,time)=>{
            if(id===this.calibration){this.keyboardKnown(device);return}
            if(this.grabs.has(id)){
                const event=Clutter.get_current_event();let grab={...this.grabs.get(id),code:event?.get_key_code()||this.grabs.get(id).code,modifiers:event?.get_state()||0,rawModifiers:event?.get_key_state()||[0,0,0]};
                if(grab.trigger==='literal'){const key=Clutter.get_current_event()?.get_key_symbol()||grab.key;grab={...grab,key,text:String.fromCodePoint(Clutter.keysym_to_unicode(key))}}
                this.run(()=>this.confirm(grab,time)).catch(e=>this.failure(e));
            }
        });
        this.connect(global.window_manager,'filter-keybinding',(_wm,binding)=>{const own=[...this.grabs.values()].some(grab=>grab.binding===binding.get_name());return !!own&&Clutter.get_current_event()?.get_source_device()===this.ownedKeyboard});
        this.configSubscription=Gio.DBus.session.signal_subscribe('io.github.waystroke.Core','io.github.waystroke.Core1','ConfigChanged','/io/github/waystroke/Core',null,Gio.DBusSignalFlags.NONE,(_bus,sender,_path,_interface,_signal,args)=>{if(sender===this.coreOwner)this.configure(JSON.parse(args.deep_unpack()[0]))});
        this.runtimeSubscription=Gio.DBus.session.signal_subscribe('io.github.waystroke.Core','io.github.waystroke.Core1','RuntimeChanged','/io/github/waystroke/Core',null,Gio.DBusSignalFlags.NONE,(_bus,sender,_path,_interface,_signal,args)=>{if(sender!==this.coreOwner)return;const event=JSON.parse(args.deep_unpack()[0]);if(event.event==='textCapability'&&event.adapter==='atspi'&&event.state!=='available')this.accessibleUndo=null;else if(event.event==='textExpansion'&&event.adapter==='atspi'&&event.undoToken)this.accessibleUndo={token:event.undoToken}});
        this.ownerWatch=Gio.bus_watch_name_on_connection(Gio.DBus.session,'io.github.waystroke.Core',Gio.BusNameWatcherFlags.NONE,(_bus,_name,owner)=>{this.coreOwner=owner;this.refresh().catch(e=>this.failure(e))},()=>{this.coreOwner=undefined;this.coreEpoch++;this.enabled=false;this.configRevision=undefined;this.selectionPrepared=false;this.reset();this.updateGrabs()});
    }
    calibrateKeyboard(){
        for(const name of ['F23','F22','F21']){const id=global.display.grab_accelerator(name,Meta.KeyBindingFlags.NONE);if(id){this.calibration=id;this.calibrationKey=Clutter['KEY_'+name];break}}
        if(!this.calibration){this.extension.changed({event:'textCapability',adapter:'atspi',state:'limited',reason:'本程序合成输入身份确认键不可用'});return}
        Main.wm.allowKeybinding('external-grab-'+this.calibration,Shell.ActionMode.NORMAL);
        const send=()=>this.sendCalibration();
        if(Main.layoutManager._startingUp)this.connect(Main.layoutManager,'startup-complete',send);else this.later(0,send);
    }
    sendCalibration(){
        // The first startup attempt can run in the overview before NORMAL
        // bindings are allowed. Retry when an application gains focus.
        if(!this.calibration||Main.actionMode!==Shell.ActionMode.NORMAL)return;
        const now=GLib.get_monotonic_time();this.extension.keyboard.notify_keyval(now,this.calibrationKey,Clutter.KeyState.PRESSED);this.extension.keyboard.notify_keyval(now+1,this.calibrationKey,Clutter.KeyState.RELEASED);
    }
    keyboardKnown(device){
        this.ownedKeyboard=device;global.display.ungrab_accelerator(this.calibration);this.calibration=0;this.updateGrabs();
    }
    trackPanel(){
        for(const [panel,id] of this.panelSignals)if(GObject.signal_handler_is_connected(panel,id))panel.disconnect(id);this.panelSignals=[];
        this.panel=this.ibusManager._panelService;this.panelComposing=false;if(!this.panel)return;
        const connect=(name,handler)=>this.panelSignals.push([this.panel,this.panel.connect(name,handler)]);
        connect('destroy',()=>{this.panelSignals=[];this.panel=null;this.panelPreedit=false;this.panelLookup=false;this.panelComposing=false;this.reset();this.updateGrabs()});
        this.panelPreedit=false;this.panelLookup=false;
        const update=()=>this.panelComposing=this.panelPreedit||this.panelLookup;
        connect('update-preedit-text',(_panel,_text,_cursor,visible)=>{this.panelPreedit=visible;update()});
        connect('show-preedit-text',()=>{this.panelPreedit=true;update()});connect('hide-preedit-text',()=>{this.panelPreedit=false;update()});
        connect('update-lookup-table',(_panel,_table,visible)=>{this.panelLookup=visible;update()});
        connect('show-lookup-table',()=>{this.panelLookup=true;update()});connect('hide-lookup-table',()=>{this.panelLookup=false;update()});
        connect('focus-out',()=>{this.panelPreedit=false;this.panelLookup=false;update()});
    }
    status(){
        const window=global.display.focus_window,applicationId=window?this.extension.windowInfo(window).applicationId:null;
        const status={connected:this.alive,enabled:!!this.preferenceEnabled,terminalEnabled:!!this.terminal.enabled,adapter:'none',state:'unavailable',applicationId,reason:'当前应用没有可靠的编辑上下文。',undoAvailable:!!this.undo||!!this.accessibleUndo};
        if(this.extension.locked())return {...status,state:'locked',reason:'锁屏时停止文本处理，并清除待处理替换与撤销记录。',undoAvailable:false};
        if(!this.preferenceEnabled)return {...status,state:'disabled',reason:'文本替换已关闭，原输入透传。'};
        if(!this.hasRules)return {...status,state:'empty',reason:'尚无已启用的文本规则；可新建规则后使用。'};
        if(this.excludedApplications?.has(applicationId))return {...status,state:'excluded',reason:'此应用已排除文本替换，原输入透传。',undoAvailable:false};
        if(this.composing()||this.panelComposing)return {...status,state:'composing',reason:'输入法组合期间暂缓替换，不重放已消费的确认键。',undoAvailable:false};
        if(window?.get_client_type()===Meta.WindowClientType.X11){
            if(this.accessibleBlockedWindow===window)return {...status,adapter:'atspi',state:'unavailable',reason:'此窗口的编辑接口未可靠响应，已暂缓文本替换；空格、回车等原键正常输入。切换窗口后重试。',undoAvailable:false};
            if(!this.terminal.native?.x11_replay)return {...status,adapter:'atspi',reason:'XWayland 确认转发组件尚未就绪，原输入透传。',undoAvailable:false};
            if(!this.ownedKeyboard||!this.panel)return {...status,adapter:'atspi',state:'partial',reason:'XWayland 输入来源或组合状态尚不可确认。'};
            const fallback=this.compatibilityExcluded?.has(applicationId)?'此应用已停用兼容替换，只在焦点提供编辑接口时替换。':this.terminalClasses.has((window.get_wm_class()||'').toLowerCase())?'X11 终端不使用兼容替换，只在焦点提供编辑接口时替换。':'没有编辑接口时以选区校验兼容替换，替换时会短暂选中关键词。';
            return {...status,adapter:'atspi',state:'partial',reason:'XWayland 焦点提供 Text/EditableText 接口时直接编辑；'+fallback+'不代表所有应用可编辑。'};
        }
        if(!this.im._context)return {...status,state:'unavailable',reason:'输入法连接尚未就绪，原输入透传。',undoAvailable:false};
        if(this.terminal.focused()){
            if(this.terminal.enabled&&!this.terminal.watch)return {...status,adapter:'terminal',state:'unavailable',reason:'终端粘贴观察组件尚未就绪，原输入透传。',undoAvailable:false};
            return {...status,adapter:'terminal',state:this.terminal.enabled?'partial':'disabled',reason:this.terminal.enabled?'终端普通与密码输入均参与；canonical/Readline/getpass 支持，raw/TUI 无法确认文档编辑结果。':'整个终端路径已关闭，原输入透传。'};
        }
        if(this.im.currentFocus&&(this.sensitive()))return {...status,state:'password',reason:'非终端密码字段已跳过，不读取或编辑密码文本。',undoAvailable:false};
        if(this.snapshot())return {...status,adapter:'native',state:'ready',reason:'当前应用提供周围文本与编辑上下文，替换前后校验焦点、范围和光标。'};
        return status;
    }
    guard(){
        const window=global.display.focus_window;if(!window)return null;
        const info=this.extension.windowInfo(window);
        return {instance:this.extension.instance,generation:this.generation,window:info.handle,applicationId:info.applicationId,pid:window.get_pid(),clientType:window.get_client_type(),composing:this.composing()||this.panelComposing,imeKnown:!!this.panel,locked:this.extension.locked(),enabled:this.enabled&&!this.excludedApplications?.has(info.applicationId),wmClass:window.get_wm_class()||''};
    }
    sameGuard(expected){
        const actual=this.guard();
        return !!actual&&!!expected&&['instance','generation','pid','locked','enabled'].every(key=>actual[key]===expected[key])&&actual.window.instance===expected.window?.instance&&actual.window.id===expected.window?.id;
    }
    // Core keeps an XWayland connection only while an X11 window has focus;
    // Shell's environment names the current display and its cookie file.
    prepareSelection(){
        const window=global.display.focus_window,active=!!this.coreOwner&&this.enabled&&!this.extension.locked()&&window?.get_client_type()===Meta.WindowClientType.X11;
        if(!active&&!this.selectionPrepared)return;
        this.selectionPrepared=active;
        this.rpc('PrepareSelectionText',{active,display:GLib.getenv('DISPLAY'),xauthority:GLib.getenv('XAUTHORITY')},1500).catch(error=>this.failure(error,'selection'));
    }
    clearAccessibleUndo(){
        const undo=this.accessibleUndo;this.accessibleUndo=null;
        if(undo&&this.alive)this.rpc('ClearAccessibleText',{token:undo.token}).catch(error=>this.failure(error));
    }
    clearNativeInput(){for(const resolve of this.nativeExpected?.waiters||[])resolve(false);this.nativeExpected=null;this.nativeUnsettled=true}
    noteNativeInput(text){
        if(!text)return;
        const snapshot=this.snapshot(true,true);if(!snapshot||snapshot.adapter==='terminal')return;
        const previous=this.nativeExpected,base=previous||snapshot,ticket=previous?.ticket||{};
        if(this.nativeUnsettled||base.inserted!==undefined||base.cursor!==base.anchor){
            // A deletion/shortcut may not produce a fresh surrounding report.
            // Bind the actual committed input, without predicting from that cache.
            this.nativeExpected={...snapshot,text:null,inserted:(base.inserted||'')+text,ticket,waiters:base.waiters||[]};
        }else{
            const points=[...base.text];
            this.nativeExpected={...base,text:points.slice(0,base.cursor).join('')+text+points.slice(base.cursor).join(''),cursor:base.cursor+[...text].length,ticket,waiters:base.waiters||[]};
        }
        if(!previous)this.later(500,()=>{if(this.nativeExpected?.ticket===ticket){this.clearNativeInput();this.lastInput=null}});
    }
    waitNativeInput(){
        if(!this.nativeExpected)return Promise.resolve(true);
        const expected=this.nativeExpected;
        return new Promise(resolve=>{expected.waiters.push(resolve);this.later(300,()=>{if(this.nativeExpected===expected)this.clearNativeInput()})});
    }
    enqueue(callback,cancel){this.keyQueue.push({callback,cancel,focus:this.im.currentFocus,window:global.display.focus_window})}
    drain(){
        if(this.processing||!this.keyQueue.length)return;
        const item=this.keyQueue.shift();
        if(this.alive&&item.focus===this.im.currentFocus&&item.window===global.display.focus_window)item.callback();else item.cancel?.();
        if(!this.processing&&this.keyQueue.length){this.processing=true;const transaction=this.transaction;this.afterInputFrame(()=>{if(transaction===this.transaction){this.processing=false;this.drain()}})}
    }
    run(operation){
        if(this.processing)return new Promise((resolve,reject)=>this.enqueue(()=>this.run(operation).then(resolve,reject),()=>resolve({stale:true})));
        this.processing=true;const transaction=++this.transaction;
        return Promise.resolve().then(operation).finally(()=>{
            // Clutter dispatches IM commits during the stage update. Mutter then
            // sends text-input-v3 done at CLUTTER_PRIORITY_EVENTS + 1.
            // Keep later commits behind that boundary so clients do not replace
            // an earlier commit_string with the next one in the same batch.
            if(transaction===this.transaction)this.afterInputFrame(()=>{if(transaction===this.transaction){this.processing=false;this.drain()}});
        });
    }
    afterInputFrame(callback){
        const id=global.stage.connect('after-update',()=>{
            global.stage.disconnect(id);this.frames.delete(id);
            this.later(0,callback,GLib.PRIORITY_DEFAULT_IDLE);
        });
        this.frames.add(id);
        // A pending key release need not damage any actor. Request a frame,
        // otherwise an idle Devkit stage can leave this input fence unserviced.
        global.stage.queue_redraw();
    }
    connect(object,name,callback){this.signals.push([object,object.connect(name,callback)])}
    async rpc(method,payload,timeout=500) {
        return new Promise((resolve,reject)=>Gio.DBus.session.call('io.github.waystroke.Core','/io/github/waystroke/Core','io.github.waystroke.Core1',method,payload===undefined?null:new GLib.Variant('(s)',[JSON.stringify(payload)]),new GLib.VariantType('(s)'),Gio.DBusCallFlags.NONE,timeout,this.cancellable,(bus,result)=>{
            try{const reply=JSON.parse(bus.call_finish(result).deep_unpack()[0]);if(reply.status==='error')throw Object.assign(Error(reply.error.message),{kind:reply.error.kind,details:reply.error.details});resolve(reply.value)}catch(e){reject(e)}
        }));
    }
    async refresh(){const epoch=this.coreEpoch,snapshot=await this.rpc('GetConfig');if(epoch===this.coreEpoch)this.configure(snapshot)}
    configure(snapshot){
        if(!this.alive||this.configRevision!==undefined&&snapshot.revision<=this.configRevision)return;
        this.configRevision=snapshot.revision;
        this.accessibleBlockedWindow=null;
        this.preferenceEnabled=snapshot.config.settings.textEnabled;this.hasRules=snapshot.config.snippets.some(rule=>rule.enabled);
        this.enabled=this.preferenceEnabled&&this.hasRules;
        this.excludedApplications=new Set(snapshot.config.exclusions.filter(entry=>entry.text).map(entry=>entry.applicationId));
        this.compatibilityExcluded=new Set(snapshot.config.exclusions.filter(entry=>entry.compatibility).map(entry=>entry.applicationId));
        this.immediateCharacters=[...new Set(snapshot.config.snippets.filter(rule=>rule.enabled&&rule.trigger==='immediate').flatMap(rule=>{const char=[...rule.key].at(-1);return !char?[]:rule.caseSensitive?[char]:[char.toLowerCase(),char.toUpperCase()]}))];
        this.terminal.configure(snapshot.config);this.reset(true);this.updateGrabs();this.prepareSelection();
    }
    reset(preserveInput=false){
        // Configuration changes invalidate edits, but ordinary input already
        // intercepted for the same focus must still reach the application.
        const input=preserveInput?this.keyQueue.filter(item=>!item.cancel):[];
        for(const id of this.frames)global.stage.disconnect(id);this.frames.clear();this.deliveredPresses.clear();this.clearAccessibleUndo();this.clearNativeInput();
        for(const item of this.keyQueue)item.cancel?.();this.keyQueue=input;this.processing=false;this.transaction++;this.pendingEdit?.resolve(false);this.generation++;this.lastInput=null;this.candidates.clear();this.pendingEdit=null;this.applying=false;this.undo=null;this.terminal.clear(true);
        if(preserveInput)this.drain();
    }
    composing(){return this.im.hasPreedit()}
    sensitive(){return this.im.content_purpose===Clutter.InputContentPurpose.PASSWORD||!!(this.im.content_hints&(Clutter.InputContentHintFlags.HIDDEN_TEXT|Clutter.InputContentHintFlags.SENSITIVE_DATA))}
    snapshot(allowComposition=false,allowSelection=false){
        if(this.terminal.focused())return this.terminal.snapshot();
        if(!this.enabled||!this.im._context||this.extension.locked()||(this.composing()&&!allowComposition)||!this.im.currentFocus||this.im.content_purpose===Clutter.InputContentPurpose.TERMINAL)return null;
        if(this.sensitive())return null;
        const window=global.display.focus_window;if(!window)return null;
        const applicationId=this.extension.windowInfo(window).applicationId;
        if(this.excludedApplications?.has(applicationId))return null;
        const [text,cursor,anchor]=this.im.getSurroundingText();
        if(text===null||cursor===null||(!allowSelection&&cursor!==anchor))return null;
        return {focus:this.im.currentFocus,window,text,cursor,anchor,generation:this.generation,applicationId};
    }
    same(a,b){return !!a&&!!b&&a.focus===b.focus&&a.window===b.window&&a.text===b.text&&a.cursor===b.cursor&&a.anchor===b.anchor&&a.generation===b.generation}
    surroundingChanged(){
        if(this.pendingEdit){
            const actual=this.snapshot(),expected=this.pendingEdit;
            if(actual&&actual.focus===expected.focus&&actual.window===expected.window){
                const full=actual.text===expected.text&&actual.cursor===expected.cursor&&actual.anchor===expected.cursor;
                // Firefox reports only the paragraph containing the caret after
                // a multiline commit. Acknowledge that exact paragraph, but do
                // not retain an undo range outside the reported surrounding text.
                const points=[...expected.text],start=points.lastIndexOf('\n',expected.cursor-1)+1,next=points.indexOf('\n',expected.cursor),end=next<0?points.length:next;
                const paragraph=points.includes('\n')&&actual.text===points.slice(start,end).join('')&&actual.cursor===expected.cursor-start&&actual.anchor===actual.cursor;
                if(full||paragraph){
                    expected.clipped=!full;this.pendingEdit=null;this.applying=false;expected.resolve(true);
                    this.extension.changed({event:'textExpansion',adapter:'native',state:full?(expected.state||'succeeded'):'submittedPartial',ruleId:expected.ruleId,reason:full?undefined:'应用仅回报当前段落；完整替换范围不可用于受控撤销。'});
                }
            }
            return;
        }
        if(this.undo){
            const actual=this.snapshot(),undo=this.undo;
            const points=[...undo.text];
            if(actual&&actual.focus===undo.focus&&actual.window===undo.window&&undo.confirmation&&actual.text===points.slice(0,undo.cursor).join('')+undo.confirmation+points.slice(undo.cursor).join('')&&actual.cursor===undo.cursor+1){
                const before=[...undo.before];undo.before=before.slice(0,undo.beforeCursor).join('')+undo.confirmation+before.slice(undo.beforeCursor).join('');undo.beforeCursor++;undo.text=actual.text;undo.cursor=actual.cursor;undo.anchor=actual.anchor;undo.confirmation='';
            }else if(!this.same({...undo,generation:this.generation},actual))this.undo=null;
        }
        if(this.nativeExpected){
            const expected=this.nativeExpected,actual=this.snapshot();
            if(!actual||actual.focus!==expected.focus||actual.window!==expected.window||actual.cursor!==actual.anchor)return;
            const committed=expected.inserted!==undefined?[...actual.text].slice(0,actual.cursor).join('').endsWith(expected.inserted):actual.text===expected.text&&actual.cursor===expected.cursor;
            if(!committed)return;
            this.nativeExpected=null;this.nativeUnsettled=false;this.lastInput=null;
            for(const resolve of expected.waiters)resolve(true);
            if(!expected.waiters.length)this.run(()=>this.expand(actual,'commit')).catch(error=>this.failure(error));
            return;
        }
        if(this.applying||this.lastInput!==this.generation)return;
        this.lastInput=null;
        const snapshot=this.snapshot();
        if(snapshot)this.run(()=>this.expand(snapshot,'commit')).catch(e=>this.failure(e));
    }
    async expand(snapshot,trigger){
        const result=await this.rpc('TestTextRule',{applicationId:snapshot.applicationId,beforeCursor:(snapshot.adapter==='terminal'&&snapshot.uncertain?'a':'')+[...snapshot.text].slice(0,snapshot.cursor).join(''),trigger,composing:false,password:false,terminal:snapshot.adapter==='terminal'});
        if(!this.same(snapshot,this.snapshot()))return {stale:true};
        if(!result)return {matched:false};
        const start=snapshot.cursor-result.deleteChars,points=[...snapshot.text];
        if(start<0||points.slice(start,snapshot.cursor).join('')!==result.keyword)throw Error('文本范围已变化，取消替换');
        if(snapshot.adapter==='terminal')return this.terminal.apply(snapshot,result);
        this.applying=true;this.lastInput=null;
        const space=result.preserve&&result.confirmation===' '?' ':'';
        let resolve;const verified=new Promise(done=>resolve=done);
        this.pendingEdit={resolve,...snapshot,text:points.slice(0,start).join('')+result.replacement+space+points.slice(snapshot.cursor).join(''),cursor:start+[...result.replacement+space].length,ruleId:result.ruleId};
        this.pendingEdit.anchor=this.pendingEdit.cursor;
        this.im.delete_surrounding(-result.deleteChars,result.deleteChars);
        this.originalCommit.call(this.im,result.replacement+space);
        const pending=this.pendingEdit;
        this.later(300,()=>{if(this.pendingEdit===pending){this.pendingEdit=null;this.applying=false;this.undo=null;pending.resolve(false);this.extension.changed({event:'textExpansion',adapter:'native',state:'failed',reason:'应用未确认替换后的文本'})}});
        if(!await verified)return {stale:true};
        this.undo=pending.clipped?null:{...pending,before:points.slice(0,snapshot.cursor).join('')+space+points.slice(snapshot.cursor).join(''),beforeCursor:snapshot.cursor+space.length,start,confirmation:space?'':result.preserve?result.confirmation:''};
        return {matched:true,preserve:result.preserve,confirmationHandled:!!space};
    }
    undoLast(){
        const undo=this.undo,actual=this.snapshot();
        if(!undo||!this.same({...undo,generation:this.generation},actual))return false;
        if(undo.adapter==='terminal')return this.terminal.undo(undo,actual);
        this.undo=null;this.lastInput=null;this.applying=true;
        this.pendingEdit={...actual,text:undo.before,cursor:undo.beforeCursor,anchor:undo.beforeCursor,ruleId:undo.ruleId,state:'undone',resolve:()=>{}};
        const count=actual.cursor-undo.start;
        this.im.delete_surrounding(-count,count);
        this.originalCommit.call(this.im,[...undo.before].slice(undo.start,undo.beforeCursor).join(''));
        const pending=this.pendingEdit;
        this.later(300,()=>{if(this.pendingEdit===pending){this.pendingEdit=null;this.applying=false;pending.resolve(false);this.failure(Error('应用未确认撤销后的文本'))}});
        return true;
    }
    generated(callback){this.reset();this.applying=true;try{return callback()}finally{this.applying=false}}
    bindingMode(){
        const window=global.display.focus_window;
        return this.enabled&&window&&window!==this.accessibleBlockedWindow&&window.get_client_type()===Meta.WindowClientType.X11&&!this.excludedApplications?.has(this.extension.windowInfo(window).applicationId)&&this.ownedKeyboard&&this.panel&&this.terminal.native?.x11_replay?Shell.ActionMode.NORMAL:Shell.ActionMode.NONE;
    }
    updateGrabs(){
        for(const id of this.grabs.keys())global.display.ungrab_accelerator(id);
        this.grabs.clear();
        if(!this.alive||!this.enabled||this.extension.locked())return;
        for(const [name,key,code,trigger] of [['space',Clutter.KEY_space,65,'space'],['Return',Clutter.KEY_Return,36,'enter'],['<Control>z',Clutter.KEY_z,52,'undo']]){
            const id=global.display.grab_accelerator(name,Meta.KeyBindingFlags.NONE);
            if(!id){this.extension.changed({event:'textCapability',adapter:'native',state:'limited',reason:'确认键已被其他桌面功能占用：'+name});continue}
            const binding='external-grab-'+id;this.grabs.set(id,{key,code,trigger,binding});Main.wm.allowKeybinding(binding,this.bindingMode());
        }
        const bindings=new Map();
        if(this.ownedKeyboard)for(const char of this.immediateCharacters){
            const lower=char.toLowerCase(),upper=char.toUpperCase();
            const paired=lower!==upper&&[...lower].length===1&&[...upper].length===1;
            const base=paired?lower:char,key=Clutter.unicode_to_keysym(base.codePointAt(0));
            if(key===Clutter.KEY_space||key===Clutter.KEY_Return)continue;
            const symbol=Object.keys(Clutter).find(name=>name.startsWith('KEY_')&&Clutter[name]===key)?.slice(4);
            if(!symbol)continue;
            bindings.set(symbol,{key,text:base});
            if(paired)bindings.set('<Shift>'+symbol,{key:Clutter.unicode_to_keysym(upper.codePointAt(0)),text:upper});
        }
        for(const [accelerator,literal] of bindings){
            const id=global.display.grab_accelerator(accelerator,Meta.KeyBindingFlags.NONE);
            if(!id){this.extension.changed({event:'textCapability',adapter:'atspi',state:'limited',reason:'立即规则的末字符快捷键被占用：'+accelerator});continue}
            const binding='external-grab-'+id;this.grabs.set(id,{...literal,trigger:'literal',binding});Main.wm.allowKeybinding(binding,this.bindingMode());
        }
    }
    async confirm(grab,time){
        const focus=this.im.currentFocus,window=global.display.focus_window,generation=this.generation;
        const candidate=this.candidates.get(time),snapshot=candidate?.snapshot;this.candidates.delete(time);
        let result;
        // Selection-verified XWayland edits wait for the client; core bounds them at 1.2 s.
        try{if(grab.trigger==='literal'){const guard=this.guard();if(guard?.enabled&&!guard.composing&&!await this.rpc('NoteAccessibleInput',{guard,text:grab.text}))result=await this.rpc('ExpandAccessibleText',{guard,trigger:'commit',literal:grab.text},1500)}else if(grab.trigger==='undo'){const undo=this.accessibleUndo;this.accessibleUndo=null;if(undo)result=await this.rpc('UndoAccessibleText',{guard:this.guard(),token:undo.token},1500)}else if(snapshot)result=await this.expand(snapshot,grab.trigger);else if(!focus&&window!==this.accessibleBlockedWindow&&this.guard()?.clientType===1){const guard=this.guard();if(guard.enabled&&guard.imeKnown){if(guard.composing&&this.immediateCharacters.length)await this.rpc('NoteAccessibleInput',{guard,text:null});else if(!guard.composing){result=await this.rpc('ExpandAccessibleText',{guard,trigger:grab.trigger},1500);const text=grab.trigger==='space'?' ':'\n';if(result?.matched===false&&this.immediateCharacters.includes(text))await this.rpc('NoteAccessibleInput',{guard,text})}}}}catch(e){
            this.failure(e,window?.get_client_type()===1?'atspi':'native');
            if(window?.get_client_type()===1){
                // Stop intercepting this window after an unreliable accessible
                // call. Only a proven pre-edit failure permits key replay.
                this.accessibleBlockedWindow=window;this.accessibleUndo=null;
                for(const binding of this.grabs.values())Main.wm.allowKeybinding(binding.binding,this.bindingMode());
                if(grab.trigger!=='literal'&&result?.matched!==false&&!e.details?.some(detail=>detail.path==='text.unmodified'))result={stale:true};
            }
        }
        if(!this.alive||this.extension.locked()||generation!==this.generation||window!==global.display.focus_window||focus!==this.im.currentFocus||result?.stale)return;
        if(result?.undoToken)this.accessibleUndo={token:result.undoToken};
        if(grab.trigger==='undo'&&result?.matched)return;
        // A native confirmation must have passed the post-IME notify hook. A
        // consumed composition confirmation is never replayed.
        if(focus&&!candidate)return;
        if(snapshot?.adapter==='terminal'){if(!result?.confirmationHandled)this.terminal.confirmUnmatched(grab);return}
        if(result?.confirmationHandled||result?.matched&&!result.preserve)return;
        if(focus&&result?.matched===false){const text=grab.trigger==='space'?' ':'\n';if(this.immediateCharacters.includes(text)){this.noteNativeInput(text);this.lastInput=this.generation}}
        if(!focus){
            this.terminal.native.x11_replay(this.ownedKeyboard,grab.key,grab.code,grab.modifiers,...grab.rawModifiers);return;
        }
        const stamp=global.display.get_current_time_roundtrip();this.im.forward_key(grab.key,grab.code,0,stamp,true);this.im.forward_key(grab.key,grab.code,0,stamp,false);
    }
    later(delay,callback,priority=GLib.PRIORITY_DEFAULT){const id=GLib.timeout_add(priority,delay,()=>{this.timers.delete(id);if(this.alive)callback();return GLib.SOURCE_REMOVE});this.timers.add(id)}
    failure(error,adapter='native'){if(this.alive)this.extension.changed({event:'textExpansion',adapter,state:'failed',reason:error.message})}
    disable(){
        this.terminal.disable();
        if(this.calibration)global.display.ungrab_accelerator(this.calibration);this.calibration=0;
        for(const [panel,id] of this.panelSignals)if(GObject.signal_handler_is_connected(panel,id))panel.disconnect(id);this.panelSignals=[];
        this.alive=false;this.cancellable.cancel();this.reset();this.updateGrabs();
        if(this.im.notify_key_event===this.notify)this.im.notify_key_event=this.originalNotify;
        if(this.im.commit===this.commit)this.im.commit=this.originalCommit;
        if(this.im.set_preedit_text===this.preedit)this.im.set_preedit_text=this.originalPreedit;
        if(this.im._fullReset===this.fullReset)this.im._fullReset=this.originalReset;
        for(const [object,id] of this.signals)object.disconnect(id);
        for(const id of this.timers)GLib.source_remove(id);
        this.timers.clear();Gio.DBus.session.signal_unsubscribe(this.configSubscription);Gio.DBus.session.signal_unsubscribe(this.runtimeSubscription);Gio.bus_unwatch_name(this.ownerWatch);
    }
}
