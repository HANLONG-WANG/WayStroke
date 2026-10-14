// This tests the production native source, not clipboard integration with an app.
import GLib from 'gi://GLib';
import Native from 'gi://WayStrokeClipboard?version=1.0';
import {clipboardSource} from '../extension/clipboard.js';
const formats=new Map([
    ['text/plain;charset=utf-8',new Uint8Array(new TextEncoder().encode('中文🙂'))],
    ['text/html',new Uint8Array(new TextEncoder().encode('<b>中文🙂</b>'))],
    ['image/png',new Uint8Array([137,80,78,71,0,255])],
]);
const source=await clipboardSource(new Map([...formats].map(([mime,bytes])=>[mime,new GLib.Bytes(bytes)])));
const watch=Native.watch_new();let requested=0;
watch.connect('requested',()=>requested++);
const results=[];
for(const [mimetype,expected] of formats){
    const stream=await new Promise((resolve,reject)=>source.read_async(mimetype,null,(object,result)=>{try{resolve(object.read_finish(result))}catch(error){reject(error)}}));
    const actual=stream.read_bytes(100,null).toArray();stream.close(null);
    if(actual.length!==expected.length||actual.some((byte,index)=>byte!==expected[index]))throw Error('MIME bytes changed: '+mimetype);
    results.push({mimetype,bytes:actual.length});
}
if(requested!==formats.size)throw Error('Transfer observer missed existing source');
Native.watch_stop(watch);
const stream=await new Promise((resolve,reject)=>source.read_async('text/html',null,(object,result)=>{try{resolve(object.read_finish(result))}catch(error){reject(error)}}));
stream.close(null);
if(requested!==formats.size)throw Error('Stopped transfer observer remained active');
print(JSON.stringify({complete:true,scope:'native selection source byte round-trip and observer lifecycle only',formats:results,transferObserver:true,stoppedObserverInactive:true},null,2));
