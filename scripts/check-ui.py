#!/usr/bin/env python3
"""Native WebKitGTK/Wayland UI check on a disposable GNOME desktop."""
import ast,base64,json,os,shutil,signal,socket,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
from gi.repository import Gio,GLib
REPO=Path(__file__).resolve().parents[1]
if '--inside' not in sys.argv:
    root=Path(tempfile.mkdtemp(prefix='waystroke-ui-check-'))
    for name in ['runtime','config','data','cache']:(root/name).mkdir(mode=0o700)
    ext=root/'data/gnome-shell/extensions/waystroke-probe@local';ext.mkdir(parents=True)
    for name in ['extension.js','metadata.json','terminal-monitor.js']:shutil.copy(REPO/'probes/gnome50'/name,ext/name)
    formal=root/'data/gnome-shell/extensions/waystroke@local';formal.mkdir()
    for name in ['extension.js','metadata.json','clipboard.js','dialogs.js','system.js','text.js','terminal.js']:shutil.copy(REPO/'extension'/name,formal/name)
    helper=ext/'extension.js';helper.write_text(helper.read_text().replace('clientType:a.meta_window.get_client_type()', 'clientType:a.meta_window.get_client_type(),minimized:a.meta_window.minimized').replace('return {panelState:', 'return {startingUp:Main.layoutManager._startingUp,actionMode:Main.actionMode,ibusReady:!!IBusManager.getIBusManager()._panelService,panelState:'))
    env=os.environ.copy();env.update(XDG_RUNTIME_DIR=str(root/'runtime'),XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),XDG_CACHE_HOME=str(root/'cache'),GSETTINGS_BACKEND='keyfile',LIBGL_ALWAYS_SOFTWARE='1',GIO_USE_VFS='local',WAYSTROKE_PROBE_DIR=str(root),GDK_BACKEND='wayland',GSK_RENDERER='cairo',WAYLAND_DISPLAY='waystroke-ui-check-0')
    if '--devkit' in sys.argv:
        env['WAYSTROKE_OUTER_RUNTIME']=os.environ['XDG_RUNTIME_DIR'];env['WAYSTROKE_OUTER_DISPLAY']=os.environ.get('WAYLAND_DISPLAY','wayland-0')
        env['PIPEWIRE_RUNTIME_DIR']=os.environ['XDG_RUNTIME_DIR']
        env.pop('LIBGL_ALWAYS_SOFTWARE',None)
        schema=Path('/usr/share/glib-2.0/schemas/org.gnome.mutter.devkit.gschema.xml')
        schemas=root/'schemas';schemas.mkdir();shutil.copy(schema,schemas/schema.name);subprocess.run(['glib-compile-schemas',str(schemas)],check=True);env['GSETTINGS_SCHEMA_DIR']=str(schemas)
    env['GI_TYPELIB_PATH']=str(REPO/'target/native')+':/usr/lib64/mutter-18'
    env['LD_LIBRARY_PATH']=str(REPO/'target/native')+':/usr/lib64/mutter-18:/usr/lib64/gnome-shell'
    for name in ['DISPLAY','IBUS_ADDRESS','AT_SPI_BUS_ADDRESS']:env.pop(name,None)
    print('Native UI artifacts:',root,flush=True)
    sys.exit(subprocess.run(['dbus-run-session','--',sys.executable,__file__,'--inside',*sys.argv[1:]],env=env).returncode)
root=Path(os.environ['WAYSTROKE_PROBE_DIR']);processes=[];results={}
def spawn(name,args):
    log=(root/(name+'.log')).open('w');p=subprocess.Popen(args,stdout=log,stderr=log,start_new_session=True);processes.append(p);return p
connection=Gio.bus_get_sync(Gio.BusType.SESSION,None)
def core(method,payload=None):
    args=None if payload is None else GLib.Variant('(s)',(json.dumps(payload,ensure_ascii=False),))
    return json.loads(connection.call_sync('io.github.waystroke.Core','/io/github/waystroke/Core','io.github.waystroke.Core1',method,args,GLib.VariantType('(s)'),Gio.DBusCallFlags.NONE,3000,None).unpack()[0])
def shell(q):
    return json.loads(connection.call_sync('org.gnome.Shell','/org/waystroke/Probe','org.waystroke.Probe','Call',GLib.Variant('(s)',(json.dumps(q),)),GLib.VariantType('(s)'),Gio.DBusCallFlags.NONE,3000,None).unpack()[0])
def wait(fn,timeout=15):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        try:
            value=fn()
            if value:return value
        except (GLib.Error,ConnectionError,OSError):pass
        time.sleep(.1)
    raise RuntimeError('Timed out waiting for native UI condition')
def free_port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
port=free_port();native_port=free_port();session=None
base=f'http://127.0.0.1:{port}'
def http(method,path,payload=None):
    request=urllib.request.Request(base+path,data=None if payload is None else json.dumps(payload).encode(),headers={'Content-Type':'application/json'},method=method)
    try:response=urllib.request.urlopen(request,timeout=30)
    except urllib.error.HTTPError as error:raise RuntimeError(error.read().decode()) from error
    result=json.load(response)
    if isinstance(result.get('value'),dict) and result['value'].get('error'):raise RuntimeError(result['value'])
    return result['value']
def execute(script):return http('POST',f'/session/{session}/execute/sync',{'script':script,'args':[]})
def fill(selector,value):
    execute(f"const e=document.querySelector({json.dumps(selector)});e.focus();e.value={json.dumps(value)};e.dispatchEvent(new Event('input',{{bubbles:true}}));return true;")
def draw(selector):
    rect=execute(f'const e=document.querySelector({json.dumps(selector)});e.scrollIntoView({{block:"center"}});const r=e.getBoundingClientRect();return {{x:r.x,y:r.y,width:r.width,height:r.height}};')
    execute(f'window.strokeEvents=[];const c=document.querySelector({json.dumps(selector)});for(const name of ["pointerdown","pointermove","pointerup"])c.addEventListener(name,e=>window.strokeEvents.push({{type:e.type,button:e.button,x:e.clientX,y:e.clientY}}));return true;')
    x=int(rect['x']+50);y=int(rect['y']+50)
    window=[w for w in shell({'action':'snapshot'})['windows'] if w['title']=='WayStroke'][0]['rect']
    shell({'action':'activate','title':'WayStroke'})
    shell({'action':'pointer','x':window['x']+x,'y':window['y']+y})
    wait(lambda:core('GetRuntime')['value']['recording']=='canvas');time.sleep(.05);shell({'action':'button','button':3,'pressed':True});time.sleep(.05)
    for dx,dy in [(25,10),(50,40),(75,20),(100,70)]:
        shell({'action':'pointer','x':window['x']+x+dx,'y':window['y']+y+dy});time.sleep(.08)
    shell({'action':'button','button':3,'pressed':False});time.sleep(.1)

def capture(name,dialog=None):
    if dialog:assert execute(f'return document.querySelector({json.dumps(dialog)}).open;')
    time.sleep(.25) # WebKit paint follows the synchronous DOM callback.
    (root/name).write_bytes(base64.b64decode(http('GET',f'/session/{session}/screenshot')))

def click(selector):
    wait(lambda:execute(f'return Boolean(document.querySelector({json.dumps(selector)}));'))
    execute(f'document.querySelector({json.dumps(selector)}).click();return true;')
try:
    for schema,key,value in [('org.gnome.shell','enabled-extensions',"['waystroke@local','waystroke-probe@local']"),('org.gnome.shell','disable-user-extensions','false'),('org.gnome.desktop.interface','enable-hot-corners','false')]:subprocess.run(['gsettings','set',schema,key,value],check=True)
    if '--phase-d' in sys.argv and '--devkit' not in sys.argv:raise RuntimeError('Phase D UI tests require --devkit')
    spawn('shell',['gnome-shell','--headless','--wayland','--no-x11','--wayland-display=waystroke-ui-check-0',*(['--devkit'] if '--devkit' in sys.argv else ['--virtual-monitor=1440x1000'])])
    wait(lambda:shell({'action':'snapshot'}))
    if '--devkit' in sys.argv:
        viewer_env=os.environ.copy();viewer_env['XDG_RUNTIME_DIR']=viewer_env['WAYSTROKE_OUTER_RUNTIME'];viewer_env['WAYLAND_DISPLAY']=viewer_env['WAYSTROKE_OUTER_DISPLAY']
        viewer_log=(root/'viewer.log').open('w');viewer=subprocess.Popen(['/usr/libexec/mutter-devkit'],env=viewer_env,stdout=viewer_log,stderr=viewer_log,start_new_session=True);processes.append(viewer)
        wait(lambda:shell({'action':'snapshot'})['monitors']>0)
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
    if '--phase-d' in sys.argv:
        wait(lambda:not shell({'action':'snapshot'})['startingUp'])
        connection.call_sync('io.github.waystroke.Gnome','/io/github/waystroke/Gnome','io.github.waystroke.Gnome1','Call',GLib.Variant('(s)',(json.dumps({'operation':'desktopOverview','value':'隐藏概览'}),)),GLib.VariantType('(s)'),Gio.DBusCallFlags.NONE,3000,None)
        wait(lambda:shell({'action':'snapshot'})['actionMode']==1 and shell({'action':'snapshot'})['ibusReady'])
    spawn('core',[str(REPO/'target/debug/waystroke-core')]);wait(lambda:core('GetConfig')['status']=='ok')
    snapshot=core('GetConfig')['value'];snapshot['config']['settings']['setupComplete']=True
    assert core('CommitConfig',{'requestId':'fixture-init','expectedRevision':snapshot['revision'],'config':snapshot['config']})['status']=='ok'
    driver=Path(os.environ.get('WAYSTROKE_TAURI_DRIVER',shutil.which('tauri-driver') or '/tmp/waystroke-tools/bin/tauri-driver'))
    spawn('driver',[str(driver),'--port',str(port),'--native-port',str(native_port),'--native-driver','/usr/bin/WebKitWebDriver'])
    wait(lambda:http('GET','/status'))
    session=http('POST','/session',{'capabilities':{'alwaysMatch':{'tauri:options':{'application':str(REPO/'target/debug/waystroke')}}}})['sessionId']
    wait(lambda:execute('return Boolean(document.querySelector("#main h1"))'))
    results['initial']=execute('return {title:document.querySelector("#main h1").textContent,nav:document.querySelectorAll(".nav").length,reviewTools:document.querySelectorAll(".review-tools").length};')
    assert results['initial']['nav']==8 and results['initial']['reviewTools']==0
    if '--phase-d' in sys.argv:
        # Formal saved rule and page-local input use the same Rust matcher.
        click('.nav[data-page="text"]')
        click('.text-help summary')
        results['textHelp']=execute('return document.querySelector(".text-help").textContent;')
        assert all(term in results['textHelp'] for term in ['组合输入','Ctrl+Z','raw/TUI','密码'])
        capture('text-help.png')
        click('.text-help summary');click('#new-snippet')
        fill('#snippet-form [name="key"]','abc');fill('#snippet-form [name="value"]','2003\n中文')
        execute('document.querySelector("#snippet-form").requestSubmit();return true;')
        wait(lambda:len(core('GetConfig')['value']['config']['snippets'])==1)
        wait(lambda:execute('return document.querySelector("#snippet-list").textContent.includes("abc")&&!document.querySelector("#snippet-dialog").open;'))
        execute('const e=document.querySelector("#try-text");e.focus();e.value="abc ";e.setSelectionRange(4,4);e.dispatchEvent(new InputEvent("input",{inputType:"insertText",data:" ",bubbles:true}));return true;')
        wait(lambda:execute('return document.querySelector("#try-text").value;')=='2003\n中文 ')
        click('#undo-expansion');wait(lambda:execute('return document.querySelector("#try-text").value;')=='abc ')
        results['pageMatcherMultilineAndUndo']=True
        snippet_id=core('GetConfig')['value']['config']['snippets'][0]['id']
        click('#snippet-list [data-edit]');fill('#snippet-form [name="value"]','2003')
        execute('const f=document.querySelector("#snippet-form");f.elements.trigger.value="immediate";f.elements.caseSensitive.checked=false;f.elements.keepDelimiter.checked=false;f.requestSubmit();return true;')
        wait(lambda:execute('return !document.querySelector("#snippet-dialog").open && document.querySelector("#snippet-list").textContent.includes("立即替换");'))
        saved=core('GetConfig')['value']['config']['snippets'][0]
        assert saved['id']==snippet_id and saved['trigger']=='immediate' and not saved['caseSensitive'] and not saved['preserve']
        execute('const e=document.querySelector("#try-text");e.value="ABC";e.setSelectionRange(3,3);e.dispatchEvent(new InputEvent("input",{inputType:"insertText",data:"C",bubbles:true}));return true;')
        wait(lambda:execute('return document.querySelector("#try-text").value;')=='2003')
        results['existingSnippetEditorPersistsAndMatches']=True
        click('#snippet-list [data-edit]')
        execute('const f=document.querySelector("#snippet-form");f.elements.trigger.value="confirm";f.elements.caseSensitive.checked=true;f.elements.keepDelimiter.checked=true;f.requestSubmit();return true;')
        wait(lambda:execute('return !document.querySelector("#snippet-dialog").open && document.querySelector("#snippet-list").textContent.includes("空格或 Enter 确认");'))
        client_source=(REPO/'probes/gnome50/client.py').read_text().replace("(root/('client.json' if prefix=='Probe' else prefix+'-client.json')).write_text(json.dumps(state,ensure_ascii=False))", "tmp=root/'client.tmp';tmp.write_text(json.dumps(state,ensure_ascii=False));tmp.replace(root/'client.json')")
        client_source=client_source.replace("(p if kind=='password' else e).grab_focus();", "(p if kind=='password' else e).grab_focus();e.set_position(-1);e.select_region(-1,-1);")
        (root/'client.py').write_text(client_source);spawn('client',[sys.executable,str(root/'client.py')])
        wait(lambda:{'Probe A','Probe B'}.issubset({w['title'] for w in shell({'action':'snapshot'})['windows']}))
        def focus(kind):
            shell({'action':'activate','title':'Probe A'})
            wait(lambda:shell({'action':'snapshot'})['focus']=='Probe A')
            connection.call_sync('org.waystroke.Client','/org/waystroke/Client','org.waystroke.Client','Focus',GLib.Variant('(s)',('Probe A:'+kind,)),None,Gio.DBusCallFlags.NONE,3000,None)
        def status():return core('GetRuntime')['value']['text']
        def key(keyval):
            shell({'action':'key','keyval':keyval,'pressed':True});shell({'action':'key','keyval':keyval,'pressed':False})
        connection.call_sync('io.github.waystroke.Gnome','/io/github/waystroke/Gnome','io.github.waystroke.Gnome1','Call',GLib.Variant('(s)',(json.dumps({'operation':'desktopOverview','value':'隐藏概览'}),)),GLib.VariantType('(s)'),Gio.DBusCallFlags.NONE,3000,None)
        click('.nav[data-page="runtime"]')
        # Establish a real GTK text-input context for the status subscription.
        focus('password');wait(lambda:status()['state']=='password')
        focus('normal')
        window=next(w for w in shell({'action':'snapshot'})['windows'] if w['title']=='Probe A')['rect']
        shell({'action':'pointer','x':window['x']+150,'y':window['y']+65});shell({'action':'button','button':1,'pressed':True});shell({'action':'button','button':1,'pressed':False})
        wait(lambda:shell({'action':'snapshot'})['ime']['hasFocus']);key(ord('x'));key(0xff08);wait(lambda:status()['state']=='ready')
        wait(lambda:execute('return document.querySelector(".input-capability .chip").textContent;')=='可用')
        assert not core('GetRuntime')['value']['inputArmed'] and core('GetRuntime')['value']['selectedDeviceId'] is None
        results['textIndependentOfMouseArming']=status();capture('text-runtime-ready.png')
        # Reestablish the target field after WebKit inspection and capture.
        focus('password');focus('normal');key(ord('x'));key(0xff08)
        wait(lambda:shell({'action':'snapshot'})['ime']['hasFocus'])
        for char in 'abc':key(ord(char))
        key(32)
        wait(lambda:json.loads((root/'client.json').read_text())['Probe A']['text']=='2003 ')
        last=wait(lambda:core('GetRuntime')['value']['lastTextResult'])
        assert last['state']=='succeeded' and last['adapter']=='native',last
        wait(lambda:'最近' in execute('return document.querySelector(".input-capability p").textContent;'))
        results['nativeExpansionRuntimeResult']=last
        focus('password');wait(lambda:status()['state']=='password')
        wait(lambda:execute('return document.querySelector(".input-capability .chip").textContent;')=='已跳过')
        results['passwordRuntimeState']=status();capture('text-runtime-password.png')
        snapshot=core('GetConfig')['value'];snapshot['config']['settings']['textEnabled']=False
        assert core('CommitConfig',{'requestId':'text-off','expectedRevision':snapshot['revision'],'config':snapshot['config']})['status']=='ok'
        wait(lambda:status()['state']=='disabled')
        wait(lambda:execute('return document.querySelector(".input-capability .chip").textContent;')=='已暂停')
        results['disabledRuntimeState']=status()
        connection.call_sync('org.gnome.ScreenSaver','/org/gnome/ScreenSaver','org.gnome.ScreenSaver','SetActive',GLib.Variant('(b)',(True,)),None,Gio.DBusCallFlags.NONE,3000,None)
        wait(lambda:core('GetRuntime')['value']['locked'])
        wait(lambda:execute('return document.querySelector(".input-capability .chip").textContent;')=='锁屏暂停')
        results['actualLockedTextUI']=status()
        connection.call_sync('org.gnome.ScreenSaver','/org/gnome/ScreenSaver','org.gnome.ScreenSaver','SetActive',GLib.Variant('(b)',(False,)),None,Gio.DBusCallFlags.NONE,3000,None)
        wait(lambda:not core('GetRuntime')['value']['locked'])
        wait(lambda:execute('return document.querySelector(".input-capability .chip").textContent;')=='已暂停')
        results['unlockTextUIRestored']=True;results['complete']=True
        sys.exit(0)
    assert len(core('GetActionCapabilities')['value'])==69;results['actionCapabilityRegistry']=True
    windows=wait(lambda:[w for w in shell({'action':'snapshot'})['windows'] if w['title']=='WayStroke'])
    assert all(w['clientType']==0 for w in windows);results['nativeWindows']=windows
    for page in ['rules','gestures','actions','text','test','runtime','configuration','settings']:
        click(f'.nav[data-page="{page}"]')
        results[page]=execute('return {heading:document.querySelector("#main h1").textContent,active:document.querySelectorAll(".nav.active").length};')
        results[page]['metrics']=execute('const shell=document.querySelector(".shell").getBoundingClientRect();return Object.fromEntries([".sidebar",".appbar","#main",".page-heading",".settings-page",".runtime-grid",".rule-layout","#setting-mouse","#mouse-access-settings",".setting-row",".desktop-state-banner"].map(selector=>{const e=document.querySelector(selector);if(!e)return [selector,null];const r=e.getBoundingClientRect(),s=getComputedStyle(e);return [selector,{x:r.x-shell.x,y:r.y-shell.y,width:r.width,height:r.height,fontSize:s.fontSize,lineHeight:s.lineHeight,padding:s.padding,gap:s.gap}];}));')
        assert results[page]['active']==1
        screenshot=http('GET',f'/session/{session}/screenshot');(root/(page+'.png')).write_bytes(base64.b64decode(screenshot))
    click('#setting-feedback');wait(lambda:core('GetConfig')['value']['config']['settings']['feedback']==False)
    results['settingSaved']=True
    click('.nav[data-page="text"]');click('#new-snippet')
    results['textDialog']=execute('return document.querySelector("#snippet-dialog").open;')
    assert results['textDialog']
    capture('dialog-text.png','#snippet-dialog')
    fill('#snippet-form [name="key"]','abc');fill('#snippet-form [name="value"]','2003\n中文')
    execute('document.querySelector("#snippet-form").requestSubmit();return true;')
    wait(lambda:len(core('GetConfig')['value']['config']['snippets'])==1)
    click('.nav[data-page="gestures"]');click('#new-gesture');fill('#template-name','自由曲线');draw('#template-canvas');results['drawing']=execute('return {status:document.querySelector("#sample-status").textContent,events:window.strokeEvents};');click('#save-template')
    wait(lambda:len(core('GetConfig')['value']['config']['gestures'])==1)
    click('.nav[data-page="actions"]');click('#new-workflow');fill('#workflow-name','等待测试');click('#composer-add-root');click('[data-action-id="wait"]');fill('#composer-timeout','300');execute('document.querySelector("#composer-timeout").dispatchEvent(new Event("change",{bubbles:true}));return true;')
    if '--phase-c' in sys.argv:
        click('#composer-add-root');click('[data-action-id="loop.break"]');click('#composer-save')
        error=wait(lambda:execute('const e=document.querySelector("#composer-errors");return e&&!e.hidden?e.textContent:null;'))
        assert '循环' in error or '重复' in error,error
        assert execute('return document.querySelector("#composer-param-title").textContent;')=='退出当前重复'
        assert len(core('GetConfig')['value']['config']['workflows'])==0
        results['illegalLoopExitLocated']=error;capture('composer-error-loop.png');click('#composer-delete')
        click('#composer-add-root');click('[data-action-id="number.calculate"]');fill('#composer-params [data-param-key="left"] input','${未定义}');click('#composer-save')
        error=wait(lambda:execute('const e=document.querySelector("#composer-errors");return e&&!e.hidden&&e.textContent.includes("未定义")?e.textContent:null;'))
        assert execute('return document.querySelector("#composer-param-title").textContent;')=='数字计算'
        results['missingVariableLocated']=error;click('#composer-delete')
        click('#composer-add-root');click('[data-action-id="json.parse"]');fill('#composer-params [data-param-key="value"] textarea','8')
        fill('#composer-params [data-param-key="output"] input','自动数值')
        assert execute('return document.querySelector("#composer-params [data-param-key=resultKind] select").value;')=='自动'
        click('#composer-add-root');click('[data-action-id="number.calculate"]');fill('#composer-params [data-param-key="left"] input','');click('#composer-params [data-param-key="left"] .insert-variable');click('[data-variable="自动数值"]')
        fill('#composer-params [data-param-key="output"] input','计算结果')
        click('#composer-save');wait(lambda:len(core('GetConfig')['value']['config']['workflows'])==1)
        saved=core('GetConfig')['value']['config']['workflows'][0];assert saved['steps'][1]['output']['kind']=='any' and saved['steps'][2]['params']['left']['mode']=='reference'
        results['automaticResultTypedReferenceSaved']=saved
        click(f'[data-edit-workflow="{saved["id"]}"]');click('#composer-add-root');click('[data-action-id="flow.call"]')
        execute(f'const e=document.querySelector("#composer-fields select");e.value={json.dumps(saved["id"])};e.dispatchEvent(new Event("change",{{bubbles:true}}));return true;');click('#composer-save')
        error=wait(lambda:execute('const e=document.querySelector("#composer-errors");return e&&!e.hidden&&e.textContent.includes("递归")?e.textContent:null;'))
        assert execute('return document.querySelector("#composer-param-title").textContent;')=='调用可复用动作';results['recursiveCallLocated']=error;click('#composer-delete')
        click(f'[data-step-uid="{saved["steps"][1]["id"]}"]');click('#composer-delete');click('#composer-delete')
    capture('composer.png')
    click('#composer-add-root')
    capture('dialog-actions.png','#action-dialog')
    click('[data-action-id="clipboard.read"]');fill('#composer-params [data-param-key="output"] input','读到的文本')
    click('#composer-add-root');click('[data-action-id="clipboard.write"]');click('#composer-params .insert-variable')
    capture('dialog-variable.png','#variable-dialog')
    click('[data-variable="读到的文本"]')
    click('#add-workflow-output');fill('#workflow-outputs [data-declaration-key="name"]','返回文本');fill('#workflow-outputs [data-declaration-key="value"]','${读到的文本}')
    click('#composer-save');wait(lambda:any(s['action']=='clipboard.read' for s in core('GetConfig')['value']['config']['workflows'][0]['steps']))
    workflow=core('GetConfig')['value']['config']['workflows'][0]
    assert workflow['steps'][0]['timeoutMs']==300;results['stepTimeoutSaved']=True
    stable_output=workflow['steps'][1]['output']['id'];assert workflow['steps'][2]['params']['value']['value']['symbolId']==stable_output
    click(f'[data-edit-workflow="{workflow["id"]}"]');click(f'[data-step-uid="{workflow["steps"][1]["id"]}"]')
    fill('#composer-params [data-param-key="output"] input','重命名文本');execute('document.querySelector("#composer-params [data-param-key=output] input").blur();return true;')
    click('#composer-save');wait(lambda:core('GetConfig')['value']['config']['workflows'][0]['steps'][1]['output']['name']=='重命名文本')
    renamed=core('GetConfig')['value']['config']['workflows'][0]
    assert renamed['steps'][1]['output']['id']==stable_output and renamed['steps'][2]['params']['value']['value']['symbolId']==stable_output
    results['stableReferenceRename']=True
    click('.nav[data-page="rules"]');click('#new-rule');fill('#rule-name','配置测试')
    gesture=core('GetConfig')['value']['config']['gestures'][0]['id']
    execute(f'const e=document.querySelector("#rule-gesture");e.value={json.dumps(gesture)};e.dispatchEvent(new Event("change",{{bubbles:true}}));return true;')
    click('#pick-rule-window');wait(lambda:execute('return Boolean(document.querySelector("#window-dialog .window-picker button"));'));click('#window-dialog .window-picker button')
    click('#rule-feedback');click('#save-rule');wait(lambda:len(core('GetConfig')['value']['config']['rules'])==1)
    saved=core('GetConfig')['value']['config'];assert saved['rules'][0]['applicationId'];assert saved['applications'][0]['name']==saved['rules'][0]['applicationId']
    assert saved['rules'][0]['feedback'] is False
    results['ruleFeedbackSaved']=True
    results['pickedApplicationSavesWithName']=True
    snapshot=core('GetConfig')['value'];rule=snapshot['config']['rules'][0];rule['steps'][0].update(action='wait',params={'value':{'mode':'literal','value':{'kind':'number','value':1000}}})
    assert core('CommitConfig',{'requestId':'ui-execution','expectedRevision':snapshot['revision'],'config':snapshot['config']})['status']=='ok'
    wait(lambda:execute('return document.querySelector("#steps")?.textContent.includes("等待");'))
    click('.nav[data-page="test"]');draw('#canvas')
    wait(lambda:execute('return document.querySelector("#test-match").textContent;')=='配置测试')
    assert execute('return document.querySelector("#test-score").textContent;')=='100.0%'
    results['formalRecognitionPage']=True
    assert core('GetRuntime')['value']['recording']=='canvas'
    click('.nav[data-page="rules"]');wait(lambda:core('GetRuntime')['value']['recording'] is None)
    results['recordingModeReleasedOnNavigation']=True
    click('.nav[data-page="test"]');draw('#canvas');wait(lambda:execute('return Boolean(document.querySelector("#preview-matched-action"));'))
    click('#preview-matched-action');wait(lambda:execute('return Boolean(document.querySelector("#window-dialog .window-picker button"));'));click('#window-dialog .window-picker button')
    wait(lambda:execute('return document.querySelector("#main h1").textContent;')=='运行状态')
    wait(lambda:len(core('GetRuntime')['value']['executions'])==1 and core('GetRuntime')['value']['executions'][0]['state']=='succeeded')
    wait(lambda:execute('return Boolean(document.querySelector("#runtime-log [data-execution]"));'))
    click('#runtime-log [data-execution]');assert execute('return document.querySelector("#execution-dialog").open;');capture('dialog-real-execution.png','#execution-dialog');click('#dismiss-execution')
    results['realExecutionFromInspector']=True
    click('.nav[data-page="rules"]')
    results['continuousRuleScroll']=execute('const e=document.querySelector("#editor"),f=e.querySelector(".editor-footer"),before=f.getBoundingClientRect().bottom;e.scrollTop=e.scrollHeight;return {scrollable:e.scrollHeight>e.clientHeight,position:getComputedStyle(f).position,before,after:f.getBoundingClientRect().bottom};')
    assert results['continuousRuleScroll']['scrollable'] and results['continuousRuleScroll']['position']=='sticky'
    assert abs(results['continuousRuleScroll']['before']-results['continuousRuleScroll']['after'])<1
    click('#open-composer');click('#save-as-workflow');wait(lambda:execute('return document.querySelector("#workflow-dialog").open;'))
    capture('dialog-save-action.png','#workflow-dialog')
    click('#cancel-save-workflow');click('#composer-back')
    results['createdDocuments']= {k:len(core('GetConfig')['value']['config'][k]) for k in ['gestures','workflows','rules','snippets']}
    # Copy has independent identities and can be removed without disturbing the original.
    click('.nav[data-page="actions"]');click('[data-copy-workflow]')
    wait(lambda:len(core('GetConfig')['value']['config']['workflows'])==2)
    copied=core('GetConfig')['value']['config']['workflows'];assert copied[0]['steps'][0]['id']!=copied[1]['steps'][0]['id']
    assert copied[1]['outputs'][0]['value']['value']['symbolId']==copied[1]['steps'][1]['output']['id']
    assert copied[1]['outputs'][0]['symbol']['id']!=copied[0]['outputs'][0]['symbol']['id']
    results['copiedReturnReferences']=True
    copy_id=copied[1]['id'];click(f'[data-delete-workflow="{copy_id}"]');click('#accept-confirm')
    wait(lambda:len(core('GetConfig')['value']['config']['workflows'])==1)
    results['copyDelete']=True
    if '--phase-c' in sys.argv:
        click('.nav[data-page="rules"]');click('#open-composer');click('#save-as-workflow');wait(lambda:execute('return document.querySelector("#workflow-dialog").open;'))
        fill('#save-workflow-form input[name="name"]','实际调用测试');click('#save-workflow-form button[type="submit"]')
        wait(lambda:len(core('GetConfig')['value']['config']['workflows'])==2)
        wait(lambda:execute('return !document.querySelector("#workflow-dialog").open;'))
        click('#composer-save');wait(lambda:execute('return Boolean(document.querySelector("#save-rule"));'));click('#save-rule')
        snapshot=wait(lambda:(lambda value:value if value['rules'][0]['steps'][0]['action']=='flow.call' else None)(core('GetConfig')['value']['config']))
        reused=next(w for w in snapshot['workflows'] if w['name']=='实际调用测试');assert snapshot['rules'][0]['steps'][0]['workflowId']==reused['id']
        context=core('GetContext')['value'];id=core('RunRule',{'ruleId':snapshot['rules'][0]['id'],'context':context})['value']['executionId']
        result=wait(lambda:next((e for e in core('GetRuntime')['value']['executions'] if e['id']==id and e['state'] not in ['queued','running']),None));assert result['state']=='succeeded' and result['steps'][0]['summary']=='调用可复用动作' and len(result['steps'])>1,result
        results['saveAsAndExecuteReusableWorkflow']=result
        # Actual native navigation through the single-instance launch path.
        click('.nav[data-page="runtime"]')
        committed=core('GetConfig')['value'];config=committed['config'];rule=config['rules'][0];original_steps=rule['steps']
        rule['steps']=[{'id':'ui-open-page','action':'waystroke.open','enabled':True,'params':{'value':{'mode':'literal','value':{'kind':'text','value':'文本替换'}}},'output':None,'onFailure':'stop','timeoutMs':None,'workflowId':None,'arguments':{},'children':[],'otherwise':[],'loopItem':None,'loopIndex':None}]
        core('CommitConfig',{'requestId':'ui-page-action','expectedRevision':committed['revision'],'config':config})
        id=core('RunRule',{'ruleId':rule['id'],'context':context})['value']['executionId'];result=wait(lambda:next((e for e in core('GetRuntime')['value']['executions'] if e['id']==id and e['state'] not in ['queued','running']),None));assert result['state']=='succeeded',result;results['realWayStrokeOpenAction']=result
        committed=core('GetConfig')['value'];config=committed['config'];config['rules'][0]['steps']=original_steps;core('CommitConfig',{'requestId':'restore-ui-rule','expectedRevision':committed['revision'],'config':config})
        wait(lambda:execute('return document.querySelector(".nav.active").dataset.page;')=='text');results['nativeRequestedPage']=True
    click('.nav[data-page="settings"]');click('#pick-exclusion');assert execute('return document.querySelector("#window-dialog").open;')
    capture('dialog-window.png','#window-dialog');click('#close-window-dialog')
    click('.nav[data-page="runtime"]');click('#reopen-setup')
    capture('dialog-setup.png','#setup-dialog');click('#close-setup')
    execute('document.dispatchEvent(new CustomEvent("waystroke:execution-details",{detail:{name:"配置测试"}}));return true;')
    wait(lambda:execute('return document.querySelector("#execution-dialog").open;'))
    capture('dialog-execution.png','#execution-dialog');click('#dismiss-execution')
    # Native window API and compositor behavior, rather than hiding the HTML frame.
    http('POST',f'/session/{session}/window/rect',{'width':1000,'height':720})
    results['narrow']=execute('return {width:innerWidth,height:innerHeight,frame:document.querySelector(".shell").getBoundingClientRect().width};')
    assert results['narrow']['frame']==results['narrow']['width']
    http('POST',f'/session/{session}/window/rect',{'width':1280,'height':820})
    click('#window-maximize');wait(lambda:execute('return document.querySelector("#window-maximize").getAttribute("aria-label");')=='还原窗口')
    click('#window-maximize');wait(lambda:execute('return document.querySelector("#window-maximize").getAttribute("aria-label");')=='最大化窗口')
    results['maximizeRestore']=True
    before=wait(lambda:next((w['rect'] for w in shell({'action':'snapshot'})['windows'] if w['title']=='WayStroke' and w['rect']['width']==1280),None))
    execute('window.dragEvents=[];document.addEventListener("mousedown",e=>window.dragEvents.push({button:e.button,detail:e.detail,target:e.target.outerHTML?.slice(0,100),x:e.clientX,y:e.clientY}),true);window.addEventListener("unhandledrejection",e=>window.dragEvents.push({error:String(e.reason)}));return true;')
    shell({'action':'activate','title':'WayStroke'});shell({'action':'pointer','x':before['x']+650,'y':before['y']+25});time.sleep(.1)
    shell({'action':'button','button':1,'pressed':True});time.sleep(.2)
    shell({'action':'pointer','x':before['x']+680,'y':before['y']+45});time.sleep(.2);shell({'action':'button','button':1,'pressed':False})
    results['dragEvents']=execute('return window.dragEvents;')
    after=wait(lambda:next((w['rect'] for w in shell({'action':'snapshot'})['windows'] if w['title']=='WayStroke' and (w['rect']['x']!=before['x'] or w['rect']['y']!=before['y'])),None))
    results['drag']={'before':before,'after':after}
    # A second settings process must focus this window, not spawn another one.
    duplicate=subprocess.run([str(REPO/'target/debug/waystroke')],capture_output=True,timeout=5)
    assert duplicate.returncode==0
    assert len([w for w in shell({'action':'snapshot'})['windows'] if w['title']=='WayStroke'])==1
    results['desktopSingleInstance']=True
    click('#window-minimize');time.sleep(.25)
    minimized=next(w for w in shell({'action':'snapshot'})['windows'] if w['title']=='WayStroke')
    results['minimizedSnapshot']=minimized
    assert minimized['minimized']
    subprocess.run([str(REPO/'target/debug/waystroke')],check=True,timeout=5)
    wait(lambda:not next(w for w in shell({'action':'snapshot'})['windows'] if w['title']=='WayStroke')['minimized'])
    results['minimizeReopen']=True
    click('.nav[data-page="rules"]');fill('#rule-name','未保存草稿');click('#window-close')
    assert execute('return document.querySelector("#confirm-dialog").open;')
    capture('dialog-confirm.png','#confirm-dialog')
    click('#cancel-confirm');assert execute('return document.querySelector("#rule-name").value;')=='未保存草稿'
    assert core('GetConfig')['value']['config']['rules'][0]['name']=='配置测试'
    results['dirtyCloseCancel']=True
    click('#window-close');execute('setTimeout(()=>document.querySelector("#accept-confirm").click(),50);return true;')
    wait(lambda:not [w for w in shell({'action':'snapshot'})['windows'] if w['title']=='WayStroke'])
    assert core('GetConfig')['status']=='ok';results['backgroundSurvivesClose']=True
    http('DELETE',f'/session/{session}');session=None
    session=http('POST','/session',{'capabilities':{'alwaysMatch':{'tauri:options':{'application':str(REPO/'target/debug/waystroke')}}}})['sessionId']
    wait(lambda:execute('return Boolean(document.querySelector("#main h1"))'))
    assert execute('return document.querySelector("#rule-name").value;')=='配置测试'
    results['reopenSavedConfiguration']=True
    core('Quit');wait(lambda:execute('return document.querySelector(".environment small").textContent;')=='桌面服务连接中断')
    fill('#rule-name','断连草稿');click('#save-rule')
    wait(lambda:execute('return document.querySelector("#message-dialog").open;'))
    assert execute('return document.querySelector("#rule-name").value;')=='断连草稿'
    results['disconnectRetainsDraft']=True
    capture('dialog-message.png','#message-dialog')
    click('#ack-message');click('#revert-rule');assert execute('return document.querySelector("#rule-name").value;')=='配置测试'
    results['failedSaveCancelRestoresActive']=True
    spawn('core-reconnected',[str(REPO/'target/debug/waystroke-core')]);wait(lambda:core('GetConfig')['status']=='ok')
    wait(lambda:execute('return document.querySelector(".environment small").textContent;')!='桌面服务连接中断')
    results['reconnectSnapshot']=True
    click('.nav[data-page="runtime"]');click('#quit-app')
    wait(lambda:not [w for w in shell({'action':'snapshot'})['windows'] if w['title']=='WayStroke'])
    owned=connection.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','NameHasOwner',GLib.Variant('(s)',('io.github.waystroke.Core',)),GLib.VariantType('(b)'),Gio.DBusCallFlags.NONE,3000,None).unpack()[0]
    assert not owned;results['quitStopsCoreAndDesktop']=True
    results['complete']=True
except Exception as error:
    results['error']=str(error)
    try:results['runtimeOnFailure']=core('GetRuntime')['value']
    except Exception:pass
    try:results['shellOnFailure']=shell({'action':'snapshot'})
    except Exception:pass
    if session:
        try:
            results['uiError']=execute('return [...document.querySelectorAll("dialog[open],#rule-errors,#composer-errors")].map(e=>e.textContent);')
            results['textOnFailure']=execute('return {value:document.querySelector("#try-text")?.value,status:document.querySelector("#expand-status")?.textContent};')
            (root/'failure.png').write_bytes(base64.b64decode(http('GET',f'/session/{session}/screenshot')))
        except Exception:pass
    raise
finally:
    if session:
        try:http('DELETE',f'/session/{session}')
        except Exception:pass
    try:core('Quit')
    except Exception:pass
    for process in reversed(processes):
        if process.poll() is None:os.killpg(process.pid,signal.SIGTERM);process.wait(timeout=5)
    (root/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps(results,ensure_ascii=False,indent=2),flush=True)
