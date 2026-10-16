// Run with GJS and the Mutter typelib/library paths from docs/development.md.
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import {snapshot} from '../extension/clipboard.js';

const controls=['SAVE_TARGETS','TARGETS','TIMESTAMP','MULTIPLE','DELETE','INSERT_SELECTION','INSERT_PROPERTY'];
const formats=new Map([
    ['text/plain;charset=utf-8',new TextEncoder().encode('original 中文')],
    ['text/html',new TextEncoder().encode('<b>original</b>')],
    ['application/x-waystroke-fixture',new Uint8Array([0,255,42])],
    ['UTF8_STRING',new TextEncoder().encode('original 中文')],
]);
function selection(failure=null){
    return {
        requested:[],
        get_mimetypes(){return [...controls,...formats.keys()]},
        transfer_async(_type,mime,_limit,stream,_cancel,done){
            this.requested.push(mime);
            const error=controls.includes(mime)||mime===failure?Error('Cannot read '+mime):null;
            if(!error)stream.write_all(formats.get(mime),null);
            GLib.idle_add(GLib.PRIORITY_DEFAULT,()=>{done(this,{error});return GLib.SOURCE_REMOVE});
        },
        transfer_finish(result){if(result.error)throw result.error},
    };
}
const original=selection(),saved=await snapshot(original,null);
if(original.requested.join('|')!==[...formats.keys()].join('|'))throw Error('Selection controls must never be requested');
for(const [mime,bytes] of formats){
    if(JSON.stringify([...saved.get(mime).toArray()])!==JSON.stringify([...bytes]))throw Error('Changed clipboard bytes: '+mime);
}
let rejected=false;
try{await snapshot(selection('text/html'),null)}catch(error){rejected=error.message==='Cannot read text/html'}
if(!rejected)throw Error('Real data read failures must propagate');
print('PASS: X11 control targets skipped; text, HTML, binary and UTF8_STRING preserved; real read errors propagated.');
