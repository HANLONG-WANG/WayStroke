// Only window-preview interactions; the native app will use Tauri window APIs.
function previewWindowAction(action){
 const hide=()=>{
  const reopen=document.getElementById('preview-reopen');
  document.querySelector('.shell').hidden=true;
  reopen.hidden=false;
  reopen.textContent=action==='minimize'?'恢复窗口':action==='quit'?'打开 WayStroke（已退出）':'打开设置（后台继续运行）';
  document.querySelector('.review-more').open=true;
 };
 if(action==='minimize'){hide();return}
 const finish=()=>{if(dirty){dirty=false;draft=null;if(page==='composer')page=composer.kind==='rule'?'rules':'actions';composer=null;templateDraft=null;render()}hide()};
 if(dirty){askConfirm(action==='quit'?'退出并放弃未保存的修改？手势、文本替换和当前动作将停止。':'关闭设置窗口并放弃未保存的修改？后台会继续运行。',finish);return}
 finish();
}
document.getElementById('window-minimize').onclick=()=>previewWindowAction('minimize');
document.getElementById('window-close').onclick=()=>previewWindowAction('close');
document.getElementById('window-maximize').onclick=()=>{
 const maximized=document.querySelector('.shell').classList.toggle('preview-maximized');
 document.body.classList.toggle('preview-maximized',maximized);
 const button=document.getElementById('window-maximize');
 button.setAttribute('aria-label',maximized?'还原窗口':'最大化窗口');button.title=maximized?'还原':'最大化';button.innerHTML=maximized?'<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5.5 5.5v-3h8v8h-3"/><rect x="2.5" y="5.5" width="8" height="8"/></svg>':'<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="3.5" y="3.5" width="9" height="9"/></svg>';
 window.dispatchEvent(new Event('resize'));
};
document.getElementById('preview-reopen').onclick=()=>{
 document.querySelector('.shell').hidden=false;
 document.getElementById('preview-reopen').hidden=true;
 document.querySelector('.review-more').open=false;
 render();
};
