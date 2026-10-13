// 窗口外的评审工具；场景只更换界面样本，不改变配置或产品权限。
function applyReviewState(){
 if(reviewState==='empty'){
  const fixtures={rules:['#rule-list','#editor','还没有手势规则','创建一条规则，将手势、窗口条件与动作关联。'],gestures:['#gesture-list','#template-editor','还没有手势模板','自由绘制一个轨迹，再将它用于规则。'],actions:['#workflow-list',null,'还没有可复用动作','把常用步骤保存为动作，供多条规则调用。'],text:['#snippet-list',null,'还没有文本替换','添加关键词和替换内容，减少重复输入。']};
  const fixture=fixtures[page];if(fixture){const [list,editor,title,description]=fixture;$(list).innerHTML=`<div class="empty review-empty"><span class="empty-symbol">＋</span><h2>${title}</h2><p>${description}</p></div>`;if(editor)$(editor).innerHTML='<div class="empty review-empty">创建条目后，在这里编辑详细设置。</div>';if($('#list-count'))$('#list-count').textContent='0 条规则'}
 }
 if(reviewState==='error'){
  const errors={rules:['#rule-errors','已启用规则使用相同的窗口条件、手势和辅助键。请调整条件或停用其中一条规则。'],gestures:['#template-compare-result','轨迹过短，请按住右键重新绘制。'],composer:['#composer-errors','步骤 2：输入参数需要数字。请选择数字变量或修改参数值。'],text:['#expand-status','无法替换文本：目标窗口已关闭。'],test:['#test-match','未找到匹配手势']};const fixture=errors[page];if(fixture&&$(fixture[0])){const node=$(fixture[0]);node.hidden=false;node.textContent=fixture[1]}
 }
}
document.getElementById('review-state').onchange=e=>{reviewState=e.target.value;render()};
document.getElementById('review-service').onchange=e=>{runtimeMode=e.target.value;if(reviewExecution==='running'&&!textRuntimeReady()){reviewExecution='canceled';$('#review-execution-state').value='canceled'}render()};
document.getElementById('review-setup').onclick=()=>startSetup();

document.getElementById('review-execution').onclick=()=>previewExecution('打开工作目录',[]);

document.getElementById('review-input').onchange=e=>{reviewInput=e.target.value;if(page==='runtime')render()};
document.getElementById('review-reset').onclick=()=>askConfirm('恢复全部示例数据？恢复前会自动备份当前配置。',()=>{createBackup('恢复示例前自动备份');data=structuredClone(starter);data.applications=structuredClone(sampleApps);data.exclusions=[];ensureWorkflows();for(const rule of data.rules){rule.applicationId=data.applications.find(app=>app.name===rule.scope)?.id||'';rule.titleMatch={operator:'包含',value:''}}draft=null;selected=data.rules[0].id;persist();dirty=false;render();toast('已恢复示例数据')});

document.getElementById('review-execution-state').onchange=e=>{reviewExecution=e.target.value;if(page==='runtime')render()};
