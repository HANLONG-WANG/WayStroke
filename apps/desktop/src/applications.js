const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

// Display names are labels only. Every control and saved condition uses an ID.
export function applicationOptions(apps,current='',globalLabel='所有应用'){
 const entries=new Map(apps.filter(app=>app.id).map(app=>[app.id,app]));
 if(current&&!entries.has(current))entries.set(current,{id:current,name:current});
 return `<option value="" ${current===''?'selected':''}>${esc(globalLabel)}</option>`+[...entries.values()].map(app=>`<option value="${esc(app.id)}" ${app.id===current?'selected':''}>${esc(app.name)} · ${esc(app.id)}</option>`).join('');
}

export function createApplicationPicker(backend,getSavedApps){
 const preferenceKey='waystroke.applicationCandidates';
 const preferences=JSON.parse(localStorage.getItem(preferenceKey)||'{"recent":[],"hidden":[]}');
 let installed=[];const recent=new Map(preferences.recent.map(app=>[app.id,app])),hidden=new Set(preferences.hidden),controls=new Set();
 const unique=apps=>[...new Map(apps.map(app=>[app.id,app])).values()];
 function catalogApps(){return unique([...installed,...recent.values(),...getSavedApps()])}
 function candidateApps(){return unique([...recent.values(),...getSavedApps()]).filter(app=>!hidden.has(app.id))}
 function saveCandidates(){localStorage.setItem(preferenceKey,JSON.stringify({recent:[...recent.values()],hidden:[...hidden]}))}
 function refresh(){for(const control of controls){if(control.root.isConnected)control.paint();else controls.delete(control)}}
 function mount(root,{id,current='',name='',label='作用范围',globalLabel='所有应用',includeTitle=false,onChange}){
  let selection={id:current,name:name||current};
  root.classList.add('application-control');
  root.innerHTML=`<label class="field"><span>${esc(label)}</span><select id="${id}" aria-label="${esc(label)}"></select></label><div class="application-controls"><button type="button" class="link-button choose-application">选择应用…</button><button type="button" class="link-button remove-application" title="从候选中移除，并重置当前选择；已保存规则保持不变。">删除此候选</button></div><small class="application-identity"></small>`;
  const select=root.querySelector('select'),identity=root.querySelector('.application-identity'),remove=root.querySelector('.remove-application');
  // A saved rule's current condition must remain visible even if its candidate
  // was hidden elsewhere. Removing a candidate never rewrites saved rules.
  function paint(){select.innerHTML=applicationOptions([...candidateApps(),selection],selection.id,globalLabel);identity.textContent=selection.id?'应用 ID：'+selection.id:'';remove.disabled=!selection.id;}
  function choose(app){if(!root.isConnected)return;selection={id:app.id,name:app.name};if(app.id){recent.set(app.id,selection);hidden.delete(app.id);saveCandidates()}refresh();onChange(app);}
  select.onchange=()=>choose({id:select.value,name:candidateApps().find(app=>app.id===select.value)?.name||select.value});
  root.querySelector('.choose-application').onclick=()=>open(choose,includeTitle);
  remove.onclick=()=>{hidden.add(selection.id);recent.delete(selection.id);selection={id:'',name:''};saveCandidates();refresh();onChange(selection)};
  controls.add({root,paint});
  paint();return {get value(){return selection.id},get name(){return selection.name}};
 }
 async function open(choose,includeTitle){
  const dialog=document.getElementById('application-dialog');
  dialog.innerHTML=`<div class="dialog-header"><div><h2>选择应用</h2><p class="note">搜索已安装应用，或从打开的窗口获取真实应用标识。</p></div><button type="button" aria-label="关闭应用选择器">×</button></div><div class="dialog-body"><input class="application-search" aria-label="搜索应用" placeholder="搜索应用名称、应用 ID 或窗口标题…"><p class="note application-loading" role="status">正在读取应用和窗口…</p>${includeTitle?'<label class="application-title-option"><input type="checkbox" id="application-use-title">选取窗口时，同时将其标题作为“包含”条件</label>':''}<div class="application-results"></div><details class="manual-application"><summary>手动填写应用 ID</summary><form id="manual-application-form"><label class="field"><span>应用 ID</span><input name="applicationId" required placeholder="例如 org.mozilla.firefox.desktop"></label><label class="field"><span>显示名称（可选）</span><input name="applicationName" placeholder="例如 Firefox"></label><p class="note">请使用运行状态或窗口选择器显示的真实标识。</p><button class="primary" type="submit">使用此应用</button></form></details></div>`;
  const close=()=>dialog.close();dialog.querySelector('.dialog-header>button').onclick=close;
  const finish=app=>{close();choose(app)};
  dialog.querySelector('form').onsubmit=e=>{e.preventDefault();const form=new FormData(e.target),id=String(form.get('applicationId')).trim();if(!id){e.target.elements.applicationId.setCustomValidity('请填写应用 ID');e.target.reportValidity();return}finish({id,name:String(form.get('applicationName')).trim()||id})};
  dialog.querySelector('[name="applicationId"]').oninput=e=>e.target.setCustomValidity('');
  dialog.showModal();
  const results=dialog.querySelector('.application-results'),search=dialog.querySelector('.application-search'),status=dialog.querySelector('.application-loading');
  search.focus();
  const reads=await Promise.allSettled([backend.listApplications(),backend.listWindows()]);
  if(!status.isConnected||!dialog.open)return;
  if(reads[0].status==='fulfilled')installed=reads[0].value;
  const windows=reads[1].status==='fulfilled'?reads[1].value.filter(window=>window.applicationId):[];
  status.textContent=reads.map((result,index)=>result.status==='rejected'?`${index?'窗口':'已安装应用'}读取失败：${String(result.reason)}`:'').filter(Boolean).join('；');
  function render(){
   const query=search.value.trim().toLowerCase(),matches=(...values)=>values.join(' ').toLowerCase().includes(query);
   const apps=catalogApps().sort((a,b)=>a.name.localeCompare(b.name));
   const rows=windows.filter(window=>matches(window.title,window.applicationId));
   const entries=apps.filter(app=>matches(app.name,app.id));
   results.innerHTML=`<h3>当前窗口</h3>${rows.map((window,index)=>`<button type="button" data-window-index="${index}"><strong>${esc(window.title||window.applicationId)}</strong><small>${esc(window.applicationId)}</small></button>`).join('')||'<p class="note">没有匹配的窗口</p>'}<h3>已安装及已配置应用</h3>${entries.map((app,index)=>`<button type="button" data-app-index="${index}"><strong>${esc(app.name)}</strong><small>${esc(app.id)}</small></button>`).join('')||'<p class="note">没有匹配的应用，可在下方手动填写。</p>'}`;
   results.querySelectorAll('[data-app-index]').forEach(button=>button.onclick=()=>finish(entries[Number(button.dataset.appIndex)]));
   results.querySelectorAll('[data-window-index]').forEach(button=>button.onclick=()=>{const window=rows[Number(button.dataset.windowIndex)],app=apps.find(app=>app.id===window.applicationId);finish({id:window.applicationId,name:app?.name||window.applicationId,...(includeTitle&&dialog.querySelector('#application-use-title').checked?{title:window.title}:{})})});
  }
  search.oninput=render;render();
 }
 return {mount};
}
