import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as Volume from 'resource:///org/gnome/shell/ui/status/volume.js';
import * as Screenshot from 'resource:///org/gnome/shell/ui/screenshot.js';

function unavailable(message){return Object.assign(Error(message),{kind:'unavailable'})}
export class SystemBridge {
    constructor(clipboard,target){this.clipboard=clipboard;this.target=target;this.generation=0;this.selection=null;this.pending=new Set()}
    async support(){const control=Volume.getMixerControl();return {audio:{output:!!control.get_default_sink(),input:!!control.get_default_source()},brightness:!!Main.brightnessManager?.globalScale};}
    volume(request){
        const control=Volume.getMixerControl(),stream=request.device==='默认输出'?control.get_default_sink():request.device==='默认输入'?control.get_default_source():null;
        if(!stream)throw unavailable('当前没有可用的默认音频设备');
        const normal=control.get_vol_max_norm(),current=stream.volume/normal*100;
        switch(request.value){
            case '静音':stream.change_is_muted(true);break;case '取消静音':stream.change_is_muted(false);break;case '切换静音':stream.change_is_muted(!stream.is_muted);break;
            case '增加音量':case '降低音量':case '设置音量':{
                if(!Number.isFinite(request.amount)||request.amount<0)throw Object.assign(Error('音量百分比无效'),{kind:'validation'});
                const volume=Math.max(0,Math.min(100,request.value==='设置音量'?request.amount:current+(request.value==='增加音量'?request.amount:-request.amount)));
                if(stream.set_volume(Math.round(normal*volume/100))&&!stream.push_volume())throw unavailable('音频服务拒绝调整音量');break;
            }
            default:throw Object.assign(Error('未知音量操作'),{kind:'validation'});
        }
        return {volume:stream.volume/normal*100,muted:stream.is_muted};
    }
    brightness(request){
        const scale=Main.brightnessManager?.globalScale;if(!scale)throw unavailable('GNOME 没有可控制亮度的显示器或背光设备');
        if(!Number.isFinite(request.amount)||request.amount<0)throw Object.assign(Error('亮度百分比无效'),{kind:'validation'});
        switch(request.value){case '增加':scale.value=Math.min(1,scale.value+request.amount/100);break;case '降低':scale.value=Math.max(0,scale.value-request.amount/100);break;case '设置':scale.value=Math.max(0,Math.min(1,request.amount/100));break;default:throw Object.assign(Error('未知亮度操作'),{kind:'validation'})}
        return {brightness:scale.value*100};
    }
    async screenshot(request){
        const generation=this.generation,cancel=new Gio.Cancellable();this.pending.add(cancel);
        try{
            const shooter=new Shell.Screenshot(),stream=Gio.MemoryOutputStream.new_resizable();let captured;
            switch(request.value){
                case '全屏':captured=await shooter.screenshot(false,stream);break;
                case '目标窗口':{
                    const window=this.target(request.window);window.unminimize();window.activate(global.get_current_time());
                    if(global.display.focus_window!==window)throw Object.assign(Error('目标窗口没有获得截图焦点'),{kind:'targetInvalid'});
                    captured=await shooter.screenshot_window(true,false,stream);break;
                }
                case '选区':{
                    this.selection=new Screenshot.SelectArea();let area;
                    try{area=await this.selection.selectAsync()}finally{this.selection=null}
                    if(!area)throw Object.assign(Error('用户取消了截图选区'),{kind:'canceled'});
                    captured=await shooter.screenshot_area(area.x,area.y,area.width,area.height,stream);break;
                }
                default:throw Object.assign(Error('未知截图范围'),{kind:'validation'});
            }
            if(generation!==this.generation)throw Object.assign(Error('截图已取消'),{kind:'canceled'});
            if(!captured[0])throw unavailable('GNOME 截图未成功');
            stream.close(null);const bytes=stream.steal_as_bytes(),raw=bytes.toArray();
            const view=new DataView(raw.buffer,raw.byteOffset,raw.byteLength),width=view.getUint32(16),height=view.getUint32(20);
            if(request.destination==='剪贴板'){await this.clipboard.writeFormats(new Map([['image/png',bytes]]));}
            else if(request.destination==='文件'){
                if(!request.path)throw Object.assign(Error('请选择截图文件路径'),{kind:'validation'});
                const file=Gio.File.new_for_path(request.path);
                await new Promise((resolve,reject)=>file.replace_contents_bytes_async(bytes,null,false,Gio.FileCreateFlags.REPLACE_DESTINATION,cancel,(object,result)=>{try{object.replace_contents_finish(result);resolve()}catch(error){reject(error)}}));
            }else throw Object.assign(Error('未知截图输出'),{kind:'validation'});
            return {path:request.destination==='文件'?request.path:null,destination:request.destination,width,height};
        }catch(error){if(cancel.is_cancelled())throw Object.assign(Error('截图已取消'),{kind:'canceled'});throw error}finally{this.pending.delete(cancel)}
    }
    cancel(){this.generation++;for(const cancel of this.pending)cancel.cancel();this.selection?._grabHelper.ungrab()}
}
