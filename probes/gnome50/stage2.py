"""Window binding and application text compatibility in a disposable GNOME session."""
import os,sys,json,time,tempfile,subprocess,shutil,signal,ast,threading,shlex
from pathlib import Path
from gi.repository import GLib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
source=Path(__file__).resolve().parent
if '--inside' not in sys.argv:
 root=Path(tempfile.mkdtemp(prefix='waystroke-stage2-'))
 for name in ['runtime','config','data','cache']:(root/name).mkdir(mode=0o700)
 # Ptyxis systemd-run connects to the user's fixed runtime bus, independently of
 # the private DBUS_SESSION_BUS_ADDRESS used by the test compositor.
 if any(c.startswith('terminal') for c in os.environ.get('WAYSTROKE_STAGE2_CASES','firefox,terminal,code').split(',')):
  (root/'runtime/bus').symlink_to(Path(os.environ['XDG_RUNTIME_DIR'])/'bus')
  (root/'runtime/systemd').symlink_to(Path(os.environ['XDG_RUNTIME_DIR'])/'systemd')
 ext=root/'data/gnome-shell/extensions/waystroke-probe@local';ext.mkdir(parents=True)
 for name in ['extension.js','metadata.json','terminal-monitor.js']:shutil.copy(source/name,ext/name)
 config=root/'bus.conf';config.write_text('<busconfig><type>session</type><listen>unix:tmpdir='+str(root/'runtime')+'</listen><auth>EXTERNAL</auth><policy context="default"><allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/></policy></busconfig>')
 env=os.environ.copy();env.update(XDG_RUNTIME_DIR=str(root/'runtime'),XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),XDG_CACHE_HOME=str(root/'cache'),GSETTINGS_BACKEND='keyfile',LIBGL_ALWAYS_SOFTWARE='1',GIO_USE_VFS='local',WAYSTROKE_PROBE_DIR=str(root),GDK_BACKEND='wayland',GSK_RENDERER='cairo',WAYLAND_DISPLAY='waystroke-probe-0')
 env.pop('DISPLAY',None);env.pop('IBUS_ADDRESS',None);env.pop('AT_SPI_BUS_ADDRESS',None)
 print('Probe artifacts:',root,flush=True)
 result=subprocess.run(['dbus-run-session','--config-file='+str(config),'--',sys.executable,str(source/'stage2.py'),'--inside'],env=env,timeout=220)
 sys.exit(result.returncode)
root=Path(os.environ['WAYSTROKE_PROBE_DIR']);cases=set(os.environ.get('WAYSTROKE_STAGE2_CASES','firefox,terminal,code').split(','));results={};processes=[];browser_state={};focus_field='normal'
def spawn(name,args,env=None):
 log=(root/(name+'.log')).open('w');p=subprocess.Popen(args,stdout=log,stderr=log,start_new_session=True,env=env);processes.append(p);return p
def call(q):
 output=subprocess.check_output(['gdbus','call','--session','--dest','org.gnome.Shell','--object-path','/org/waystroke/Probe','--method','org.waystroke.Probe.Call',GLib.Variant('s',json.dumps(q)).print_(True)],text=True,stderr=subprocess.DEVNULL,timeout=3)
 result=json.loads(ast.literal_eval(output)[0])
 if 'error' in result:raise RuntimeError(result['error'])
 return result
def wait_for(fn,timeout=12):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  try:
   value=fn()
   if value:return value
  except (OSError,RuntimeError,subprocess.CalledProcessError):pass
  time.sleep(.1)
 raise RuntimeError('Timed out waiting for probe condition')
def type_text(text):
 for c in text:
  for press in [True,False]:call({'action':'key','keyval':ord(c),'pressed':press});time.sleep(.025)
 time.sleep(.3)
def input_state():return call({'action':'snapshot'})['ime']
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  self.send_response(200);self.send_header('Content-Type','application/json' if self.path=='/focus' else 'text/html');self.end_headers()
  self.wfile.write(json.dumps({'field':focus_field}).encode() if self.path=='/focus' else (source/'browser-fixture.html').read_bytes())
 def do_POST(self):
  global browser_state
  browser_state=json.loads(self.rfile.read(int(self.headers['Content-Length'])));self.send_response(204);self.end_headers()
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
try:
 for schema,key,value in [('org.gnome.shell','enabled-extensions',"['waystroke-probe@local']"),('org.gnome.shell','disable-user-extensions','false'),('org.gnome.desktop.interface','enable-hot-corners','false'),('org.gnome.desktop.input-sources','sources',"[('xkb', 'us'), ('xkb', 'fr'), ('ibus', 'rime')]")]:subprocess.run(['gsettings','set',schema,key,value],check=True)
 if any(c.startswith('a11y') for c in cases):
  spawn('a11y-bus',['/usr/libexec/at-spi-bus-launcher','--launch-immediately','--a11y=1','--screen-reader=1'])
  address=wait_for(lambda:subprocess.check_output(['gdbus','call','--session','--dest','org.a11y.Bus','--object-path','/org/a11y/bus','--method','org.a11y.Bus.GetAddress'],text=True,stderr=subprocess.DEVNULL))
  os.environ['AT_SPI_BUS_ADDRESS']=ast.literal_eval(address)[0]
  
  os.environ['GTK_A11Y']='atspi'
 spawn('ibus',['ibus-daemon','--single','--panel=disable','--config=disable','--emoji-extension=disable']);time.sleep(.5)
 spawn('shell',['gnome-shell','--headless','--wayland','--wayland-display=waystroke-probe-0','--virtual-monitor=1280x800']+([] if 'xwayland' in cases or 'a11y-x' in cases or 'a11y-auto' in cases or 'a11y-ime' in cases or 'a11y-enter' in cases or ('a11y-accelerator' in cases and os.environ.get('WAYSTROKE_A11Y_BACKEND')!='wayland') else ['--no-x11']))
 wait_for(lambda:call({'action':'snapshot'}))
 if any(c.startswith('a11y') for c in cases):
  registry_env=os.environ.copy();snapshot=call({'action':'snapshot'})
  if snapshot['xDisplay']:registry_env.update(DISPLAY=snapshot['xDisplay'],XAUTHORITY=snapshot['xAuthority'])
  spawn('a11y-registry',['/usr/libexec/at-spi2-registryd'],registry_env);time.sleep(.4)
 spawn('gtk',[sys.executable,str(source/'client.py')]);wait_for(lambda:(root/'client.json').exists());call({'action':'normal'});time.sleep(.6)
 for title,x in [('Probe A',80),('Probe B',700)]:call({'action':'position','title':title,'x':x,'y':180,'focus':title=='Probe B'})
 call({'action':'pointer','x':200,'y':300});time.sleep(.2);results['startBound']=call({'action':'bind-start'})
 call({'action':'pointer','x':850,'y':360});time.sleep(.2);results['afterCrossing']=call({'action':'bound'});call({'action':'close-bound'});time.sleep(.4);results['afterTargetClosed']=call({'action':'bound'})
 if 'firefox' in cases:
  profile=root/'firefox-profile';profile.mkdir();(profile/'user.js').write_text('user_pref("datareporting.policy.firstRunURL","");\nuser_pref("browser.shell.checkDefaultBrowser",false);\nuser_pref("browser.aboutwelcome.enabled",false);\nuser_pref("browser.startup.homepage_override.mstone","ignore");\n')
  spawn('firefox',['firefox','--no-remote','--profile',str(profile),f'http://127.0.0.1:{server.server_port}/'])
  wait_for(lambda:browser_state.get('active')=='normal',25);call({'action':'activate','title':'WayStroke compatibility fixture'});time.sleep(.4)
  results['firefoxBefore']=input_state();type_text('abc ');results['firefoxTyped']=dict(browser_state);results['firefoxSurrounding']=input_state()
  call({'action':'replace','offset':-4,'count':4,'text':'2003 '});time.sleep(.5);results['firefoxReplaced']=dict(browser_state)
  call({'action':'ime'});time.sleep(1);type_text('nihao');results['firefoxPreedit']=input_state();results['firefoxDuringPreedit']=dict(browser_state);type_text(' ');results['firefoxCommitted']=dict(browser_state);results['firefoxAfterIme']=input_state()
  focus_field='password';wait_for(lambda:browser_state.get('active')=='password');time.sleep(.3);results['firefoxPassword']=input_state()
 if 'firefox-extra' in cases or 'electron' in cases:
  if 'firefox-extra' in cases:
   profile=root/'firefox-extra';profile.mkdir();(profile/'user.js').write_text('user_pref("browser.aboutwelcome.enabled",false);\nuser_pref("browser.shell.checkDefaultBrowser",false);\n')
   spawn('firefox-extra',['firefox','--no-remote','--profile',str(profile),f'http://127.0.0.1:{server.server_port}/'])
  else:
   # Use the installed Electron runtime, with a disposable resources/app per
   # Electron's documented packaging layout; never change the Code installation.
   runtime=root/'electron';runtime.mkdir()
   for item in Path('/usr/share/code').iterdir():
    if item.name in ['code','resources']:continue
    (runtime/item.name).symlink_to(item)
   shutil.copy2('/usr/share/code/code',runtime/'electron')
   appdir=runtime/'resources/app';appdir.mkdir(parents=True)
   (appdir/'package.json').write_text(json.dumps({'name':'waystroke-electron-fixture','version':'1.0.0','main':'main.js'}))
   (appdir/'main.js').write_text("const {app,BrowserWindow}=require('electron');app.whenReady().then(()=>{const w=new BrowserWindow({width:1100,height:750,webPreferences:{sandbox:true}});w.loadURL('http://127.0.0.1:%d/');require('fs').writeFileSync('%s',JSON.stringify(process.versions));});" % (server.server_port,root/'electron-versions.json'))
   spawn('electron',[str(runtime/'electron'),'--ozone-platform=wayland','--disable-gpu']+(['--enable-wayland-ime','--wayland-text-input-version=3'] if os.environ.get('WAYSTROKE_NATIVE_IME','enabled')=='enabled' else []))
  wait_for(lambda:browser_state.get('active')=='normal',30);call({'action':'activate','title':'WayStroke compatibility fixture'});call({'action':'source','id':'us'});time.sleep(.4)
  prefix='firefoxExtra' if 'firefox-extra' in cases else 'electron'
  results[prefix]={}
  for field in ['multiline','editable']:
   focus_field=field;wait_for(lambda:browser_state.get('active')==field);time.sleep(.3)
   if prefix=='firefoxExtra' and field=='multiline':call({'action':'commit','text':'前文\n'});time.sleep(.2)
   type_text('abc ');before=input_state();call({'action':'replace','offset':-4,'count':4,'text':'2003 '});time.sleep(.3)
   results[prefix][field]={'before':before,'after':dict(browser_state),'passed':browser_state[field]==(('前文\n' if prefix=='firefoxExtra' else '')+'2003 ' if field=='multiline' else '2003 Editable')}
  focus_field='normal';wait_for(lambda:browser_state.get('active')=='normal');time.sleep(.3)
  call({'action':'ime'});time.sleep(1);type_text('nihao');pre=input_state();during=dict(browser_state)
  try:call({'action':'replace','offset':-1,'count':1,'text':'SHOULD_NOT_APPEAR'});denial='unexpected success'
  except RuntimeError as error:denial=str(error)
  type_text(' ');results[prefix]['rime']={'preedit':pre,'during':during,'blockedReplacement':denial,'after':dict(browser_state),'committedState':input_state()}
  call({'action':'source','id':'us'});focus_field='password';wait_for(lambda:browser_state.get('active')=='password');time.sleep(.4)
  try:call({'action':'replace','offset':0,'count':0,'text':'SHOULD_NOT_APPEAR'});denial='unexpected success'
  except RuntimeError as error:denial=str(error)
  results[prefix]['password']={'ime':input_state(),'blockedReplacement':denial,'passwordLength':browser_state['passwordLength']}
  if prefix=='electron':results[prefix]['versions']=json.loads((root/'electron-versions.json').read_text())
  if prefix=='firefoxExtra':
   focus_field='normal';wait_for(lambda:browser_state.get('active')=='normal');time.sleep(.3)
   def key(keyval,pressed):call({'action':'key','keyval':keyval,'pressed':pressed});time.sleep(.04)
   for val,press in [(0xffe3,True),(ord('a'),True),(ord('a'),False),(0xffe3,False)]:key(val,press)
   type_text('replacement');results['shortcutCtrlA']={'text':browser_state['normal'],'events':list(browser_state['events'])}
   key(0xffe1,True);key(ord('Z'),True);key(ord('Z'),False);key(0xffe1,False)
   results['shortcutShift']={'text':browser_state['normal'],'events':list(browser_state['events'])}
   for val,press in [(0xffe3,True),(0xffe1,True),(0xff51,True),(0xff51,False),(0xffe1,False),(0xffe3,False)]:key(val,press)
   type_text('end');results['shortcutCtrlShiftLeft']={'text':browser_state['normal'],'events':list(browser_state['events'])}
   results['layout']={}
   for layout in ['us','fr']:
    call({'action':'source','id':layout});time.sleep(.5)
    for pressed in [True,False]:call({'action':'keycode','keycode':16,'pressed':pressed});time.sleep(.04)
    time.sleep(.3);results['layout'][layout]={'ime':input_state(),'text':browser_state['normal'],'events':list(browser_state['events'])}
 if 'xwayland' in cases:
  xenv=os.environ.copy();xenv['GDK_BACKEND']='x11';xsnapshot=call({'action':'snapshot'});xenv['DISPLAY']=xsnapshot['xDisplay'];xenv['XAUTHORITY']=xsnapshot['xAuthority']
  xenv['WAYSTROKE_CLIENT_PREFIX']='XProbe'
  spawn('xgtk',[sys.executable,str(source/'client.py')],xenv)
  wait_for(lambda:any(w['title']=='XProbe B' for w in call({'action':'snapshot'})['windows']),25)
  for title,x in [('XProbe A',80),('XProbe B',700)]:call({'action':'position','title':title,'x':x,'y':180,'focus':title=='XProbe B'})
  call({'action':'source','id':'us'});time.sleep(.5)
  type_text('abc ');before=input_state()
  try:call({'action':'replace','offset':-4,'count':4,'text':'2003 '});denial=None
  except RuntimeError as error:denial=str(error)
  time.sleep(.3);results['xwayland']={'before':before,'replacementError':denial,'snapshot':call({'action':'snapshot'}),'client':json.loads((root/'XProbe-client.json').read_text())}
  call({'action':'pointer','x':200,'y':300});time.sleep(.2);results['xwayland']['start']=call({'action':'bind-start'})
  call({'action':'pointer','x':850,'y':360});time.sleep(.2);results['xwayland']['afterCrossing']=call({'action':'bound'})
  call({'action':'maximize','title':'XProbe B'});time.sleep(.3);results['xwayland']['maximized']=call({'action':'snapshot'})['windows']
 if 'a11y-x' in cases or 'a11y-native' in cases or 'a11y-auto' in cases or 'a11y-ime' in cases or 'a11y-enter' in cases or 'a11y-accelerator' in cases:
  if 'a11y-x' in cases or 'a11y-auto' in cases or 'a11y-ime' in cases or 'a11y-enter' in cases or ('a11y-accelerator' in cases and os.environ.get('WAYSTROKE_A11Y_BACKEND')!='wayland'):
   aenv=os.environ.copy();aenv['GDK_BACKEND']='x11';snap=call({'action':'snapshot'});aenv['DISPLAY']=snap['xDisplay'];aenv['XAUTHORITY']=snap['xAuthority'];aenv['WAYSTROKE_CLIENT_PREFIX']='XProbe'
   if 'a11y-ime' in cases or 'a11y-accelerator' in cases:aenv['GTK_IM_MODULE']='ibus'
   spawn('xgtk',[sys.executable,str(source/'client.py')],aenv);title='XProbe B';busname='org.waystroke.XProbeClient'
   wait_for(lambda:any(w['title']==title for w in call({'action':'snapshot'})['windows']),25)
  else:title='Probe B';busname='org.waystroke.Client'
  clientFile=root/('XProbe-client.json' if title.startswith('XProbe') else 'client.json')
  call({'action':'activate','title':title});call({'action':'source','id':'us'});time.sleep(.5)
  if 'a11y-auto' in cases or 'a11y-ime' in cases:
   spawn('a11y-watch',[sys.executable,str(source/'accessibility-watch.py'),title]);wait_for(lambda:(root/'a11y-watch-ready').exists())
  if 'a11y-enter' in cases:
   spawn('a11y-enter',[sys.executable,str(source/'accessibility-enter.py'),title]);wait_for(lambda:(root/'a11y-enter-ready').exists());type_text('abc')
   for pressed in [True,False]:call({'action':'key','keyval':0xff0d,'pressed':pressed})
   time.sleep(.4);results['accessibilityEnter']={'registration':json.loads((root/'a11y-enter-ready').read_text()),'events':[json.loads(line) for line in (root/'a11y-enter.jsonl').read_text().splitlines()]}
  elif 'a11y-accelerator' in cases:
   results['confirmGrab']=call({'action':'grab-confirm'});type_text('abc')
   for pressed in [True,False]:call({'action':'key','keyval':0xff0d,'pressed':pressed})
   time.sleep(.3);results['confirmEventsBefore']=call({'action':'poll-confirm'});results['clientBeforeConfirm']=json.loads(clientFile.read_text())
  else:type_text('abc ')
  def accessible(replace=False):
   return json.loads(subprocess.check_output([sys.executable,str(source/'accessibility.py'),title]+(['--replace'] if replace else []),text=True,timeout=12))
  results['accessibilityBefore']=accessible()
  if 'a11y-accelerator' in cases:
   # The fixture helper has a fixed abc-space rule; replace just the three
   # characters directly here to verify ordering before the Entry activates.
   subprocess.check_output([sys.executable,str(source/'accessibility.py'),title,'--replace','--confirm','enter'],text=True,timeout=12)
   call({'action':'replay-confirm'});time.sleep(.4);results['clientAfterConfirm']=json.loads(clientFile.read_text());results['confirmEventsAfter']=call({'action':'poll-confirm'})
  if not ({'a11y-auto','a11y-ime','a11y-enter','a11y-accelerator'} & cases):results['accessibilityReplace']=accessible(True)
  time.sleep(.4)
  if 'a11y-ime' in cases:
   spawn('ibus-composition',[sys.executable,str(source/'ibus-composition.py')]);wait_for(lambda:(root/'ibus-composition-ready').exists())
   call({'action':'ime'});time.sleep(1);type_text('nihao');results['xImeDuring']=accessible();results['xImeClientDuring']=json.loads(clientFile.read_text())
   type_text(' ');time.sleep(.3);results['xImeAfter']=accessible();results['xImeClientAfter']=json.loads(clientFile.read_text());results['xImeComposition']={'registration':json.loads((root/'ibus-composition-ready').read_text()),'signals':[json.loads(line) for line in (root/'ibus-composition.jsonl').read_text().splitlines()]}
   call({'action':'source','id':'us'});time.sleep(.3)
  if 'a11y-accelerator' in cases and os.environ.get('WAYSTROKE_ACCEL_IME')=='1':
   call({'action':'track-panel'})
   for keyval,pressed in [(0xffe3,True),(ord('a'),True),(ord('a'),False),(0xffe3,False)]:call({'action':'key','keyval':keyval,'pressed':pressed})
   type_text('abc');call({'action':'ime'});time.sleep(1);type_text('nihao');results['confirmImeBefore']=call({'action':'snapshot'});results['confirmImeClientBefore']=json.loads(clientFile.read_text())
   for pressed in [True,False]:call({'action':'key','keyval':0xff0d,'pressed':pressed})
   time.sleep(.3);imeEvents=call({'action':'poll-confirm'})['events'];results['confirmImeEvent']=imeEvents[-1]
   if title.startswith('XProbe'):
    assert results['confirmImeEvent']['imeGuard'], 'No protection while X11 GTK composes'
    call({'action':'replay-confirm'})
   else:
    assert len(imeEvents)==len(results['confirmEventsAfter']['events']), 'Native IME did not consume its confirmation key'
    results['confirmImeConsumedByNative']=True
   time.sleep(.4);results['confirmImeClientAfter']=json.loads(clientFile.read_text());call({'action':'source','id':'us'});time.sleep(.3)
  subprocess.run(['gdbus','call','--session','--dest',busname,'--object-path','/org/waystroke/Client','--method','org.waystroke.Client.Focus',title+':password'],check=True,stdout=subprocess.DEVNULL)
  time.sleep(.4)
  if 'a11y-auto' in cases or 'a11y-ime' in cases:
   type_text('abc ');time.sleep(.4);results['accessibilityAutomatic']=[json.loads(line) for line in (root/'a11y-watch.jsonl').read_text().splitlines()]
   results['accessibilityClient']=json.loads(clientFile.read_text())
  if 'a11y-accelerator' in cases:
   type_text('abc')
   for pressed in [True,False]:call({'action':'key','keyval':0xff0d,'pressed':pressed})
   time.sleep(.2);results['passwordBeforeReplay']=accessible(True);call({'action':'replay-confirm'});time.sleep(.3);results['passwordAfterReplay']=json.loads(clientFile.read_text())
   subprocess.run(['gdbus','call','--session','--dest',busname,'--object-path','/org/waystroke/Client','--method','org.waystroke.Client.Focus',title+':normal'],check=True,stdout=subprocess.DEVNULL)
   time.sleep(.2)
   for keyval,pressed in [(0xffe3,True),(ord('a'),True),(ord('a'),False),(0xffe3,False)]:call({'action':'key','keyval':keyval,'pressed':pressed})
   type_text('plain')
   for pressed in [True,False]:call({'action':'key','keyval':0xff0d,'pressed':pressed})
   time.sleep(.2);call({'action':'replay-confirm'});time.sleep(.3);results['ordinaryAfterReplay']=json.loads(clientFile.read_text());results['confirmEventsComplete']=call({'action':'poll-confirm'});call({'action':'release-confirm'})
  results['accessibilityFinalFocus' if 'a11y-accelerator' in cases else 'accessibilityPassword']=accessible(True)
 if 'terminal-generic' in cases:
  spawn('ptyxis',['ptyxis','--standalone','--title','WayStroke generic fixture','--execute',shlex.join([sys.executable,str(source/'terminal-generic.py'),str(root)])])
  wait_for(lambda:(root/'generic-stage').exists(),25);call({'action':'activate','title':'WayStroke generic fixture'});call({'action':'source','id':'us'});time.sleep(.5);call({'action':'terminal-monitor'})
  results['terminalGeneric']={}
  for mode in ['canonical','canonical-enter','readline','password','password-enter','ime','raw']:
   wait_for(lambda:(root/'generic-stage').read_text()==mode);time.sleep(.2);call({'action':'terminal-reset'})
   if mode=='ime':
    call({'action':'ime'});time.sleep(1);type_text('nihao');results['terminalGenericPreedit']=input_state();type_text(' ');call({'action':'source','id':'us'});time.sleep(.3);type_text(' abc ')
   else:type_text('abc' if mode.endswith('-enter') else 'abc ')
   for pressed in [True,False]:call({'action':'key','keyval':0xff0d,'pressed':pressed})
   wait_for(lambda:(root/('generic-'+mode+'.json')).exists());results['terminalGeneric'][mode]=json.loads((root/('generic-'+mode+'.json')).read_text())
  results['terminalGenericEvents']=call({'action':'terminal-records'});call({'action':'terminal-stop'})
 if 'terminal-zle' in cases:
  spawn('ptyxis',['ptyxis','--standalone','--title','WayStroke ZLE fixture','--execute',shlex.join(['/usr/bin/zsh','-dfi',str(source/'terminal-zle.zsh'),str(root)])])
  wait_for(lambda:(root/'zle-stage').exists(),25);call({'action':'activate','title':'WayStroke ZLE fixture'});call({'action':'source','id':'us'});time.sleep(.4)
  def enter():
   for pressed in [True,False]:call({'action':'key','keyval':0xff0d,'pressed':pressed})
   time.sleep(.3)
  wait_for(lambda:(root/'zle-stage').read_text()=='space');type_text('abc ');enter()
  wait_for(lambda:(root/'zle-stage').read_text()=='enter');type_text('abc');enter()
  wait_for(lambda:(root/'zle-stage').read_text()=='ime');call({'action':'ime'});time.sleep(1);type_text('nihao');results['zlePreedit']=input_state();type_text(' ');results['zleCommitted']=input_state();call({'action':'source','id':'us'});enter()
  wait_for(lambda:(root/'zle-stage').read_text()=='secret');type_text('abc');enter()
  wait_for(lambda:(root/'terminal-password-ready.json').exists());type_text('abc');enter()
  wait_for(lambda:(root/'zle-stage').read_text()=='complete')
  results['terminalZle']={'space':(root/'zle-space.txt').read_text(),'enter':(root/'zle-enter.txt').read_text(),'secretLength':int((root/'zle-secret-length').read_text()),'expansions':int((root/'zle-expansions').read_text()),'ime':(root/'zle-ime.txt').read_text(),'externalPassword':json.loads((root/'terminal-password.json').read_text()),'externalPrompt':json.loads((root/'terminal-password-ready.json').read_text())}
 if 'terminal-password' in cases:
  spawn('ptyxis',['ptyxis','--standalone','--title','WayStroke password fixture','--execute',shlex.join([sys.executable,str(source/'terminal-fixture.py'),str(root),'password'])])
  wait_for(lambda:(root/'terminal-password-ready.json').exists(),25);call({'action':'activate','title':'WayStroke password fixture'});call({'action':'source','id':'us'});time.sleep(.5)
  before=input_state();type_text('fixture-only')
  for pressed in [True,False]:call({'action':'key','keyval':0xff0d,'pressed':pressed})
  wait_for(lambda:(root/'terminal-password.json').exists());results['terminalPassword']={'ime':before,'prompt':json.loads((root/'terminal-password-ready.json').read_text()),'fixture':json.loads((root/'terminal-password.json').read_text())}
 if 'terminal' in cases:
  try:
   line_mode=os.environ.get('WAYSTROKE_TERMINAL_MODE')=='readline'
   spawn('ptyxis',['ptyxis','--standalone','--title','WayStroke terminal fixture','--execute',shlex.join([sys.executable,str(source/'terminal-fixture.py'),str(root)]+(['readline'] if line_mode else []))])
   wait_for(lambda:any('WayStroke terminal fixture' in w['title'] for w in call({'action':'snapshot'})['windows']));call({'action':'activate','title':'WayStroke terminal fixture'});call({'action':'source','id':'us'});time.sleep(.5);results['terminalBefore']=call({'action':'snapshot'})
   wait_for(lambda:(root/'terminal.json').exists())
   type_text('abc ');call({'action':'screenshot'});wait_for(lambda:(root/'terminal.json').exists());results['terminalTyped']=json.loads((root/'terminal.json').read_text());results['terminalIme']=input_state()
   if line_mode:
    for _ in range(4):
     for pressed in [True,False]:call({'action':'key','keyval':0xff08,'pressed':pressed});time.sleep(.025)
    call({'action':'commit','text':'2003 '});time.sleep(.2)
    for pressed in [True,False]:call({'action':'key','keyval':0xff0d,'pressed':pressed})
    wait_for(lambda:(root/'terminal-line.json').exists());results['terminalLineReplacement']=json.loads((root/'terminal-line.json').read_text())
   else:
    try:call({'action':'replace','offset':-4,'count':4,'text':'2003 '})
    except RuntimeError as error:results['terminalReplaceUnavailable']=str(error)
    time.sleep(.2);results['terminalAfterReplace']=json.loads((root/'terminal.json').read_text());results['terminalAfterIme']=input_state()
    call({'action':'ime'});time.sleep(1);type_text('nihao');results['terminalPreedit']=input_state();results['terminalDuringPreedit']=json.loads((root/'terminal.json').read_text());type_text(' ');results['terminalCommitted']=json.loads((root/'terminal.json').read_text());results['terminalCommittedIme']=input_state()
  except Exception as error:
   results['terminalError']=str(error);results['terminalFailureState']=call({'action':'snapshot'});call({'action':'screenshot','tag':'terminal'});time.sleep(.3)

 if 'code' in cases or 'code-extra' in cases:
  try:
   code_dir=root/'code-data';(code_dir/'User').mkdir(parents=True);(code_dir/'User/settings.json').write_text(json.dumps({'workbench.startupEditor':'none','security.workspace.trust.enabled':False,'editor.quickSuggestions':False,'editor.suggestOnTriggerCharacters':False,'update.mode':'none','telemetry.telemetryLevel':'off'}))
   text_file=root/'waystroke-fixture.txt';text_file.write_text('')
   spawn('code',['/usr/share/code/code','--new-window','--user-data-dir',str(code_dir),'--extensions-dir',str(root/'code-extensions'),'--disable-extensions','--skip-welcome','--skip-release-notes','--ozone-platform=wayland','--enable-wayland-ime','--wayland-text-input-version=3','--disable-gpu',str(text_file)])
   wait_for(lambda:any('waystroke-fixture.txt' in w['title'] for w in call({'action':'snapshot'})['windows']),25);call({'action':'activate','title':'waystroke-fixture.txt'});call({'action':'source','id':'us'});time.sleep(1)
   type_text('abc ');results['codeIme']=input_state()
   for keyval,pressed in [(0xffe3,True),(ord('s'),True),(ord('s'),False),(0xffe3,False)]:call({'action':'key','keyval':keyval,'pressed':pressed})
   time.sleep(.5);results['codeTyped']=text_file.read_text()
   call({'action':'replace','offset':-4,'count':4,'text':'2003 '});time.sleep(.5)
   for keyval,pressed in [(0xffe3,True),(ord('s'),True),(ord('s'),False),(0xffe3,False)]:call({'action':'key','keyval':keyval,'pressed':pressed})
   time.sleep(.5);results['codeAfterReplace']=text_file.read_text();results['codeAfterIme']=input_state()
   if 'code-extra' in cases:
    call({'action':'ime'});time.sleep(1);type_text('nihao');results['codePreedit']=input_state();results['codeFileDuringPreedit']=text_file.read_text()
    type_text(' ');results['codeCommittedIme']=input_state()
    for keyval,pressed in [(0xffe3,True),(ord('s'),True),(ord('s'),False),(0xffe3,False)]:call({'action':'key','keyval':keyval,'pressed':pressed})
    time.sleep(.5);results['codeFileAfterCommit']=text_file.read_text()
   call({'action':'screenshot'});time.sleep(.3)
  except Exception as error:results['codeError']=str(error)
except Exception as error:
 results['error']=str(error)
finally:
 for p in reversed(processes):
  if p.poll() is None:os.killpg(p.pid,signal.SIGTERM)
 server.shutdown();(root/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps(results,ensure_ascii=False,indent=2),flush=True)
 if 'error' in results:sys.exit(1)
