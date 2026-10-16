// Reuse the ordinary parameter input so manual values and variable bindings
// continue through the same editor and serialization path.
export function enhanceShortcutField(root,input,backend){
 root.classList.add('shortcut-field');
 const modes=document.createElement('div');modes.className='shortcut-modes';modes.setAttribute('role','group');modes.setAttribute('aria-label','快捷键设置方式');
 modes.innerHTML='<button type="button" data-shortcut-mode="manual">手动输入</button><button type="button" data-shortcut-mode="capture">按键捕获</button>';
 root.prepend(modes);
 const capture=document.createElement('button');capture.type='button';capture.className='shortcut-capture-button';root.append(capture);
 const status=document.createElement('small');status.className='shortcut-capture-status';status.setAttribute('role','status');root.append(status);
 let mode=input.value.includes('${')?'manual':localStorage.getItem('waystroke.shortcutEntryMode')||'capture',busy=false;
 function paint(){
  root.dataset.mode=mode;input.readOnly=mode==='capture';capture.hidden=mode!=='capture';capture.disabled=busy;
  capture.textContent=busy?'正在捕获…':input.value?'重新捕获':'开始捕获';
  modes.querySelectorAll('button').forEach(button=>{button.setAttribute('aria-pressed',String(button.dataset.shortcutMode===mode));button.disabled=busy;});
 }
 modes.querySelectorAll('button').forEach(button=>button.onclick=event=>{event.preventDefault();mode=button.dataset.shortcutMode;localStorage.setItem('waystroke.shortcutEntryMode',mode);status.textContent='';paint()});
 input.addEventListener('input',paint);
 capture.onclick=async event=>{
  event.preventDefault();busy=true;status.textContent='请在捕获窗口中按下快捷键。';paint();
  try{
   const shortcut=await backend.captureShortcut();if(!root.isConnected)return;
   if(shortcut!==null){input.value=shortcut;input.dispatchEvent(new Event('input',{bubbles:true}));status.textContent='已记录 '+shortcut;}else status.textContent='已取消，原快捷键已保留。';
  }catch(error){if(root.isConnected)status.textContent='捕获失败：'+String(error)+'。可切换为手动输入。';}
  finally{busy=false;if(root.isConnected)paint();}
 };
 paint();
}
