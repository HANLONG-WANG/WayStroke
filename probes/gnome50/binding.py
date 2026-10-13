"""Bind a start before allowing later mouse packets to move the desktop pointer."""
import argparse,ast,collections,json,os,signal,socket,subprocess,sys,tempfile,threading,time
from pathlib import Path

BASE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--device',default='/dev/input/event3')
parser.add_argument('--seconds',type=int,default=60)
parser.add_argument('--self-test',action='store_true')
parser.add_argument('--inside',action='store_true')
parser.add_argument('--viewer-smoke',action='store_true')
parser.add_argument('--viewer',default='/usr/libexec/mutter-devkit')
args=parser.parse_args()

def service(q,path='/run/waystroke-input-probe/control.sock'):
 with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as connection:
  connection.settimeout(3);connection.connect(path);connection.send(json.dumps(q).encode());value=json.loads(connection.recv(16384))
  if 'error' in value:raise RuntimeError(value['error'])
  return value

def host_locked(address):
 text=subprocess.check_output(['gdbus','call','--address',address,'--dest','org.gnome.ScreenSaver','--object-path','/org/gnome/ScreenSaver','--method','org.gnome.ScreenSaver.GetActive'],text=True,timeout=2)
 return text.strip().startswith('(true')

if not args.inside:
 if not args.self_test and not args.viewer_smoke:
  if host_locked(os.environ['DBUS_SESSION_BUS_ADDRESS']):parser.exit(1,'请解锁后再运行真实鼠标联动验证。\n')
  if service({'action':'status'}).get('protocolVersion',0)<2:parser.exit(1,'请先更新鼠标验证服务，当前版本不支持起点绑定握手。\n')
 root=Path(tempfile.mkdtemp(prefix='waystroke-binding-'))
 for name in ['runtime','config','data','cache']:(root/name).mkdir(mode=0o700)
 ext=root/'data/gnome-shell/extensions/waystroke-probe@local';ext.mkdir(parents=True)
 for name in ['extension.js','metadata.json','terminal-monitor.js']:(ext/name).write_bytes((BASE/name).read_bytes())
 config=root/'bus.conf';config.write_text('<busconfig><type>session</type><listen>unix:tmpdir='+str(root/'runtime')+'</listen><auth>EXTERNAL</auth><policy context="default"><allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/></policy></busconfig>')
 env=os.environ.copy();env.update(WAYSTROKE_HOST_BUS_ADDRESS=env['DBUS_SESSION_BUS_ADDRESS'],XDG_RUNTIME_DIR=str(root/'runtime'),XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),XDG_CACHE_HOME=str(root/'cache'),GSETTINGS_BACKEND='keyfile',GIO_USE_VFS='local',WAYSTROKE_PROBE_DIR=str(root),GDK_BACKEND='wayland',GSK_RENDERER='cairo',WAYLAND_DISPLAY='waystroke-probe-0')
 # The devkit viewer connects to the outer display; the compositor and clients use their own.
 env['WAYSTROKE_OUTER_RUNTIME']=os.environ['XDG_RUNTIME_DIR'];env['WAYSTROKE_OUTER_DISPLAY']=os.environ.get('WAYLAND_DISPLAY','wayland-0')
 env.pop('DISPLAY',None);env.pop('IBUS_ADDRESS',None)
 env['PIPEWIRE_RUNTIME_DIR']=os.environ['XDG_RUNTIME_DIR']
 if not args.self_test:
  if not Path(args.viewer).is_file():parser.exit(1,'缺少 mutter-devkit；请先执行联动工具安装脚本。\n')
  schema=Path(args.viewer).parents[1]/'share/glib-2.0/schemas/org.gnome.mutter.devkit.gschema.xml'
  if schema.exists():
   directory=root/'schemas';directory.mkdir();(directory/schema.name).write_bytes(schema.read_bytes());subprocess.run(['glib-compile-schemas',str(directory)],check=True);env['GSETTINGS_SCHEMA_DIR']=str(directory)
 print('Probe artifacts:',root,flush=True)
 command=['dbus-run-session','--config-file='+str(config),'--',sys.executable,str(BASE/'binding.py'),'--inside']+sys.argv[1:]
 completed=subprocess.run(command,env=env,timeout=args.seconds+45)
 sys.exit(completed.returncode)

root=Path(os.environ['WAYSTROKE_PROBE_DIR']);processes=[];results=[];fake=None;fake_thread=None

def call(q):
 text=subprocess.check_output(['gdbus','call','--session','--dest','org.gnome.Shell','--object-path','/org/waystroke/Probe','--method','org.waystroke.Probe.Call',json.dumps(q)],text=True,stderr=subprocess.DEVNULL,timeout=2)
 result=json.loads(ast.literal_eval(text)[0])
 if 'error' in result:raise RuntimeError(result['error'])
 return result

def wait_for(fn):
 until=time.monotonic()+15
 while time.monotonic()<until:
  try:
   if fn():return
  except (OSError,RuntimeError,subprocess.CalledProcessError):pass
  time.sleep(.1)
 raise RuntimeError('Probe desktop did not become ready')

def spawn(name,command,env=None):
 log=(root/(name+'.log')).open('w');p=subprocess.Popen(command,stdout=log,stderr=log,start_new_session=True,env=env);processes.append(p);return p

try:
 for schema,key,value in [('org.gnome.shell','enabled-extensions',"['waystroke-probe@local']"),('org.gnome.shell','disable-user-extensions','false'),('org.gnome.desktop.interface','enable-hot-corners','false')]:subprocess.run(['gsettings','set',schema,key,value],check=True)
 # A separate viewer is launched below; the compositor never uses the host display socket.
 spawn('shell',['gnome-shell','--headless','--wayland','--no-x11','--wayland-display=waystroke-probe-0']+(['--virtual-monitor=1280x800'] if args.self_test else ['--devkit']))
 wait_for(lambda:call({'action':'snapshot'}))
 if not args.self_test:
  viewer_env=os.environ.copy();viewer_env['XDG_RUNTIME_DIR']=viewer_env['WAYSTROKE_OUTER_RUNTIME'];viewer_env['WAYLAND_DISPLAY']=viewer_env['WAYSTROKE_OUTER_DISPLAY']
  viewer=spawn('viewer',[args.viewer],viewer_env);wait_for(lambda:call({'action':'snapshot'})['monitors']>0)
 spawn('gtk',[sys.executable,str(BASE/'client.py')]);wait_for(lambda:(root/'client.json').exists());call({'action':'normal'});time.sleep(.6)
 width=call({'action':'snapshot'})['stageSize'][0];window_width=min(420,int(width/2)-60)
 for title,x in [('Probe A',80 if args.self_test else 25),('Probe B',700 if args.self_test else int(width/2)+15)]:call({'action':'position','title':title,'x':x,'y':180,'width':window_width,'focus':title=='Probe B'})
 time.sleep(.3)
 if args.self_test:
  sys.path.insert(0,str(BASE.parent/'input'))
  from daemon import Server
  from routing import Router
  from evdev import InputEvent,ecodes as E
  fd_read,fd_write=os.pipe();queue=collections.deque()
  class Mouse:
   path='synthetic-mouse'
   def fileno(self):return fd_read
   def read(self):os.read(fd_read,1);return [InputEvent(0,0,*event) for event in queue.popleft()]
   def close(self):os.close(fd_read)
  class Virtual:
   x,y=200,300
   def write(self,kind,code,value):
    if kind==E.EV_REL:
     if code==E.REL_X:self.x+=value
     if code==E.REL_Y:self.y+=value
    if kind==E.EV_SYN:call({'action':'pointer','x':self.x,'y':self.y})
   def close(self):pass
  call({'action':'pointer','x':200,'y':300});time.sleep(.1)
  fake=Server(os.getuid(),str(root/'fake.sock'));fake.mouse=Mouse();fake.virtual=Virtual();fake.router=Router(fake.virtual.write,fake.record,bind_start=True);fake.owner=os.getpid();fake.deadline=time.monotonic()+10;fake.heartbeat=time.monotonic()+3;fake.selector.register(fake.mouse,1,'mouse')
  fake_thread=threading.Thread(target=fake.run);fake_thread.start()
  queue.append([(E.EV_KEY,E.BTN_RIGHT,1),(E.EV_SYN,E.SYN_REPORT,0)]);os.write(fd_write,b'1')
  path=str(root/'fake.sock');wait_for(lambda:service({'action':'poll'},path)['awaitingStart'])
  queue.append([(E.EV_REL,E.REL_X,650),(E.EV_REL,E.REL_Y,60),(E.EV_SYN,E.SYN_REPORT,0),(E.EV_KEY,E.BTN_RIGHT,0),(E.EV_SYN,E.SYN_REPORT,0)]);os.write(fd_write,b'2');time.sleep(.04)
  before=call({'action':'bind-start'});assert before['title']=='Probe A' and before['focus']=='Probe B'
  state=service({'action':'poll'},path);service({'action':'bound','sequence':state['startSequence']},path);time.sleep(.1);after=call({'action':'bound'})
  assert after['title']=='Probe A' and after['endTitle']=='Probe B'
  results.append({'case':'real-GNOME + synthetic-input-service-ordering','before':before,'after':after,'passed':True})
 elif args.viewer_smoke:
  time.sleep(1);assert viewer.poll() is None;results.append({'case':'devkit-viewer-startup','monitors':call({'action':'snapshot'})['monitors'],'passed':True})
 else:
  if host_locked(os.environ['WAYSTROKE_HOST_BUS_ADDRESS']):raise RuntimeError('请先解锁')
  service({'action':'arm','device':args.device,'seconds':args.seconds,'bind_start':True})
  print('请在新打开的测试桌面中操作：先让 B 获得焦点，再从 A 按住右键绘制到 B。Ctrl+C 结束。',flush=True)
  sequence=0;start=None;next_lock_check=0
  try:
   while True:
    if time.monotonic()>=next_lock_check:
     if host_locked(os.environ['WAYSTROKE_HOST_BUS_ADDRESS']):raise RuntimeError('检测到锁屏，停止验证')
     next_lock_check=time.monotonic()+.5
    if viewer.poll() is not None:raise RuntimeError('测试桌面已关闭')
    state=service({'action':'poll'})
    if not state['armed']:print(state['note'],flush=True);break
    for record in state['records']:
     if record['sequence']<=sequence:continue
     sequence=record['sequence']
     if record['result']=='begin':
      began=time.monotonic();start=call({'action':'bind-start'});service({'action':'bound','sequence':sequence})
      item={'event':'start','window':start,'bindingMs':round((time.monotonic()-began)*1000,1)}
     elif record['result'] in ['stroke','click']:
      item={'event':'finish','gesture':record,'window':call({'action':'bound'})}
     else:item=record
     results.append(item);print(json.dumps(item,ensure_ascii=False),flush=True)
    time.sleep(.02)
  finally:service({'action':'disarm'})

except KeyboardInterrupt:
 print('验证已停止。',flush=True)
except Exception as error:
 results.append({'error':str(error)});print(str(error),file=sys.stderr)
finally:
 if fake:
  fake.running=False;fake_thread.join(3);os.close(fd_write)
 for p in reversed(processes):
  if p.poll() is None:os.killpg(p.pid,signal.SIGTERM)
 (root/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps(results,ensure_ascii=False,indent=2),flush=True)
 if any('error' in r for r in results):sys.exit(1)
