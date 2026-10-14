#!/usr/bin/env python3
"""Formal desktop extension checks in a disposable GNOME session; no host hooks."""
import json,os,shutil,signal,subprocess,sys,tempfile,time
from pathlib import Path
from gi.repository import Gio,GLib
REPO=Path(__file__).resolve().parents[1]
if '--inside' not in sys.argv:
    root=Path(tempfile.mkdtemp(prefix='waystroke-desktop-check-'))
    for directory in ['runtime','config','data','cache','state']:(root/directory).mkdir(mode=0o700)
    for uuid,source,files in [('waystroke@local',REPO/'extension',['extension.js','metadata.json','clipboard.js','dialogs.js','system.js']),('waystroke-probe@local',REPO/'probes/gnome50',['extension.js','metadata.json','terminal-monitor.js'])]:
        dest=root/'data/gnome-shell/extensions'/uuid;dest.mkdir(parents=True)
        for file in files:shutil.copy(source/file,dest/file)
        if uuid=='waystroke@local':
            ext=dest/'extension.js';ext.write_text(ext.read_text().replace("case 'windows':","case 'overviewInfo':return {visible:Main.overview.visible,shown:Main.overview._shown,animating:Main.overview.animationInProgress,modal:Main.overview._modal,keyFocus:String(global.stage.get_key_focus()),focus:global.display.focus_window?.get_title()};case 'systemInfo':return {dialogOpen:this.prompts.active?.dialog.state===0,selection:!!this.system.selection,notifications:Main.messageTray.getSources().flatMap(source=>source.notifications||[]).map(notification=>notification.title)};case 'fixtureGesture':this.beginGesture({sequence:99,color:'#6262cf',trail:false,minimumLength:12,cancelTimeout:1200},this.context());const [x,y]=this.stroke.points[0];this.point([x+120,y]);return null;case 'gestureInfo':return {active:!!this.stroke,label:!!this.ruleLabel,trail:!!this.trail};case 'feedbackInfo':return this.feedbackActor?{text:this.feedbackActor.text,position:this.feedbackActor.get_position(),width:this.feedbackActor.get_preferred_width(-1)[1],height:this.feedbackActor.get_preferred_height(-1)[1],monitors:Main.layoutManager.monitors.map(m=>({x:m.x,y:m.y,width:m.width,height:m.height}))}:null;case 'windows':",1))
    applications=root/'data/applications';applications.mkdir()
    (applications/'org.waystroke.LaunchedClient.desktop').write_text('[Desktop Entry]\nType=Application\nName=WayStroke launch fixture\nExec=/usr/bin/env WAYSTROKE_CLIENT_PREFIX=Launched /usr/bin/python3 '+str(REPO/'probes/gnome50/client.py')+'\nStartupWMClass=org.waystroke.LaunchedClient\nTerminal=false\n')
    launcher=root/'launch-arguments.py'
    launcher.write_text("import os,sys,json\nfrom pathlib import Path\nPath(os.environ['WAYSTROKE_PROBE_DIR'],'launch-arguments.json').write_text(json.dumps(sys.argv[1:]))\nos.environ['WAYSTROKE_CLIENT_PREFIX']='Arguments'\nos.execv('/usr/bin/python3',['/usr/bin/python3',"+repr(str(REPO/'probes/gnome50/client.py'))+"])\n")
    (applications/'org.waystroke.ArgumentsClient.desktop').write_text('[Desktop Entry]\nType=Application\nName=WayStroke arguments fixture\nExec=/usr/bin/python3 '+str(launcher)+'\nStartupWMClass=org.waystroke.ArgumentsClient\nTerminal=false\n')
    background=root/'background.py';background.write_text("import os,sys,json\nfrom pathlib import Path\nPath(os.environ['WAYSTROKE_PROBE_DIR'],'background-arguments.json').write_text(json.dumps(sys.argv[1:]))\n")
    (applications/'org.waystroke.Background.desktop').write_text('[Desktop Entry]\nType=Application\nName=WayStroke background fixture\nExec=/usr/bin/python3 '+str(background)+'\nTerminal=false\n')
    env=os.environ.copy();env.update(XDG_RUNTIME_DIR=str(root/'runtime'),XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),XDG_CACHE_HOME=str(root/'cache'),XDG_STATE_HOME=str(root/'state'),GSETTINGS_BACKEND='keyfile',LIBGL_ALWAYS_SOFTWARE='1',GIO_USE_VFS='local',WAYSTROKE_PROBE_DIR=str(root),GDK_BACKEND='wayland',GSK_RENDERER='cairo',WAYLAND_DISPLAY='waystroke-desktop-check-0')
    if '--devkit' in sys.argv:
        env['WAYSTROKE_OUTER_RUNTIME']=os.environ['XDG_RUNTIME_DIR'];env['WAYSTROKE_OUTER_DISPLAY']=os.environ.get('WAYLAND_DISPLAY','wayland-0')
        env['PIPEWIRE_RUNTIME_DIR']=os.environ['XDG_RUNTIME_DIR']
        env.pop('LIBGL_ALWAYS_SOFTWARE',None)
        schema=Path('/usr/share/glib-2.0/schemas/org.gnome.mutter.devkit.gschema.xml')
        schemas=root/'schemas';schemas.mkdir();shutil.copy(schema,schemas/schema.name);subprocess.run(['glib-compile-schemas',str(schemas)],check=True);env['GSETTINGS_SCHEMA_DIR']=str(schemas)
    if '--phase-c-system' in sys.argv:env['PULSE_SERVER']='unix:'+str(root/('runtime/pulse/native' if '--phase-c-audio' in sys.argv else 'runtime/unavailable-pulse'))
    env['GI_TYPELIB_PATH']=str(REPO/'target/native')+':/usr/lib64/mutter-18'
    env['LD_LIBRARY_PATH']=str(REPO/'target/native')+':/usr/lib64/mutter-18:/usr/lib64/gnome-shell'
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
    if '--phase-c-audio' in sys.argv:
        pipewire_config=root/'pipewire.conf';pipewire_config.write_text(Path('/usr/share/pipewire/pipewire.conf').read_text()+'\ncontext.objects = [ { factory = metadata args = { metadata.name = default } } ]\n')
        spawn('pipewire',['pipewire','-c',str(pipewire_config)]);spawn('wireplumber',['wireplumber','--profile=policy']);spawn('pipewire-pulse',['pipewire-pulse'])
        wait(lambda:subprocess.run(['pactl','info'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0)
        subprocess.run(['pactl','load-module','module-null-sink','sink_name=waystroke_fixture','sink_properties=device.description=WayStroke_Fixture'],check=True,stdout=subprocess.DEVNULL)
        wait(lambda:subprocess.check_output(['pactl','list','short','sinks'],text=True).strip())
        subprocess.run(['pactl','set-default-sink','waystroke_fixture'],check=True)
        subprocess.run(['pactl','load-module','module-remap-source','master=waystroke_fixture.monitor','source_name=waystroke_input','source_properties=device.description=WayStroke_Input'],check=True,stdout=subprocess.DEVNULL)
        wait(lambda:'waystroke_input' in subprocess.check_output(['pactl','list','short','sources'],text=True))
        subprocess.run(['pactl','set-default-source','waystroke_input'],check=True)
    for schema,key,value in [('org.gnome.shell','enabled-extensions',"['waystroke@local','waystroke-probe@local']"),('org.gnome.shell','disable-user-extensions','false'),('org.gnome.desktop.interface','enable-hot-corners','false')]:subprocess.run(['gsettings','set',schema,key,value],check=True)
    if '--phase-c-window' in sys.argv:
        subprocess.run(['gsettings','set','org.gnome.mutter','dynamic-workspaces','false'],check=True)
        subprocess.run(['gsettings','set','org.gnome.desktop.wm.preferences','num-workspaces','2'],check=True)
    spawn('shell',['gnome-shell','--headless','--wayland','--no-x11','--wayland-display=waystroke-desktop-check-0',*(['--devkit'] if '--devkit' in sys.argv else ['--virtual-monitor=1440x1000',*(['--virtual-monitor=1280x900'] if '--multi-monitor' in sys.argv else [])])])
    results['hello']=wait(lambda:call({'operation':'hello'}));assert results['hello']['shellVersion']=='50.5'
    if '--devkit' in sys.argv:
        viewer_env=os.environ.copy();viewer_env['XDG_RUNTIME_DIR']=viewer_env['WAYSTROKE_OUTER_RUNTIME'];viewer_env['WAYLAND_DISPLAY']=viewer_env['WAYSTROKE_OUTER_DISPLAY']
        viewer_log=(root/'viewer.log').open('w');viewer=subprocess.Popen(['/usr/libexec/mutter-devkit'],env=viewer_env,stdout=viewer_log,stderr=viewer_log,start_new_session=True);processes.append(viewer)
        wait(lambda:call({'action':'snapshot'},False)['monitors']>0)
        assert viewer.poll() is None;results['devkit']={'viewer':True,'privateBusAndConfig':True,'softwareRenderingForced':False}
        # GNOME 50 Devkit forwards clipboard data to the outer desktop.
        # Disable that bridge on this private bus before any clipboard tests.
        import xml.etree.ElementTree as ET
        def disable_viewer_clipboard():
            base='/org/gnome/Mutter/RemoteDesktop/Session'
            xml=connection.call_sync('org.gnome.Mutter.RemoteDesktop',base,'org.freedesktop.DBus.Introspectable','Introspect',None,GLib.VariantType('(s)'),Gio.DBusCallFlags.NONE,3000,None).unpack()[0]
            paths=[base+'/'+node.attrib['name'] for node in ET.fromstring(xml).findall('node')]
            if not paths:return False
            for path in paths:connection.call_sync('org.gnome.Mutter.RemoteDesktop',path,'org.gnome.Mutter.RemoteDesktop.Session','DisableClipboard',None,None,Gio.DBusCallFlags.NONE,3000,None)
            return paths
        results['devkit']['clipboardForwardingDisabled']=wait(disable_viewer_clipboard)
    client_source=(REPO/'probes/gnome50/client.py').read_text()
    client_source=client_source.replace("  state[name]={'text'", "  keys=Gtk.EventControllerKey();keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)\n  keys.connect('key-pressed',lambda controller,keyval,*args,n=name:state[n].update(f24=state[n]['f24']+1) if keyval==Gdk.KEY_F24 else False)\n  win.add_controller(keys)\n  state[name]={'f24':0,'text'")
    if '--phase-c-input' in sys.argv:
        client_source=client_source.replace("  state[name]={'f24':0", "  state[name]={'keyEvents':[],'mouseEvents':[],'scrollEvents':[],'motions':0,'f24':0")
        client_source=client_source.replace("  area.add_controller(gesture);win.present();", """  area.add_controller(gesture)
  all_buttons=Gtk.GestureClick(button=0)
  all_buttons.connect('pressed',lambda controller,count,x,y,n=name:state[n]['mouseEvents'].append([controller.get_current_button(),True,count]))
  all_buttons.connect('released',lambda controller,count,x,y,n=name:state[n]['mouseEvents'].append([controller.get_current_button(),False,count]))
  area.add_controller(all_buttons)
  scroll=Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.BOTH_AXES)
  scroll.connect('scroll',lambda controller,dx,dy,n=name:(state[n]['scrollEvents'].append([dx,dy]),False)[1]);scroll.set_propagation_phase(Gtk.PropagationPhase.CAPTURE);win.add_controller(scroll)
  motion=Gtk.EventControllerMotion();motion.connect('motion',lambda controller,x,y,n=name:state[n].update(motions=state[n]['motions']+1));area.add_controller(motion)
  input_keys=Gtk.EventControllerKey();input_keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
  input_keys.connect('key-pressed',lambda controller,keyval,*args,n=name:(state[n]['keyEvents'].append([keyval,True]),False)[1])
  input_keys.connect('key-released',lambda controller,keyval,*args,n=name:state[n]['keyEvents'].append([keyval,False]));win.add_controller(input_keys)
  win.present();""")
        client_source=client_source.replace(" (root/('client.json' if prefix=='Probe' else prefix+'-client.json')).write_text(json.dumps(state,ensure_ascii=False));return True", " path=root/('client.json' if prefix=='Probe' else prefix+'-client.json');temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(state,ensure_ascii=False));temporary.replace(path);return True")
    if '--phase-c-clipboard' in sys.argv:
        client_source=client_source.replace("<method name=\"Focus\"><arg type=\"s\" direction=\"in\"/></method>","<method name=\"Focus\"><arg type=\"s\" direction=\"in\"/></method><method name=\"Clipboard\"><arg type=\"s\" direction=\"in\"/><arg type=\"s\" direction=\"out\"/></method>")
        client_source=client_source.replace("  title,kind=parameters.unpack()[0].split(':');", """  if method=='Clipboard':
   q=json.loads(parameters.unpack()[0]);clipboard=Gdk.Display.get_default().get_clipboard()
   if q['operation']=='write':
    provider=Gdk.ContentProvider.new_union([Gdk.ContentProvider.new_for_bytes(mime,GLib.Bytes.new(bytes(content))) for mime,content in q['formats'].items()]);clipboard.set_content(provider);invocation.return_value(GLib.Variant('(s)',('true',)));return
   if q['operation']=='read':
    def completed(object,result):
     try:
      stream,mime=object.read_finish(result)
      def read_completed(stream,result):
       try:
        contents=stream.read_bytes_finish(result).get_data();stream.close(None);invocation.return_value(GLib.Variant('(s)',(json.dumps({'mime':mime,'bytes':list(contents)}),)))
       except Exception as error:invocation.return_dbus_error('org.waystroke.Error',str(error))
      stream.read_bytes_async(65536,GLib.PRIORITY_DEFAULT,None,read_completed)
     except Exception as error:invocation.return_dbus_error('org.waystroke.Error',str(error))
    clipboard.read_async([q['mime']],GLib.PRIORITY_DEFAULT,None,completed);return
  title,kind=parameters.unpack()[0].split(':');""")
        client_source=client_source.replace("(p if kind=='password' else e).grab_focus();", "(p if kind=='password' else e).grab_focus();\n  if kind=='none':e.select_region(0,0);w.get_child().get_last_child().set_focusable(True);w.get_child().get_last_child().grab_focus();\n  elif kind=='normal':e.set_position(-1);e.select_region(-1,-1)\n  " )
    (root/'client.py').write_text(client_source)
    spawn('client',[sys.executable,str(root/'client.py')])
    windows=wait(lambda:(lambda ws:ws if {'Probe A','Probe B'}.issubset({w['title'] for w in ws}) else None)(call({'operation':'windows'})));a=next(w for w in windows if w['title']=='Probe A');b=next(w for w in windows if w['title']=='Probe B')
    assert a['clientType']==0;results['windows']=windows
    if '--devkit' in sys.argv:call({'operation':'desktopOverview','value':'隐藏概览'})
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
    if '--devkit' in sys.argv:results['devkitInitialState']={'context':call({'operation':'getContext'}),'desktop':call({'action':'snapshot'},False)}
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
    capabilities=core('GetActionCapabilities');assert len(capabilities)==69 and all(item['executor'] for item in capabilities),capabilities
    assert next(item for item in capabilities if item['actionId']=='brightness')['state']=='unavailable'
    assert next(item for item in capabilities if item['actionId']=='paste')['state']=='available'
    results['actionCapabilities']=capabilities
    config['gestures']=[{'id':'g','name':'Fixture','mainSampleId':'s','samples':[{'id':'s','points':[[0,0],[100,0]]}]}]
    step_serial=0
    def step(action,**params):
        global step_serial
        step_serial+=1
        return {'id':'step-'+action+'-'+str(step_serial),'action':action,'enabled':True,'params':{key:{'mode':'literal','value':{'kind':'text' if isinstance(value,str) else 'number','value':value}} for key,value in params.items()},'output':None,'onFailure':'stop','timeoutMs':None,'workflowId':None,'arguments':{},'children':[],'otherwise':[],'loopItem':None,'loopIndex':None}
    config['rules']=[{'id':action,'name':action,'enabled':False,'gestureId':'g','auxiliaryButtons':[],'applicationId':None,'titleMatch':{'operator':'包含','value':''},'steps':[item]} for action,item in [('shortcut',step('shortcut',value='Return',target='起点窗口',count=1)),('window',step('window',value='最大化',target='起点窗口')),('launch',step('launch',value='org.waystroke.LaunchedClient.desktop',arguments='',windowTarget='否'))]]
    core('CommitConfig',{'requestId':'executors','expectedRevision':snapshot['revision'],'config':config})
    def run_rule(rule):
        execution_id=core('RunRule',{'ruleId':rule,'context':origin})['executionId']
        execution=wait(lambda:next((item for item in core('GetRuntime')['executions'] if item['id']==execution_id and item['state'] not in ['queued','running']),None))
        assert execution['state']=='succeeded',execution
        return execution
    results['coreShortcut']=run_rule('shortcut');wait(lambda:json.loads((root/'client.json').read_text())['Probe A']['activate']==2)
    results['coreWindow']=run_rule('window')
    results['coreLaunch']=run_rule('launch');wait(lambda:any(window['applicationId']=='org.waystroke.LaunchedClient.desktop' for window in call({'operation':'windows'})))
    feedback=wait(lambda:(lambda value:value if value and value['text']=='launch · 已执行' else None)(call({'operation':'feedbackInfo'})))
    m=feedback['monitors'][origin['monitor']];x,y=feedback['position']
    assert abs(x+feedback['width']/2-(m['x']+m['width']/2))<=1
    assert abs(y+feedback['height']-(m['y']+m['height']-64))<=1
    results['feedbackBottomCentered']=feedback
    if '--phase-c-window' in sys.argv:
        def info(handle=a['handle']):return call({'operation':'windowInfo','window':handle})
        states=[]
        for action,key,value in [('unmaximize','maximized',False),('maximize','maximized',True),('toggleMaximize','maximized',False),('fullscreen','fullscreen',True),('unfullscreen','fullscreen',False),('toggleFullscreen','fullscreen',True),('toggleFullscreen','fullscreen',False),('above','above',True),('unabove','above',False),('toggleAbove','above',True),('toggleAbove','above',False),('stick','sticky',True),('unstick','sticky',False),('minimize','minimized',True),('unminimize','minimized',False)]:
            call({'operation':'windowAction','window':a['handle'],'action':action});state=wait(lambda:info() if info()[key]==value else None);states.append({'action':action,'state':state})
        call({'operation':'windowAction','window':a['handle'],'action':'activate'})
        for action in ['leftHalf','rightHalf']:
            call({'operation':'windowAction','window':a['handle'],'action':action});state=wait(lambda:info() if 600<info()['geometry']['width']<800 else None);states.append({'action':action,'state':state})
        call({'operation':'windowGeometry','window':a['handle'],'unit':'像素','x':100,'y':180,'width':420,'height':260})
        wait(lambda:info()['geometry']['width']==420)
        call({'operation':'windowGeometry','window':a['handle'],'unit':'工作区百分比','x':10,'y':10,'width':40,'height':40})
        wait(lambda:info()['geometry']['width']==576)
        call({'operation':'windowGeometry','window':a['handle'],'unit':'像素','x':100,'y':180,'width':420,'height':260})
        if '--multi-monitor' in sys.argv:
            call({'operation':'windowMonitor','window':a['handle'],'value':'下一个显示器','index':1});wait(lambda:info()['monitor']==2)
            call({'operation':'windowMonitor','window':a['handle'],'value':'上一个显示器','index':1});wait(lambda:info()['monitor']==1)
            call({'operation':'windowMonitor','window':a['handle'],'value':'指定编号','index':2});wait(lambda:info()['monitor']==2)
            call({'operation':'windowMonitor','window':a['handle'],'value':'主显示器','index':1});wait(lambda:info()['monitor']==1)
        assert call({'operation':'windowFind','applicationId':a['applicationId'],'title':'Probe A','workspace':'所有工作区','pick':'最近使用'})==a['handle']
        assert call({'operation':'windowFind','applicationId':a['applicationId'],'title':'Probe B','workspace':'当前工作区','pick':'最前方'})==b['handle']
        call({'operation':'workspaceMove','window':a['handle'],'index':2,'follow':True});wait(lambda:info()['workspace']==2 and call({'operation':'getContext'})['workspace']==1)
        call({'operation':'windowAction','window':a['handle'],'action':'previousWorkspace'});wait(lambda:info()['workspace']==1)
        call({'operation':'windowAction','window':a['handle'],'action':'nextWorkspace'});wait(lambda:info()['workspace']==2)
        call({'operation':'workspaceMove','window':a['handle'],'index':1,'follow':False});wait(lambda:info()['workspace']==1)
        call({'operation':'workspaceSwitch','value':'上一工作区','index':1});wait(lambda:call({'operation':'getContext'})['workspace']==0)
        call({'operation':'workspaceSwitch','value':'下一工作区','index':1});wait(lambda:call({'operation':'getContext'})['workspace']==1)
        call({'operation':'workspaceSwitch','value':'指定编号','index':1});wait(lambda:call({'operation':'getContext'})['workspace']==0)
        call({'operation':'windowAction','window':b['handle'],'action':'minimize'});wait(lambda:info(b['handle'])['minimized'])
        call({'operation':'desktopShow','value':'显示桌面'});wait(lambda:info()['minimized'])
        call({'operation':'desktopShow','value':'恢复窗口'});wait(lambda:not info()['minimized']);assert info(b['handle'])['minimized']
        call({'operation':'desktopShow','value':'切换'});wait(lambda:info()['minimized'])
        call({'operation':'desktopShow','value':'切换'});wait(lambda:not info()['minimized']);assert info(b['handle'])['minimized']
        call({'operation':'windowAction','window':b['handle'],'action':'unminimize'})
        for value in ['显示概览','显示应用列表','隐藏概览','切换概览','切换概览']:call({'operation':'desktopOverview','value':value})
        call({'operation':'desktopOverview','value':'隐藏概览'})
        snapshot=core('GetConfig');config=snapshot['config']
        found=step('window.find',value=a['applicationId'],title='Probe B',workspace='所有工作区',pick='最近使用');found['output']={'id':'found','name':'found','kind':'window'}
        settarget=step('window.target',value='窗口变量',variable='');settarget['params']['variable']={'mode':'reference','value':{'symbolId':'found','path':[],'kind':'window'}}
        readinfo=step('window.info',value='标题',target='当前动作目标');readinfo['output']={'id':'title-output','name':'title','kind':'text'}
        config['rules'][1]['steps']=[found,settarget,readinfo]
        core('CommitConfig',{'requestId':'phase-c-routing','expectedRevision':snapshot['revision'],'config':config})
        routed=run_rule('window');assert routed['steps'][-1]['output']['value']=='Probe B'
        reads=[]
        for value,kind in [('标题','text'),('应用 ID','text'),('位置与尺寸','data'),('工作区','number'),('所在显示器','number'),('是否最大化','boolean'),('是否全屏','boolean'),('是否置顶','boolean')]:
            read=step('window.info',value=value,target='当前动作目标');read['output']={'id':'info-'+kind+'-'+str(len(reads)),'name':'info'+str(len(reads)),'kind':kind};reads.append(read)
        focused=step('window.target',value='当前聚焦窗口',variable='');starting=step('window.target',value='起点窗口',variable='')
        snapshot=core('GetConfig');config=snapshot['config'];config['rules'][1]['steps']=[focused,starting,*reads]
        core('CommitConfig',{'requestId':'window-info-enums','expectedRevision':snapshot['revision'],'config':config});information=run_rule('window');outputs=[r['output'] for r in information['steps'][2:]]
        assert outputs[0]['value']=='Probe A' and outputs[1]['value']==a['applicationId'] and outputs[3]['value']==1 and outputs[4]['value']==1,outputs
        results['windowInformationAndTargetEnums']=information
        inactive=[step('workspace.switch',value='指定编号',index=1)]
        for action,value in [('window.monitor','下一个显示器'),('window.monitor','上一个显示器'),('workspace.switch','下一工作区'),('workspace.switch','上一工作区')]:
            item=step(action,value=value,index=1,**({'target':'当前动作目标'} if action=='window.monitor' else {}));item['params']['index']={'mode':'reference','value':{'symbolId':'removed-hidden-index','kind':'number','path':[]}};inactive.append(item)
        snapshot=core('GetConfig');config=snapshot['config'];config['rules'][1]['steps']=inactive
        core('CommitConfig',{'requestId':'inactive-desktop-parameters','expectedRevision':snapshot['revision'],'config':config});results['inactiveDesktopParameters']=run_rule('window')

        results['phaseCWindows']={'operations':states,'geometryPercent':True,'workspaceOperations':True,'monitorOperations':'--multi-monitor' in sys.argv,'findWindowOrdering':True,'desktopRestorePreservesMinimized':True,'overviewOperations':True,'coreFoundWindowRouting':routed}
        call({'action':'position','title':'Probe A','x':100,'y':180,'width':420,'focus':False},False)
    if '--phase-c-input' in sys.argv:
        call({'operation':'windowAction','window':a['handle'],'action':'unmaximize'})
        call({'action':'position','title':'Probe A','x':100,'y':180,'width':420,'focus':True},False)
        wait(lambda:call({'operation':'windowInfo','window':a['handle']})['geometry']['width']==420)
        connection.call_sync('org.waystroke.Client','/org/waystroke/Client','org.waystroke.Client','Focus',GLib.Variant('(s)',('Probe A:normal',)),None,Gio.DBusCallFlags.NONE,3000,None)
        snapshot=core('GetConfig');config=snapshot['config'];config['settings']['feedback']=False
        input_rule={'id':'input','name':'input','enabled':False,'feedback':False,'gestureId':'g','auxiliaryButtons':[],'applicationId':None,'titleMatch':{'operator':'包含','value':''},'steps':[dict(step('wait',value=0),id='input-initial')]};config['rules'].append(input_rule)
        core('CommitConfig',{'requestId':'input-seed','expectedRevision':snapshot['revision'],'config':config})
        def execute_input(steps):
            snapshot=core('GetConfig');config=snapshot['config'];next(r for r in config['rules'] if r['id']=='input')['steps']=steps
            core('CommitConfig',{'requestId':'input-check','expectedRevision':snapshot['revision'],'config':config});return run_rule('input')
        keydown=step('key',value='Shift',operation='按下',target='起点窗口');keydown['id']='key-down'
        keyup=step('key',value='Shift',operation='释放',target='起点窗口');keyup['id']='key-up'
        text=step('text',value='a',target='起点窗口',method='模拟文本输入');text['id']='text-shifted'
        unicode=step('text',value='中文🙂',target='起点窗口',method='自动');unicode['id']='text-unicode'
        execution=execute_input([keydown,text,keyup,unicode])
        results['inputStateAfter']=call({'operation':'overviewInfo'});results['inputStateAfter']['context']=call({'operation':'getContext'});results['inputStateAfter']['client']=json.loads((root/'client.json').read_text())
        wait(lambda:json.loads((root/'client.json').read_text())['Probe A']['text']=='A中文🙂')
        results['phaseCKeyAndUnicode']=execution
        pointer=step('pointer',value='目标窗口内',x=100,y=180,target='起点窗口');execution=execute_input([pointer]);wait(lambda:call({'operation':'getContext'})['position']==[200,360])
        relative=step('pointer',value='相对当前位置',x=10,y=-5,target='起点窗口');execute_input([relative]);wait(lambda:call({'operation':'getContext'})['position']==[210,355])
        clicks=[]
        for i,button in enumerate(['左键','中键','右键','侧键 1','侧键 2']):
            click=step('mouse',value=button,operation='单击',position='指定坐标',x=200,y=360);click['id']='mouse-'+str(i);clicks.append(click)
        execute_input(clicks)
        buttons=wait(lambda:(lambda records:records if {1,2,3,8,9}.issubset({event[0] for event in records if event[1]}) else None)(json.loads((root/'client.json').read_text())['Probe A']['mouseEvents']))
        scrolls=[]
        for i,direction in enumerate(['向上','向下','向左','向右']):
            scroll=step('scroll',value=direction,amount=1,target='起点窗口');scroll['id']='scroll-'+str(i);scrolls.append(scroll)
        execute_input(scrolls)
        scroll_events=wait(lambda:(lambda records:records if len(records)>=4 else None)(json.loads((root/'client.json').read_text())['Probe A']['scrollEvents']))
        assert any(dy<0 for dx,dy in scroll_events) and any(dy>0 for dx,dy in scroll_events) and any(dx<0 for dx,dy in scroll_events) and any(dx>0 for dx,dy in scroll_events),scroll_events
        before_a=len(json.loads((root/'client.json').read_text())['Probe A']['scrollEvents']);before_b=len(json.loads((root/'client.json').read_text())['Probe B']['scrollEvents'])
        execute_input([step('pointer',value='屏幕绝对坐标',x=650,y=400,target='起点窗口'),step('scroll',value='向下',amount=1,target='起点窗口')])
        wait(lambda:len(json.loads((root/'client.json').read_text())['Probe A']['scrollEvents'])==before_a+1)
        assert len(json.loads((root/'client.json').read_text())['Probe B']['scrollEvents'])==before_b
        results['scrollTargetsWindowAcrossPointerLocation']=True
        before=json.loads((root/'client.json').read_text())['Probe A']['motions']
        execute_input([step('drag',value='左键',start='200, 360',end='320, 360',duration=100,target='起点窗口')]);wait(lambda:call({'operation':'getContext'})['position']==[320,360])
        wait(lambda:json.loads((root/'client.json').read_text())['Probe A']['motions']>before)
        # Complete the normal catalog variants, observing actual GTK events.
        before_keys=len(json.loads((root/'client.json').read_text())['Probe A']['keyEvents'])
        execute_input([step('key',value='Shift',operation='按下并释放',target='起点窗口')])
        wait(lambda:len(json.loads((root/'client.json').read_text())['Probe A']['keyEvents'])>=before_keys+2)
        execute_input([step('pointer',value='屏幕绝对坐标',x=200,y=360,target='起点窗口')]);wait(lambda:call({'operation':'getContext'})['position']==[200,360])
        before_buttons=len(json.loads((root/'client.json').read_text())['Probe A']['mouseEvents'])
        execute_input([step('mouse',value='左键',operation='双击',position='当前位置',x=0,y=0)])
        double=wait(lambda:(lambda events:events if len(events)>=4 else None)(json.loads((root/'client.json').read_text())['Probe A']['mouseEvents'][before_buttons:]));assert [e[1] for e in double[:4]]==[True,False,True,False],double
        before_buttons=len(json.loads((root/'client.json').read_text())['Probe A']['mouseEvents'])
        execute_input([step('mouse',value='中键',operation='按下',position='当前位置',x=0,y=0),step('wait',value=30),step('mouse',value='中键',operation='释放',position='当前位置',x=0,y=0)])
        held_mouse=wait(lambda:(lambda events:events if len(events)>=2 else None)(json.loads((root/'client.json').read_text())['Probe A']['mouseEvents'][before_buttons:]));assert [e[:2] for e in held_mouse[:2]]==[[2,True],[2,False]],held_mouse
        execute_input([step('mouse',value='左键',operation='单击',position='手势起点',x=0,y=0)]);wait(lambda:call({'operation':'getContext'})['position']==origin['position'])
        drags=[]
        for button in ['中键','右键']:
            before_buttons=len(json.loads((root/'client.json').read_text())['Probe A']['mouseEvents'])
            record=execute_input([step('drag',value=button,start='200, 360',end='320, 360',duration=80,target='起点窗口')]);wait(lambda:call({'operation':'getContext'})['position']==[320,360])
            events=wait(lambda:(lambda events:events if len(events)>=2 else None)(json.loads((root/'client.json').read_text())['Probe A']['mouseEvents'][before_buttons:]));assert events[0][0]==(2 if button=='中键' else 3) and events[0][1] and not events[-1][1],events;drags.append(record)
        results['additionalInputEnums']={'keyPressRelease':True,'absolutePointer':True,'doubleClick':double,'mouseHoldRelease':held_mouse,'gestureStartPosition':True,'middleAndRightDrags':drags}
        # A timed held-input sequence must release the virtual Shift before later input.
        held=step('repeat',value=1);held['timeoutMs']=50;held['children']=[keydown,step('wait',value=1000)]
        snapshot=core('GetConfig');config=snapshot['config'];next(r for r in config['rules'] if r['id']=='input')['steps']=[held]
        core('CommitConfig',{'requestId':'held-timeout','expectedRevision':snapshot['revision'],'config':config})
        id=core('RunRule',{'ruleId':'input','context':origin})['executionId'];execution=wait(lambda:next((e for e in core('GetRuntime')['executions'] if e['id']==id and e['state']=='timedOut'),None))
        wait(lambda:[65505,False] in json.loads((root/'client.json').read_text())['Probe A']['keyEvents'])
        results['phaseCInput']={'buttons':buttons,'scrolls':scroll_events,'dragMotion':True,'pointerModes':True,'timeoutReleasesHeldShift':execution}
        # Restore the editor focus used by the baseline keyboard checks.
        call({'action':'position','title':'Probe A','x':100,'y':180,'width':420,'focus':False},False)
    if '--phase-c-clipboard' in sys.argv:
        def clipboard(q):return json.loads(connection.call_sync('org.waystroke.Client','/org/waystroke/Client','org.waystroke.Client','Clipboard',GLib.Variant('(s)',(json.dumps(q),)),GLib.VariantType('(s)'),Gio.DBusCallFlags.NONE,3000,None).unpack()[0])
        def focus(kind='normal'):
            call({'operation':'windowAction','action':'activate','window':a['handle']})
            connection.call_sync('org.waystroke.Client','/org/waystroke/Client','org.waystroke.Client','Focus',GLib.Variant('(s)',('Probe A:'+kind,)),None,Gio.DBusCallFlags.NONE,3000,None)
        snapshot=core('GetConfig');config=snapshot['config'];config['settings']['feedback']=False
        if not any(r['id']=='clipboard' for r in config['rules']):config['rules'].append({'id':'clipboard','name':'clipboard','enabled':False,'feedback':False,'gestureId':'g','auxiliaryButtons':[],'applicationId':None,'titleMatch':{'operator':'包含','value':''},'steps':[dict(step('wait',value=0),id='clipboard-initial')]})
        core('CommitConfig',{'requestId':'clipboard-seed','expectedRevision':snapshot['revision'],'config':config})
        def execute_clipboard(steps,expected='succeeded'):
            snapshot=core('GetConfig');config=snapshot['config'];
            for index,item in enumerate(steps):item['id']='clipboard-'+str(index)+'-'+item['id']
            next(r for r in config['rules'] if r['id']=='clipboard')['steps']=steps
            core('CommitConfig',{'requestId':'clipboard-check','expectedRevision':snapshot['revision'],'config':config})
            id=core('RunRule',{'ruleId':'clipboard','context':origin})['executionId'];execution=wait(lambda:next((e for e in core('GetRuntime')['executions'] if e['id']==id and e['state'] not in ['queued','running']),None));assert execution['state']==expected,execution;return execution
        call({'operation':'windowAction','window':a['handle'],'action':'activate'});focus()
        original={'text/plain;charset=utf-8':list('original 中文'.encode()),'text/html':list(b'<b>original</b>'),'application/x-waystroke-fixture':[0,255,42]}
        clipboard({'operation':'write','formats':original});wait(lambda:call({'operation':'clipboardRead'})=='original 中文')
        before=json.loads((root/'client.json').read_text())['Probe A']['text']
        paste=step('paste',value='追加🙂中文',target='起点窗口',restore='恢复原内容')
        execution=execute_clipboard([paste]);wait(lambda:json.loads((root/'client.json').read_text())['Probe A']['text']==before+'追加🙂中文')
        for mime,content in original.items():assert clipboard({'operation':'read','mime':mime})['bytes']==content
        results['phaseCClipboardRestoreAllMime']=execution
        before=json.loads((root/'client.json').read_text())['Probe A']['text']
        first=step('paste',value='连续一',target='起点窗口',restore='恢复原内容');second=step('paste',value='连续二',target='起点窗口',restore='恢复原内容')
        serial=execute_clipboard([first,step('wait',value=20),second]);wait(lambda:json.loads((root/'client.json').read_text())['Probe A']['text']==before+'连续一连续二')
        results['serialPastePreservesCursor']=serial

        keep=step('paste',value='kept🙂',target='起点窗口',restore='保留本次内容');execute_clipboard([keep]);wait(lambda:call({'operation':'clipboardRead'})=='kept🙂')
        execute_clipboard([step('shortcut',value='Ctrl+A',target='起点窗口',count=1),step('selection.copy',target='起点窗口',timeout=1000)])
        expected=json.loads((root/'client.json').read_text())['Probe A']['text'];assert call({'operation':'clipboardRead'})==expected
        results['phaseCSelectionCopy']=True
        execute_clipboard([step('clipboard.write',value='stale value')]);focus('none')
        no_paste=step('paste',value='must-not-paste',target='起点窗口',restore='恢复原内容');no_paste['timeoutMs']=120
        no_paste_result=execute_clipboard([no_paste],expected='timedOut');assert call({'operation':'clipboardRead'})=='stale value'
        results['phaseCPasteRequiresAppRead']=no_paste_result
        failed=execute_clipboard([step('selection.copy',target='起点窗口',timeout=120)],expected='timedOut');assert call({'operation':'clipboardRead'})=='stale value'
        results['phaseCSelectionDoesNotReturnOldClipboard']=failed
        execute_clipboard([step('clipboard.clear')]);assert call({'operation':'clipboardRead'})==''
        clipboard({'operation':'write','formats':original});wait(lambda:call({'operation':'clipboardRead'})=='original 中文')
        call({'operation':'clipboardPasteStart','window':a['handle'],'text':'temporary','restore':True})
        call({'operation':'releaseInputs'})
        for mime,content in original.items():assert clipboard({'operation':'read','mime':mime})['bytes']==content
        results['phaseCCanceledPasteRestoresAllMime']=True
        focus()
    if '--phase-c-system' in sys.argv:
        snapshot=core('GetConfig');config=snapshot['config'];config['settings']['feedback']=False
        config['rules'].append({'id':'system','name':'system','enabled':False,'feedback':False,'gestureId':'g','auxiliaryButtons':[],'applicationId':None,'titleMatch':{'operator':'包含','value':''},'steps':[step('wait',value=0)]})
        core('CommitConfig',{'requestId':'system-seed','expectedRevision':snapshot['revision'],'config':config})
        def start_system(steps):
            snapshot=core('GetConfig');config=snapshot['config'];next(r for r in config['rules'] if r['id']=='system')['steps']=steps
            core('CommitConfig',{'requestId':'system-check','expectedRevision':snapshot['revision'],'config':config});return core('RunRule',{'ruleId':'system','context':origin})['executionId']
        def finish_system(id,expected='succeeded'):
            execution=wait(lambda:next((e for e in core('GetRuntime')['executions'] if e['id']==id and e['state'] not in ['queued','running']),None));assert execution['state']==expected,execution;return execution
        message=step('dialog.message',value='WayStroke fixture',body='Native action prompt without settings UI',buttons='确定')
        id=start_system([message]);wait(lambda:call({'operation':'systemInfo'})['dialogOpen'])
        assert not any(w['title']=='WayStroke' for w in call({'operation':'windows'}))
        call({'action':'key','keyval':65293,'pressed':True},False);call({'action':'key','keyval':65293,'pressed':False},False)
        result=finish_system(id);assert result['steps'][0]['output']=={'kind':'boolean','value':True};results['phaseCNativePromptWithoutUI']=result
        input=step('dialog.input',value='Input fixture',default='input-value')
        id=start_system([input]);wait(lambda:call({'operation':'systemInfo'})['dialogOpen']);call({'action':'key','keyval':65293,'pressed':True},False);call({'action':'key','keyval':65293,'pressed':False},False)
        result=finish_system(id);assert result['steps'][0]['output']=={'kind':'text','value':'input-value'};results['phaseCNativeInput']=result
        id=start_system([input]);wait(lambda:call({'operation':'systemInfo'})['dialogOpen']);call({'action':'key','keyval':65307,'pressed':True},False);call({'action':'key','keyval':65307,'pressed':False},False)
        result=finish_system(id,'canceled');assert result['steps'][0]['output'] is None;results['phaseCPromptCancelIsNotEmptyResult']=result
        id=start_system([input]);wait(lambda:call({'operation':'systemInfo'})['dialogOpen']);core('RuntimeControl',{'operation':'stopAll'});finish_system(id,'canceled');wait(lambda:not call({'operation':'systemInfo'})['dialogOpen'])
        finish_system(start_system([step('notification',value='WayStroke fixture notification',body='Actual GNOME notification')]))
        wait(lambda:'WayStroke fixture notification' in call({'operation':'systemInfo'})['notifications']);results['phaseCNotification']=True
        screenshot_path=root/'full-screen.png'
        result=finish_system(start_system([step('screenshot',value='全屏',destination='文件',path=str(screenshot_path))]));assert screenshot_path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n');results['phaseCFullScreenshot']=result
        window_path=root/'target-window.png'
        result=finish_system(start_system([step('screenshot',value='目标窗口',destination='文件',path=str(window_path))]));assert window_path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n');results['phaseCWindowScreenshot']=result
        if '--phase-c-clipboard' in sys.argv:
            capture=step('screenshot',value='全屏',destination='剪贴板',path='');capture['params']['path']={'mode':'reference','value':{'symbolId':'removed-hidden-path','kind':'text','path':[]}}
            results['inactiveScreenshotPath']=finish_system(start_system([capture]))
            assert clipboard({'operation':'read','mime':'image/png'})['bytes'][:8]==list(b'\x89PNG\r\n\x1a\n');results['phaseCScreenshotClipboard']=True
        selection_path=root/'selection.png'
        id=start_system([step('screenshot',value='选区',destination='文件',path=str(selection_path))]);wait(lambda:call({'operation':'systemInfo'})['selection'])
        call({'action':'pointer','x':250,'y':300},False);call({'action':'button','button':1,'pressed':True},False)
        for x in [270,300,350,380]:call({'action':'pointer','x':x,'y':400},False);time.sleep(.03)
        call({'action':'button','button':1,'pressed':False},False);result=finish_system(id);assert selection_path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n');results['phaseCSelectionScreenshot']=result
        id=start_system([step('screenshot',value='选区',destination='文件',path=str(root/'must-not-exist.png'))]);wait(lambda:call({'operation':'systemInfo'})['selection']);core('RuntimeControl',{'operation':'stopAll'});finish_system(id,'canceled');assert not (root/'must-not-exist.png').exists();wait(lambda:not call({'operation':'systemInfo'})['selection']);results['phaseCSelectionCancel']=True
        if '--phase-c-audio' in sys.argv:
            import re
            volume_records=[]
            for device,kind,name in [('默认输出','sink','waystroke_fixture'),('默认输入','source','waystroke_input')]:
                for operation,amount,expected in [('设置音量',30,30),('增加音量',10,40),('降低音量',5,35)]:
                    finish_system(start_system([step('volume',value=operation,amount=amount,device=device)]))
                    actual=wait(lambda:(lambda values:values if values and all(abs(value-expected)<=1 for value in values) else None)([int(value) for value in re.findall(r'(\d+)%',subprocess.check_output(['pactl','get-'+kind+'-volume',name],text=True))]))
                    volume_records.append({'device':device,'operation':operation,'volume':actual})
                for operation,expected in [('静音',True),('取消静音',False),('切换静音',True)]:
                    finish_system(start_system([step('volume',value=operation,amount=0,device=device)]))
                    wait(lambda:('yes' in subprocess.check_output(['pactl','get-'+kind+'-mute',name],text=True))==expected)
                    volume_records.append({'device':device,'operation':operation,'muted':expected})
            results['phaseCRealPrivateAudio']=volume_records
        result=finish_system(start_system([step('brightness',value='设置',amount=50)]),'failed');assert '背光' in result['reason'];results['phaseCBrightnessUnavailable']=result
    if '--phase-c-apps' in sys.argv:
        def execute_app(steps,expected='succeeded'):
            snapshot=core('GetConfig');config=snapshot['config'];config['settings']['feedback']=False
            config['rules']=[r for r in config['rules'] if r['id']!='apps']+[{'id':'apps','name':'apps','enabled':False,'gestureId':'g','auxiliaryButtons':[],'applicationId':None,'titleMatch':{'operator':'包含','value':''},'steps':steps}]
            core('CommitConfig',{'requestId':'apps','expectedRevision':snapshot['revision'],'config':config})
            id=core('RunRule',{'ruleId':'apps','context':origin})['executionId']
            execution=wait(lambda:next((item for item in core('GetRuntime')['executions'] if item['id']==id and item['state'] not in ['queued','running']),None));assert execution['state']==expected,execution;return execution
        results['backgroundApplicationLaunch']=execute_app([step('launch',value='org.waystroke.Background',arguments='alpha "two words"',windowTarget='否')])
        assert wait(lambda:json.loads((root/'background-arguments.json').read_text()))==['alpha','two words']
        application=next(w['applicationId'] for w in call({'operation':'windows'}) if w['title']=='Launched A')
        results['applicationActivateExisting']=execute_app([step('app.activate',value=application,title='Launched B',timeout=2000)])
        wait(lambda:call({'operation':'focusedWindow'})==next(w['handle'] for w in call({'operation':'windows'}) if w['title']=='Launched B'))
        find=step('window.find',value=application,title='Launched A',workspace='所有工作区',pick='最近使用');find['output']={'id':'app-window','name':'app-window','kind':'window'}
        target=step('window.target',value='窗口变量',variable='');target['params']['variable']={'mode':'reference','value':{'symbolId':'app-window','kind':'window','path':[]}}
        results['applicationQuitOne']=execute_app([find,target,step('app.quit',value=application,mode='当前目标窗口',target='当前动作目标')])
        wait(lambda:not any(w['title']=='Launched A' for w in call({'operation':'windows'})));assert any(w['title']=='Launched B' for w in call({'operation':'windows'}))
        results['applicationQuitAll']=execute_app([step('app.quit',value=application,mode='该应用的所有窗口',target='起点窗口')])
        wait(lambda:not any(w['title'].startswith('Launched ') for w in call({'operation':'windows'})))
        launched=step('launch',value='org.waystroke.ArgumentsClient',arguments='alpha "two words"',windowTarget='是');launched['output']={'id':'new-window','name':'new-window','kind':'window'}
        results['applicationArgumentsAndNewTarget']=execute_app([launched,step('window.info',value='标题',target='当前动作目标')])
        assert json.loads((root/'launch-arguments.json').read_text())==['alpha','two words']
        assert results['applicationArgumentsAndNewTarget']['steps'][0]['output']['kind']=='window'
        missing=step('app.activate',value='org.waystroke.Background',title='never exists',timeout=250)
        results['applicationWindowTimeout']=execute_app([missing],'timedOut');assert '超时' in results['applicationWindowTimeout']['reason']
        results['actualSystemSettings']=execute_app([step('settings.open',value='声音')])
        assert any(w['applicationId']=='org.gnome.Settings.desktop' for w in call({'operation':'windows'}))
    if '--phase-c-integration' in sys.argv:
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        import threading
        received=[]
        class PipelineHandler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                body=self.rfile.read(int(self.headers['Content-Length'])).decode();received.append(body)
                self.send_response(201);self.end_headers();self.wfile.write(('accepted '+body).encode())
        server=ThreadingHTTPServer(('127.0.0.1',0),PipelineHandler);threading.Thread(target=server.serve_forever,daemon=True).start()
        def ref(id,kind,path=None):return {'mode':'reference','value':{'symbolId':id,'kind':kind,'path':path or []}}
        def result(s,id,kind):s['output']={'id':id,'name':id,'kind':kind};return s
        def execute_pipeline(steps):
            snapshot=core('GetConfig');config=snapshot['config'];config['settings']['feedback']=False
            rule={'id':'pipeline','name':'pipeline','enabled':False,'feedback':False,'gestureId':'g','auxiliaryButtons':[],'applicationId':None,'titleMatch':{'operator':'包含','value':''},'steps':steps}
            config['rules']=[r for r in config['rules'] if r['id']!='pipeline']+[rule]
            core('CommitConfig',{'requestId':'integration','expectedRevision':snapshot['revision'],'config':config});return run_rule('pipeline')
        try:
            directory=root/'pipeline-files';directory.mkdir();(directory/'a.txt').write_text('A');(directory/'b.txt').write_text('B')
            call({'operation':'clipboardWrite','text':'  pipeline  '})
            read=result(step('clipboard.read'),'pipeline-clip','text')
            trim=result(step('text.transform',value='',operation='去首尾空白',argument='',replacement=''),'pipeline-trim','text');trim['params']['value']=ref('pipeline-clip','text')
            request=result(step('http.request',value=f'http://127.0.0.1:{server.server_port}/',method='POST',headers='',body='',timeout=2000),'pipeline-http','data');request['params']['body']=ref('pipeline-trim','text')
            branch=step('condition',value='变量',source='',operator='等于',compare=201);branch['params']['source']=ref('pipeline-http','number',['status'])
            listing=result(step('directory.list',value=str(directory),filter='*.txt',recursive='否'),'pipeline-list','list')
            loop=step('foreach',value='',item='file',index='index',itemKind='文本');loop['params']['value']=ref('pipeline-list','list');loop['loopItem']={'id':'pipeline-item','name':'file','kind':'text'};loop['loopIndex']={'id':'pipeline-index','name':'index','kind':'number'}
            file=result(step('file.read',value='',encoding='UTF-8'),'pipeline-content','text');file['params']['value']=ref('pipeline-item','text')
            notice=step('notification',value='WayStroke pipeline file',body='');notice['params']['body']=ref('pipeline-content','text');loop['children']=[file,notice]
            done=step('notification',value='WayStroke pipeline complete',body='');done['params']['body']=ref('pipeline-http','text',['body'])
            branch['children']=[listing,loop,done];branch['otherwise']=[step('flow.stop',value='Unexpected HTTP status')]
            execution=execute_pipeline([read,trim,request,branch]);assert received==['pipeline'] and sum(s['summary']=='读取文本文件' for s in execution['steps'])==2
            wait(lambda:'WayStroke pipeline complete' in call({'operation':'systemInfo'})['notifications']);results['representativeClipboardHttpFilesNotification']=execution
            # Waiting for a real window, then explicitly changing the action target.
            waiting=step('wait.condition',value='窗口出现',subject=a['applicationId'],compare='',timeout=2000,interval=30)
            found=result(step('window.find',value=a['applicationId'],title='Probe B',workspace='所有工作区',pick='最近使用'),'pipeline-window','window')
            target=step('window.target',value='窗口变量',variable='');target['params']['variable']=ref('pipeline-window','window')
            before=json.loads((root/'client.json').read_text())['Probe B']['text']
            typing=step('text',value='pipeline target',target='当前动作目标',method='自动')
            execution=execute_pipeline([waiting,found,target,typing]);wait(lambda:'pipeline target' in json.loads((root/'client.json').read_text())['Probe B']['text']);assert json.loads((root/'client.json').read_text())['Probe A']['text']!='pipeline target'
            results['representativeWaitFindTargetInput']=execution
        finally:server.shutdown();server.server_close()
    if '--phase-c-composed-input' in sys.argv:
        subprocess.run([sys.executable,str(REPO/'scripts/check-composed-input.py')],check=True)
        results['composedInput']=json.loads((REPO/'fixtures/phase-c/devkit-composed-input.json').read_text())
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
    after=wait(lambda:(lambda info:info['geometry'] if info['maximized'] else None)(call({'operation':'windowInfo','window':a['handle']})));results['maximize']={'before':before,'after':after,'nativeMaximized':True}
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
    if '--phase-c-session' in sys.argv:
        snapshot=core('GetConfig');config=snapshot['config'];config['settings']['feedback']=False
        config['rules'].append({'id':'session','name':'session','enabled':False,'gestureId':'g','auxiliaryButtons':[],'applicationId':None,'titleMatch':{'operator':'包含','value':''},'steps':[step('session',value='锁屏',confirm='是')]})
        core('CommitConfig',{'requestId':'session','expectedRevision':snapshot['revision'],'config':config})
        id=core('RunRule',{'ruleId':'session','context':end})['executionId']
        wait(lambda:call({'operation':'systemInfo'})['dialogOpen']);call({'action':'key','keyval':65307,'pressed':True},False);call({'action':'key','keyval':65307,'pressed':False},False)
        canceled=wait(lambda:next((e for e in core('GetRuntime')['executions'] if e['id']==id and e['state']=='canceled'),None));assert not core('GetRuntime')['locked'];results['sessionConfirmationCancel']=canceled
        snapshot=core('GetConfig');config=snapshot['config'];next(r for r in config['rules'] if r['id']=='session')['steps']=[step('session',value='锁屏',confirm='否')]
        core('CommitConfig',{'requestId':'session-lock','expectedRevision':snapshot['revision'],'config':config})
        id=core('RunRule',{'ruleId':'session','context':end})['executionId'];locked=wait(lambda:core('GetRuntime') if core('GetRuntime')['locked'] else None)
        assert not locked['status']['executionAvailable'] and locked['status']['reason']=='桌面已锁定'
        execution=wait(lambda:next((e for e in core('GetRuntime')['executions'] if e['id']==id and e['state'] not in ['queued','running']),None))
        assert execution['state'] in ['succeeded','canceled'],execution
        results['sessionActualPrivateLock']={'locked':True,'execution':execution,'mainSessionUntouched':True}
        try:core('RunRule',{'ruleId':'session','context':end})
        except RuntimeError as error:assert '桌面已锁定' in str(error);results['lockedRunRejected']=True
        else:raise AssertionError('RunRule accepted while locked')
    results['complete']=True
finally:
    for p in reversed(processes):
        if p.poll() is None:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=5)
    (root/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps(results,ensure_ascii=False,indent=2),flush=True)
