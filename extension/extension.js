import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';
import {ClipboardBridge,clipboardCapability} from './clipboard.js';
import {PromptBridge} from './dialogs.js';
import {SystemBridge} from './system.js';
import {TextBridge} from './text.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as Config from 'resource:///org/gnome/shell/misc/config.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
const XML=`<node><interface name="io.github.waystroke.Gnome1">
<method name="Call"><arg type="s" direction="in"/><arg type="s" direction="out"/></method>
<signal name="Changed"><arg type="s"/></signal></interface></node>`;
const TRAIL_TILE=256;
const modifierNames=['Control','Alt','Shift','Super'];
export default class WayStroke extends Extension {
    enable() {
        if(Config.PACKAGE_VERSION!=='50.5')throw Error('WayStroke requires GNOME Shell 50.5');
        this.instance=GLib.uuid_string_random();this.windows=new Map();this.snapshots=new Map();this.bindings=[];this.ordinal=0;
        this.seat=global.stage.context.get_backend().get_default_seat();
        this.keyboard=this.seat.create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
        this.pointer=this.seat.create_virtual_device(Clutter.InputDeviceType.POINTER_DEVICE);this.heldKeys=new Set();this.heldButtons=new Set();
        this.overviewWaiters=new Set();
        this.object=Gio.DBusExportedObject.wrapJSObject(XML,{CallAsync:([text],invocation)=>this.handle(text,invocation)});
        this.object.export(Gio.DBus.session,'/io/github/waystroke/Gnome');
        this.clipboard=new ClipboardBridge(global.display.get_selection(),value=>this.changed(value));
        this.prompts=new PromptBridge(value=>this.changed(value));
        this.system=new SystemBridge(this.clipboard,handle=>this.target(handle));
        this.text=new TextBridge(this);
        this.deviceSignal=this.seat.connect('device-added',(_seat,device)=>this.changed({event:'deviceAdded',name:device.get_device_name()}));
        this.busName=Gio.bus_own_name_on_connection(Gio.DBus.session,'io.github.waystroke.Gnome',Gio.BusNameOwnerFlags.NONE,null,null);
        this.windowSignal=global.display.connect('window-created',(_display,window)=>this.changed({event:'window',window:this.windowInfo(window)}));
        this.lockSignal=Main.sessionMode.connect('updated',()=>{if(this.locked()){this.cancelGesture('锁屏');this.releaseBarrier();this.releaseInputs()}this.changed({event:'lock',locked:this.locked()})});
        this.ownerWatch=Gio.bus_watch_name_on_connection(Gio.DBus.session,'io.github.waystroke.Core',Gio.BusNameWatcherFlags.NONE,()=>{},()=>{this.cancelGesture('后台断开');this.releaseBarrier();this.releaseInputs()});
    }
    locked(){return Main.sessionMode.isLocked||Main.sessionMode.isGreeter}
    changed(value){this.object.emit_signal('Changed',new GLib.Variant('(s)',[JSON.stringify(value)]))}
    async handle(text,invocation) {
        try {
            const uid=await new Promise((resolve,reject)=>Gio.DBus.session.call('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','GetConnectionUnixUser',new GLib.Variant('(s)',[invocation.get_sender()]),new GLib.VariantType('(u)'),Gio.DBusCallFlags.NONE,1000,null,(connection,result)=>{try{resolve(connection.call_finish(result).deep_unpack()[0])}catch(e){reject(e)}}));
            if(uid!==Gio.Credentials.new().get_unix_user())throw Object.assign(Error('仅允许同一用户会话访问'),{kind:'permission'});
            const value=await this.call(JSON.parse(text));invocation.return_value(new GLib.Variant('(s)',[JSON.stringify({status:'ok',value})]));
        }catch(e){invocation.return_value(new GLib.Variant('(s)',[JSON.stringify({status:'error',error:{kind:e.kind||'unavailable',message:e.message,details:[]}})]))}
    }
    async call(q) {
        if(q.operation==='textStatus')return this.text.status();
        if(q.operation==='textGuard')return this.text.guard();
        if(q.operation==='textFocusChanged'){
            const window=global.display.focus_window;
            if(window?.get_client_type()===Meta.WindowClientType.X11&&window.get_pid()===q.pid)this.text.reset();
            return null;
        }
        if(q.operation==='textUndoInvalidated'){
            if(this.text.accessibleUndo?.token===q.token)this.text.accessibleUndo=null;
            return null;
        }
        if(q.operation==='hello')return {protocolVersion:1,instance:this.instance,locked:this.locked(),shellVersion:Config.PACKAGE_VERSION,capabilities:['liveRuleName','bottomFeedback','quietGestureStart','declarativeActionsV1','stableInputFocus']};
        if(q.operation==='release') {this.cancelGesture('已释放');this.releaseBarrier();return null}
        if(this.locked())throw Error('桌面已锁定，鼠标接入与动作暂停');
        switch(q.operation) {
            case 'actionSupport':return this.system.support().then(support=>clipboardCapability().then(clipboard=>({...support,clipboard})));
            case 'getContext':return this.context();
            case 'devicesReady':return this.devicesReady(q.leaseId);
            case 'registerBarrier':this.registerBarrier(q.leaseId);return {instance:this.instance};
            case 'barrierSnapshot': {
                if(q.leaseId!==this.leaseId)throw Object.assign(Error('输入租期已失效'),{kind:'targetInvalid'});
                const snapshot=this.snapshots.get(q.ordinal);if(!snapshot)throw Object.assign(Error('输入屏障尚未处理或已过期'),{kind:'timeout'});
                return {context:snapshot,devicesReady:this.devicesReady(this.leaseId)};
            }
            case 'beginGesture': {
                if(q.leaseId!==this.leaseId)throw Object.assign(Error('输入租期已失效'),{kind:'targetInvalid'});
                if(this.stroke)throw Error('已有活动手势或录制会话');
                const context=this.snapshots.get(q.ordinal);if(!context)throw Error('起点输入屏障尚未处理');
                this.beginGesture(q,context);return context;
            }
            case 'previewGesture': {
                if(q.leaseId!==this.leaseId||this.stroke?.sequence!==q.sequence)return null;
                if(q.interaction)this.stroke.lastMoved=GLib.get_monotonic_time();
                if(this.ruleLabel.text!==q.text)this.ruleLabel.text=q.text;
                if(q.text){this.ruleLabel.show();this.positionRuleLabel()}else this.ruleLabel.hide();
                return null;
            }
            case 'finishGesture': {
                if(q.leaseId!==this.leaseId)throw Object.assign(Error('输入租期已失效'),{kind:'targetInvalid'});
                if(!this.stroke||this.stroke.sequence!==q.sequence)throw Error('手势会话已过期');
                const end=this.snapshots.get(q.ordinal);if(!end)throw Error('结束输入屏障尚未处理');
                this.point(end.position);const value={context:this.stroke.context,points:this.stroke.points};this.clearGesture();return value;
            }
            case 'cancelGesture':this.cancelGesture(q.reason||'已取消');return null;
            case 'windows':return global.get_window_actors().map(a=>this.windowInfo(a.meta_window));
            case 'windowAction':return this.windowAction(q);
            case 'windowFind':return this.findWindow(q);
            case 'windowInfo':return this.fullWindowInfo(this.target(q.window));
            case 'focusedWindow':return global.display.focus_window?this.windowInfo(global.display.focus_window).handle:null;
            case 'windowGeometry': {
                const window=this.target(q.window),area=window.get_work_area_for_monitor(window.get_monitor());
                let {x,y,width,height}=q;
                if(q.unit==='工作区百分比'){x=area.x+area.width*x/100;y=area.y+area.height*y/100;width=area.width*width/100;height=area.height*height/100}
                if(![x,y,width,height].every(Number.isFinite)||width<=0||height<=0)throw Object.assign(Error('窗口位置与尺寸无效'),{kind:'validation'});
                window.unmake_fullscreen();window.unmaximize();window.move_resize_frame(false,Math.round(x),Math.round(y),Math.round(width),Math.round(height));return null;
            }
            case 'windowMonitor': {
                const window=this.target(q.window),monitors=Main.layoutManager.monitors;let index;
                switch(q.value){case '下一个显示器':index=(window.get_monitor()+1)%monitors.length;break;case '上一个显示器':index=(window.get_monitor()+monitors.length-1)%monitors.length;break;case '主显示器':index=Main.layoutManager.primaryIndex;break;case '指定编号':index=q.index-1;break;default:throw Error('未知显示器操作')}
                if(!Number.isInteger(index)||!monitors[index])throw Object.assign(Error('指定显示器不存在'),{kind:'targetInvalid'});window.move_to_monitor(index);return null;
            }
            case 'workspaceSwitch': {
                const manager=global.workspace_manager,current=manager.get_active_workspace_index();let index;
                switch(q.value){case '上一工作区':index=current-1;break;case '下一工作区':index=current+1;break;case '指定编号':index=q.index-1;break;default:throw Error('未知工作区操作')}
                this.workspace(index).activate(global.get_current_time());return null;
            }
            case 'workspaceMove': {
                const window=this.target(q.window),workspace=this.workspace(q.index-1);window.change_workspace(workspace);if(q.follow)workspace.activate(global.get_current_time());return null;
            }
            case 'desktopOverview':return this.overviewOperation(q.value);
            case 'desktopShow':return this.showDesktop(q.value);
            case 'applicationQuit': {
                if(q.mode==='当前目标窗口'){const window=this.target(q.window);if(q.applicationId&&this.windowInfo(window).applicationId!==q.applicationId)throw Object.assign(Error('目标窗口不属于指定应用'),{kind:'targetInvalid'});window.delete(global.get_current_time());}
                else if(q.mode==='该应用的所有窗口'){if(!q.applicationId)throw Object.assign(Error('关闭全部窗口需要应用 ID'),{kind:'validation'});const windows=global.get_window_actors().map(a=>a.meta_window).filter(w=>this.windowInfo(w).applicationId===q.applicationId);if(!windows.length)throw Object.assign(Error('指定应用没有窗口'),{kind:'targetInvalid'});for(const window of windows)window.delete(global.get_current_time());}
                else throw Error('未知关闭范围');return null;
            }
            case 'shortcut':return this.shortcut(q);
            case 'keyInput': {
                const window=this.target(q.window);await this.activateInputWindow(window);const key=this.keyValue(q.key);
                switch(q.value){case '按下':this.pressKey(key);break;case '释放':this.releaseKey(key);break;case '按下并释放':{const held=this.heldKeys.has(key);this.pressKey(key);if(!held)this.releaseKey(key);break;}default:throw Error('未知按键操作')}return null;
            }
            case 'pointerMove': {
                if(q.window)this.target(q.window);let {x,y}=q;
                if(q.mode==='相对当前位置'){const [px,py]=global.get_pointer();x+=px;y+=py}
                else if(q.mode==='目标窗口内'){const rect=this.target(q.window).get_frame_rect();x+=rect.x;y+=rect.y}
                else if(q.mode!=='屏幕绝对坐标')throw Error('未知坐标参考');
                if(!Number.isFinite(x)||!Number.isFinite(y))throw Object.assign(Error('指针坐标无效'),{kind:'validation'});
                this.pointer.notify_absolute_motion(GLib.get_monotonic_time(),x,y);return null;
            }
            case 'mouseInput': {
                if(![1,2,3,8,9].includes(q.button))throw Object.assign(Error('鼠标按钮无效'),{kind:'validation'});
                if(q.pressed){if(!this.heldButtons.has(q.button)){this.pointer.notify_button(GLib.get_monotonic_time(),q.button,Clutter.ButtonState.PRESSED);this.heldButtons.add(q.button)}}
                else if(this.heldButtons.delete(q.button))this.pointer.notify_button(GLib.get_monotonic_time(),q.button,Clutter.ButtonState.RELEASED);return null;
            }
            case 'scrollInput': {
                const window=this.target(q.window);await this.activateInputWindow(window);const directions={'向上':Clutter.ScrollDirection.UP,'向下':Clutter.ScrollDirection.DOWN,'向左':Clutter.ScrollDirection.LEFT,'向右':Clutter.ScrollDirection.RIGHT};
                const direction=directions[q.direction];if(direction===undefined)throw Error('未知滚动方向');
                const [x,y]=global.get_pointer();
                if(this.windowAt(x,y)!==window){const rect=window.get_frame_rect();this.pointer.notify_absolute_motion(GLib.get_monotonic_time(),rect.x+rect.width/2,rect.y+rect.height/2);}
                this.pointer.notify_discrete_scroll(GLib.get_monotonic_time(),direction,Clutter.ScrollSource.WHEEL);return null;
            }
            case 'textInput': {
                await this.activateInputWindow(this.target(q.window));
                if(Main.inputMethod.currentFocus){this.text.generated(()=>Main.inputMethod.commit(q.text));return null}
                if([...q.text].some(character=>character.codePointAt(0)>127))throw Object.assign(Error('当前应用没有原生文本提交接口，请使用剪贴板粘贴方式'),{kind:'unavailable'});
                for(const character of q.text){const key=character==='\n'?Clutter.KEY_Return:character==='\t'?Clutter.KEY_Tab:Clutter.unicode_to_keysym(character.codePointAt(0));this.keyboard.notify_keyval(GLib.get_monotonic_time(),key,Clutter.KeyState.PRESSED);this.keyboard.notify_keyval(GLib.get_monotonic_time(),key,Clutter.KeyState.RELEASED)}return null;
            }
            case 'volume':return this.system.volume(q);
            case 'brightness':return this.system.brightness(q);
            case 'notification':Main.notify(q.title,q.body);return null;
            case 'screenshot':return this.system.screenshot(q);
            case 'dialogMessage':return this.prompts.show({...q,kind:'message'});
            case 'dialogInput':return this.prompts.show({...q,kind:'input'});
            case 'clipboardRead':return this.clipboard.read();
            case 'clipboardWrite':return this.clipboard.write(q.text);
            case 'clipboardClear':return this.clipboard.clear();
            case 'clipboardVersion':return {version:this.clipboard.version};
            case 'clipboardCopyStart': {
                await this.activateInputWindow(this.target(q.window));const version=this.clipboard.version;await this.shortcut({window:q.window,keys:'Ctrl+C'});return {version};
            }
            case 'clipboardCopyResult': {
                if(this.clipboard.version<=q.version)return {changed:false};return this.clipboard.read().then(text=>({changed:true,text}));
            }
            case 'clipboardPasteStart': {
                this.target(q.window);return this.clipboard.beginPaste(q.text,q.restore,()=>this.shortcut({window:q.window,keys:'Ctrl+V'}));
            }
            case 'clipboardPasteStatus':return this.clipboard.pasteStatus(q.token);
            case 'clipboardPasteFinish':this.clipboard.pasteStatus(q.token);this.clipboard.finishPaste();return null;
            case 'releaseInputs':this.releaseInputs();return null;
            case 'launch': {
                const app=Shell.AppSystem.get_default().lookup_app(q.applicationId)||Shell.AppSystem.get_default().lookup_app(q.applicationId+'.desktop');if(!app)throw Error('未找到所选桌面应用');
                if(q.arguments){const info=app.get_app_info(),command=info?.get_commandline();if(!command)throw Error('应用没有可用启动命令');Gio.AppInfo.create_from_commandline(command+' '+q.arguments,info.get_name(),Gio.AppInfoCreateFlags.NONE).launch([],global.create_app_launch_context(global.get_current_time(),-1));}
                else if(q.newWindow)app.open_new_window(-1);
                else app.activate();return {applicationId:app.get_id()};
            }
            case 'feedback':this.feedback(q.text,q.monitor);return null;
            default:throw Error('不支持的桌面操作');
        }
    }
    windowInfo(window) {
        const id=String(window.get_stable_sequence());this.windows.set(id,window);
        const appId=Shell.WindowTracker.get_default().get_window_app(window)?.get_id();
        const applicationId=appId&&!appId.startsWith('window:')?appId:window.get_gtk_application_id()||window.get_wm_class()||'';
        return {handle:{instance:this.instance,id},title:window.get_title()||'',applicationId,clientType:window.get_client_type()};
    }
    windowAt(x,y) {let actor=global.stage.get_actor_at_pos(Clutter.PickMode.REACTIVE,x,y);while(actor){if(actor.meta_window)return actor.meta_window;actor=actor.get_parent()}return null}
    context() {
        const [x,y]=global.get_pointer(),window=this.windowAt(x,y),info=window?this.windowInfo(window):null;
        return {sequence:0,monotonicMs:GLib.get_monotonic_time()/1000,position:[x,y],window:info?.handle||null,applicationId:info?.applicationId||null,title:info?.title||null,workspace:global.workspace_manager.get_active_workspace_index(),monitor:Main.layoutManager.monitors.findIndex(m=>x>=m.x&&x<m.x+m.width&&y>=m.y&&y<m.y+m.height),locked:this.locked()};
    }
    devicesReady(leaseId) {
        if(leaseId!==this.leaseId)throw Object.assign(Error('输入租期已失效'),{kind:'targetInvalid'});
        const names=new Set(this.seat.list_devices().map(device=>device.get_device_name()));
        return names.has(`WayStroke Virtual Pointer ${leaseId}`)&&names.has(`WayStroke Virtual Source Keys ${leaseId}`);
    }
    registerBarrier(leaseId) {
        if(this.bindings.length)throw Error('输入屏障已注册');
        if(typeof leaseId!=='string'||!/^[-a-f0-9]{36}$/.test(leaseId))throw Error('输入租期身份无效');
        this.leaseId=leaseId;this.ordinal=0;this.snapshots.clear();
        try {
            // Cover held desktop modifiers without releasing keys owned by users.
            for(let mask=0;mask<16;mask++) {
                const accelerator=modifierNames.filter((_,i)=>mask&(1<<i)).map(name=>`<${name}>`).join('')+'F24';
                const id=global.display.grab_accelerator(accelerator,Meta.KeyBindingFlags.IGNORE_AUTOREPEAT);
                if(!id)throw Error('输入屏障快捷键冲突，未接管鼠标');
                this.bindings.push(id);Main.wm.allowKeybinding('external-grab-'+id,Shell.ActionMode.NORMAL);
            }
            this.bindingFilter=global.window_manager.connect('filter-keybinding',(_wm,binding)=>{
                if(!this.bindings.some(id=>'external-grab-'+id===binding.get_name()))return false;
                // Foreign keyboard F24 and mouse-macro keys remain ordinary input.
                const event=Clutter.get_current_event();
                return event?.get_source_device()?.get_device_name()!==`WayStroke Virtual Pointer ${this.leaseId}`;
            });
            this.barrierSignal=global.display.connect('accelerator-activated',(_display,action,device)=>{
                if(!this.bindings.includes(action)||device.get_device_name()!==`WayStroke Virtual Pointer ${this.leaseId}`)return;
                const context=this.context();this.snapshots.set(++this.ordinal,context);if(this.snapshots.size>64)this.snapshots.delete(this.snapshots.keys().next().value);
                if(this.stroke)this.point(context.position);
                this.changed({event:'barrier',leaseId:this.leaseId,ordinal:this.ordinal,context});
            });
        }catch(e){this.releaseBarrier();throw e}
    }
    releaseBarrier() {
        if(this.bindingFilter){global.window_manager.disconnect(this.bindingFilter);this.bindingFilter=0}
        if(this.barrierSignal){global.display.disconnect(this.barrierSignal);this.barrierSignal=0}
        for(const id of this.bindings)global.display.ungrab_accelerator(id);this.bindings=[];this.snapshots.clear();
    }
    beginGesture(q,context) {
        this.stroke={sequence:q.sequence,context:{...context,sequence:q.sequence},points:[context.position],pointsSent:1,lastPreview:0,bounds:[...context.position,...context.position],length:0,minimumLength:q.minimumLength,lastMoved:GLib.get_monotonic_time(),cancelTimeout:q.cancelTimeout,trail:q.trail,color:q.color};
        const escape=global.display.grab_accelerator('Escape',Meta.KeyBindingFlags.NONE);
        if(!escape){this.stroke=null;throw Error('Esc 取消按键不可用，未开始手势')}
        this.escape=escape;Main.wm.allowKeybinding('external-grab-'+escape,Shell.ActionMode.NORMAL);
        this.escapeSignal=global.display.connect('accelerator-activated',(_display,action)=>{if(action===this.escape)this.cancelGesture('Esc 取消')});
        this.tiles=new Map();
        if(q.trail) {
            // The container has no raster backing; only touched tiles allocate textures.
            this.trail=new St.Widget({reactive:false,width:global.stage.width,height:global.stage.height});Main.layoutManager.addTopChrome(this.trail);
        }
        this.ruleLabel=new St.Label({text:'',visible:false,reactive:false,style:'background:rgba(30,30,40,0.92);color:white;padding:7px 12px;border-radius:9px;font-size:13px;'});
        Main.layoutManager.addTopChrome(this.ruleLabel);this.positionRuleLabel();
        this.sampleTimer=GLib.timeout_add(GLib.PRIORITY_DEFAULT,8,()=>{
            if(!this.stroke)return GLib.SOURCE_REMOVE;
            this.point(global.get_pointer().slice(0,2));
            this.flushPreview();
            if(this.stroke.length>=this.stroke.minimumLength&&GLib.get_monotonic_time()-this.stroke.lastMoved>=this.stroke.cancelTimeout*1000){this.cancelGesture('停留超时');return GLib.SOURCE_REMOVE}
            return GLib.SOURCE_CONTINUE;
        });
    }
    point(point) {
        if(!this.stroke)return;const last=this.stroke.points.at(-1);
        if(last[0]===point[0]&&last[1]===point[1])return;
        this.stroke.length+=Math.hypot(point[0]-last[0],point[1]-last[1]);this.stroke.points.push(point);this.stroke.lastMoved=GLib.get_monotonic_time();this.queueTrail(last,point);
        const b=this.stroke.bounds;b[0]=Math.min(b[0],point[0]);b[1]=Math.min(b[1],point[1]);b[2]=Math.max(b[2],point[0]);b[3]=Math.max(b[3],point[1]);this.positionRuleLabel();
    }
    flushPreview() {
        const s=this.stroke,now=GLib.get_monotonic_time();
        if(!s||s.pointsSent===s.points.length||now-s.lastPreview<50000)return;
        const offset=s.pointsSent,points=s.points.slice(offset);s.pointsSent=s.points.length;s.lastPreview=now;
        this.changed({event:'previewStroke',leaseId:this.leaseId,sequence:s.sequence,offset,points});
    }
    positionRuleLabel() {
        if(!this.ruleLabel||!this.stroke)return;
        const b=this.stroke.bounds,[px,py]=this.stroke.points.at(-1);
        const m=Main.layoutManager.monitors.find(m=>px>=m.x&&px<m.x+m.width&&py>=m.y&&py<m.y+m.height)||Main.layoutManager.primaryMonitor;
        const width=this.ruleLabel.get_preferred_width(-1)[1],height=this.ruleLabel.get_preferred_height(width)[1];
        const x=Math.max(m.x+8,Math.min((b[0]+b[2]-width)/2,m.x+m.width-width-8));
        let y=b[3]+12;if(y+height>m.y+m.height-8)y=b[1]-height-12;
        this.ruleLabel.set_position(Math.round(x),Math.round(Math.max(m.y+8,Math.min(y,m.y+m.height-height-8))));
    }
    queueTrail(a,b) {
        if(!this.trail)return;
        const minX=Math.floor((Math.min(a[0],b[0])-3)/TRAIL_TILE),maxX=Math.floor((Math.max(a[0],b[0])+3)/TRAIL_TILE);
        const minY=Math.floor((Math.min(a[1],b[1])-3)/TRAIL_TILE),maxY=Math.floor((Math.max(a[1],b[1])+3)/TRAIL_TILE);
        for(let x=minX;x<=maxX;x++)for(let y=minY;y<=maxY;y++) {
            const key=`${x},${y}`;let tile=this.tiles.get(key);
            if(!tile) {
                const area=new St.DrawingArea({reactive:false,width:TRAIL_TILE,height:TRAIL_TILE});tile={x:x*TRAIL_TILE,y:y*TRAIL_TILE,area,segments:[]};
                area.set_position(tile.x,tile.y);this.trail.add_child(area);area.connect('repaint',()=>this.paintTile(tile));this.tiles.set(key,tile);
            }
            tile.segments.push([a,b]);tile.area.queue_repaint();
        }
    }
    paintTile(tile) {
        if(!this.stroke)return;const ctx=tile.area.get_context(),hex=this.stroke.color.replace('#','');
        ctx.setSourceRGBA(parseInt(hex.slice(0,2),16)/255,parseInt(hex.slice(2,4),16)/255,parseInt(hex.slice(4,6),16)/255,.9);ctx.setLineWidth(3);ctx.setLineCap(1);
        for(const [a,b] of tile.segments){ctx.moveTo(a[0]-tile.x,a[1]-tile.y);ctx.lineTo(b[0]-tile.x,b[1]-tile.y)}ctx.stroke();ctx.$dispose();
    }
    clearGesture() {
        if(this.sampleTimer){GLib.source_remove(this.sampleTimer);this.sampleTimer=0}
        if(this.escapeSignal){global.display.disconnect(this.escapeSignal);this.escapeSignal=0}
        if(this.escape){global.display.ungrab_accelerator(this.escape);this.escape=0}
        this.ruleLabel?.destroy();this.ruleLabel=null;
        this.trail?.destroy();this.trail=null;this.tiles?.clear();this.stroke=null;
    }
    cancelGesture(reason) {if(this.stroke)this.changed({event:'canceled',sequence:this.stroke.sequence,reason});this.clearGesture()}
    target(handle) {
        if(!handle||handle.instance!==this.instance)throw Object.assign(Error('窗口身份已失效'),{kind:'targetInvalid'});
        const window=this.windows.get(handle.id);if(!window||!global.get_window_actors().some(a=>a.meta_window===window))throw Object.assign(Error('起点窗口已关闭'),{kind:'targetInvalid'});return window;
    }
    async windowAction(q) {
        const window=this.target(q.window);
        switch(q.action) {
            case 'activate':await this.activateInputWindow(window);break;
            case 'maximize':window.maximize();break;
            case 'unmaximize':window.unmaximize();break;
            case 'toggleMaximize':window.is_maximized()?window.unmaximize():window.maximize();break;
            case 'minimize':window.minimize();break;
            case 'close':window.delete(global.get_current_time());break;
            case 'unminimize':window.unminimize();break;
            case 'fullscreen':window.make_fullscreen();break;
            case 'unfullscreen':window.unmake_fullscreen();break;
            case 'toggleFullscreen':window.is_fullscreen()?window.unmake_fullscreen():window.make_fullscreen();break;
            case 'above':window.make_above();break;
            case 'unabove':window.unmake_above();break;
            case 'toggleAbove':window.is_above()?window.unmake_above():window.make_above();break;
            case 'stick':window.stick();break;
            case 'unstick':window.unstick();break;
            case 'previousWorkspace':window.change_workspace(this.workspace(window.get_workspace().index()-1));break;
            case 'nextWorkspace':window.change_workspace(this.workspace(window.get_workspace().index()+1));break;
            case 'leftHalf':case 'rightHalf': {
                const area=window.get_work_area_for_monitor(window.get_monitor()),left=Math.floor(area.width/2);
                window.unmake_fullscreen();window.unmaximize();window.move_resize_frame(false,area.x+(q.action==='rightHalf'?left:0),area.y,q.action==='rightHalf'?area.width-left:left,area.height);break;
            }
            default:throw Error('未知窗口操作');
        }return this.windowInfo(window);
    }
    workspace(index) {
        const manager=global.workspace_manager;
        if(!Number.isInteger(index)||index<0||index>=manager.n_workspaces)throw Object.assign(Error('指定工作区不存在'),{kind:'targetInvalid'});
        return manager.get_workspace_by_index(index);
    }
    fullWindowInfo(window) {
        const rect=window.get_frame_rect();return {...this.windowInfo(window),geometry:{x:rect.x,y:rect.y,width:rect.width,height:rect.height},workspace:window.get_workspace().index()+1,monitor:window.get_monitor()+1,maximized:window.is_maximized(),fullscreen:window.is_fullscreen(),above:window.is_above(),minimized:window.minimized,sticky:window.is_on_all_workspaces()};
    }
    findWindow(q) {
        let windows=global.get_window_actors().map(a=>a.meta_window).filter(window=>{
            const info=this.windowInfo(window);return (!q.applicationId||info.applicationId===q.applicationId)&&(!q.title||info.title.includes(q.title))&&(q.workspace!=='当前工作区'||window.located_on_workspace(global.workspace_manager.get_active_workspace()));
        });
        if(q.pick==='最近使用'){const recent=global.display.get_tab_list(Meta.TabList.NORMAL_ALL,null);windows.sort((a,b)=>recent.indexOf(a)-recent.indexOf(b));}
        else if(q.pick==='最前方')windows=global.display.sort_windows_by_stacking(windows).reverse();
        else throw Error('未知窗口选择方式');
        if(!windows.length)throw Object.assign(Error('没有符合条件的窗口'),{kind:'targetInvalid'});return this.windowInfo(windows[0]).handle;
    }
    overviewOperation(operation) {
        const overview=Main.overview;
        if(!['显示概览','隐藏概览','切换概览','显示应用列表'].includes(operation))throw Error('未知概览操作');
        if(overview.isDummy)throw Object.assign(Error('当前桌面没有可用概览'),{kind:'unavailable'});
        const show=operation==='切换概览'?!overview.visible:operation!=='隐藏概览';
        return new Promise((resolve,reject)=>{
            const signals=[];let finished=false,idle=0;
            const finish=error=>{
                if(finished)return;finished=true;
                if(idle){GLib.source_remove(idle);idle=0;}
                for(const signal of signals)overview.disconnect(signal);
                this.overviewWaiters.delete(cancel);
                if(error)reject(error);else resolve(null);
            };
            const cancel=()=>finish(Object.assign(Error('概览操作已取消'),{kind:'canceled'}));
            // GNOME emits hidden/shown before restoring its modal input grab.
            // Resume on the next main-loop dispatch, after that cleanup.
            const check=()=>{
                if(finished||idle||overview.animationInProgress||overview.visible!==show)return;
                idle=GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE,()=>{idle=0;if(!overview.animationInProgress&&overview.visible===show)finish();return GLib.SOURCE_REMOVE});
            };
            signals.push(overview.connect('shown',check),overview.connect('hidden',check));
            this.overviewWaiters.add(cancel);
            try{
                if(operation==='显示应用列表'){overview.dash.showAppsButton.checked=true;overview.showApps();}
                else if(show)overview.show();else overview.hide();
                check();
            }catch(error){finish(error)}
        });
    }
    showDesktop(operation) {
        const show=operation==='显示桌面'||(operation==='切换'&&!this.hiddenWindows);
        if(show){
            if(this.hiddenWindows)return null;
            const workspace=global.workspace_manager.get_active_workspace();
            this.hiddenWindows=global.display.get_tab_list(Meta.TabList.NORMAL,workspace).filter(window=>!window.minimized);
            this.desktopFocus=global.display.focus_window;for(const window of this.hiddenWindows)window.minimize();
        }else if(operation==='恢复窗口'||operation==='切换'){
            const alive=new Set(global.get_window_actors().map(a=>a.meta_window));
            for(const window of this.hiddenWindows||[]){if(alive.has(window))window.unminimize();}
            if(alive.has(this.desktopFocus))this.desktopFocus.activate(global.get_current_time());
            this.hiddenWindows=null;this.desktopFocus=null;
        }else throw Error('未知显示桌面操作');return null;
    }
    async activateInputWindow(window) {
        if(Main.overview.visible||Main.overview.animationInProgress)await this.overviewOperation('隐藏概览');
        await new Promise((resolve,reject)=>{
            let idle=0,finished=false;const signals=[];
            const finish=error=>{
                if(finished)return;finished=true;if(idle)GLib.source_remove(idle);
                for(const [object,id] of signals)object.disconnect(id);
                this.overviewWaiters.delete(cancel);if(error)reject(error);else resolve();
            };
            const cancel=()=>finish(Object.assign(Error('窗口输入已取消'),{kind:'canceled'}));
            const check=()=>{
                if(idle||finished||global.display.focus_window!==window)return;
                idle=GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE,()=>{idle=0;if(global.display.focus_window===window)finish();return GLib.SOURCE_REMOVE});
            };
            signals.push([global.display,global.display.connect('notify::focus-window',check)],[window,window.connect('unmanaged',()=>finish(Object.assign(Error('目标窗口已关闭'),{kind:'targetInvalid'})))]);
            this.overviewWaiters.add(cancel);
            try{if(global.display.focus_window!==window)Main.activateWindow(window);check()}catch(error){finish(error)}
        });
    }
    async shortcut(q) {
        const window=this.target(q.window);await this.activateInputWindow(window);
        const parts=q.keys.split('+').map(part=>part.trim()),modifiers={Ctrl:Clutter.KEY_Control_L,Control:Clutter.KEY_Control_L,Alt:Clutter.KEY_Alt_L,Shift:Clutter.KEY_Shift_L,Super:Clutter.KEY_Super_L};
        const input=parts.pop(),value=this.keyValue(/^[A-Z]$/.test(input)?input.toLowerCase():input);
        const held=parts.map(name=>{if(!modifiers[name])throw Error('无法识别修饰键');return modifiers[name]});
        const state=global.get_pointer()[2],masks=new Map([[Clutter.KEY_Control_L,Clutter.ModifierType.CONTROL_MASK],[Clutter.KEY_Alt_L,Clutter.ModifierType.MOD1_MASK],[Clutter.KEY_Shift_L,Clutter.ModifierType.SHIFT_MASK],[Clutter.KEY_Super_L,Clutter.ModifierType.SUPER_MASK|Clutter.ModifierType.MOD4_MASK]]);
        const own=held.filter(key=>!(state&masks.get(key)));
        const now=GLib.get_monotonic_time();for(const k of own)this.keyboard.notify_keyval(now,k,Clutter.KeyState.PRESSED);this.keyboard.notify_keyval(now,value,Clutter.KeyState.PRESSED);this.keyboard.notify_keyval(now,value,Clutter.KeyState.RELEASED);for(const k of own.reverse())this.keyboard.notify_keyval(now,k,Clutter.KeyState.RELEASED);return null;
    }
    keyValue(input) {
        const name=({Ctrl:'Control_L',Control:'Control_L',Alt:'Alt_L',Shift:'Shift_L',Super:'Super_L',Enter:'Return',Space:'space',Esc:'Escape',Backspace:'BackSpace',PageUp:'Page_Up',PageDown:'Page_Down'})[input]||input;
        if([...name].length===1&&name.codePointAt(0)>127)throw Object.assign(Error('该字符不能作为虚拟按键发送，请使用输入文本动作'),{kind:'unavailable'});
        const value=Clutter['KEY_'+name]??([...name].length===1?Clutter.unicode_to_keysym(name.codePointAt(0)):null);
        if(!value)throw Object.assign(Error('无法识别按键'),{kind:'validation'});return value;
    }
    pressKey(key) {if(!this.heldKeys.has(key)){this.keyboard.notify_keyval(GLib.get_monotonic_time(),key,Clutter.KeyState.PRESSED);this.heldKeys.add(key)}}
    releaseKey(key) {if(this.heldKeys.delete(key))this.keyboard.notify_keyval(GLib.get_monotonic_time(),key,Clutter.KeyState.RELEASED)}
    releaseInputs() {
        for(const cancel of [...this.overviewWaiters])cancel();
        this.system?.cancel();this.clipboard?.cancel();this.prompts?.cancel();
        for(const key of [...this.heldKeys].reverse())this.releaseKey(key);
        for(const button of this.heldButtons)this.pointer.notify_button(GLib.get_monotonic_time(),button,Clutter.ButtonState.RELEASED);
        this.heldButtons.clear();
    }
    feedback(text,monitorIndex) {
        this.feedbackActor?.destroy();if(this.feedbackTimer)GLib.source_remove(this.feedbackTimer);
        this.feedbackActor=new St.Label({text,reactive:false,style:'background:#262633;color:white;padding:12px 20px;border-radius:12px;font-size:13px;'});Main.layoutManager.addTopChrome(this.feedbackActor);
        const [px,py]=global.get_pointer();
        const monitor=Main.layoutManager.monitors[monitorIndex]||Main.layoutManager.monitors.find(m=>px>=m.x&&px<m.x+m.width&&py>=m.y&&py<m.y+m.height)||Main.layoutManager.primaryMonitor;
        const width=this.feedbackActor.get_preferred_width(-1)[1],height=this.feedbackActor.get_preferred_height(width)[1];
        this.feedbackActor.set_position(Math.round(monitor.x+(monitor.width-width)/2),Math.round(monitor.y+monitor.height-height-64));
        this.feedbackTimer=GLib.timeout_add(GLib.PRIORITY_DEFAULT,1500,()=>{this.feedbackActor?.destroy();this.feedbackActor=null;this.feedbackTimer=0;return GLib.SOURCE_REMOVE});
    }
    disable() {
        this.text.disable();
        this.clearGesture();this.releaseBarrier();this.releaseInputs();this.feedbackActor?.destroy();if(this.feedbackTimer)GLib.source_remove(this.feedbackTimer);
        this.clipboard.disable();this.seat.disconnect(this.deviceSignal);global.display.disconnect(this.windowSignal);Main.sessionMode.disconnect(this.lockSignal);Gio.bus_unwatch_name(this.ownerWatch);Gio.bus_unown_name(this.busName);this.object.unexport();this.keyboard=null;this.pointer=null;this.windows.clear();
    }
}
