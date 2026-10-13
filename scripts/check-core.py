#!/usr/bin/env python3
"""Real core protocol/config checks in a private bus and temporary XDG directory."""
import copy,json,os,subprocess,sys,tempfile,time
from pathlib import Path
from gi.repository import Gio,GLib
REPO=Path(__file__).resolve().parents[1]
if '--inside' not in sys.argv:
    with tempfile.TemporaryDirectory(prefix='waystroke-core-check-') as root:
        env=os.environ.copy();env['XDG_CONFIG_HOME']=root
        runtime=Path(root)/'runtime';runtime.mkdir(mode=0o700);env['XDG_RUNTIME_DIR']=str(runtime)
        result=subprocess.run(['dbus-run-session','--',sys.executable,__file__,'--inside'],env=env)
        sys.exit(result.returncode)
connection=Gio.bus_get_sync(Gio.BusType.SESSION,None)
def call(method,payload=None):
    args=None if payload is None else GLib.Variant('(s)',(json.dumps(payload,ensure_ascii=False),))
    result=connection.call_sync('io.github.waystroke.Core','/io/github/waystroke/Core','io.github.waystroke.Core1',method,args,GLib.VariantType('(s)'),Gio.DBusCallFlags.NONE,3000,None)
    return json.loads(result.unpack()[0])
def spawn():
    process=subprocess.Popen([str(REPO/'target/debug/waystroke-core')],stdout=subprocess.DEVNULL)
    for _ in range(50):
        if process.poll() is not None:raise RuntimeError('core exited before ready')
        try:
            if call('GetConfig')['status']=='ok':return process
        except GLib.Error:pass
        time.sleep(.05)
    raise RuntimeError('core unavailable')
process=spawn()
try:
    snapshot=call('GetConfig')['value'];config=snapshot['config']
    runtime=call('GetRuntime');assert runtime['status']=='ok' and runtime['value']['recording'] is None
    assert call('RuntimeControl',{'operation':'beginRecording'})['status']=='ok'
    assert call('GetRuntime')['value']['recording']=='canvas'
    assert call('RuntimeControl',{'operation':'endRecording'})['status']=='ok'
    assert call('GetRuntime')['value']['recording'] is None
    assert call('RuntimeControl',{'operation':'stop'})['status']=='error'
    assert call('CompareStrokes',{'points':[[0,0],[120,0],[120,80]],'samples':[[[30,60],[270,60],[270,220]] ]})['value']==[100.0]
    other=Gio.DBusConnection.new_for_address_sync(os.environ['DBUS_SESSION_BUS_ADDRESS'],Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT|Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,None,None)
    response=json.loads(other.call_sync('io.github.waystroke.Core','/io/github/waystroke/Core','io.github.waystroke.Core1','RuntimeControl',GLib.Variant('(s)',(json.dumps({'operation':'beginRecording'}),)),GLib.VariantType('(s)'),Gio.DBusCallFlags.NONE,3000,None).unpack()[0]);assert response['status']=='ok'
    assert call('GetRuntime')['value']['recording']=='canvas'
    other.close_sync(None)
    for _ in range(30):
        if call('GetRuntime')['value']['recording'] is None:break
        time.sleep(.01)
    assert call('GetRuntime')['value']['recording'] is None,'UI owner disconnect must end recording'
    assert not any(config[k] for k in ['rules','gestures','workflows','snippets'])
    second=subprocess.run([str(REPO/'target/debug/waystroke-core')],capture_output=True,timeout=5)
    assert second.returncode!=0,'second core must not become another writer'
    config['settings']['setupComplete']=True
    config['gestures']=[{'id':'g','name':'自由轨迹','mainSampleId':'s','samples':[{'id':'s','points':[[1.2,3.4],[17.8,15.6],[10,30]]}]}]
    step={'id':'wait-step','action':'wait','enabled':True,'params':{'value':{'mode':'literal','value':{'kind':'number','value':10}}},'output':None,'onFailure':'stop','timeoutMs':None,'workflowId':None,'arguments':{},'children':[],'otherwise':[],'loopItem':None,'loopIndex':None}
    config['rules']=[{'id':'r','name':'配置闭环','enabled':True,'gestureId':'g','auxiliaryButtons':[],'applicationId':None,'titleMatch':{'operator':'包含','value':''},'steps':[step]}]
    config['workflows']=[{'id':'w','name':'可复用配置','description':'持久化检查','inputs':[],'outputs':[],'steps':[dict(step,id='workflow-wait')]}]
    config['snippets']=[{'id':'t','key':'abc','value':'2003\n中文','enabled':True,'applicationId':None,'trigger':'confirm','caseSensitive':True,'boundary':True,'preserve':True}]
    signals=[]
    subscription=connection.signal_subscribe('io.github.waystroke.Core','io.github.waystroke.Core1','ConfigChanged','/io/github/waystroke/Core',None,Gio.DBusSignalFlags.NONE,lambda *args:signals.append(json.loads(args[-1].unpack()[0])))
    request={'requestId':'save','expectedRevision':0,'config':config}
    saved=call('CommitConfig',request);assert saved['status']=='ok',saved
    assert saved['value']['config']['rules'][0]['feedback'] is True
    config=saved['value']['config']
    for _ in range(30):
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        if signals:break
        time.sleep(.02)
    assert signals and signals[-1]['revision']==1
    path=Path(os.environ['XDG_CONFIG_HOME'])/'waystroke/config.json';original=path.read_bytes()
    assert call('CommitConfig',request)['error']['kind']=='conflict'
    bad=copy.deepcopy(config);bad['rules'][0]['gestureId']='missing'
    assert call('CommitConfig',dict(request,expectedRevision=1,config=bad))['error']['kind']=='validation'
    assert path.read_bytes()==original
    assert call('Quit')['status']=='ok';process.wait(timeout=5)
    process=spawn();restarted=call('GetConfig')['value']
    assert restarted['revision']==1 and restarted['config']==config
    recognized=call('RecognizeStroke',{'points':config['gestures'][0]['samples'][0]['points'],'auxiliaryButtons':[],'context':{'sequence':1,'monotonicMs':1,'position':[0,0],'window':None,'applicationId':None,'title':None,'workspace':0,'monitor':0,'locked':False}})
    assert recognized['status']=='ok' and recognized['value']['outcome']=='matched' and recognized['value']['ruleId']=='r'
    assert not call('GetStatus')['value']['executionAvailable']
    assert call('Quit')['status']=='ok';process.wait(timeout=5)
    print('PASS: real D-Bus save/signal; unique owner; all document kinds survive restart; conflict/invalid writes preserve file; graceful quit; formal recognition RPC.')
finally:
    if process.poll() is None:process.terminate();process.wait(timeout=5)
