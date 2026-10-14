#!/usr/bin/env python3
"""Exercise the real core executor on a private bus; the desktop fixture only supplies hello.

No physical input is injected. All values, branches, loops, calls, failures and
execution events are produced by the production core, not the fixture.
"""
import copy,json,os,subprocess,sys,tempfile,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from gi.repository import Gio,GLib
REPO=Path(__file__).resolve().parents[1]
if '--inside' not in sys.argv:
    root=Path(tempfile.mkdtemp(prefix='waystroke-execution-check-'))
    (root/'runtime').mkdir(mode=0o700);(root/'data').mkdir(mode=0o700);(root/'cache').mkdir(mode=0o700)
    # The temporary /tmp mount cannot be trashed by GIO. Keep both source and
    # private trash on the workspace/home filesystem, and remove only this fixture.
    with tempfile.TemporaryDirectory(prefix='.waystroke-trash-check-',dir=REPO) as trash_root:
        trash_root=Path(trash_root);(trash_root/'data').mkdir(mode=0o700)
        env=os.environ.copy();env.update(XDG_CONFIG_HOME=str(root),XDG_RUNTIME_DIR=str(root/'runtime'),XDG_DATA_HOME=str(trash_root/'data'),XDG_CACHE_HOME=str(root/'cache'),WAYSTROKE_EXECUTION_CHECK=str(root),WAYSTROKE_TRASH_CHECK=str(trash_root))
        print('Execution artifacts:',root,flush=True)
        sys.exit(subprocess.run(['dbus-run-session','--',sys.executable,__file__,'--inside'],env=env).returncode)

# Route system calls exclusively to this disposable bus; never the host login1.
os.environ['DBUS_SYSTEM_BUS_ADDRESS']=os.environ['DBUS_SESSION_BUS_ADDRESS']
root=Path(os.environ['WAYSTROKE_EXECUTION_CHECK']);connection=Gio.bus_get_sync(Gio.BusType.SESSION,None)
loop=GLib.MainLoop()
xml=Gio.DBusNodeInfo.new_for_xml('<node><interface name="io.github.waystroke.Gnome1"><method name="Call"><arg type="s" direction="in"/><arg type="s" direction="out"/></method></interface></node>')
def fixture(c,s,p,i,m,args,invocation):
    q=json.loads(args.unpack()[0]);assert q['operation'] in ['hello','release','releaseInputs'],q
    if q['operation'] in ['release','releaseInputs']:
        invocation.return_value(GLib.Variant('(s)',(json.dumps({'status':'ok','value':None}),)));return
    invocation.return_value(GLib.Variant('(s)',(json.dumps({'status':'ok','value':{'protocolVersion':1,'shellVersion':'50.5','instance':'execution-fixture','locked':False}}),)))
connection.register_object('/io/github/waystroke/Gnome',xml.interfaces[0],fixture,None,None)
Gio.bus_own_name_on_connection(connection,'io.github.waystroke.Gnome',Gio.BusNameOwnerFlags.NONE,None,None)
fixture_xml=Gio.DBusNodeInfo.new_for_xml('<node><interface name="io.github.waystroke.Fixture"><method name="Echo"><arg type="s" direction="in"/><arg type="i" direction="in"/><arg type="d" direction="in"/><arg type="b" direction="in"/><arg type="as" direction="in"/><arg type="s" direction="out"/><arg type="i" direction="out"/><arg type="d" direction="out"/><arg type="b" direction="out"/><arg type="as" direction="out"/></method><method name="Ping"/><method name="Slow"/></interface><interface name="org.freedesktop.DBus.Properties"><method name="Get"><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/></method><method name="Set"><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="in"/></method></interface></node>')
fixture_property={'value':'initial'}
def integration_fixture(c,s,p,i,m,args,invocation):
    if m=='Echo':invocation.return_value(GLib.Variant('(sidbas)',args.unpack()))
    elif m=='Ping':invocation.return_value(GLib.Variant('()',()))
    elif m=='Slow':GLib.timeout_add(200,lambda:(invocation.return_value(GLib.Variant('()',())),False)[1])
    elif m=='Get':invocation.return_value(GLib.Variant('(v)',(GLib.Variant('s',fixture_property['value']),)))
    elif m=='Set':fixture_property['value']=args.unpack()[2];invocation.return_value(GLib.Variant('()',()))
for interface in fixture_xml.interfaces:connection.register_object('/io/github/waystroke/Fixture',interface,integration_fixture,None,None)
media_state={'status':'Stopped','seek':0,'calls':[],'canSeek':True}
media_xml=Gio.DBusNodeInfo.new_for_xml('<node><interface name="org.mpris.MediaPlayer2"><property name="Identity" type="s" access="read"/><property name="DesktopEntry" type="s" access="read"/></interface><interface name="org.mpris.MediaPlayer2.Player"><property name="PlaybackStatus" type="s" access="read"/><property name="CanControl" type="b" access="read"/><property name="CanPlay" type="b" access="read"/><property name="CanPause" type="b" access="read"/><property name="CanSeek" type="b" access="read"/><property name="CanGoNext" type="b" access="read"/><property name="CanGoPrevious" type="b" access="read"/><method name="Play"/><method name="Pause"/><method name="PlayPause"/><method name="Stop"/><method name="Previous"/><method name="Next"/><method name="Seek"><arg type="x" direction="in"/></method></interface></node>')
def media_call(c,s,p,i,m,args,invocation):
    media_state['calls'].append([m,*args.unpack()])
    if m=='Play':media_state['status']='Playing'
    elif m=='Pause':media_state['status']='Paused'
    elif m=='PlayPause':media_state['status']='Paused' if media_state['status']=='Playing' else 'Playing'
    elif m=='Stop':media_state['status']='Stopped'
    elif m=='Seek':media_state['seek']+=args.unpack()[0]
    invocation.return_value(GLib.Variant('()',()))
def media_property(c,s,p,i,name):
    if name=='Identity':return GLib.Variant('s','Fixture Player')
    if name=='DesktopEntry':return GLib.Variant('s','fixture')
    if name=='PlaybackStatus':return GLib.Variant('s',media_state['status'])
    return GLib.Variant('b',media_state['canSeek'] if name=='CanSeek' else True)
for interface in media_xml.interfaces:connection.register_object('/org/mpris/MediaPlayer2',interface,media_call,media_property,None)
Gio.bus_own_name_on_connection(connection,'org.mpris.MediaPlayer2.waystrokeFixture',Gio.BusNameOwnerFlags.NONE,None,None)
session_calls=[];suspend_state={'capability':'yes','deny':False}
session_xml=Gio.DBusNodeInfo.new_for_xml('<node><interface name="org.gnome.SessionManager"><method name="Logout"><arg type="u" direction="in"/></method></interface><interface name="org.freedesktop.login1.Manager"><method name="CanSuspend"><arg type="s" direction="out"/></method><method name="Suspend"><arg type="b" direction="in"/></method></interface></node>')
def session_fixture(c,s,p,i,m,args,invocation):
    session_calls.append([m,*args.unpack()])
    if m=='CanSuspend':invocation.return_value(GLib.Variant('(s)',(suspend_state['capability'],)))
    elif suspend_state['deny']:invocation.return_dbus_error('org.freedesktop.DBus.Error.AccessDenied','Fixture permission denied')
    else:invocation.return_value(GLib.Variant('()',()))
connection.register_object('/org/gnome/SessionManager',session_xml.interfaces[0],session_fixture,None,None)
connection.register_object('/org/freedesktop/login1',session_xml.interfaces[1],session_fixture,None,None)
for name in ['org.gnome.SessionManager','org.freedesktop.login1']:Gio.bus_own_name_on_connection(connection,name,Gio.BusNameOwnerFlags.NONE,None,None)
thread=threading.Thread(target=loop.run,daemon=True);thread.start()
def call(method,payload=None):
    result=connection.call_sync('io.github.waystroke.Core','/io/github/waystroke/Core','io.github.waystroke.Core1',method,None if payload is None else GLib.Variant('(s)',(json.dumps(payload),)),GLib.VariantType('(s)'),Gio.DBusCallFlags.NONE,3000,None)
    response=json.loads(result.unpack()[0]);assert response['status']=='ok',response
    return response['value']
def wait(fn):
    end=time.monotonic()+10
    while time.monotonic()<end:
        try:
            value=fn()
            if value:return value
        except GLib.Error:pass
        time.sleep(.02)
    raise AssertionError('executor condition timed out')
def literal(v):
    kind='boolean' if isinstance(v,bool) else 'number' if isinstance(v,(int,float)) else 'text'
    return {'mode':'literal','value':{'kind':kind,'value':v}}
def ref(id,kind='number',path=None):return {'mode':'reference','value':{'symbolId':id,'path':path or [],'kind':kind}}
def symbol(id,kind='number'):return {'id':id,'name':id,'kind':kind}
def step(id,action,**params):
    return {'id':id,'action':action,'enabled':True,'params':{k:literal(v) for k,v in params.items()},'output':None,'onFailure':'stop','timeoutMs':None,'workflowId':None,'arguments':{},'children':[],'otherwise':[],'loopItem':None,'loopIndex':None}
def output(s,id,kind='number'):s['output']=symbol(id,kind);return s
context={'sequence':1,'monotonicMs':1,'position':[24,35],'window':None,'applicationId':'fixture.desktop','title':'Fixture','workspace':0,'monitor':0,'locked':False}
log=(root/'core.log').open('w');process=subprocess.Popen([str(REPO/'target/debug/waystroke-core')],stdout=log,stderr=log)
results={};events=[]
connection.signal_subscribe('io.github.waystroke.Core','io.github.waystroke.Core1','RuntimeChanged','/io/github/waystroke/Core',None,Gio.DBusSignalFlags.NONE,lambda *args:events.append(json.loads(args[-1].unpack()[0])))
try:
    wait(lambda:call('GetConfig'))
    config=call('GetConfig')['config'];config['settings']['feedback']=False
    config['gestures']=[{'id':'g','name':'fixture','mainSampleId':'sample','samples':[{'id':'sample','points':[[0,0],[100,0]]}]}]
    def save(steps,workflows=None):
        snapshot=call('GetConfig');config=copy.deepcopy(snapshot['config'])
        config['rules']=[{'id':'rule','name':'Execution check','enabled':True,'feedback':False,'gestureId':'g','auxiliaryButtons':[],'applicationId':None,'titleMatch':{'operator':'包含','value':''},'steps':steps}]
        config['workflows']=workflows or []
        return call('CommitConfig',{'requestId':'check','expectedRevision':snapshot['revision'],'config':config})
    # Seed the gesture before the first save.
    call('CommitConfig',{'requestId':'seed','expectedRevision':0,'config':config})
    def run():return call('RunRule',{'ruleId':'rule','context':context})['executionId']
    def finished(id):return wait(lambda:next((e for e in call('GetRuntime')['executions'] if e['id']==id and e['state'] not in ['queued','running']),None))
    initial=output(step('initial','variable',name='base',kind='数字',value=2),'base')
    calc=output(step('calc','number.calculate',left=0,value='乘',right=3),'product');calc['params']['left']=ref('input')
    workflow={'id':'workflow','name':'Multiply','description':'','inputs':[{'symbol':symbol('input'),'default':None}],'outputs':[{'symbol':symbol('return'),'value':ref('product')}],'steps':[calc]}
    callstep=output(step('call','flow.call'),'called','data');callstep.update(workflowId='workflow',arguments={'input':ref('base')})
    branch=step('branch','condition',value='变量',source='',operator='等于',compare=6);branch['params']['source']=ref('called','number',['return'])
    loopstep=step('repeat','repeat',value=3);loopstep['loopIndex']=symbol('index')
    item=output(step('loop-value','variable',name='local',kind='数字',value=0),'local');item['params']['value']=ref('index');loopstep['children']=[item]
    branch['children']=[loopstep];branch['otherwise']=[step('wrong','wait',value=1000)]
    disabled=step('disabled','wait',value=1000);disabled['enabled']=False
    save([initial,callstep,branch,disabled],[workflow]);execution=finished(run())
    assert execution['state']=='succeeded',execution
    assert [e['stepId'] for e in execution['steps']]==['initial','call','calc','branch','repeat','loop-value','loop-value','loop-value'],execution
    assert [e['output']['value'] for e in execution['steps'] if e['stepId']=='loop-value']==[0,1,2]
    assert next(e for e in execution['steps'] if e['stepId']=='call')['output']['value']['return']['value']==6
    results['scopedNestedCallAndRepeat']=execution
    # Continue and break only affect their nearest loop; iterations remain sequential.
    repeat=step('control-repeat','repeat',value=5);repeat['loopIndex']=symbol('iteration')
    skip=step('skip','condition',value='变量',source='',operator='等于',compare=1);skip['params']['source']=ref('iteration');skip['children']=[step('continue','loop.continue')]
    stop=step('break-if','condition',value='变量',source='',operator='等于',compare=3);stop['params']['source']=ref('iteration');stop['children']=[step('break','loop.break')]
    value=output(step('visit','variable',name='visit',kind='数字',value=0),'visit-result');value['params']['value']=ref('iteration')
    repeat['children']=[skip,stop,value]
    save([repeat,step('after-loop','wait',value=0)]);execution=finished(run())
    assert execution['state']=='succeeded' and execution['steps'][-1]['stepId']=='after-loop'
    assert [s['output']['value'] for s in execution['steps'] if s['stepId']=='visit']==[0,2]
    results['nearestLoopControl']=execution
    stopping=step('stop-loop','repeat',value=3);stopping['children']=[step('stop-sequence','flow.stop',value='done'),step('not-run-child','wait',value=0)]
    save([stopping,step('not-run-root','wait',value=0)]);execution=finished(run());assert execution['state']=='succeeded' and [s['stepId'] for s in execution['steps']]==['stop-loop','stop-sequence'],execution;results['stopWholeNestedSequence']=execution
    lists=[]
    for index,(operation,argument,expected) in enumerate([('追加',3,{'kind':'list','value':[{'kind':'number','value':1},{'kind':'number','value':2},{'kind':'number','value':3}]}),('查找',2,{'kind':'number','value':1}),('读取指定索引',0,{'kind':'number','value':1}),('移除指定索引',0,{'kind':'list','value':[{'kind':'number','value':2}]}),('获取长度',0,{'kind':'number','value':2})]):
        item=output(step('list-'+str(index),'list.change',value='',operation=operation,argument=argument),'list-result-'+str(index),'list' if expected['kind']=='list' else 'number');item['params']['value']={'mode':'literal','value':{'kind':'list','value':[{'kind':'number','value':1},{'kind':'number','value':2}]}};lists.append((item,expected))
    save([s for s,_ in lists]);execution=finished(run());assert execution['state']=='succeeded' and [s['output'] for s in execution['steps']]==[expected for _,expected in lists],execution;results['allListOperations']=execution
    # A continued failure remains visible, but permits subsequent steps.
    bad=output(step('divide-zero','number.calculate',left=1,value='除',right=0),'bad');bad['onFailure']='continue'
    save([bad,step('after-error','wait',value=0)]);execution=finished(run())
    assert execution['state']=='failed' and [s['state'] for s in execution['steps']]==['failed','succeeded'],execution
    results['continuedFailure']=execution
    parent=step('timed-repeat','repeat',value=2);parent['children']=[step('slow-child','wait',value=1000)];parent['timeoutMs']=40
    save([parent]);execution=finished(run());assert execution['state']=='timedOut' and all(s['state']=='timedOut' for s in execution['steps']),execution
    results['nestedTimeout']=execution
    save([step('cancel-wait','wait',value=3000)])
    first=run();wait(lambda:any(e['id']==first and e['steps'] for e in call('GetRuntime')['executions']))
    second=run();call('RuntimeControl',{'operation':'stopAll'})
    a,b=finished(first),finished(second)
    assert a['state']==b['state']=='canceled' and b['startedAt'] is None and not b['steps']
    assert a['steps'][0]['state']=='canceled'
    results['cancelRunningAndQueue']=[a,b]
    # Queue captures workflow definitions, not just top-level steps.
    save([step('snapshot-wait','wait',value=150),initial,callstep],[workflow])
    id=run();wait(lambda:any(e['id']==id and e['steps'] for e in call('GetRuntime')['executions']))
    changed=copy.deepcopy(workflow);changed['steps'][0]['params']['right']=literal(99)
    save([initial,callstep],[changed]);execution=finished(id)
    assert next(s for s in execution['steps'] if s['stepId']=='call')['output']['value']['return']['value']==6
    results['immutableWorkflowSnapshot']=execution
    item=output(step('foreach-value','variable',name='value',kind='文本',value=''),'item-copy','text');item['params']['value']=ref('item','text')
    foreach=step('foreach','foreach',value='',item='item',index='position',itemKind='文本');foreach['params']['value']={'mode':'list','value':[literal('A'),literal('中文')]};foreach['loopItem']=symbol('item','text');foreach['loopIndex']=symbol('position');foreach['children']=[item]
    save([foreach]);execution=finished(run());assert execution['state']=='succeeded',execution
    assert [s['output']['value'] for s in execution['steps'] if s['stepId']=='foreach-value']==['A','中文']
    results['typedForeach']=execution
    snapshot=call('GetConfig');invalid=copy.deepcopy(snapshot['config']);leak=output(step('leak','variable',name='leak',kind='文本',value=''),'leaked','text');leak['params']['value']=ref('item-copy','text');invalid['rules'][0]['steps'].append(leak)
    checked=call('ValidateDocument',invalid);assert any('尚未产生' in e['message'] for e in checked),checked
    results['localScopeLeakRejected']=checked
    save([step('self-pause','waystroke.toggle',value='手势',operation='暂停'),step('after-pause','wait',value=0),step('self-disable','waystroke.rule',value='Execution check',operation='停用')])
    execution=finished(run());assert execution['state']=='succeeded',execution
    assert not call('GetConfig')['config']['settings']['gesturesEnabled'] and not call('GetConfig')['config']['rules'][0]['enabled']
    results['realWayStrokeControl']=execution
    parse=output(step('parse','json.parse',value='{"status":200,"empty":null,"ok":true,"items":["A","中文"]}'),'parsed','data')
    field=output(step('field','data.field',value='',path='items'),'items','list');field['params']['value']=ref('parsed','data')
    join=output(step('join','text.transform',value='',operation='按分隔符合并',argument=',',replacement=''),'joined','text');join['params']['value']=ref('items','list')
    length=output(step('length','text.transform',value='中文🙂',operation='获取长度',argument='',replacement=''),'length-value')
    save([parse,field,join,length]);execution=finished(run());assert execution['state']=='succeeded',execution
    assert execution['steps'][0]['output']['value']['empty']=={'kind':'null'} and execution['steps'][2]['output']['value']=='A,中文' and execution['steps'][3]['output']['value']==3
    results['jsonListUnicodeChain']=execution
    save([output(step('home','variable.read',value='用户主目录'),'home-value','text'),output(step('date','date.format',value='YYYY-MM-DD',timezone='UTC'),'date-value','text'),output(step('random','number.random',min=10,max=20),'random-value')]);execution=finished(run());assert execution['state']=='succeeded',execution
    assert execution['steps'][0]['output']['value']==os.environ['HOME'] and 10<=execution['steps'][2]['output']['value']<=20
    results['contextDateRandom']=execution
    inferred=output(step('inferred-json','json.parse',value='{"number":8,"list":[true,"text"]}'),'inferred','any')
    field=output(step('inferred-field','data.field',value='',path='number'),'inferred-number','any');field['params']['value']=ref('inferred','any')
    arithmetic=output(step('inferred-calc','number.calculate',left=0,value='加',right=2),'inferred-sum');arithmetic['params']['left']=ref('inferred-number','any')
    save([inferred,field,arithmetic]);execution=finished(run());assert execution['state']=='succeeded' and execution['steps'][-1]['output']=={'kind':'number','value':10},execution
    results['inferredResultConsumesActualType']=execution
    field['output']['kind']='text';save([inferred,field]);execution=finished(run());assert execution['state']=='failed' and '实际类型' in execution['reason'],execution
    results['explicitOutputTypeIsEnforced']=execution
    # Files, command results and HTTP are real temporary resources.
    folder=root/'files';source=folder/'source.txt';target=folder/'copy.txt';moved=folder/'moved.txt'
    read=output(step('read-file','file.read',value=str(source),encoding='UTF-8'),'read-result','text')
    listing=output(step('list-files','directory.list',value=str(folder),filter='*.txt',recursive='否'),'files','list')
    save([step('mkdir','directory.create',value=str(folder),parents='是'),
          step('write','file.write',value=str(source),content='中文',mode='覆盖',encoding='UTF-8'),
          step('append','file.write',value=str(source),content=' suffix',mode='追加',encoding='UTF-8'),read,
          step('copy-file','file.copy',value=str(source),destination=str(target),conflict='报告失败'),
          step('rename-copy','file.copy',value=str(source),destination=str(target),conflict='自动重命名'),
          step('move-file','file.move',value=str(target),destination=str(moved),conflict='报告失败'),listing])
    execution=finished(run());assert execution['state']=='succeeded',execution
    assert source.read_text()==moved.read_text()=='中文 suffix' and not target.exists()
    assert (folder/'copy (1).txt').read_text()=='中文 suffix'
    assert next(e for e in execution['steps'] if e['stepId']=='read-file')['output']['value']=='中文 suffix'
    assert len(execution['steps'][-1]['output']['value'])==3
    results['realFiles']=execution
    save([step('copy-conflict','file.copy',value=str(source),destination=str(moved),conflict='报告失败')])
    execution=finished(run());assert execution['state']=='failed' and moved.read_text()=='中文 suffix'
    results['fileConflict']=execution
    tree=root/'tree';tree.mkdir();(tree/'nested').mkdir();(tree/'nested/content.txt').write_text('directory payload');(tree/'link').symlink_to('nested/content.txt')
    copied_tree=root/'copied-tree';moved_tree=root/'moved-tree'
    save([step('copy-tree','file.copy',value=str(tree),destination=str(copied_tree),conflict='报告失败'),step('move-tree','file.move',value=str(copied_tree),destination=str(moved_tree),conflict='报告失败')]);execution=finished(run())
    assert execution['state']=='succeeded' and (moved_tree/'nested/content.txt').read_text()=='directory payload' and (moved_tree/'link').is_symlink() and not copied_tree.exists(),execution
    results['directoryCopyMoveAndSymlink']=execution
    (moved_tree/'obsolete.txt').write_text('old')
    save([step('overwrite-tree','file.copy',value=str(tree),destination=str(moved_tree),conflict='覆盖'),output(step('recursive-list','directory.list',value=str(moved_tree),filter='*.txt',recursive='是'),'recursive-files','list')]);execution=finished(run())
    assert execution['state']=='succeeded' and not (moved_tree/'obsolete.txt').exists() and [v['value'] for v in execution['steps'][-1]['output']['value']]==[str(moved_tree/'nested/content.txt')],execution
    results['directoryOverwriteAndRecursiveFilter']=execution
    properties=['是否存在','是否为目录','文件名','扩展名','父目录','大小','修改时间']
    kinds=['boolean','boolean','text','text','text','number','text']
    save([output(step('info-'+str(i),'file.info',value=str(source),property=property),'info-result-'+str(i),kind) for i,(property,kind) in enumerate(zip(properties,kinds))]);execution=finished(run());assert execution['state']=='succeeded',execution
    values=[s['output']['value'] for s in execution['steps']];assert values[:5]==[True,False,'source.txt','txt',str(folder)] and values[5]==source.stat().st_size and 'T' in values[6]
    results['allFileInfoProperties']=execution
    trashfile=Path(os.environ['WAYSTROKE_TRASH_CHECK'])/'trash-fixture.txt';trashfile.write_text('only our disposable fixture')
    save([step('trash-file','file.trash',value=str(trashfile))]);execution=finished(run());assert execution['state']=='succeeded' and not trashfile.exists(),execution
    assert any(p.read_text()=='only our disposable fixture' for p in (Path(os.environ['XDG_DATA_HOME'])/'Trash/files').iterdir())
    results['actualTrash']=execution
    uri_output=root/'opened-uri.txt';uri_helper=root/'uri-helper.py'
    uri_helper.write_text('import sys\nfrom pathlib import Path\nPath('+repr(str(uri_output))+').write_text(sys.argv[1])\n')
    appdir=Path(os.environ['XDG_DATA_HOME'])/'applications';appdir.mkdir()
    desktop=appdir/'io.github.waystroke.UriFixture.desktop'
    desktop.write_text('[Desktop Entry]\nType=Application\nName=WayStroke private URI fixture\nExec='+sys.executable+' '+str(uri_helper)+' %u\nMimeType=x-scheme-handler/waystroke-fixture;\nTerminal=false\n')
    subprocess.run(['gio','mime','x-scheme-handler/waystroke-fixture',desktop.name],check=True,stdout=subprocess.DEVNULL)
    save([step('open-uri','uri.open',value='waystroke-fixture://actual/result')]);execution=finished(run());assert execution['state']=='succeeded',execution
    wait(lambda:uri_output.exists());assert uri_output.read_text()=='waystroke-fixture://actual/result';results['actualUriHandler']=execution
    def command(id,program,arguments='',mode='直接启动程序',wait='是',timeout=1000):
        return output(step(id,'command',value=program,arguments=arguments,mode=mode,directory=str(root),environment='WAYSTROKE_FIXTURE=real',waitExit=wait,timeout=timeout),id+'-output','data')
    direct=command('direct',sys.executable,"-c 'import os,sys;print(os.environ[\"WAYSTROKE_FIXTURE\"]);sys.stderr.write(\"stderr\");sys.exit(7)'")
    shell=command('shell','printf shell-output',mode='通过 Shell 运行')
    save([direct,shell]);execution=finished(run());assert execution['state']=='succeeded',execution
    assert execution['steps'][0]['output']['value']['exitCode']['value']==7
    assert execution['steps'][0]['output']['value']['stdout']['value']=='real\n'
    assert execution['steps'][0]['output']['value']['stderr']['value']=='stderr'
    assert execution['steps'][1]['output']['value']['stdout']['value']=='shell-output'
    results['directAndShellCommands']=execution
    asynchronous=command('async',sys.executable,"-c 'import time;time.sleep(30)'",wait='否')
    terminate=step('signal','process.signal',value=0,signal='TERM');terminate['params']['value']=ref('async-output','number',['pid'])
    save([asynchronous,terminate]);execution=finished(run());assert execution['state']=='succeeded',execution
    assert execution['steps'][0]['output']['value']['exitCode']=={'kind':'null'}
    results['asyncAndSignal']=execution
    utf16=root/'utf16.txt'
    save([step('utf16-write','file.write',value=str(utf16),content='中文🙂',mode='覆盖',encoding='UTF-16LE'),output(step('utf16-read','file.read',value=str(utf16),encoding='UTF-16LE'),'utf16-content','text')]);execution=finished(run())
    assert execution['state']=='succeeded' and execution['steps'][-1]['output']['value']=='中文🙂' and utf16.read_bytes()=='中文🙂'.encode('utf-16-le')
    results['utf16ActualEncoding']=execution
    # A timed shell owns its child group; cancellation must not leave the child alive.
    pidfile=root/'child.pid'
    script=f"import os,time;open({str(pidfile)!r},'w').write(str(os.getpid()));time.sleep(30)"
    import shlex
    slow=command('slow-command',shlex.quote(sys.executable)+' -c '+shlex.quote(script),mode='通过 Shell 运行',timeout=150)
    save([slow]);execution=finished(run());assert execution['state']=='timedOut' and pidfile.exists(),execution
    pid=int(pidfile.read_text())
    def stopped_child():
        try:return Path(f'/proc/{pid}/stat').read_text().split(') ')[1].startswith('Z')
        except FileNotFoundError:return True
    assert wait(stopped_child)
    results['commandTimeoutKillsChildGroup']=execution
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            content=self.rfile.read(int(self.headers.get('Content-Length',0))).decode()
            self.send_response(201);self.send_header('X-Fixture',self.headers['X-Test']);self.end_headers();self.wfile.write(content.upper().encode())
        def do_GET(self):
            time.sleep(.2);self.send_response(200);self.end_headers()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        request=output(step('http','http.request',value=f'http://127.0.0.1:{server.server_port}/',method='POST',headers='X-Test=actual',body='real body',timeout=1000),'response','data')
        body=output(step('http-body','data.field',value='',path='body'),'response-body','text');body['params']['value']=ref('response','data')
        save([request,body]);execution=finished(run());assert execution['state']=='succeeded',execution
        response=execution['steps'][0]['output']['value'];assert response['status']['value']==201 and response['headers']['value']['x-fixture']['value']=='actual'
        assert execution['steps'][1]['output']['value']=='REAL BODY'
        results['realHttpAndTypedField']=execution
        request['params']['method']=literal('GET');request['params']['timeout']=literal(30)
        save([request]);execution=finished(run());assert execution['state']=='timedOut',execution
        results['httpTimeout']=execution
    finally:server.shutdown();server.server_close()
    def dbus(id,action,**params):
        return output(step(id,action,bus='会话总线',service='io.github.waystroke.Gnome',path='/io/github/waystroke/Fixture',interface='io.github.waystroke.Fixture',**params),id+'-result','data')
    echo=dbus('echo','dbus.call',value='Echo',signature='sidbas',arguments='',timeout=1000)
    echo['params']['dbusArgs']={'mode':'list','value':[{'mode':'object','value':{'type':literal(kind),'value':value}} for kind,value in [('s',literal('hello')),('i',literal(42)),('d',literal(1.25)),('b',literal(True)),('as',{'mode':'list','value':[literal('A'),literal('中文')]})]]}
    save([echo]);execution=finished(run());assert execution['state']=='succeeded',execution
    returned=execution['steps'][0]['output']['value']['values']['value'];assert [v['value'] for v in returned[:4]]==['hello',42,1.25,True] and [v['value'] for v in returned[4]['value']]==['A','中文']
    results['dbusTypedArgumentsAndReturns']=execution
    write=dbus('property-set','dbus.property',value='Value',operation='设置',signature='s',content='updated');write['output']=None
    read=dbus('property-get','dbus.property',value='Value',operation='读取',signature='s',content='')
    ping=dbus('ping','dbus.call',value='Ping',signature='',arguments='[]',timeout=1000)
    save([write,read,ping]);execution=finished(run());assert execution['state']=='succeeded',execution
    assert execution['steps'][1]['output']['value']['value']['value']=='updated'
    assert execution['steps'][2]['output']['value']['values']['value']==[]
    results['dbusPropertiesAndEmptyCall']=execution
    slow=dbus('dbus-timeout','dbus.call',value='Slow',signature='',arguments='[]',timeout=30)
    save([slow]);execution=finished(run());assert execution['state']=='timedOut',execution
    results['dbusTimeout']=execution
    operations=['播放','暂停','播放 / 暂停','停止','上一首','下一首','快进','快退']
    save([step('media-'+str(i),'media',value=operation,player='Fixture Player',seconds=2) for i,operation in enumerate(operations)])
    execution=finished(run());assert execution['state']=='succeeded',execution
    assert [call[0] for call in media_state['calls']]==['Play','Pause','PlayPause','Stop','Previous','Next','Seek','Seek'],media_state
    assert media_state['calls'][-2:]==[['Seek',2000000],['Seek',-2000000]]
    results['mprisAllOperations']={'execution':execution,'received':copy.deepcopy(media_state['calls'])}
    media_state['canSeek']=False
    save([step('media-no-seek','media',value='快进',player='org.mpris.MediaPlayer2.waystrokeFixture',seconds=2)])
    execution=finished(run());assert execution['state']=='failed' and '不支持' in execution['reason'];assert len(media_state['calls'])==8
    results['mprisCapabilityFailure']=execution
    assert any(e['event']=='executionStepStarted' for e in events)
    assert any(e['event']=='executionStepFinished' for e in events)
    save([step('logout','session',value='注销',confirm='否'),step('suspend','session',value='挂起',confirm='否')]);execution=finished(run());assert execution['state']=='succeeded',execution
    assert session_calls==[['Logout',0],['CanSuspend'],['Suspend',True]],session_calls
    results['sessionPrivateServiceContract']={'execution':execution,'received':session_calls.copy(),'hostSessionUntouched':True}
    suspend_state['capability']='no';save([step('no-suspend','session',value='挂起',confirm='否')]);execution=finished(run());assert execution['state']=='failed' and '不能挂起' in execution['reason'],execution;results['sessionUnsupportedIsFailure']=execution
    suspend_state.update(capability='yes',deny=True);save([step('denied-suspend','session',value='挂起',confirm='否')]);execution=finished(run());assert execution['state']=='failed' and 'permission' in json.dumps(execution).lower(),execution;results['sessionPermissionIsFailure']=execution
    results['stepEvents']=True
    call('Quit');process.wait(timeout=5)
    results['complete']=True
    print('PASS: real nested execution, calls/typed returns, scopes, loop control, continued errors, nested timeout, cancellation and queued snapshots.')
finally:
    (root/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    if process.poll() is None:process.terminate();process.wait(timeout=5)
    loop.quit()
