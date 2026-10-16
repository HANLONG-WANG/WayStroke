#!/usr/bin/env python3
"""Native WebKitGTK/Wayland UI check on a disposable GNOME desktop."""
import ast,base64,hashlib,json,os,shutil,signal,socket,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
from gi.repository import Gio,GLib
REPO=Path(__file__).resolve().parents[1]
BINDIR=REPO/('target/release' if '--release' in sys.argv else 'target/debug')
if '--inside' not in sys.argv:
    root=Path(tempfile.mkdtemp(prefix='waystroke-ui-check-'))
    for name in ['runtime','config','data','cache','state']:(root/name).mkdir(mode=0o700)
    # D-Bus activation must use the build under test, not /usr/bin/waystroke-core.
    services=root/'data/dbus-1/services';services.mkdir(parents=True)
    (services/'io.github.waystroke.Core.service').write_text(f'[D-BUS Service]\nName=io.github.waystroke.Core\nExec={BINDIR / "waystroke-core"}\n')
    if '--application-scope' in sys.argv:
        apps=root/'data/applications';apps.mkdir()
        for suffix in ['alpha','beta','unused']:
            (apps/f'io.waystroke.ScopeCheck.{suffix}.desktop').write_text('[Desktop Entry]\nType=Application\nName='+('Unselected Candidate' if suffix=='unused' else 'WayStroke Scope Check')+'\nExec=/usr/bin/true\n')
    ext=root/'data/gnome-shell/extensions/waystroke-probe@local';ext.mkdir(parents=True)
    for name in ['extension.js','metadata.json','terminal-monitor.js']:shutil.copy(REPO/'probes/gnome50'/name,ext/name)
    formal=root/'data/gnome-shell/extensions/waystroke@local';formal.mkdir()
    for name in ['extension.js','metadata.json','clipboard.js','dialogs.js','system.js','text.js','terminal.js']:shutil.copy(REPO/'extension'/name,formal/name)
    helper=ext/'extension.js';helper.write_text(helper.read_text().replace('clientType:a.meta_window.get_client_type()', 'clientType:a.meta_window.get_client_type(),minimized:a.meta_window.minimized').replace('return {panelState:', 'return {startingUp:Main.layoutManager._startingUp,actionMode:Main.actionMode,ibusReady:!!IBusManager.getIBusManager()._panelService,panelState:'))
    if '--shortcut-capture' in sys.argv:
        helper.write_text(helper.read_text().replace('return {startingUp:', 'return {shortcutCaptureOpen:!!Main.extensionManager.lookup("waystroke@local")?.stateObj?.shortcutCapture?.active,captureCancelRect:(()=>{const button=Main.extensionManager.lookup("waystroke@local")?.stateObj?.shortcutCapture?.active?.dialog.buttonLayout.get_children()[0];if(!button)return null;const [x,y]=button.get_transformed_position();return {x,y,width:button.width,height:button.height};})(),startingUp:'))
    if '--ime-shortcuts' in sys.argv:
        # Trace only the shortcut's modifier bits in this disposable extension copy.
        code=formal/'text.js';code.write_text(code.read_text().replace('this.notify=(event,handled)=>{', 'this.notify=(event,handled)=>{if(event.type()===Clutter.EventType.KEY_PRESS&&event.get_key_symbol()===Clutter.KEY_space)console.log("IME_SHORTCUT state="+event.get_state()+" handled="+handled+" snapshot="+!!this.snapshot());'))
    if '--phase-e' in sys.argv:
        # Explicit external-command fixture; the application still invokes its fixed pkexec command.
        # Denial and real unprivileged file installation are tested, never the host service.
        bins=root/'bin';bins.mkdir()
        launcher=bins/'pkexec';launcher.write_text('#!/usr/bin/bash\nset -eu\nprintf \'%s\\n\' "$@" >> "$WAYSTROKE_SETUP_TEST_ROOT/auth-args"\nif [[ ! -e "$WAYSTROKE_SETUP_TEST_ROOT/allow" ]]; then exit 126; fi\nexport PKEXEC_UID=$(id -u)\nexec "$@"\n');launcher.chmod(0o755)
        (root/'installation').mkdir()
    if '--phase-e' in sys.argv:
        # Only the test copy can advertise a deliberately incompatible protocol.
        code=formal/'extension.js';code.write_text(code.read_text().replace('protocolVersion:1,instance:', 'protocolVersion:this._testProtocolVersion??1,instance:'))
        helper.write_text(helper.read_text().replace('  const now=GLib.get_monotonic_time();', "  if(q.action==='protocol-version'){Main.extensionManager.lookup('waystroke@local').stateObj._testProtocolVersion=q.version;return null;}\n  const now=GLib.get_monotonic_time();"))
    env=os.environ.copy();env.update(XDG_RUNTIME_DIR=str(root/'runtime'),XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),XDG_CACHE_HOME=str(root/'cache'),XDG_STATE_HOME=str(root/'state'),GSETTINGS_BACKEND='keyfile',LIBGL_ALWAYS_SOFTWARE='1',GIO_USE_VFS='local',WAYSTROKE_PROBE_DIR=str(root),GDK_BACKEND='wayland',GSK_RENDERER='cairo',WAYLAND_DISPLAY='waystroke-ui-check-0')
    if '--devkit' in sys.argv:
        env['WAYSTROKE_OUTER_RUNTIME']=os.environ['XDG_RUNTIME_DIR'];env['WAYSTROKE_OUTER_DISPLAY']=os.environ.get('WAYLAND_DISPLAY','wayland-0')
        env['PIPEWIRE_RUNTIME_DIR']=os.environ['XDG_RUNTIME_DIR']
        env.pop('LIBGL_ALWAYS_SOFTWARE',None)
        schema=Path('/usr/share/glib-2.0/schemas/org.gnome.mutter.devkit.gschema.xml')
        schemas=root/'schemas';schemas.mkdir();shutil.copy(schema,schemas/schema.name);subprocess.run(['glib-compile-schemas',str(schemas)],check=True);env['GSETTINGS_SCHEMA_DIR']=str(schemas)
    if '--phase-e' in sys.argv:
        env['PATH']=str(root/'bin')+':'+env['PATH'];env['WAYSTROKE_SETUP_TEST_ROOT']=str(root/'installation')
    env['GI_TYPELIB_PATH']=str(REPO/'target/native')+':/usr/lib64/mutter-18'
    env['LD_LIBRARY_PATH']=str(REPO/'target/native')+':/usr/lib64/mutter-18:/usr/lib64/gnome-shell'
    for name in ['DISPLAY','IBUS_ADDRESS','AT_SPI_BUS_ADDRESS']:env.pop(name,None)
    print('Native UI artifacts:',root,flush=True)
    sys.exit(subprocess.run(['dbus-run-session','--',sys.executable,__file__,'--inside',*sys.argv[1:]],env=env).returncode)
root=Path(os.environ['WAYSTROKE_PROBE_DIR']);processes=[];results={'extensionSourceSha256AtStartup':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'data/gnome-shell/extensions/waystroke@local').iterdir() if p.is_file()}}
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
    wait(lambda:core('GetRuntime')['value']['recording']=='canvas')
    wait(lambda:execute(f'return window.strokeEvents.some(e=>e.type==="pointermove"&&Math.abs(e.x-{x})<1&&Math.abs(e.y-{y})<1);'))
    shell({'action':'button','button':3,'pressed':True});wait(lambda:execute('return window.strokeEvents.some(e=>e.type==="pointerdown");'))
    for dx,dy in [(25,10),(50,40),(75,20),(100,70)]:
        shell({'action':'pointer','x':window['x']+x+dx,'y':window['y']+y+dy});time.sleep(.08)
    shell({'action':'button','button':3,'pressed':False});wait(lambda:execute('return window.strokeEvents.some(e=>e.type==="pointerup");'))

def capture(name,dialog=None):
    if dialog:assert execute(f'return document.querySelector({json.dumps(dialog)}).open;')
    time.sleep(.25) # WebKit paint follows the synchronous DOM callback.
    (root/name).write_bytes(base64.b64decode(http('GET',f'/session/{session}/screenshot')))

def click(selector):
    wait(lambda:execute(f'const e=document.querySelector({json.dumps(selector)});if(!e||e.disabled)return false;e.click();return true;'))
try:
    for schema,key,value in [('org.gnome.shell','enabled-extensions',"['waystroke@local','waystroke-probe@local']"),('org.gnome.shell','disable-user-extensions','false'),('org.gnome.desktop.interface','enable-hot-corners','false')]:subprocess.run(['gsettings','set',schema,key,value],check=True)
    if '--ime-shortcuts' in sys.argv or '--shortcut-capture' in sys.argv:
        for schema,key,value in [('org.gnome.desktop.input-sources','sources',"[('xkb', 'us'), ('xkb', 'fr')]"),('org.gnome.desktop.wm.keybindings','switch-input-source',"['<Super>space']"),('org.gnome.desktop.wm.keybindings','switch-input-source-backward',"['<Shift><Super>space']")]:subprocess.run(['gsettings','set',schema,key,value],check=True)
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
    spawn('core',[str(BINDIR/'waystroke-core')]);wait(lambda:core('GetConfig')['status']=='ok')
    snapshot=core('GetConfig')['value'];snapshot['config']['settings']['setupComplete']=True
    assert core('CommitConfig',{'requestId':'fixture-init','expectedRevision':snapshot['revision'],'config':snapshot['config']})['status']=='ok'
    driver=Path(os.environ.get('WAYSTROKE_TAURI_DRIVER',shutil.which('tauri-driver') or '/tmp/waystroke-tools/bin/tauri-driver'))
    spawn('driver',[str(driver),'--port',str(port),'--native-port',str(native_port),'--native-driver','/usr/bin/WebKitWebDriver'])
    wait(lambda:http('GET','/status'))
    session=http('POST','/session',{'capabilities':{'alwaysMatch':{'tauri:options':{'application':str(BINDIR/'waystroke')}}}})['sessionId']
    wait(lambda:execute('return Boolean(document.querySelector("#main h1"))'))
    results['initial']=execute('return {title:document.querySelector("#main h1").textContent,nav:document.querySelectorAll(".nav").length,reviewTools:document.querySelectorAll(".review-tools").length};')
    assert results['initial']['nav']==8 and results['initial']['reviewTools']==0
    if '--shortcut-capture' in sys.argv:
        wait(lambda:shell({'action':'snapshot'})['ibusReady'] and not shell({'action':'snapshot'})['startingUp'])
        shell({'action':'normal'});shell({'action':'activate','title':'WayStroke'})
        click('#new-rule');fill('#rule-name','快捷键捕获测试')
        field='#steps [data-param-key="value"]'
        click(field+' [data-shortcut-mode="manual"]');fill(field+' input','${起点应用}')
        click(field+' [data-shortcut-mode="capture"]');click(field+' [data-shortcut-mode="manual"]')
        assert execute(f'return document.querySelector({json.dumps(field+" input")}).value;')=='${起点应用}'
        click(field+' [data-shortcut-mode="manual"]');fill(field+' input','Ctrl + A')
        click(field+' [data-shortcut-mode="capture"]')
        assert execute(f'return document.querySelector({json.dumps(field+" input")}).value;')=='Ctrl + A'
        def key_event(value,pressed):shell({'action':'key','keyval':value,'pressed':pressed})
        def record(keys,expected,root_selector=field):
            click(root_selector+' .shortcut-capture-button')
            wait(lambda:shell({'action':'snapshot'})['shortcutCaptureOpen'])
            for value in keys:key_event(value,True)
            if expected=='Ctrl + Shift + T':
                key_event(keys[-1],False)
                assert shell({'action':'snapshot'})['shortcutCaptureOpen']
                time.sleep(.15)
                shell({'action':'screenshot','tag':'shortcut-capture-modal'})
                wait(lambda:(root/'shortcut-capture-modal.png').exists() and (root/'shortcut-capture-modal.png').stat().st_size>0)
                keys=keys[:-1]
            for value in reversed(keys):key_event(value,False)
            wait(lambda:not shell({'action':'snapshot'})['shortcutCaptureOpen'])
            wait(lambda:execute(f'return document.querySelector({json.dumps(root_selector+" input")}).value;')==expected)
        record([0xffe3,0xffe1,ord('t')],'Ctrl + Shift + T')
        results['nativeChordCaptured']=True
        shell({'action':'source','id':'us'})
        record([0xffeb,32],'Super + Space')
        assert shell({'action':'snapshot'})['ime']['source']=='us'
        record([0xffe9,0xff09],'Alt + Tab')
        for keys,value in [([0xff1b],'Esc'),([0xff09],'Tab'),([0xff0d],'Enter'),([0xffc2],'F5'),([0xffe3,ord('+')],'Ctrl + Shift + plus')]:record(keys,value)
        results['systemAndStandaloneKeysCaptured']=True
        record([0xffe3,ord('a')],'Ctrl + A')
        click(field+' .shortcut-capture-button');wait(lambda:shell({'action':'snapshot'})['shortcutCaptureOpen'])
        rect=shell({'action':'snapshot'})['captureCancelRect'];shell({'action':'pointer','x':rect['x']+rect['width']/2,'y':rect['y']+rect['height']/2})
        shell({'action':'button','button':1,'pressed':True});shell({'action':'button','button':1,'pressed':False})
        wait(lambda:not shell({'action':'snapshot'})['shortcutCaptureOpen'])
        wait(lambda:execute(f'return document.querySelector({json.dumps(field+" .shortcut-capture-status")}).textContent.includes("已取消");'))
        assert execute(f'return document.querySelector({json.dumps(field+" input")}).value;')=='Ctrl + A'
        results['captureCancelPreservesPreviousValue']=True
        client=spawn('capture-owner',['gdbus','call','--session','--dest','io.github.waystroke.Gnome','--object-path','/io/github/waystroke/Gnome','--method','io.github.waystroke.Gnome1.Call',json.dumps({'operation':'captureShortcut'})])
        wait(lambda:shell({'action':'snapshot'})['shortcutCaptureOpen']);client.terminate();client.wait(timeout=3)
        wait(lambda:not shell({'action':'snapshot'})['shortcutCaptureOpen'])
        for value in [0xffeb,32]:key_event(value,True)
        for value in [32,0xffeb]:key_event(value,False)
        wait(lambda:shell({'action':'snapshot'})['ime']['source']=='fr')
        shell({'action':'source','id':'us'})
        results['ownerExitReleasesCaptureAndSystemShortcutRestored']=True
        execute(f'document.querySelector({json.dumps(field)}).scrollIntoView({{block:"center"}});return true;');capture('shortcut-capture-editor.png')
        click('#open-composer')
        record([0xffe3,ord('a')],'Ctrl + A','#composer-fields [data-param-key="value"]')
        capture('shortcut-capture-composer.png')
        click('#composer-save');wait(lambda:execute('return Boolean(document.querySelector("#record-canvas"));'));draw('#record-canvas');click('#save-rule')
        wait(lambda:len(core('GetConfig')['value']['config']['rules'])==1)
        config=core('GetConfig')['value']['config'];rule=config['rules'][0]
        assert rule['steps'][0]['params']['value']=={'mode':'literal','value':{'kind':'text','value':'Ctrl + A'}}
        click('.nav[data-page="text"]');click('.nav[data-page="rules"]')
        assert execute(f'return document.querySelector({json.dumps(field+" input")}).value;')=='Ctrl + A'
        results['captureSharedWithComposerAndSavedReopened']=True
        click('.nav[data-page="text"]');execute('const e=document.querySelector("#try-text");e.focus();e.value="hello";e.setSelectionRange(5,5);return true;')
        context=core('GetContext')['value'];execution=core('RunRule',{'ruleId':rule['id'],'context':context})['value']['executionId']
        wait(lambda:next((e for e in core('GetRuntime')['value']['executions'] if e['id']==execution and e['state']=='succeeded'),None))
        wait(lambda:execute('const e=document.querySelector("#try-text");return e.selectionStart===0&&e.selectionEnd===5;'))
        results['capturedShortcutActuallySends']=True
        raise SystemExit(0)
    if '--ime-shortcuts' in sys.argv:
        wait(lambda:shell({'action':'snapshot'})['ibusReady'])
        wait(lambda:not shell({'action':'snapshot'})['startingUp'])
        shell({'action':'normal'});shell({'action':'activate','title':'WayStroke'})
        snapshot=core('GetConfig')['value'];config=snapshot['config']
        config['snippets']=[{'id':'shortcut-test','key':'abc','value':'expanded','enabled':True,'applicationId':None,'trigger':'confirm','caseSensitive':True,'boundary':True,'preserve':True}]
        assert core('CommitConfig',{'requestId':'shortcut-fixture','expectedRevision':snapshot['revision'],'config':config})['status']=='ok'
        click('.nav[data-page="text"]')
        def key_event(key,pressed):shell({'action':'key','keyval':key,'pressed':pressed})
        def switch_source(expected,backwards=False):
            if backwards:key_event(0xffe1,True)
            key_event(0xffeb,True);key_event(32,True);key_event(32,False);key_event(0xffeb,False)
            if backwards:key_event(0xffe1,False)
            wait(lambda:shell({'action':'snapshot'})['ime']['source']==expected)
        shell({'action':'source','id':'us'})
        execute('document.querySelector("#clear-text").focus();return true;')
        wait(lambda:not shell({'action':'snapshot'})['ime']['hasFocus'])
        switch_source('fr');switch_source('us',True)
        results['inputSourceShortcutOutsideTextField']=True
        execute('document.querySelector("#try-text").focus();return true;')
        wait(lambda:shell({'action':'snapshot'})['ime']['hasFocus'])
        key_event(ord('x'),True);key_event(ord('x'),False)
        wait(lambda:execute('return document.querySelector("#try-text").value;')=='x')
        switch_source('fr');switch_source('us',True)
        assert execute('return document.querySelector("#try-text").value;')=='x'
        results['inputSourceShortcutsInsideTextFieldPreserveText']=True
        key_event(32,True);key_event(32,False)
        wait(lambda:execute('return document.querySelector("#try-text").value;')=='x ')
        execute('document.querySelector("#snippet-search").focus();return true;')
        wait(lambda:shell({'action':'snapshot'})['ime']['hasFocus'])
        key_event(ord('x'),True);key_event(ord('x'),False)
        wait(lambda:execute('return document.querySelector("#snippet-search").value;')=='x')
        switch_source('fr');switch_source('us',True)
        assert execute('return document.querySelector("#snippet-search").value;')=='x'
        results['inputSourceShortcutsWorkInSingleLineInput']=True
        results['ordinarySpaceStillDelivered']=True
        capture('input-source-shortcuts.png')
        raise SystemExit(0)
    if '--rule-filter' in sys.argv:
        click('#new-rule');fill('#rule-name','全局筛选测试');draw('#record-canvas');click('#save-rule')
        wait(lambda:len(core('GetConfig')['value']['config']['rules'])==1)
        snapshot=core('GetConfig')['value'];config=snapshot['config'];global_id=config['rules'][0]['id']
        config['applications']=[{'id':'filter.app','name':'应用规则测试'},{'id':'org.waystroke.ProbeClient','name':'probe'},{'id':'text.only','name':'文本专属应用'}]
        app_rule=json.loads(json.dumps(config['rules'][0]));app_rule.update(id='filter-app-rule',name='应用筛选测试',applicationId='filter.app')
        app_rule['steps'][0]['id']='filter-app-step';config['rules'].append(app_rule)
        config['snippets'].append({'id':'text-only','key':';text','value':'text','enabled':True,'applicationId':'text.only','trigger':'confirm','caseSensitive':True,'boundary':True,'preserve':True})
        assert core('CommitConfig',{'requestId':'filter-fixture','expectedRevision':snapshot['revision'],'config':config})['status']=='ok'
        wait(lambda:execute('return document.querySelectorAll("#rule-list [data-id]").length;')==2)
        def scope_options():return execute('return [...document.querySelector("#scope").options].map(option=>({value:option.value,label:option.textContent}));')
        def filter_scope(value):
            execute(f'const e=document.querySelector("#scope");e.value={json.dumps(value)};e.dispatchEvent(new Event("change",{{bubbles:true}}));return true;')
            return execute('return [...document.querySelectorAll("#rule-list [data-id]")].map(row=>row.dataset.id);')
        results['gestureScopeOptions']=scope_options()
        assert [option['value'] for option in results['gestureScopeOptions']]==['全部','','filter.app']
        assert [option['label'] for option in results['gestureScopeOptions']][:2]==['全部范围','所有应用']
        assert filter_scope('')==[global_id]
        assert filter_scope('filter.app')==['filter-app-rule']
        assert len(filter_scope('全部'))==2
        filter_scope('filter.app');click('[data-id="filter-app-rule"]');click('#delete-rule');click('#accept-confirm')
        wait(lambda:len(core('GetConfig')['value']['config']['rules'])==1)
        wait(lambda:[option['value'] for option in scope_options()]==['全部',''])
        assert execute('return document.querySelector("#scope").value;')=='全部'
        results['gestureFilterGlobalAllAndApplicationScopesWork']=True
        results['deletingLastApplicationRuleRemovesItsFilter']=True
        capture('scope-rule-filters.png')
        raise SystemExit(0)
    if '--application-scope' in sys.argv:
        alpha='io.waystroke.ScopeCheck.alpha.desktop';beta='io.waystroke.ScopeCheck.beta.desktop'
        assert core('GetConfig')['value']['config']['applications']==[]
        click('.nav[data-page="runtime"]');click('#runtime-text-settings')
        assert execute('return document.querySelector("#main h1").textContent;')=='文本替换'
        results['runtimeTextLinkOpensTextRules']=True
        click('.text-help summary')
        results['textHelpWidth']=execute('const e=document.querySelector(".text-help"),p=e.querySelector("p");return {available:e.clientWidth,paragraph:p.getBoundingClientRect().width};')
        assert abs(results['textHelpWidth']['available']-results['textHelpWidth']['paragraph'])<2
        capture('text-help-full-width.png');click('.text-help summary')
        click('#new-snippet')
        results['snippetSelectAlignment']=execute('const a=document.querySelector("#snippet-scope").getBoundingClientRect(),b=document.querySelector("#snippet-form [name=trigger]").getBoundingClientRect();return {scopeTop:a.top,triggerTop:b.top,scopeHeight:a.height,triggerHeight:b.height};')
        assert abs(results['snippetSelectAlignment']['scopeTop']-results['snippetSelectAlignment']['triggerTop'])<1
        assert results['snippetSelectAlignment']['scopeHeight']==results['snippetSelectAlignment']['triggerHeight']
        capture('snippet-aligned-selects.png','#snippet-dialog')
        click('#snippet-application .choose-application')
        wait(lambda:execute('return document.querySelectorAll("#application-dialog [data-app-index]").length>0;'))
        fill('.application-search','WayStroke Scope Check')
        assert execute('return document.querySelectorAll("#application-dialog [data-app-index]").length;')==2
        capture('scope-installed-same-name.png','#application-dialog')
        execute(f'const buttons=[...document.querySelectorAll("#application-dialog [data-app-index]")];buttons.find(b=>b.textContent.includes({json.dumps(alpha)})).click();return true;')
        assert execute('return [...document.querySelector("#snippet-scope").options].map(option=>option.value);')==['',alpha]
        fill('#snippet-form [name="key"]',';scope');fill('#snippet-form [name="value"]','alpha')
        execute('document.querySelector("#snippet-form").requestSubmit();return true;')
        wait(lambda:len(core('GetConfig')['value']['config']['snippets'])==1)
        for app,value in [(beta,'beta'),('','global')]:
            click('#new-snippet')
            if app:
                click('#snippet-application .choose-application');wait(lambda:execute('return document.querySelectorAll("#application-dialog [data-app-index]").length>0;'))
                fill('.application-search',app);click('#application-dialog [data-app-index]')
            fill('#snippet-form [name="key"]',';scope');fill('#snippet-form [name="value"]',value)
            execute('document.querySelector("#snippet-form").requestSubmit();return true;')
            wait(lambda:not execute('return document.querySelector("#snippet-dialog").open;'))
        config=core('GetConfig')['value']['config'];assert {r['applicationId'] for r in config['snippets']}=={alpha,beta,None}
        first=config['snippets'][0];click(f'[data-edit="{first["id"]}"]')
        assert execute('return document.querySelector("#snippet-scope").value;')==alpha
        click('#cancel-dialog')
        def simulate_text(app,expected):
            execute(f'const select=document.querySelector("#snippet-test-scope");select.value={json.dumps(app)};select.dispatchEvent(new Event("change",{{bubbles:true}}));const e=document.querySelector("#try-text");e.focus();e.value=";scope ";e.setSelectionRange(7,7);e.dispatchEvent(new InputEvent("input",{{inputType:"insertText",data:" ",bubbles:true}}));return true;')
            wait(lambda:execute('return document.querySelector("#try-text").value;')==expected+' ')
        simulate_text(alpha,'alpha');simulate_text(beta,'beta');simulate_text('','global')
        results['sameNameScopesSaveReopenAndMatchById']=True
        click('#new-snippet');click('#snippet-application .choose-application')
        click('.manual-application summary');fill('#manual-application-form [name="applicationId"]','io.waystroke.manual')
        fill('#manual-application-form [name="applicationName"]','Manual Scope')
        execute('document.querySelector("#manual-application-form").requestSubmit();return true;')
        fill('#snippet-form [name="key"]',';scope');fill('#snippet-form [name="value"]','manual')
        execute('document.querySelector("#snippet-form").requestSubmit();return true;')
        wait(lambda:len(core('GetConfig')['value']['config']['snippets'])==4)
        simulate_text('io.waystroke.manual','manual');results['manualScopeSavedAndMatched']=True
        capture('scope-text-test.png')
        click('.nav[data-page="rules"]');click('#new-rule');fill('#rule-name','范围与标题测试')
        click('#rule-application .choose-application')
        wait(lambda:execute('return Boolean(document.querySelector("#application-dialog [data-window-index]"));'))
        click('#application-dialog [data-window-index]')
        assert execute('return document.querySelector("#rule-scope").value;')
        assert execute('return document.querySelector("#rule-title-op").value;')=='不限标题'
        click('#rule-application .choose-application')
        wait(lambda:execute('return Boolean(document.querySelector("#application-dialog [data-window-index]"));'))
        click('#application-use-title');click('#application-dialog [data-window-index]')
        assert execute('return document.querySelector("#rule-title-value").value;')=='WayStroke'
        results['windowApplicationAndExplicitTitleSelection']=True
        execute(f'const e=document.querySelector("#rule-scope");e.value={json.dumps(alpha)};e.dispatchEvent(new Event("change",{{bubbles:true}}));return true;')
        fill('#rule-title-value','Document');draw('#record-canvas');click('#save-rule')
        wait(lambda:len(core('GetConfig')['value']['config']['rules'])==1)
        saved=core('GetConfig')['value']['config']['rules'][0]
        assert saved['applicationId']==alpha and saved['titleMatch']=={'operator':'包含','value':'Document'}
        click('.nav[data-page="text"]');click('.nav[data-page="rules"]')
        assert execute('return document.querySelector("#rule-scope").value;')==alpha
        assert execute('return document.querySelector("#rule-title-value").value;')=='Document'
        execute('document.querySelector("#rule-application").scrollIntoView({block:"center"});return true;');capture('scope-gesture-conditions.png')
        click('.nav[data-page="test"]')
        execute(f'const e=document.querySelector("#test-scope");e.value={json.dumps(alpha)};e.dispatchEvent(new Event("change",{{bubbles:true}}));return true;')
        fill('#test-title','Other');draw('#canvas')
        wait(lambda:execute('return document.querySelector("#test-match").textContent;')=='未匹配到规则')
        fill('#test-title','Document - Editor')
        wait(lambda:execute('return document.querySelector("#test-match").textContent;')=='范围与标题测试')
        execute(f'const e=document.querySelector("#test-scope");e.value={json.dumps(beta)};e.dispatchEvent(new Event("change",{{bubbles:true}}));return true;')
        wait(lambda:execute('return document.querySelector("#test-match").textContent;')=='未匹配到规则')
        results['gestureScopeAndTitlePersistAndMatch']=True
        capture('scope-gesture-test.png')
        original=core('GetConfig')['value']['config']
        def candidates(selector):return execute(f'return [...document.querySelector({json.dumps(selector)}).options].map(option=>option.value);')
        def pick_candidate(root_selector,app_id):
            click(root_selector+' .choose-application')
            wait(lambda:execute('return document.querySelectorAll("#application-dialog [data-app-index]").length>0;'))
            fill('.application-search',app_id);click('#application-dialog [data-app-index]')
        # Gesture simulation and text simulation share the same candidate history.
        click('#test-application .remove-application')
        assert beta not in candidates('#test-scope')
        assert execute('return document.querySelector("#test-scope").value;')==''
        click('.nav[data-page="text"]')
        assert beta not in candidates('#snippet-test-scope')
        pick_candidate('#snippet-test-application',beta)
        assert 'io.waystroke.ScopeCheck.unused.desktop' not in candidates('#snippet-test-scope')
        click('#snippet-test-application .remove-application')
        assert beta not in candidates('#snippet-test-scope')
        click('#new-snippet');assert beta not in candidates('#snippet-scope')
        pick_candidate('#snippet-application',beta);click('#snippet-application .remove-application')
        assert beta not in candidates('#snippet-scope') and beta not in candidates('#snippet-test-scope')
        assert execute('return document.querySelector("#snippet-scope").value;')==''
        results['candidateButtonAlignment']=execute('const root=document.querySelector("#snippet-application"),a=root.querySelector(".choose-application").getBoundingClientRect(),b=root.querySelector(".remove-application").getBoundingClientRect(),r=root.getBoundingClientRect();return {topGap:Math.abs(a.top-b.top),rightGap:Math.abs(r.right-b.right)};')
        assert results['candidateButtonAlignment']['topGap']<1 and results['candidateButtonAlignment']['rightGap']<1
        capture('scope-remove-candidate.png','#snippet-dialog');click('#cancel-dialog')
        click('.nav[data-page="rules"]');pick_candidate('#rule-application',beta)
        click('#rule-application .remove-application');assert beta not in candidates('#rule-scope')
        assert execute('return document.querySelector("#rule-scope").value;')==''
        click('#revert-rule');assert execute('return document.querySelector("#rule-scope").value;')==alpha
        assert core('GetConfig')['value']['config']==original
        # Reopen the actual WebView to verify the deletion survives application close.
        click('#window-close')
        wait(lambda:not [w for w in shell({'action':'snapshot'})['windows'] if w['title']=='WayStroke'])
        http('DELETE',f'/session/{session}');session=None
        session=http('POST','/session',{'capabilities':{'alwaysMatch':{'tauri:options':{'application':str(BINDIR/'waystroke')}}}})['sessionId']
        wait(lambda:execute('return Boolean(document.querySelector("#main h1"))'))
        click('.nav[data-page="text"]');assert beta not in candidates('#snippet-test-scope')
        # A hidden candidate must never erase an existing rule's condition.
        snippet=next(rule for rule in original['snippets'] if rule['applicationId']==beta)
        click(f'[data-edit="{snippet["id"]}"]')
        assert execute('return document.querySelector("#snippet-scope").value;')==beta
        click('#cancel-dialog');assert core('GetConfig')['value']['config']==original
        pick_candidate('#snippet-test-application',beta)
        assert beta in candidates('#snippet-test-scope')
        capture('scope-candidate-restored.png')
        results['catalogDoesNotPolluteDropdownCandidates']=True
        results['candidateRemovalWorksAcrossAllFourControls']=True
        results['candidateRemovalPersistsWithoutChangingRules']=True
        results['explicitSelectionRestoresHiddenCandidate']=True
        raise SystemExit(0)
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
    if '--phase-e' in sys.argv:
        assert '--devkit' in sys.argv, 'Phase E extension/UI checks require mutter-devkit'
        # Re-enable the actual private extension through the setup button.
        connection.call_sync('org.gnome.Shell.Extensions','/org/gnome/Shell/Extensions','org.gnome.Shell.Extensions','DisableExtension',GLib.Variant('(s)',('waystroke@local',)),GLib.VariantType('(b)'),Gio.DBusCallFlags.NONE,3000,None)
        wait(lambda:not core('GetRuntime')['value']['status']['extensionConnected'])
        click('.nav[data-page="runtime"]');click('#reopen-setup');click('#setup-connect')
        wait(lambda:core('GetRuntime')['value']['status']['extensionConnected'])
        wait(lambda:execute('return document.querySelector("#setup-connect").textContent;')=='已连接')
        results['setupEnablesActualExtension']=True
        click('#close-setup');click('#runtime-reconnect')
        assert execute('return document.querySelector("#setup-dialog").open&&Boolean(document.querySelector("#setup-permission"));')
        click('#setup-permission')
        wait(lambda:execute('return document.querySelector("#setup-result").textContent.includes("取消");'))
        assert not execute('return document.querySelector("#setup-permission").disabled;')
        installation=root/'installation';assert not (installation/'etc/waystroke/inputd.conf').exists()
        results['setupAuthorizationDenialRetryable']=True;capture('setup-authorization-canceled.png','#setup-dialog')
        (installation/'allow').touch();click('#setup-permission')
        wait(lambda:(installation/'etc/waystroke/inputd.conf').exists())
        wait(lambda:execute('return document.querySelector("#setup-result").textContent.includes("已安装");'))
        assert (installation/'usr/local/libexec/waystroke-inputd').read_bytes()==(BINDIR/'waystroke-inputd').read_bytes()
        assert (installation/'etc/waystroke/inputd.conf').read_text()==f'WAYSTROKE_INPUT_UID={os.getuid()}\n'
        assert (installation/'etc/waystroke/inputd.conf').stat().st_mode&0o777==0o600
        assert (installation/'etc/systemd/system/waystroke-inputd.service').read_bytes()==(REPO/'packaging/systemd/waystroke-inputd.service').read_bytes().replace(b'/usr/bin/waystroke-inputd',b'/usr/local/libexec/waystroke-inputd')
        assert not core('GetRuntime')['value']['inputArmed'] and not core('GetRuntime')['value']['status']['inputConnected']
        assert execute('return document.querySelector("#setup-permission").textContent;')=='安装并授权'
        args=(installation/'auth-args').read_text().splitlines();assert len(args)==4 and args[0]==args[2]=='/usr/bin/bash' and all(args[index].endswith('/install.sh') for index in [1,3])
        results['setupInstallsRealStagedFilesWithoutClaimingConnection']=True
        click('#close-setup')
        click('.nav[data-page="configuration"]')
        wait(lambda:execute('return document.querySelector("#backup-list").textContent.includes("暂无本地备份");'))
        capture('configuration-empty.png')
        source=core('GetConfig')['value']['config']
        source['snippets']=[{'id':'e-snippet','key':';phase-e','value':'migration content','enabled':True,'applicationId':None,'trigger':'confirm','caseSensitive':False,'boundary':True,'preserve':True}]
        def text_binding(value):return {'mode':'literal','value':{'kind':'text','value':value}}
        base_step={'enabled':True,'output':None,'onFailure':'stop','timeoutMs':None,'workflowId':None,'arguments':{},'children':[],'otherwise':[],'loopItem':None,'loopIndex':None}
        source['gestures']=[{'id':'e-gesture','name':'导入轨迹','mainSampleId':'e-sample','samples':[{'id':'e-sample','points':[[0,0],[50,0],[50,80]]}]}]
        source['workflows']=[{'id':'e-workflow','name':'导入动作','description':'实际文件效果','inputs':[],'outputs':[],'steps':[dict(base_step,id='e-write',action='file.write',params={key:text_binding(value) for key,value in {'value':str(root/'import-effect.txt'),'content':'imported workflow','mode':'覆盖','encoding':'UTF-8'}.items()})]}]
        source['rules']=[{'id':'e-rule','name':'导入规则','enabled':True,'feedback':False,'gestureId':'e-gesture','auxiliaryButtons':[],'applicationId':None,'titleMatch':{'operator':'包含','value':''},'steps':[dict(base_step,id='e-call',action='flow.call',params={},workflowId='e-workflow')]}]
        (root/'import.json').write_text(json.dumps(source,ensure_ascii=False))
        def select_import(path):
            content=path.read_text()
            execute(f'const input=document.querySelector("#import-file"),transfer=new DataTransfer();transfer.items.add(new File([{json.dumps(content)}],{json.dumps(path.name)},{{type:"application/json"}}));input.files=transfer.files;input.dispatchEvent(new Event("change",{{bubbles:true}}));return true;')
        select_import(root/'import.json')
        wait(lambda:execute('return !document.querySelector("#apply-import").disabled;'))
        assert core('GetConfig')['value']['config']['snippets']==[]
        capture('configuration-inspected.png')
        click('#apply-import');capture('configuration-confirm.png','#confirm-dialog');click('#cancel-confirm')
        assert core('GetConfig')['value']['config']['snippets']==[]
        click('#apply-import');click('#accept-confirm')
        wait(lambda:len(core('GetConfig')['value']['config']['snippets'])==1)
        wait(lambda:execute('return document.querySelectorAll("[data-restore-backup]").length;')==1)
        imported=core('GetConfig')['value'];assert imported['config']['snippets'][0]['value']=='migration content'
        backups=core('Configuration',{'operation':'list_backups'})['value'];assert len(backups)==1
        results['configurationImportConfirmAndAutomaticBackup']=True
        assert core('TestTextRule',{'applicationId':'test.editor','beforeCursor':';phase-e','trigger':'space','composing':False,'password':False,'terminal':False})['value']['replacement']=='migration content'
        execution_id=core('RunRule',{'ruleId':imported['config']['rules'][0]['id'],'context':core('GetContext')['value']})['value']['executionId']
        executed=wait(lambda:next((e for e in core('GetRuntime')['value']['executions'] if e['id']==execution_id and e['state'] not in ['queued','running']),None))
        assert executed['state']=='succeeded',executed
        assert (root/'import-effect.txt').read_text()=='imported workflow'
        results['importedRulesWorkflowsAndTextActuallyApply']=True

        # Re-import changed text by merge: the installed same-key entry wins.
        source['snippets'][0]['value']='must not replace existing'
        (root/'merge.json').write_text(json.dumps(source));select_import(root/'merge.json')
        wait(lambda:execute('return !document.querySelector("#apply-import").disabled;'))
        assert execute('return document.querySelector("#import-summary").textContent.includes("跳过 1 条已有文本");')
        click('#apply-import');click('#accept-confirm');wait(lambda:core('GetConfig')['value']['revision']==imported['revision']+1)
        assert core('GetConfig')['value']['config']['snippets'][0]['value']=='migration content'
        results['configurationMergeKeepsExistingText']=True
        merged=core('GetConfig')['value']['config'];assert len(merged['rules'])==2 and not merged['rules'][1]['enabled']
        assert merged['rules'][1]['steps'][0]['workflowId']==merged['workflows'][1]['id'] and merged['workflows'][0]['id']!=merged['workflows'][1]['id']
        assert merged['rules'][1]['gestureId']==merged['gestures'][1]['id'] and merged['gestures'][0]['id']!=merged['gestures'][1]['id']
        results['conflictingImportsCopyAndRemapAndDisableRules']=True

        # Restore the original empty document using the actual backup row.
        backup_id=backups[0]['id'];click(f'[data-restore-backup="{backup_id}"]');click('#accept-confirm')
        wait(lambda:core('GetConfig')['value']['config']['snippets']==[])
        wait(lambda:execute('return document.querySelectorAll("[data-restore-backup]").length;')==3)
        results['configurationRestoreActuallyApplies']=True
        core('RuntimeControl',{'operation':'clearLog'})
        click('#manual-backup');wait(lambda:execute('return document.querySelectorAll("[data-restore-backup]").length;')==4)
        delete_id=core('Configuration',{'operation':'list_backups'})['value'][0]['id']
        click(f'[data-delete-backup="{delete_id}"]');click('#accept-confirm')
        wait(lambda:execute('return document.querySelectorAll("[data-restore-backup]").length;')==3)
        results['configurationManualAndDelete']=True
        invalid=dict(source,schemaVersion=900);(root/'invalid.json').write_text(json.dumps(invalid));before=core('GetConfig')['value']
        select_import(root/'invalid.json');wait(lambda:execute('return document.querySelector("#import-error").textContent;'))
        assert execute('return document.querySelector("#apply-import").disabled;')
        assert core('GetConfig')['value']==before;capture('configuration-invalid.png')
        results['configurationInvalidFilePreservesActive']=True
        # The export command returns portable JSON; native save dialog is verified below.
        content=core('Configuration',{'operation':'export_config'})['value']['content'];expected=json.loads(json.dumps(before['config']));expected['settings'].update(setupComplete=False);assert json.loads(content)==expected
        diagnostics=core('ExportDiagnostics')['value']['content'];report=json.loads(diagnostics)
        assert report['format']=='waystroke-diagnostics' and len(report['capabilities']['value'])==69
        assert 'migration content' not in diagnostics and 'must not replace existing' not in diagnostics
        results['diagnosticsAllowlist']=True
        # Real save chooser cancellation must leave configuration and backups intact.
        click('#export-config')
        chooser=wait(lambda:[w for w in shell({'action':'snapshot'})['windows'] if w['title']=='保存 WayStroke 文件'])
        shell({'action':'normal'});wait(lambda:not shell({'action':'snapshot'})['overview'])
        shell({'action':'activate','title':'保存 WayStroke 文件'});wait(lambda:shell({'action':'snapshot'})['focus']=='保存 WayStroke 文件')
        shell({'action':'key','keyval':0xff1b,'pressed':True});shell({'action':'key','keyval':0xff1b,'pressed':False})
        wait(lambda:not [w for w in shell({'action':'snapshot'})['windows'] if w['title']=='保存 WayStroke 文件'])
        assert core('GetConfig')['value']==before
        results['nativeSaveDialogCancel']=True
        def native_export(selector,filename):
            destination=root/filename;click(selector)
            wait(lambda:any(w['title']=='保存 WayStroke 文件' for w in shell({'action':'snapshot'})['windows']))
            shell({'action':'activate','title':'保存 WayStroke 文件'});wait(lambda:shell({'action':'snapshot'})['focus']=='保存 WayStroke 文件')
            def key(value):
                shell({'action':'key','keyval':value,'pressed':True});shell({'action':'key','keyval':value,'pressed':False})
            shell({'action':'key','keyval':0xffe3,'pressed':True});key(ord('l'));shell({'action':'key','keyval':0xffe3,'pressed':False})
            time.sleep(.15)
            shell({'action':'key','keyval':0xffe3,'pressed':True});key(ord('a'));shell({'action':'key','keyval':0xffe3,'pressed':False})
            for char in str(destination):key(ord(char));time.sleep(.015)
            time.sleep(.2)
            key(0xff0d);shell({'action':'screenshot','tag':'save-'+filename});wait(destination.exists)
            wait(lambda:not any(w['title']=='保存 WayStroke 文件' for w in shell({'action':'snapshot'})['windows']))
            return json.loads(destination.read_text())
        assert native_export('#export-config','export-config.json')==expected
        backup_id=core('Configuration',{'operation':'list_backups'})['value'][0]['id']
        expected_backup=json.loads(core('Configuration',{'operation':'export_backup','id':backup_id})['value']['content'])
        assert native_export(f'[data-export-backup="{backup_id}"]','export-backup.json')==expected_backup
        click('.nav[data-page="runtime"]')
        report=native_export('#copy-diagnostics','export-diagnostics.json');assert report['format']=='waystroke-diagnostics'
        results['nativeConfigBackupDiagnosticsExports']=True
        shell({'action':'protocol-version','version':99})
        wait(lambda:core('GetRuntime')['value']['status']['reason']=='桌面扩展版本不兼容')
        wait(lambda:execute('return document.querySelector(".runtime-overview p").textContent;')=='桌面扩展版本不兼容')
        assert not core('GetRuntime')['value']['status']['executionAvailable']
        wait(lambda:execute('return document.querySelector(".runtime-components").textContent.includes("当前 0 项可用");'))
        capture('runtime-incompatible.png')
        shell({'action':'protocol-version','version':1});wait(lambda:core('GetRuntime')['value']['status']['extensionConnected'])
        wait(lambda:execute('return document.querySelector(".runtime-overview p").textContent;')!='桌面扩展版本不兼容')
        results['incompatibleExtensionShowsActualReasonAndRecovers']=True


    assert len(core('GetActionCapabilities')['value'])==69;results['actionCapabilityRegistry']=True
    windows=wait(lambda:[w for w in shell({'action':'snapshot'})['windows'] if w['title']=='WayStroke'])
    assert all(w['clientType']==0 for w in windows);results['nativeWindows']=windows
    for page in ['rules','gestures','actions','text','test','runtime','configuration','settings']:
        click(f'.nav[data-page="{page}"]')
        results[page]=execute('return {heading:document.querySelector("#main h1").textContent,active:document.querySelectorAll(".nav.active").length};')
        results[page]['metrics']=execute('const shell=document.querySelector(".shell").getBoundingClientRect();return Object.fromEntries([".sidebar",".appbar","#main",".page-heading",".settings-page",".runtime-grid",".rule-layout","#setting-mouse","#mouse-access-settings",".setting-row",".desktop-state-banner"].map(selector=>{const e=document.querySelector(selector);if(!e)return [selector,null];const r=e.getBoundingClientRect(),s=getComputedStyle(e);return [selector,{x:r.x-shell.x,y:r.y-shell.y,width:r.width,height:r.height,fontSize:s.fontSize,lineHeight:s.lineHeight,padding:s.padding,gap:s.gap}];}));')
        assert results[page]['active']==1
        capture(page+'.png')
    click('#setting-feedback');wait(lambda:core('GetConfig')['value']['config']['settings']['feedback']==False)
    results['settingSaved']=True
    if '--phase-e' in sys.argv:
        login_entry=Path(os.environ['XDG_CONFIG_HOME'])/'autostart/waystroke.desktop'
        assert login_entry.exists();subprocess.run(['desktop-file-validate',str(login_entry)],check=True)
        click('#setting-autostart');wait(lambda:not login_entry.exists())
        click('#setting-autostart');wait(login_entry.exists)
        assert str(BINDIR/'waystroke-core') in login_entry.read_text()
        results['autostartPreferenceCreatesAndRemovesRealEntry']=True

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
    click('#composer-save');wait(lambda:any(step['action']=='clipboard.read' for workflow in core('GetConfig')['value']['config']['workflows'] for step in workflow['steps']))
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
    click('#rule-application .choose-application');wait(lambda:execute('return Boolean(document.querySelector("#application-dialog [data-window-index]"));'));click('#application-dialog [data-window-index]')
    click('#rule-feedback');click('#save-rule');wait(lambda:len(core('GetConfig')['value']['config']['rules'])==1)
    saved=core('GetConfig')['value']['config'];assert saved['rules'][0]['applicationId'];assert any(app['id']==saved['rules'][0]['applicationId'] and app['name'] for app in saved['applications'])
    assert saved['rules'][0]['feedback'] is False
    results['ruleFeedbackSaved']=True
    results['pickedApplicationSavesWithName']=True
    snapshot=core('GetConfig')['value'];rule=snapshot['config']['rules'][0];rule['steps'][0].update(action='wait',params={'value':{'mode':'literal','value':{'kind':'number','value':1000}}})
    assert core('CommitConfig',{'requestId':'ui-execution','expectedRevision':snapshot['revision'],'config':snapshot['config']})['status']=='ok'
    wait(lambda:execute('return document.querySelector("#steps")?.textContent.includes("等待");'))
    click('.nav[data-page="test"]');execute(f'const e=document.querySelector("#test-scope");e.value={json.dumps(saved["applications"][0]["id"])};e.dispatchEvent(new Event("change",{{bubbles:true}}));return true;');draw('#canvas')
    wait(lambda:execute('return document.querySelector("#test-match").textContent;')=='配置测试')
    assert execute('return document.querySelector("#test-score").textContent;')=='100.0%'
    results['formalRecognitionPage']=True
    assert core('GetRuntime')['value']['recording']=='canvas'
    click('.nav[data-page="rules"]');wait(lambda:core('GetRuntime')['value']['recording'] is None)
    results['recordingModeReleasedOnNavigation']=True
    click('.nav[data-page="test"]');execute(f'const e=document.querySelector("#test-scope");e.value={json.dumps(saved["applications"][0]["id"])};e.dispatchEvent(new Event("change",{{bubbles:true}}));return true;');draw('#canvas');wait(lambda:execute('return Boolean(document.querySelector("#preview-matched-action"));'))
    results['inspectorActionGap']=execute('return document.querySelector("#preview-matched-action").getBoundingClientRect().top-document.querySelector("#test-candidates").getBoundingClientRect().bottom;')
    assert results['inspectorActionGap']>=20
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
    click('#runtime-log [data-execution]')
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
    http('POST',f'/session/{session}/window/rect',{'width':1000,'height':720})
    before=wait(lambda:next((w['rect'] for w in shell({'action':'snapshot'})['windows'] if w['title']=='WayStroke' and w['rect']['width']==1000),None))
    wait(lambda:execute('return innerWidth===1000&&innerHeight===720;'))
    execute('window.dragEvents=[];window.dragPointer=null;document.addEventListener("pointermove",e=>window.dragPointer={x:e.clientX,y:e.clientY,target:e.target.hasAttribute("data-tauri-drag-region")},true);document.addEventListener("mousedown",e=>window.dragEvents.push({button:e.button,detail:e.detail,target:e.target.outerHTML?.slice(0,100),x:e.clientX,y:e.clientY}),true);window.addEventListener("unhandledrejection",e=>window.dragEvents.push({error:String(e.reason)}));return true;')
    shell({'action':'activate','title':'WayStroke'});wait(lambda:shell({'action':'snapshot'}).get('focus')=='WayStroke')
    shell({'action':'pointer','x':before['x']+450,'y':before['y']+25})
    # Restore animations transform pointer coordinates; require the actual draggable hit target.
    # The assertion below measures the resulting compositor window movement.
    wait(lambda:execute('return window.dragPointer?.target;'))
    shell({'action':'button','button':1,'pressed':True});time.sleep(.2)
    shell({'action':'pointer','x':before['x']+480,'y':before['y']+45});time.sleep(.2);shell({'action':'button','button':1,'pressed':False})
    results['dragEvents']=execute('return window.dragEvents;')
    after=wait(lambda:next((w['rect'] for w in shell({'action':'snapshot'})['windows'] if w['title']=='WayStroke' and (w['rect']['x']!=before['x'] or w['rect']['y']!=before['y'])),None))
    results['drag']={'before':before,'after':after}
    # A second settings process must focus this window, not spawn another one.
    duplicate=subprocess.run([str(BINDIR/'waystroke')],capture_output=True,timeout=5)
    assert duplicate.returncode==0
    assert len([w for w in shell({'action':'snapshot'})['windows'] if w['title']=='WayStroke'])==1
    results['desktopSingleInstance']=True
    click('#window-minimize');time.sleep(.25)
    minimized=next(w for w in shell({'action':'snapshot'})['windows'] if w['title']=='WayStroke')
    results['minimizedSnapshot']=minimized
    assert minimized['minimized']
    subprocess.run([str(BINDIR/'waystroke')],check=True,timeout=5)
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
    session=http('POST','/session',{'capabilities':{'alwaysMatch':{'tauri:options':{'application':str(BINDIR/'waystroke')}}}})['sessionId']
    wait(lambda:execute('return Boolean(document.querySelector("#main h1"))'))
    assert execute('return document.querySelector("#rule-name").value;')=='配置测试'
    results['reopenSavedConfiguration']=True
    if '--phase-e' in sys.argv:backups_before_restart=core('Configuration',{'operation':'list_backups'})['value']
    core('Quit');wait(lambda:execute('return document.querySelector(".environment small").textContent;')=='桌面服务连接中断')
    fill('#rule-name','断连草稿');click('#save-rule')
    wait(lambda:execute('return document.querySelector("#message-dialog").open;'))
    assert execute('return document.querySelector("#rule-name").value;')=='断连草稿'
    results['disconnectRetainsDraft']=True
    capture('dialog-message.png','#message-dialog')
    click('#ack-message');click('#revert-rule');assert execute('return document.querySelector("#rule-name").value;')=='配置测试'
    results['failedSaveCancelRestoresActive']=True
    if '--phase-e' in sys.argv:
        subprocess.run(['gio','launch',str(login_entry)],check=True)
    else:spawn('core-reconnected',[str(BINDIR/'waystroke-core')])
    wait(lambda:core('GetConfig')['status']=='ok')
    wait(lambda:execute('return document.querySelector(".environment small").textContent;')!='桌面服务连接中断')
    results['reconnectSnapshot']=True
    if '--phase-e' in sys.argv:
        assert core('Configuration',{'operation':'list_backups'})['value']==backups_before_restart
        click('.nav[data-page="configuration"]');wait(lambda:execute('return document.querySelectorAll("[data-restore-backup]").length;')==len(backups_before_restart))
        results['backupListSurvivesCoreAndUIRestart']=True
    if '--phase-e' in sys.argv:
        # Exercise a genuinely unknown extension: install files, report GNOME's relogin boundary.
        connection.call_sync('org.gnome.Shell.Extensions','/org/gnome/Shell/Extensions','org.gnome.Shell.Extensions','UninstallExtension',GLib.Variant('(s)',('waystroke@local',)),GLib.VariantType('(b)'),Gio.DBusCallFlags.NONE,3000,None)
        wait(lambda:not core('GetRuntime')['value']['status']['extensionConnected'])
        click('.nav[data-page="runtime"]');click('#reopen-setup');click('#setup-connect')
        wait(lambda:execute('return document.querySelector("#setup-result").textContent.includes("重新登录");'))
        assert not core('GetRuntime')['value']['status']['extensionConnected']
        for name in ['metadata.json','extension.js','clipboard.js','dialogs.js','system.js','text.js','terminal.js']:
            assert (root/'data/gnome-shell/extensions/waystroke@local'/name).read_bytes()==(REPO/'extension'/name).read_bytes()
        capture('setup-first-install.png','#setup-dialog');results['setupFirstInstallWritesCurrentFilesAndRequiresRelogin']=True
        click('#close-setup')
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
            results['dragOnFailure']=execute('return {pointer:window.dragPointer,events:window.dragEvents,focus:document.hasFocus(),pixelRatio:devicePixelRatio,viewport:[innerWidth,innerHeight],target:document.elementFromPoint(450,25)?.outerHTML};')
            results['gestureOnFailure']=execute('return Object.fromEntries(["#test-scope","#test-title","#test-match","#test-reason","#test-score","#test-path"].map(selector=>{const e=document.querySelector(selector);return [selector,e?.value??e?.textContent];}));')
            shell({'action':'screenshot','tag':'failure-desktop'})
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
