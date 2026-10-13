import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';
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
        this.object=Gio.DBusExportedObject.wrapJSObject(XML,{CallAsync:([text],invocation)=>this.handle(text,invocation)});
        this.object.export(Gio.DBus.session,'/io/github/waystroke/Gnome');
        this.deviceSignal=this.seat.connect('device-added',(_seat,device)=>this.changed({event:'deviceAdded',name:device.get_device_name()}));
        this.busName=Gio.bus_own_name_on_connection(Gio.DBus.session,'io.github.waystroke.Gnome',Gio.BusNameOwnerFlags.NONE,null,null);
        this.windowSignal=global.display.connect('window-created',(_display,window)=>this.changed({event:'window',window:this.windowInfo(window)}));
        this.lockSignal=Main.sessionMode.connect('updated',()=>{if(this.locked()){this.cancelGesture('锁屏');this.releaseBarrier()}this.changed({event:'lock',locked:this.locked()})});
        this.ownerWatch=Gio.bus_watch_name_on_connection(Gio.DBus.session,'io.github.waystroke.Core',Gio.BusNameWatcherFlags.NONE,()=>{},()=>{this.cancelGesture('后台断开');this.releaseBarrier()});
    }
    locked(){return Main.sessionMode.isLocked||Main.sessionMode.isGreeter}
    changed(value){this.object.emit_signal('Changed',new GLib.Variant('(s)',[JSON.stringify(value)]))}
    async handle(text,invocation) {
        try {
            const uid=await new Promise((resolve,reject)=>Gio.DBus.session.call('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','GetConnectionUnixUser',new GLib.Variant('(s)',[invocation.get_sender()]),new GLib.VariantType('(u)'),Gio.DBusCallFlags.NONE,1000,null,(connection,result)=>{try{resolve(connection.call_finish(result).deep_unpack()[0])}catch(e){reject(e)}}));
            if(uid!==Gio.Credentials.new().get_unix_user())throw Object.assign(Error('仅允许同一用户会话访问'),{kind:'permission'});
            const value=this.call(JSON.parse(text));invocation.return_value(new GLib.Variant('(s)',[JSON.stringify({status:'ok',value})]));
        }catch(e){invocation.return_value(new GLib.Variant('(s)',[JSON.stringify({status:'error',error:{kind:e.kind||'unavailable',message:e.message,details:[]}})]))}
    }
    call(q) {
        if(q.operation==='hello')return {protocolVersion:1,instance:this.instance,locked:this.locked(),shellVersion:Config.PACKAGE_VERSION,capabilities:['liveRuleName','bottomFeedback','quietGestureStart']};
        if(q.operation==='release') {this.cancelGesture('已释放');this.releaseBarrier();return null}
        if(this.locked())throw Error('桌面已锁定，鼠标接入与动作暂停');
        switch(q.operation) {
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
            case 'shortcut':return this.shortcut(q);
            case 'launch': {
                const app=Shell.AppSystem.get_default().lookup_app(q.applicationId)||Shell.AppSystem.get_default().lookup_app(q.applicationId+'.desktop');if(!app)throw Error('未找到所选桌面应用');app.activate();return {applicationId:app.get_id()};
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
    windowAction(q) {
        const window=this.target(q.window);
        switch(q.action) {
            case 'activate':window.activate(global.get_current_time());break;
            case 'maximize':window.maximize();break;
            case 'unmaximize':window.unmaximize();break;
            case 'toggleMaximize':window.is_maximized()?window.unmaximize():window.maximize();break;
            case 'minimize':window.minimize();break;
            case 'close':window.delete(global.get_current_time());break;
            default:throw Error('当前阶段不支持此窗口操作');
        }return this.windowInfo(window);
    }
    shortcut(q) {
        const window=this.target(q.window);window.activate(global.get_current_time());
        const parts=q.keys.split('+').map(part=>part.trim()),modifiers={Ctrl:Clutter.KEY_Control_L,Control:Clutter.KEY_Control_L,Alt:Clutter.KEY_Alt_L,Shift:Clutter.KEY_Shift_L,Super:Clutter.KEY_Super_L};
        const input=parts.pop(),key=({Enter:'Return',Space:'space',Esc:'Escape',Backspace:'BackSpace',PageUp:'Page_Up',PageDown:'Page_Down'})[input]||input,value=Clutter['KEY_'+key]??(key.length===1?key.codePointAt(0):null);if(!value)throw Error('无法识别快捷键');
        const held=parts.map(name=>{if(!modifiers[name])throw Error('无法识别修饰键');return modifiers[name]});
        const state=global.get_pointer()[2],masks=new Map([[Clutter.KEY_Control_L,Clutter.ModifierType.CONTROL_MASK],[Clutter.KEY_Alt_L,Clutter.ModifierType.MOD1_MASK],[Clutter.KEY_Shift_L,Clutter.ModifierType.SHIFT_MASK],[Clutter.KEY_Super_L,Clutter.ModifierType.SUPER_MASK|Clutter.ModifierType.MOD4_MASK]]);
        const own=held.filter(key=>!(state&masks.get(key)));
        const now=GLib.get_monotonic_time();for(const k of own)this.keyboard.notify_keyval(now,k,Clutter.KeyState.PRESSED);this.keyboard.notify_keyval(now,value,Clutter.KeyState.PRESSED);this.keyboard.notify_keyval(now,value,Clutter.KeyState.RELEASED);for(const k of own.reverse())this.keyboard.notify_keyval(now,k,Clutter.KeyState.RELEASED);return null;
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
        this.clearGesture();this.releaseBarrier();this.feedbackActor?.destroy();if(this.feedbackTimer)GLib.source_remove(this.feedbackTimer);
        this.seat.disconnect(this.deviceSignal);global.display.disconnect(this.windowSignal);Main.sessionMode.disconnect(this.lockSignal);Gio.bus_unwatch_name(this.ownerWatch);Gio.bus_unown_name(this.busName);this.object.unexport();this.keyboard=null;this.windows.clear();
    }
}
