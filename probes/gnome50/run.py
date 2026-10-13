"""Run a disposable GNOME 50 probe. Does not install into the host session."""
import os,sys,json,time,tempfile,subprocess,shutil,signal
from pathlib import Path
source=Path(__file__).resolve().parent
if '--inside' not in sys.argv:
 root=Path(tempfile.mkdtemp(prefix='waystroke-gnome50-'))
 for name in ['runtime','config','data','cache']:(root/name).mkdir(mode=0o700)
 ext=root/'data/gnome-shell/extensions/waystroke-probe@local';ext.mkdir(parents=True)
 for name in ['extension.js','metadata.json','terminal-monitor.js']:shutil.copy(source/name,ext/name)
 config=root/'bus.conf';config.write_text('<busconfig><type>session</type><listen>unix:tmpdir='+str(root/'runtime')+'</listen><auth>EXTERNAL</auth><policy context="default"><allow send_destination="*" eavesdrop="true"/><allow eavesdrop="true"/><allow own="*"/></policy></busconfig>')
 env=os.environ.copy();env.update(XDG_RUNTIME_DIR=str(root/'runtime'),XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),XDG_CACHE_HOME=str(root/'cache'),GSETTINGS_BACKEND='keyfile',LIBGL_ALWAYS_SOFTWARE='1',GIO_USE_VFS='local',WAYSTROKE_PROBE_DIR=str(root),GDK_BACKEND='wayland',GSK_RENDERER='cairo',WAYLAND_DISPLAY='waystroke-probe-0')
 env.pop('DISPLAY',None);env.pop('IBUS_ADDRESS',None)
 print('Probe artifacts:',root,flush=True)
 result=subprocess.run(['dbus-run-session','--config-file='+str(config),'--',sys.executable,str(source/'run.py'),'--inside'],env=env,timeout=65)
 sys.exit(result.returncode)
root=Path(os.environ['WAYSTROKE_PROBE_DIR']);results={};processes=[]
def call(q):
 out=subprocess.check_output(['gdbus','call','--session','--dest','org.gnome.Shell','--object-path','/org/waystroke/Probe','--method','org.waystroke.Probe.Call',json.dumps(q)],text=True,stderr=subprocess.DEVNULL,timeout=3)
 import ast
 result=json.loads(ast.literal_eval(out)[0]);
 if 'error' in result:raise RuntimeError(result['error'])
 return result
def snapshot():time.sleep(.3);return json.loads((root/'client.json').read_text())
def key(value):
 for pressed in [True,False]:call({'action':'key','keyval':value,'pressed':pressed});time.sleep(.05)
def click(button=3):
 for pressed in [True,False]:call({'action':'button','button':button,'pressed':pressed});time.sleep(.1)
try:
 subprocess.run(['gsettings','set','org.gnome.shell','enabled-extensions',"['waystroke-probe@local']"],check=True)
 subprocess.run(['gsettings','set','org.gnome.shell','disable-user-extensions','false'],check=True)
 subprocess.run(['gsettings','set','org.gnome.desktop.interface','enable-hot-corners','false'],check=True)
 if os.environ.get('WAYSTROKE_TEST_IME'):
  subprocess.run(['gsettings','set','org.gnome.desktop.input-sources','sources',"[('xkb', 'us'), ('ibus', 'rime')]"],check=True)
  ibuslog=(root/'ibus.log').open('w');ibus=subprocess.Popen(['ibus-daemon','--single','--panel=disable','--config=disable','--emoji-extension=disable'],stdout=ibuslog,stderr=ibuslog,start_new_session=True);processes.append(ibus);time.sleep(1)
 log=(root/'shell.log').open('w');shell=subprocess.Popen(['gnome-shell','--headless','--wayland','--no-x11','--wayland-display=waystroke-probe-0','--virtual-monitor=1280x800'],stdout=log,stderr=log,start_new_session=True);processes.append(shell)
 for _ in range(80):
  time.sleep(.2)
  try:call({'action':'snapshot'});break
  except Exception:pass
 else:raise RuntimeError('Probe extension unavailable; inspect shell.log')
 clientlog=(root/'client.log').open('w');client=subprocess.Popen([sys.executable,str(source/'client.py')],stdout=clientlog,stderr=clientlog,start_new_session=True);processes.append(client)
 for _ in range(50):
  time.sleep(.1)
  if (root/'client.json').exists():break
 call({'action':'normal'});time.sleep(1)
 for title,x in [('Probe A',80),('Probe B',700)]:call({'action':'position','title':title,'x':x,'y':180,'focus':title=='Probe B'})
 time.sleep(.5)
 results['initial']=call({'action':'snapshot'})
 results['hitNonfocused']=call({'action':'hit','x':200,'y':300})
 results['beforeRightHit']=call({'action':'hit','x':850,'y':360});call({'action':'pointer','x':850,'y':360});time.sleep(.2);call({'action':'screenshot'});time.sleep(.5);click()
 results['pointerHit']=call({'action':'hit','x':850,'y':360});results['rightClick']=snapshot();results['stageAfterRightClick']=call({'action':'snapshot'})
 key(0xff1b) # close own context menu
 for c in 'abc ':key(ord(c))
 results['virtualKeys']=snapshot();results['imeNormal']=call({'action':'snapshot'})
 call({'action':'replace','offset':-4,'count':4,'text':'2003 '});results['replace']=snapshot()
 call({'action':'preedit','text':'拼音'});results['duringPreedit']=snapshot();results['imePreedit']=call({'action':'snapshot'})
 call({'action':'preedit','text':''});call({'action':'commit','text':'中文'});results['unicodeCommit']=snapshot()
 if os.environ.get('WAYSTROKE_TEST_IME'):
  call({'action':'ime'});time.sleep(3)
  for c in 'nihao':key(ord(c))
  results['rimePreedit']=call({'action':'snapshot'});results['rimeBeforeCommit']=snapshot();key(0x20);time.sleep(.5)
  results['rimeAfterCommit']=snapshot();results['rimeCommittedState']=call({'action':'snapshot'})
 subprocess.check_output(['gdbus','call','--session','--dest','org.waystroke.Client','--object-path','/org/waystroke/Client','--method','org.waystroke.Client.Focus','Probe B:password'],text=True)
 time.sleep(.3);results['imePassword']=call({'action':'snapshot'})
 call({'action':'grab'});click();results['grabbedRightClick']=snapshot();results['stageDuringGrab']=call({'action':'snapshot'});call({'action':'ungrab'});click();results['replayedRightClick']=snapshot();call({'action':'maximize','title':'Probe A'});time.sleep(.3);results['maximized']=call({'action':'snapshot'})
except Exception as e:
 results['error']=str(e)
finally:
 for p in reversed(processes):
  if p.poll() is None:os.killpg(p.pid,signal.SIGTERM)
 (root/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps(results,ensure_ascii=False,indent=2),flush=True)
 if 'error' in results:sys.exit(1)
