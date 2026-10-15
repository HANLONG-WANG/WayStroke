import { Backend } from './backend';
import { mountEditor } from './editor.js';
import frame from './frame.html?raw';
import './style.css';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { getVersion } from '@tauri-apps/api/app';
const backend=new Backend();
try {
 const initial=await backend.initialize();document.body.innerHTML=frame;document.getElementById('app-version')!.textContent=await getVersion();const editor=mountEditor(backend,initial);if(!backend.connected)backend.onConnection(false);
 const window=getCurrentWindow();
 await window.onCloseRequested(event=>{event.preventDefault();editor.requestClose('close')});
 document.getElementById('window-minimize')!.onclick=()=>backend.windowAction('minimize');
 const updateWindowState=async()=>{const max=await window.isMaximized();const button=document.getElementById('window-maximize')!;button.setAttribute('aria-label',max?'还原窗口':'最大化窗口');button.title=max?'还原':'最大化';button.innerHTML=max?'<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5.5 5.5v-3h8v8h-3"/><rect x="2.5" y="5.5" width="8" height="8"/></svg>':'<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="3.5" y="3.5" width="9" height="9"/></svg>';};
 document.getElementById('window-maximize')!.onclick=async()=>{await window.toggleMaximize();await updateWindowState();};
 await window.onResized(updateWindowState);
 document.getElementById('window-close')!.onclick=()=>editor.requestClose('close');
} catch(error){document.getElementById('loading')!.textContent='后台连接失败：'+String(error);}
