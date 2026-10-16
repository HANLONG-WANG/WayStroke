import Clutter from 'gi://Clutter';
import St from 'gi://St';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import * as ModalDialog from 'resource:///org/gnome/shell/ui/modalDialog.js';
import * as Dialog from 'resource:///org/gnome/shell/ui/dialog.js';

// Action prompts live in GNOME, so the settings window need not be open.
export class PromptBridge {
    constructor(changed){this.changed=changed;this.active=null}
    show(request){
        if(!['确定','确定 / 取消','是 / 否'].includes(request.buttons))return Promise.reject(Object.assign(Error('未知询问按钮类型'),{kind:'validation'}));
        if(this.active)return Promise.reject(Object.assign(Error('已有询问对话框'),{kind:'conflict'}));
        return new Promise((resolve,reject)=>{
            const dialog=new ModalDialog.ModalDialog({styleClass:'prompt-dialog',destroyOnClose:true});
            const content=new Dialog.MessageDialogContent({title:request.title||'WayStroke',description:request.content||request.prompt||''});
            dialog.contentLayout.add_child(content);
            let entry=null;
            if(request.kind==='input'){
                entry=new St.Entry({text:request.defaultValue||'',can_focus:true,x_expand:true,style_class:'prompt-dialog-password-entry'});
                dialog.contentLayout.add_child(entry);dialog.setInitialKeyFocus(entry.clutter_text);
                entry.clutter_text.set_selection(0,-1);
            }
            const finish=(value,error=null)=>{
                if(this.active?.dialog!==dialog)return;
                this.active=null;dialog.close();this.changed({event:'dialog',open:false});
                if(error)reject(error);else resolve(value);
            };
            const cancel=()=>finish(null,Object.assign(Error('用户取消了对话框'),{kind:'canceled'}));
            if(entry)entry.clutter_text.connect('activate',()=>finish(entry.get_text()));
            this.active={dialog,cancel};
            if(request.kind==='input'||request.buttons==='确定 / 取消')dialog.addButton({label:'取消',action:cancel,key:Clutter.KEY_Escape});
            else if(request.buttons==='是 / 否')dialog.addButton({label:'否',action:()=>finish(false),key:Clutter.KEY_Escape});
            else dialog.addButton({label:'关闭',action:cancel,key:Clutter.KEY_Escape});
            dialog.addButton({label:request.buttons==='是 / 否'?'是':'确定',default:true,action:()=>finish(entry?entry.get_text():true)});
            if(!dialog.open()){this.active=null;dialog.destroy();reject(Object.assign(Error('GNOME 无法打开询问对话框'),{kind:'unavailable'}));return;}
            this.changed({event:'dialog',open:true,kind:request.kind});
        });
    }
    cancel(){this.active?.cancel()}
}

const SUPER=Clutter.ModifierType.SUPER_MASK|Clutter.ModifierType.MOD4_MASK;
const MODIFIERS=Clutter.ModifierType.CONTROL_MASK|Clutter.ModifierType.MOD1_MASK|Clutter.ModifierType.SHIFT_MASK|SUPER;
const modifierKeys=new Map([
    [Clutter.KEY_Control_L,Clutter.ModifierType.CONTROL_MASK],[Clutter.KEY_Control_R,Clutter.ModifierType.CONTROL_MASK],
    [Clutter.KEY_Alt_L,Clutter.ModifierType.MOD1_MASK],[Clutter.KEY_Alt_R,Clutter.ModifierType.MOD1_MASK],
    [Clutter.KEY_Shift_L,Clutter.ModifierType.SHIFT_MASK],[Clutter.KEY_Shift_R,Clutter.ModifierType.SHIFT_MASK],
    [Clutter.KEY_Super_L,SUPER],[Clutter.KEY_Super_R,SUPER],
]);
function shortcutName(key,state){
    const unicode=Clutter.keysym_to_unicode(key);
    let name=key===Clutter.KEY_ISO_Left_Tab?'Tab':Meta.accelerator_name(0,key);
    const letter=unicode>=65&&unicode<=90||unicode>=97&&unicode<=122;
    if(!name||!letter&&key!==Clutter.KEY_ISO_Left_Tab&&Clutter['KEY_'+name]!==key)return null;
    if(letter)name=String.fromCodePoint(unicode).toUpperCase();
    name=({space:'Space',Return:'Enter',Escape:'Esc',BackSpace:'Backspace'})[name]||name;
    if(!name)return null;
    const parts=[];
    if(state&Clutter.ModifierType.CONTROL_MASK)parts.push('Ctrl');
    if(state&Clutter.ModifierType.MOD1_MASK)parts.push('Alt');
    if(state&Clutter.ModifierType.SHIFT_MASK||key===Clutter.KEY_ISO_Left_Tab)parts.push('Shift');
    if(state&SUPER)parts.push('Super');
    return [...parts,name].join(' + ');
}

// A short-lived modal owns keys only while the user explicitly records a chord.
export class ShortcutCapture {
    constructor(changed){this.changed=changed;this.active=null}
    show(owner){
        if(this.active)return Promise.reject(Object.assign(Error('已有快捷键捕获正在进行'),{kind:'conflict'}));
        return new Promise((resolve,reject)=>{
            const dialog=new ModalDialog.ModalDialog({styleClass:'prompt-dialog',shouldFadeIn:false,shouldFadeOut:false});
            dialog.contentLayout.add_child(new Dialog.MessageDialogContent({title:'捕获快捷键',description:'按下想设置的组合键，松开全部按键后自动记录。Esc、Tab、Enter 也可记录；取消请点击下方按钮。'}));
            const preview=new St.Label({text:'请按下快捷键…',style_class:'headline',x_expand:true});dialog.contentLayout.add_child(preview);
            let keySignal=0,filterSignal=0,watch=0,timer=0,candidate=null;
            const pressed=new Set();
            const finish=(value,error=null)=>{
                if(this.active?.dialog!==dialog)return;
                this.active=null;
                if(keySignal)dialog.disconnect(keySignal);
                if(filterSignal)global.window_manager.disconnect(filterSignal);
                if(watch)Gio.bus_unwatch_name(watch);
                if(timer)GLib.source_remove(timer);
                dialog.close();this.changed({event:'shortcutCapture',open:false});
                if(error)reject(error);else resolve(value);
            };
            const cancel=()=>finish(null);
            this.active={dialog,cancel};
            dialog.addButton({label:'取消捕获',action:cancel});
            dialog.connect('destroy',cancel);
            if(!dialog.open()){finish(null,Object.assign(Error('GNOME 无法开始键盘捕获，请使用手动输入'),{kind:'unavailable'}));dialog.destroy();return;}
            // Binding filters run before Clutter event delivery. Suppress shell
            // actions such as Alt+Tab and Super+Space while this modal is active.
            filterSignal=global.window_manager.connect('filter-keybinding',()=>true);
            keySignal=dialog.connect('captured-event',(_stage,event)=>{
                const type=event.type();if(type!==Clutter.EventType.KEY_PRESS&&type!==Clutter.EventType.KEY_RELEASE)return Clutter.EVENT_PROPAGATE;
                const key=event.get_key_symbol(),code=event.get_key_code()||key,modifier=modifierKeys.get(key)||0;
                if(type===Clutter.EventType.KEY_PRESS){
                    pressed.add(code);
                    if(!modifier&&!candidate){candidate=shortcutName(key,event.get_state());preview.text=candidate||'无法识别此键，请尝试其他按键或取消后手动输入。';}
                }else{
                    pressed.delete(code);
                    const remaining=(event.get_state()&MODIFIERS)&~modifier;
                    if(candidate&&!pressed.size&&!remaining)finish(candidate);
                }
                return Clutter.EVENT_STOP;
            });
            watch=Gio.bus_watch_name_on_connection(Gio.DBus.session,owner,Gio.BusNameWatcherFlags.NONE,null,cancel);
            timer=GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT,20,()=>{timer=0;finish(null,Object.assign(Error('捕获超时，原快捷键已保留'),{kind:'timeout'}));return GLib.SOURCE_REMOVE});
            this.changed({event:'shortcutCapture',open:true});
        });
    }
    cancel(){this.active?.cancel()}
}
