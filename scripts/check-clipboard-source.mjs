// This tests the production native source, not clipboard integration with an app.
import GLib from 'gi://GLib';
import {clipboardSource} from '../extension/clipboard.js';
const formats=new Map([
    ['text/plain;charset=utf-8',new Uint8Array(new TextEncoder().encode('中文🙂'))],
    ['text/html',new Uint8Array(new TextEncoder().encode('<b>中文🙂</b>'))],
    ['image/png',new Uint8Array([137,80,78,71,0,255])],
]);
const source=await clipboardSource(new Map([...formats].map(([mime,bytes])=>[mime,new GLib.Bytes(bytes)])));
const results=[];
for(const [mimetype,expected] of formats){
    const stream=await new Promise((resolve,reject)=>source.read_async(mimetype,null,(object,result)=>{try{resolve(object.read_finish(result))}catch(error){reject(error)}}));
    const actual=stream.read_bytes(100,null).toArray();stream.close(null);
    if(actual.length!==expected.length||actual.some((byte,index)=>byte!==expected[index]))throw Error('MIME bytes changed: '+mimetype);
    results.push({mimetype,bytes:actual.length});
}
print(JSON.stringify({complete:true,scope:'native selection source byte round-trip only',formats:results},null,2));
