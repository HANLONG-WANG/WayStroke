#!/usr/bin/env python3
"""Formal desktop extension checks in a disposable GNOME session; no host hooks."""
import json,os,shutil,signal,subprocess,sys,tempfile,time
from pathlib import Path
from gi.repository import Gio,GLib
REPO=Path(__file__).resolve().parents[1]
if '--inside' not in sys.argv:
    root=Path(tempfile.mkdtemp(prefix='waystroke-desktop-check-'))
    for directory in ['runtime','config','data','cache']:(root/directory).mkdir(mode=0o700)
    for uuid,source,files in [('waystroke@local',REPO/'extension',['extension.js','metadata.json']),('waystroke-probe@local',REPO/'probes/gnome50',['extension.js','metadata.json','terminal-monitor.js'])]:
        dest=root/'data/gnome-shell/extensions'/uuid;dest.mkdir(parents=True)
        for file in files:shutil.copy(source/file,dest/file)
        if uuid=='waystroke@local':
            ext=dest/'extension.js';ext.write_text(ext.read_text().replace("case 'windows':","case 'fixtureGesture':this.beginGesture({sequence:99,color:'#6262cf',trail:false,minimumLength:12,cancelTimeout:1200},this.context());const [x,y]=this.stroke.points[0];this.point([x+120,y]);return null;case 'gestureInfo':return {active:!!this.stroke,label:!!this.ruleLabel,trail:!!this.trail};case 'feedbackInfo':return this.feedbackActor?{text:this.feedbackActor.text,position:this.feedbackActor.get_position(),width:this.feedbackActor.get_preferred_width(-1)[1],height:this.feedbackActor.get_preferred_height(-1)[1],monitors:Main.layoutManager.monitors.map(m=>({x:m.x,y:m.y,width:m.width,height:m.height}))}:null;case 'windows':",1))
    applications=root/'data/applications';applications.mkdir()
    (applications/'org.waystroke.LaunchedClient.desktop').write_text('[Desktop Entry]\nType=Application\nName=WayStroke launch fixture\nExec=/usr/bin/env WAYSTROKE_CLIENT_PREFIX=Launched /usr/bin/python3 '+str(REPO/'probes/gnome50/client.py')+'\nStartupWMClass=org.waystroke.LaunchedClient\nTerminal=false\n')
    env=os.environ.copy();env.update(XDG_RUNTIME_DIR=str(root/'runtime'),XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),XDG_CACHE_HOME=str(root/'cache'),GSETTINGS_BACKEND='keyfile',LIBGL_ALWAYS_SOFTWARE='1',GIO_USE_VFS='local',WAYSTROKE_PROBE_DIR=str(root),GDK_BACKEND='wayland',GSK_RENDERER='cairo',WAYLAND_DISPLAY='waystroke-desktop-check-0')
    for name in ['DISPLAY','IBUS_ADDRESS','AT_SPI_BUS_ADDRESS']:env.pop(name,None)
    print('Desktop extension artifacts:',root,flush=True)
    sys.exit(subprocess.run(['dbus-run-session','--',sys.executable,__file__,'--inside',*sys.argv[1:]],env=env).returncode)
root=Path(os.environ['WAYSTROKE_PROBE_DIR']);processes=[];results={}
connection=Gio.bus_get_sync(Gio.BusType.SESSION,None)
def spawn(name,args):
    log=(root/(name+'.log')).open('w');p=subprocess.Popen(args,stdout=log,stderr=log,start_new_session=True);processes.append(p);return p
def call(q,formal=True):
    name,path,interface=('io.github.waystroke.Gnome','/io/github/waystroke/Gnome','io.github.waystroke.Gnome1') if formal else ('org.gnome.Shell','/org/waystroke/Probe','org.waystroke.Probe')
    result=json.loads(connection.call_sync(name,path,interface,'Call',GLib.Variant('(s)',(json.dumps(q),)),GLib.VariantType('(s)'),Gio.DBusCallFlags.NONE,3000,None).unpack()[0])
    if formal:
        if result['status']=='error':raise RuntimeError(json.dumps(result['error'],ensure_ascii=False))
        return result['value']
    return result
def core(method,payload=None):
    args=None if payload is None else GLib.Variant('(s)',(json.dumps(payload),))
    result=json.loads(connection.call_sync('io.github.waystroke.Core','/io/github/waystroke/Core','io.github.waystroke.Core1',method,args,GLib.VariantType('(s)'),Gio.DBusCallFlags.NONE,3000,None).unpack()[0])
    if result['status']=='error':raise RuntimeError(json.dumps(result['error'],ensure_ascii=False))
    return result['value']
def wait(fn):
    end=time.monotonic()+15
    while time.monotonic()<end:
        try:
            value=fn()
            if value:return value
        except (GLib.Error,FileNotFoundError):pass
        time.sleep(.1)
    raise RuntimeError('Desktop condition timed out')
try:
    for schema,key,value in [('org.gnome.shell','enabled-extensions',"['waystroke@local','waystroke-probe@local']"),('org.gnome.shell','disable-user-extensions','false'),('org.gnome.desktop.interface','enable-hot-corners','false')]:subprocess.run(['gsettings','set',schema,key,value],check=True)
    spawn('shell',['gnome-shell','--headless','--wayland','--no-x11','--wayland-display=waystroke-desktop-check-0','--virtual-monitor=1440x1000',*(['--virtual-monitor=1280x900'] if '--multi-monitor' in sys.argv else [])])
    results['hello']=wait(lambda:call({'operation':'hello'}));assert results['hello']['shellVersion']=='50.5'
    client_source=(REPO/'probes/gnome50/client.py').read_text()
    client_source=client_source.replace("  state[name]={'text'", "  keys=Gtk.EventControllerKey();keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)\n  keys.connect('key-pressed',lambda controller,keyval,*args,n=name:state[n].update(f24=state[n]['f24']+1) if keyval==Gdk.KEY_F24 else False)\n  win.add_controller(keys)\n  state[name]={'f24':0,'text'")
    (root/'client.py').write_text(client_source)
    spawn('client',[sys.executable,str(root/'client.py')])
    windows=wait(lambda:(lambda ws:ws if {'Probe A','Probe B'}.issubset({w['title'] for w in ws}) else None)(call({'operation':'windows'})));a=next(w for w in windows if w['title']=='Probe A');b=next(w for w in windows if w['title']=='Probe B')
    assert a['clientType']==0;results['windows']=windows
    call({'operation':'registerBarrier','leaseId':'00000000-0000-0000-0000-000000000001'});results['barrierRegistration']=True
    focused=wait(lambda:call({'action':'snapshot'},False).get('focus'))
    call({'action':'key','keyval':0xffd5,'pressed':True},False)
    call({'action':'key','keyval':0xffd5,'pressed':False},False)
    wait(lambda:json.loads((root/'client.json').read_text())[focused]['f24']==1)
    results['foreignF24PassesThrough']=True
    call({'operation':'fixtureGesture'});assert call({'operation':'gestureInfo'})=={'active':True,'label':True,'trail':False}
    call({'action':'key','keyval':0xff1b,'pressed':True},False);call({'action':'key','keyval':0xff1b,'pressed':False},False)
    wait(lambda:not call({'operation':'gestureInfo'})['active']);assert not call({'operation':'gestureInfo'})['label']
    results['escapeClearsLiveLabel']=True
    call({'operation':'fixtureGesture'});began=time.monotonic()
    wait(lambda:not call({'operation':'gestureInfo'})['active']);elapsed=(time.monotonic()-began)*1000
    assert elapsed>=1100 and not call({'operation':'gestureInfo'})['label']
    results['idleClearsLiveLabel']={'elapsedMs':round(elapsed,1),'physicalInput':False}
    call({'operation':'release'})
    call({'action':'position','title':'Probe A','x':50,'y':200,'focus':True},False)
    call({'action':'position','title':'Probe B','x':550,'y':200,'focus':True},False)
    call({'action':'pointer','x':200,'y':300},False)
    origin=wait(lambda:(lambda c:c if c['window']==a['handle'] else None)(call({'operation':'getContext'})));results['origin']=origin;assert call({'action':'snapshot'},False)['focus']=='Probe B'
    call({'action':'pointer','x':600,'y':300},False)
    end=wait(lambda:(lambda c:c if c['window']==b['handle'] else None)(call({'operation':'getContext'})));assert origin['window']==a['handle'];results['pointWindowDiffersFromFocus']={'start':origin,'end':end}
    if '--multi-monitor' in sys.argv:
        call({'action':'position','title':'Probe B','x':1590,'y':200,'focus':True},False)
        call({'action':'pointer','x':1800,'y':300},False)
        secondary=wait(lambda:(lambda context:context if context['window']==b['handle'] and context['monitor']==1 else None)(call({'operation':'getContext'})))
        assert origin['monitor']==0 and secondary['position']==[1800,300]
        assert origin['window']==a['handle']
        results['multipleMonitorLogicalContexts']={'start':origin,'secondary':secondary}
        call({'action':'position','title':'Probe B','x':550,'y':200,'focus':True},False)
    call({'operation':'shortcut','window':a['handle'],'keys':'Return'})
    wait(lambda:json.loads((root/'client.json').read_text())['Probe A']['activate']==1)
    assert json.loads((root/'client.json').read_text())['Probe B']['activate']==0;results['shortcutTargetsOriginalHandle']=True
    spawn('core',[str(REPO/'target/debug/waystroke-core')]);snapshot=wait(lambda:core('GetConfig'));config=snapshot['config'];config['settings']['setupComplete']=True
    config['gestures']=[{'id':'g','name':'Fixture','mainSampleId':'s','samples':[{'id':'s','points':[[0,0],[100,0]]}]}]
    def step(action,**params):
        return {'id':'step-'+action,'action':action,'enabled':True,'params':{key:{'mode':'literal','value':{'kind':'text' if isinstance(value,str) else 'number','value':value}} for key,value in params.items()},'output':None,'onFailure':'stop','timeoutMs':None,'workflowId':None,'arguments':{},'children':[],'otherwise':[],'loopItem':None,'loopIndex':None}
    config['rules']=[{'id':action,'name':action,'enabled':False,'gestureId':'g','auxiliaryButtons':[],'applicationId':None,'titleMatch':{'operator':'包含','value':''},'steps':[item]} for action,item in [('shortcut',step('shortcut',value='Return',target='起点窗口',count=1)),('window',step('window',value='最大化',target='起点窗口')),('launch',step('launch',value='org.waystroke.LaunchedClient.desktop',arguments='',windowTarget='否'))]]
    core('CommitConfig',{'requestId':'executors','expectedRevision':snapshot['revision'],'config':config})
    def run_rule(rule):
        execution_id=core('RunRule',{'ruleId':rule,'context':origin})['executionId']
        execution=wait(lambda:next((item for item in core('GetRuntime')['executions'] if item['id']==execution_id and item['state'] not in ['queued','running']),None))
        assert execution['state']=='succeeded',execution
        return execution
    results['coreShortcut']=run_rule('shortcut');wait(lambda:json.loads((root/'client.json').read_text())['Probe A']['activate']==2)
    results['coreWindow']=run_rule('window')
    results['coreLaunch']=run_rule('launch');assert any(window['applicationId']=='org.waystroke.LaunchedClient.desktop' for window in call({'operation':'windows'}))
    feedback=wait(lambda:(lambda value:value if value and value['text']=='launch · 已执行' else None)(call({'operation':'feedbackInfo'})))
    m=feedback['monitors'][origin['monitor']];x,y=feedback['position']
    assert abs(x+feedback['width']/2-(m['x']+m['width']/2))<=1
    assert abs(y+feedback['height']-(m['y']+m['height']-64))<=1
    results['feedbackBottomCentered']=feedback
    snapshot=core('GetConfig');config=snapshot['config'];config['rules'][0]['steps']=[step('wait',value=3000)]
    core('CommitConfig',{'requestId':'cancel-fixture','expectedRevision':snapshot['revision'],'config':config})
    first=core('RunRule',{'ruleId':'shortcut','context':origin})['executionId'];wait(lambda:any(item['id']==first and item['state']=='running' for item in core('GetRuntime')['executions']))
    second=core('RunRule',{'ruleId':'shortcut','context':origin})['executionId'];core('RuntimeControl',{'operation':'stopAll'})
    stopped=wait(lambda:(lambda items:items if len(items)==2 and all(item['state']=='canceled' for item in items) else None)([item for item in core('GetRuntime')['executions'] if item['id'] in [first,second]]))
    assert next(item for item in stopped if item['id']==second)['startedAt'] is None
    results['cancelRunningAndQueued']=stopped
    call({'operation':'windowAction','window':a['handle'],'action':'unmaximize'})
    wait(lambda:next(w['rect']['width'] for w in call({'action':'snapshot'},False)['windows'] if w['title']=='Probe A')==420)
    before=next(w['rect'] for w in call({'action':'snapshot'},False)['windows'] if w['title']=='Probe A')
    call({'operation':'windowAction','window':a['handle'],'action':'maximize'})
    after=wait(lambda:next((w['rect'] for w in call({'action':'snapshot'},False)['windows'] if w['title']=='Probe A' and w['rect']['width']>before['width']),None));results['maximize']={'before':before,'after':after}
    call({'operation':'windowAction','window':a['handle'],'action':'close'})
    wait(lambda:not any(w['title']=='Probe A' for w in call({'operation':'windows'})))
    try:call({'operation':'windowAction','window':a['handle'],'action':'maximize'})
    except RuntimeError as e:assert '关闭' in str(e);results['closedHandleDoesNotRetarget']=True
    else:raise AssertionError('Closed handle was accepted')
    def shield(active):
        connection.call_sync('org.gnome.ScreenSaver','/org/gnome/ScreenSaver','org.gnome.ScreenSaver','SetActive',GLib.Variant('(b)',(active,)),None,Gio.DBusCallFlags.NONE,3000,None)
    active_job=core('RunRule',{'ruleId':'shortcut','context':end})['executionId']
    wait(lambda:any(item['id']==active_job and item['state']=='running' for item in core('GetRuntime')['executions']))
    queued_job=core('RunRule',{'ruleId':'shortcut','context':end})['executionId']
    shield(True)
    locked=wait(lambda:(lambda state:state if state['locked'] and not state['status']['executionAvailable'] else None)(core('GetRuntime')))
    assert not locked['inputArmed'] and locked['status']['reason']=='桌面已锁定'
    stopped=wait(lambda:(lambda items:items if len(items)==2 and all(item['state']=='canceled' for item in items) else None)([item for item in core('GetRuntime')['executions'] if item['id'] in [active_job,queued_job]]))
    assert next(item for item in stopped if item['id']==queued_job)['startedAt'] is None
    shield(False)
    wait(lambda:not core('GetRuntime')['locked'] and core('GetRuntime')['status']['executionAvailable'])
    results['nativeShieldStopsAndResumes']={'locked':locked['locked'],'reason':locked['status']['reason'],'queuedNeverStarted':True,'resumed':True,'physicalInput':False}
    results['complete']=True
finally:
    for p in reversed(processes):
        if p.poll() is None:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=5)
    (root/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps(results,ensure_ascii=False,indent=2),flush=True)
