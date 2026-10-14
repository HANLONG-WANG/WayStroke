import Clutter from 'gi://Clutter';
import St from 'gi://St';
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
