import copy,json,os,subprocess,tempfile,time,uuid
from pathlib import Path
from gi.repository import Gio,GLib
repo=Path(__file__).resolve().parents[1];root=Path(tempfile.mkdtemp(prefix='waystroke-composed-input-'))
assert os.environ.get('WAYSTROKE_PROBE_DIR'), 'Run through check-gnome.py in its private desktop'
c=Gio.bus_get_sync(Gio.BusType.SESSION,None)
def rpc(method,payload=None):
 r=json.loads(c.call_sync('io.github.waystroke.Core','/io/github/waystroke/Core','io.github.waystroke.Core1',method,None if payload is None else GLib.Variant('(s)',(json.dumps(payload),)),GLib.VariantType('(s)'),Gio.DBusCallFlags.NONE,3000,None).unpack()[0]);assert r['status']=='ok',r;return r['value']
def desktop(q):
 r=json.loads(c.call_sync('io.github.waystroke.Gnome','/io/github/waystroke/Gnome','io.github.waystroke.Gnome1','Call',GLib.Variant('(s)',(json.dumps(q),)),GLib.VariantType('(s)'),Gio.DBusCallFlags.NONE,3000,None).unpack()[0]);assert r['status']=='ok',r;return r['value']
def wait(fn):
 end=time.monotonic()+15
 while time.monotonic()<end:
  try:
   result=fn()
   if result:return result
  except (FileNotFoundError,json.JSONDecodeError):pass
  time.sleep(.1)
 raise RuntimeError('Host condition timeout')
def step(id,action,**params):return {'id':id,'action':action,'enabled':True,'params':{k:{'mode':'literal','value':{'kind':'text' if isinstance(v,str) else 'number','value':v}} for k,v in params.items()},'output':None,'onFailure':'stop','timeoutMs':3000,'workflowId':None,'arguments':{},'children':[],'otherwise':[],'loopItem':None,'loopIndex':None}
def symbol(id,kind):return {'id':id,'name':id,'kind':kind}
def ref(id,kind,path=None):return {'mode':'reference','value':{'symbolId':id,'kind':kind,'path':path or []}}
rule_id='phase-c-host-'+str(uuid.uuid4());workflow_id=rule_id+'-workflow';installed=False
hello=desktop({'operation':'hello'});assert 'declarativeActionsV1' in hello['capabilities']
capabilities=rpc('GetActionCapabilities');assert len(capabilities)==69 and next(v for v in capabilities if v['actionId']=='paste')['state']=='available'
original=rpc('GetConfig')['config'];original_ids={k:[item['id'] for item in original[k]] for k in ['rules','workflows','gestures']}
env=os.environ.copy();env.update(WAYSTROKE_PROBE_DIR=str(root),WAYSTROKE_CLIENT_PREFIX='PhaseC',GDK_BACKEND='wayland',GSK_RENDERER='cairo')
log=(root/'client.log').open('w');p=subprocess.Popen(['/usr/bin/python3',str(repo/'probes/gnome50/client.py')],env=env,stdout=log,stderr=log)
evidence={'scope':'isolated desktop composed Unicode input','hello':hello,'capabilities':capabilities,'complete':False}
try:
 windows=wait(lambda:(lambda ws:ws if {'PhaseC A','PhaseC B'}.issubset({w['title'] for w in ws}) else None)(desktop({'operation':'windows'})))
 a=next(w for w in windows if w['title']=='PhaseC A');b=next(w for w in windows if w['title']=='PhaseC B')
 assert all(w['clientType']==0 for w in [a,b]);desktop({'operation':'windowAction','action':'activate','window':b['handle']})
 context=desktop({'operation':'getContext'});context.update(window=a['handle'],applicationId=a['applicationId'],title=a['title'],sequence=0)
 transform=step('host-transform','text.transform',value='',operation='转大写',argument='',replacement='');transform['params']['value']=ref('host-input','text');transform['output']=symbol('host-message','text')
 workflow={'id':workflow_id,'name':'阶段 C 临时主会话检查','description':'执行后自动移除','inputs':[{'symbol':symbol('host-input','text'),'default':None}],'outputs':[{'symbol':symbol('host-return','text'),'value':ref('host-message','text')}],'steps':[transform]}
 call=step('host-call','flow.call');call.update(workflowId=workflow_id,arguments={'host-input':{'mode':'literal','value':{'kind':'text','value':'Stage C 主会话🙂 '}}},output=symbol('host-called','data'))
 parse=step('host-json','json.parse',value='2');parse['output']=symbol('host-count','any')
 loop=step('host-repeat','repeat',value=2);loop['params']['value']=ref('host-count','any');loop['loopIndex']=symbol('host-index','number')
 paste=step('host-paste','paste',value='',target='起点窗口',restore='恢复原内容');paste['params']['value']=ref('host-called','text',['host-return'])
 loop['children']=[paste,step('host-wait','wait',value=20)]
 snap=rpc('GetConfig');config=snap['config'];assert config['gestures'],'Existing fixture gesture required'
 config['workflows'].append(workflow);config['rules'].append({'id':rule_id,'name':'阶段 C 临时主会话检查','enabled':False,'feedback':False,'gestureId':config['gestures'][0]['id'],'auxiliaryButtons':[],'applicationId':a['applicationId'],'titleMatch':{'operator':'等于','value':'PhaseC A'},'steps':[call,parse,loop]})
 rpc('CommitConfig',{'requestId':rule_id,'expectedRevision':snap['revision'],'config':config});installed=True
 clipboard_before=desktop({'operation':'clipboardVersion'})['version']
 id=rpc('RunRule',{'ruleId':rule_id,'context':context})['executionId']
 execution=wait(lambda:next((v for v in rpc('GetRuntime')['executions'] if v['id']==id and v['state'] not in ['queued','running']),None));assert execution['state']=='succeeded',execution
 expected='STAGE C 主会话🙂 '*2
 client=wait(lambda:(lambda v:v if v['PhaseC A']['text']==expected else None)(json.loads((root/'PhaseC-client.json').read_text())))
 assert client['PhaseC B']['text']==''
 assert desktop({'operation':'clipboardVersion'})['version']>=clipboard_before+4
 evidence.update(execution=execution,actualNativeText=client['PhaseC A']['text'],otherWindowUnchanged=True,temporaryPasteRestorationCount=2,configurationValidation=rpc('ValidateDocument',rpc('GetConfig')['config']),nativeWindowClientType=0)
 assert evidence['configurationValidation']==[]
finally:
 if installed:
  snap=rpc('GetConfig');config=snap['config'];config['rules']=[v for v in config['rules'] if v['id']!=rule_id];config['workflows']=[v for v in config['workflows'] if v['id']!=workflow_id]
  rpc('CommitConfig',{'requestId':rule_id+'-cleanup','expectedRevision':snap['revision'],'config':config})
  after=rpc('GetConfig')['config'];evidence['temporaryDocumentsRemoved']=all(v['id']!=rule_id for v in after['rules']) and all(v['id']!=workflow_id for v in after['workflows']);evidence['originalIdsPreserved']=all(all(id in [v['id'] for v in after[k]] for id in ids) for k,ids in original_ids.items())
 if p.poll() is None:p.terminate();p.wait(timeout=5)
 evidence['runtime']= {k:rpc('GetRuntime')[k] for k in ['locked','inputArmed','status']}
 evidence['complete']='execution' in evidence and evidence.get('temporaryDocumentsRemoved') and evidence.get('originalIdsPreserved')
 (repo/'fixtures/phase-c/devkit-composed-input.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'artifacts':str(root),'complete':evidence['complete'],'runtime':evidence['runtime']},ensure_ascii=False))
