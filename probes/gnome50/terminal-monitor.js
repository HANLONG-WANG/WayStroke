// Fixed-rule technical probe in the disposable GNOME only; no keystroke logs.
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import IBus from 'gi://IBus';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
export class TerminalMonitor {
 constructor(keyboard){
  this.keyboard=keyboard;this.im=Main.inputMethod;this.token='';this.records=[];this.candidates=new Map();this.grabs=new Map();
  this.originalNotify=this.im.notify_key_event;
  this.im.notify_key_event=(event,handled)=>{
   if(!handled&&event.type()===Clutter.EventType.KEY_PRESS&&this.terminalFocus()){
    const key=event.get_key_symbol(),state=event.get_state();
    if(state&(Clutter.ModifierType.CONTROL_MASK|Clutter.ModifierType.MOD1_MASK|Clutter.ModifierType.SUPER_MASK))this.token='';
    else if(key===0x20||key===0xff0d){this.candidates.set(event.get_time(),this.token==='abc');this.token=''}
    else if(key===0xff08)this.token=this.token.slice(0,-1);
    else if(key>=33&&key<=126)this.token=(this.token+String.fromCharCode(key)).slice(-4);
    else this.token='';
   }else if(!this.terminalFocus())this.token='';
   return this.originalNotify.call(this.im,event,handled);
  };
  this.context=this.im._context;
  this.commitSignal=this.context.connect('commit-text',(_context,text)=>{if(this.terminalFocus())this.token=(this.token+text.get_text()).slice(-4)});
  for(const [name,key,code] of [['space',0x20,65],['Return',0xff0d,36]]){
   const id=global.display.grab_accelerator(name,Meta.KeyBindingFlags.NONE);
   if(!id)throw Error('Confirmation unavailable: '+name);
   this.grabs.set(id,{key,code,name:'external-grab-'+id});Main.wm.allowKeybinding('external-grab-'+id,Shell.ActionMode.NORMAL);
  }
  this.signal=global.display.connect('accelerator-activated',(_display,id,_device,time)=>{
   const grab=this.grabs.get(id);if(!grab)return;
   const matched=this.terminalFocus()&&this.candidates.get(time)===true;
   this.candidates.delete(time);
   for(const g of this.grabs.values())Main.wm.allowKeybinding(g.name,Shell.ActionMode.NONE);
   const stamp=global.display.get_current_time_roundtrip();
   if(matched){
    // VTE sends this single commit to the PTY in byte order. Mixing keyboard
    // Backspace with a text-input commit allowed the commit to overtake keys.
    this.im.commit('\x7f'.repeat(3)+'2003');
   }
   if(this.im.currentFocus){this.im.forward_key(grab.key,grab.code,0,stamp,true);this.im.forward_key(grab.key,grab.code,0,stamp,false)}
   else {const now=GLib.get_monotonic_time();this.keyboard.notify_keyval(now,grab.key,Clutter.KeyState.PRESSED);this.keyboard.notify_keyval(now+1,grab.key,Clutter.KeyState.RELEASED)}
   this.records.push({confirm:grab.key===0x20?'space':'enter',matched,focus:global.display.focus_window?.get_title()});
   GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE,()=>{for(const g of this.grabs.values())Main.wm.allowKeybinding(g.name,Shell.ActionMode.NORMAL);return GLib.SOURCE_REMOVE});
  });
 }
 terminalFocus(){return !!this.im.currentFocus&&this.im._purpose===IBus.InputPurpose.TERMINAL}
 reset(){this.token='';this.candidates.clear()}
 disable(){
  this.im.notify_key_event=this.originalNotify;this.context.disconnect(this.commitSignal);global.display.disconnect(this.signal);
  for(const id of this.grabs.keys())global.display.ungrab_accelerator(id);this.grabs.clear();this.reset();
 }
}
