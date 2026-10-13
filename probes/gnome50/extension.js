import {TerminalMonitor} from './terminal-monitor.js';
import Meta from 'gi://Meta';
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import IBus from 'gi://IBus';
Gio._promisify(Shell.Screenshot.prototype,'screenshot','screenshot_finish');
import * as IBusManager from 'resource:///org/gnome/shell/misc/ibusManager.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
const XML='<node><interface name="org.waystroke.Probe"><method name="Call"><arg type="s" direction="in"/><arg type="s" direction="out"/></method></interface></node>';
export default class Probe extends Extension {
 enable(){
  const root=GLib.getenv("WAYSTROKE_PROBE_DIR");if(!root||GLib.getenv("XDG_RUNTIME_DIR")!==root+"/runtime")throw Error("Probe requires its disposable session");
  this.counts={buttons:0,keys:0,motions:0};
  this.signal=global.stage.connect('captured-event',(_stage,event)=>{
   const t=event.type();if(t===Clutter.EventType.BUTTON_PRESS||t===Clutter.EventType.BUTTON_RELEASE)this.counts.buttons++;
   if(t===Clutter.EventType.KEY_PRESS||t===Clutter.EventType.KEY_RELEASE)this.counts.keys++;
   if(t===Clutter.EventType.MOTION)this.counts.motions++;
   return Clutter.EVENT_PROPAGATE;
  });
  const seat=global.stage.context.get_backend().get_default_seat();
  this.pointer=seat.create_virtual_device(Clutter.InputDeviceType.POINTER_DEVICE);
  this.keyboard=seat.create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
  this.object=Gio.DBusExportedObject.wrapJSObject(XML,{Call:s=>{
   try{return JSON.stringify(this.call(JSON.parse(s)))}catch(e){return JSON.stringify({error:e.message})}
  }});this.object.export(Gio.DBus.session,'/org/waystroke/Probe');
  Main.overview.hide();console.log('WAYSTROKE_PROBE_READY');
 }
 call(q){
  const now=GLib.get_monotonic_time();
  if(q.action==='track-panel'){
   const panel=IBusManager.getIBusManager()._panelService;if(!panel)throw Error('Panel not ready');
   this.panelState={lookupVisible:false,preeditVisible:false,context:null};this.panelSignals=[];
   const connect=(name,handler)=>this.panelSignals.push([panel,panel.connect(name,handler)]);
   connect('update-lookup-table',(_panel,_table,visible)=>this.panelState.lookupVisible=visible);
   connect('show-lookup-table',()=>this.panelState.lookupVisible=true);connect('hide-lookup-table',()=>this.panelState.lookupVisible=false);
   connect('update-preedit-text',(_panel,_text,_cursor,visible)=>this.panelState.preeditVisible=visible);
   connect('show-preedit-text',()=>this.panelState.preeditVisible=true);connect('hide-preedit-text',()=>this.panelState.preeditVisible=false);
   connect('focus-in',(_panel,path)=>this.panelState={lookupVisible:false,preeditVisible:false,context:path});
   connect('focus-out',()=>this.panelState={lookupVisible:false,preeditVisible:false,context:null});
  }
  if(q.action==='grab-confirm'){
   this.confirmId=global.display.grab_accelerator('Return',Meta.KeyBindingFlags.NONE);
   if(!this.confirmId)throw Error('Return accelerator unavailable');
   this.confirmName='external-grab-'+this.confirmId;Main.wm.allowKeybinding(this.confirmName,Shell.ActionMode.NORMAL);this.confirmEvents=[];
   this.confirmSignal=global.display.connect('accelerator-activated',(_display,action,_device,time)=>{if(action===this.confirmId)this.confirmEvents.push({time,focus:global.display.focus_window?.get_title(),imeGuard:Main.inputMethod.hasPreedit()||!!this.panelState?.lookupVisible||!!this.panelState?.preeditVisible})});
   return {action:this.confirmId};
  }
  if(q.action==='poll-confirm')return {events:this.confirmEvents};
  if(q.action==='replay-confirm'){
   Main.wm.allowKeybinding(this.confirmName,Shell.ActionMode.NONE);
   if(Main.inputMethod.currentFocus){
    // Native keys reached this accelerator after IME processing. Forward with
    // the InputMethod flag so the replay does not make a second IBus round trip.
    const time=global.display.get_current_time_roundtrip();Main.inputMethod.forward_key(0xff0d,36,0,time,true);Main.inputMethod.forward_key(0xff0d,36,0,time,false);
   }else{this.keyboard.notify_keyval(now,0xff0d,Clutter.KeyState.PRESSED);this.keyboard.notify_keyval(now+1,0xff0d,Clutter.KeyState.RELEASED)}
   GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE,()=>{Main.wm.allowKeybinding(this.confirmName,Shell.ActionMode.NORMAL);return GLib.SOURCE_REMOVE});
  }
  if(q.action==='release-confirm'){
   global.display.ungrab_accelerator(this.confirmId);global.display.disconnect(this.confirmSignal);this.confirmId=0;this.confirmSignal=0;
  }
  if(q.action==='terminal-monitor')this.terminalMonitor=new TerminalMonitor(this.keyboard);
  if(q.action==='terminal-reset')this.terminalMonitor.reset();
  if(q.action==='terminal-records')return {records:this.terminalMonitor.records};
  if(q.action==='terminal-stop'){this.terminalMonitor.disable();this.terminalMonitor=null}
  if(q.action==='normal')Main.overview.hide();
  if(q.action==='screenshot'){const file=Gio.File.new_for_path(GLib.getenv('WAYSTROKE_PROBE_DIR')+'/'+(q.tag||'desktop')+'.png');const stream=file.replace(null,false,Gio.FileCreateFlags.NONE,null);new Shell.Screenshot().screenshot(false,stream).then(()=>stream.close(null)).catch(console.error)}
  if(q.action==='pointer')this.pointer.notify_absolute_motion(now,q.x,q.y);
  if(q.action==='button')this.pointer.notify_button(now,q.button,q.pressed?Clutter.ButtonState.PRESSED:Clutter.ButtonState.RELEASED);
  if(q.action==='keycode')this.keyboard.notify_key(now,q.keycode,q.pressed?Clutter.KeyState.PRESSED:Clutter.KeyState.RELEASED);
  if(q.action==='key')this.keyboard.notify_keyval(now,q.keyval,q.pressed?Clutter.KeyState.PRESSED:Clutter.KeyState.RELEASED);
  if(q.action==='grab')this.grab=global.stage.grab(global.stage);
  if(q.action==='ungrab'){this.grab?.dismiss();this.grab=null}
  if(q.action==='source'){const source=Object.values(Main.inputMethod._inputSourceManager.inputSources).find(source=>source.id===q.id);if(!source)throw Error('Source missing');source.activate()}
  if(q.action==='ime'){const source=Object.values(Main.inputMethod._inputSourceManager.inputSources).find(source=>source.id==='rime');if(!source)throw Error('Rime source missing');source.activate()}
  if(q.action==='commit')Main.inputMethod.commit(q.text);
  if(q.action==='replace'){
   const im=Main.inputMethod;
   if(im._purpose===IBus.InputPurpose.PASSWORD||(im._hints & (IBus.InputHints.HIDDEN_TEXT|IBus.InputHints.PRIVATE)))throw Error('Sensitive input; replacement disabled');
   if(!im.currentFocus||im.hasPreedit())throw Error('No committed editable focus');
   if(im.getSurroundingText()[0]===null)throw Error('Client does not provide surrounding text; deletion unsupported');
   im.delete_surrounding(q.offset,q.count);im.commit(q.text);
  }
  if(q.action==='preedit')Main.inputMethod.set_preedit_text(q.text,q.text.length,q.text.length,Clutter.PreeditResetMode.CLEAR);
  if(q.action==='maximize'){const window=global.get_window_actors().find(actor=>actor.meta_window.get_title()===q.title)?.meta_window;window.maximize()}
  if(q.action==='position'){
   const window=global.get_window_actors().find(actor=>actor.meta_window.get_title()===q.title)?.meta_window;
   if(!window)throw Error('Probe window not found');window.unmaximize();window.move_resize_frame(false,q.x,q.y,q.width||420,260);
   if(q.focus)window.activate(global.get_current_time());
  }
  if(q.action==='bind-start'){
   const [x,y]=global.get_pointer();const window=this.windowAt(x,y);this.start={x,y,window,title:window?.get_title()||null,id:window?.get_stable_sequence(),at:GLib.get_monotonic_time()};
   return this.boundInfo();
  }
  if(q.action==='bound')return this.boundInfo();
  if(q.action==='close-bound'){if(this.boundInfo().alive)this.start.window.delete(global.get_current_time())}
  if(q.action==='activate'){
   const window=global.get_window_actors().find(actor=>actor.meta_window.get_title().includes(q.title))?.meta_window;
   if(!window)throw Error('Probe window not found: '+q.title);window.activate(global.get_current_time());
  }
  if(q.action==='hit')return {title:this.windowAt(q.x,q.y)?.get_title()||null,focus:global.display.focus_window?.get_title()};

  return {panelState:this.panelState,xDisplay:GLib.getenv('DISPLAY'),xAuthority:GLib.getenv('XAUTHORITY'),monitors:global.display.get_n_monitors(),stageSize:[global.stage.width,global.stage.height],pointer:global.get_pointer(),overview:Main.overview.visible,counts:this.counts,focus:global.display.focus_window?.get_title(),ime:{source:Main.inputMethod._currentSource?.id,engine:Main.inputMethod._context?.get_engine()?.name,hasFocus:!!Main.inputMethod.currentFocus,preedit:Main.inputMethod.hasPreedit(),purpose:Main.inputMethod._purpose,hints:Main.inputMethod._hints,surrounding:Main.inputMethod.getSurroundingText()},windows:global.get_window_actors().map(a=>({title:a.meta_window.get_title(),rect:(()=>{const r=a.meta_window.get_frame_rect();return {x:r.x,y:r.y,width:r.width,height:r.height}})(),clientType:a.meta_window.get_client_type()}))};
 }
 windowAt(x,y){let actor=global.stage.get_actor_at_pos(Clutter.PickMode.REACTIVE,x,y);while(actor){if(actor.meta_window)return actor.meta_window;actor=actor.get_parent()}return null}
 boundInfo(){if(!this.start)throw Error('No start has been bound');const w=this.start.window;return {x:this.start.x,y:this.start.y,stableId:this.start.id,title:this.start.title,alive:w?global.get_window_actors().some(a=>a.meta_window===w):false,focus:global.display.focus_window?.get_title(),endTitle:this.windowAt(...global.get_pointer().slice(0,2))?.get_title()||null}}

 disable(){this.terminalMonitor?.disable();for(const [panel,id] of this.panelSignals||[])panel.disconnect(id);if(this.confirmId)global.display.ungrab_accelerator(this.confirmId);if(this.confirmSignal)global.display.disconnect(this.confirmSignal);this.grab?.dismiss();global.stage.disconnect(this.signal);this.object.unexport();this.pointer=null;this.keyboard=null}
}
