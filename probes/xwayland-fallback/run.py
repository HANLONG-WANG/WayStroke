#!/usr/bin/env python3
"""XWayland fallback validation in a disposable Devkit GNOME session.

Checks (A) whether toolkits expose AT-SPI editing when enabled and (B) the
preconditions of selection-verified replacement for apps without any text
interface. Only fixture windows and fixed test strings are used.
"""
import base64,json,os,queue,shutil,signal,subprocess,sys,tempfile,threading,time
from pathlib import Path
from gi.repository import Gio,GLib
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
DISPLAY_NAME='waystroke-fallback-0'

if '--inside' not in sys.argv:
    root=Path(tempfile.mkdtemp(prefix='waystroke-fallback-'))
    for directory in ['runtime','config','data','cache','state']:(root/directory).mkdir(mode=0o700)
    dest=root/'data/gnome-shell/extensions/waystroke-probe@local';dest.mkdir(parents=True)
    for file in ['extension.js','metadata.json','terminal-monitor.js']:shutil.copy(REPO/'probes/gnome50'/file,dest/file)
    source=(dest/'extension.js').read_text()
    # Batched keys keep one ordered stream; keyboard2 stands in for the user's
    # physical keyboard during the race test.
    source=source.replace("  this.keyboard=seat.create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);","  this.keyboard=seat.create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);this.keyboard2=seat.create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);",1)
    source=source.replace("  if(q.action==='key')","  if(q.action==='keys'||q.action==='keys2'){const device=q.action==='keys'?this.keyboard:this.keyboard2;q.keys.forEach(([keyval,pressed],i)=>device.notify_keyval(now+i,keyval,pressed?Clutter.KeyState.PRESSED:Clutter.KeyState.RELEASED));return {sent:q.keys.length}}\n  if(q.action==='focusInfo'){const w=global.display.focus_window;return w?{title:w.get_title(),clientType:w.get_client_type(),pid:w.get_pid(),wmClass:w.get_wm_class(),wmClassInstance:w.get_wm_class_instance(),windowType:w.get_window_type()}:null}\n  if(q.action==='key')",1)
    source=source.replace('return {panelState:','return {startingUp:Main.layoutManager._startingUp,panelState:',1)
    (dest/'extension.js').write_text(source)
    env=os.environ.copy();env.update(XDG_RUNTIME_DIR=str(root/'runtime'),XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),XDG_CACHE_HOME=str(root/'cache'),XDG_STATE_HOME=str(root/'state'),GSETTINGS_BACKEND='keyfile',GIO_USE_VFS='local',WAYSTROKE_PROBE_DIR=str(root),WAYLAND_DISPLAY=DISPLAY_NAME,WAYSTROKE_OUTER_RUNTIME=os.environ['XDG_RUNTIME_DIR'],WAYSTROKE_OUTER_DISPLAY=os.environ.get('WAYLAND_DISPLAY','wayland-0'),PIPEWIRE_RUNTIME_DIR=os.environ['XDG_RUNTIME_DIR'])
    schema=Path('/usr/share/glib-2.0/schemas/org.gnome.mutter.devkit.gschema.xml');schemas=root/'schemas';schemas.mkdir();shutil.copy(schema,schemas/schema.name)
    subprocess.run(['glib-compile-schemas',str(schemas)],check=True);env['GSETTINGS_SCHEMA_DIR']=str(schemas)
    # NVIDIA EGL leaves XWayland windows stale in Devkit screenshots; glamor off
    # affects only this disposable XWayland.
    env['XWAYLAND_NO_GLAMOR']='1'
    for name in ['DISPLAY','XAUTHORITY','IBUS_ADDRESS','AT_SPI_BUS_ADDRESS','QT_LINUX_ACCESSIBILITY_ALWAYS_ON','QT_QPA_PLATFORM']:env.pop(name,None)
    print('Fallback probe artifacts:',root,flush=True)
    sys.exit(subprocess.run(['dbus-run-session','--',sys.executable,__file__,'--inside',*sys.argv[1:]],env=env).returncode)

root=Path(os.environ['WAYSTROKE_PROBE_DIR']);processes=[];results={}
connection=Gio.bus_get_sync(Gio.BusType.SESSION,None)
def spawn(name,args,env=None):
    log=(root/(name+'.log')).open('w');p=subprocess.Popen(args,stdout=log,stderr=log,start_new_session=True,env=env);processes.append(p);return p
def call(q):
    result=json.loads(connection.call_sync('org.gnome.Shell','/org/waystroke/Probe','org.waystroke.Probe','Call',GLib.Variant('(s)',(json.dumps(q),)),GLib.VariantType('(s)'),Gio.DBusCallFlags.NONE,5000,None).unpack()[0])
    if isinstance(result,dict) and 'error' in result and len(result)==1:raise RuntimeError(result['error'])
    return result
def wait(fn,timeout=15,interval=.05):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        try:
            value=fn()
            if value:return value
        except (GLib.Error,FileNotFoundError,json.JSONDecodeError,KeyError):pass
        time.sleep(interval)
    raise RuntimeError('Condition timed out')
def save():(root/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=1))

SHIFT,CONTROL,LEFT,RIGHT,RETURN,BACKSPACE=0xffe1,0xffe3,0xff51,0xff53,0xff0d,0xff08
def tap(keyval):return [(keyval,True),(keyval,False)]
def typed(text):return [event for char in text for event in tap(ord(char))]
def shifted(keyval,count):return [(SHIFT,True),*[event for _ in range(count) for event in tap(keyval)],(SHIFT,False)]
def control(keyval):return [(CONTROL,True),*tap(keyval),(CONTROL,False)]
def keys(events,device='keys'):call({'action':device,'keys':[[k,p] for k,p in events]})

# ---- X11 helper: raw key observation, selection ownership and transfers ----
class XHelper:
    def __init__(self):
        import Xlib.threaded  # noqa: F401  (thread-safe display locks)
        from Xlib import X,Xatom,display
        from Xlib.ext import xinput,xfixes
        from Xlib.protocol import rq
        self.X,self.xinput,self.xfixes=X,xinput,xfixes
        self.d=display.Display();self.opcode=self.d.query_extension('XInputExtension').major_opcode
        raw=rq.Struct(xinput.DEVICEID('deviceid'),rq.Card32('time'),rq.Card32('detail'),xinput.DEVICEID('sourceid'),rq.Card16('valuators_len'),rq.Card32('flags'),rq.Pad(4))
        for evtype in (xinput.RawKeyPress,xinput.RawKeyRelease):self.d.ge_add_event_data(self.opcode,evtype,raw)
        v=self.d.xinput_query_version();self.version=[v.major_version,v.minor_version];self.d.xfixes_query_version()
        self.root=self.d.screen().root
        self.root.xinput_select_events([(xinput.AllMasterDevices,xinput.RawKeyPressMask|xinput.RawKeyReleaseMask)])
        self.atom=lambda name:self.d.intern_atom(name)
        self.PRIMARY,self.CLIPBOARD,self.UTF8,self.TARGETS,self.PROPERTY=Xatom.PRIMARY,self.atom('CLIPBOARD'),self.atom('UTF8_STRING'),self.atom('TARGETS'),self.atom('WAYSTROKE_SELECTION')
        self.d.xfixes_select_selection_input(self.root,self.PRIMARY,xfixes.XFixesSetSelectionOwnerNotifyMask)
        self.window=self.root.create_window(0,0,1,1,0,X.CopyFromParent)
        self.raw=[];self.owners=[];self.notifies=queue.Queue();self.serving={}
        self.d.flush();threading.Thread(target=self.loop,daemon=True).start()
    def loop(self):
        X=self.X
        while True:
            try:event=self.d.next_event()
            except Exception:return  # XWayland closes at teardown
            now=time.monotonic()
            if event.type==35 and getattr(event,'extension',None)==self.opcode and event.evtype in (self.xinput.RawKeyPress,self.xinput.RawKeyRelease):
                self.raw.append((now,event.evtype==self.xinput.RawKeyPress,event.data.detail))
            elif type(event).__name__=='SetSelectionOwnerNotify':  # python-xlib builds per-display subclasses
                self.owners.append((now,event.owner.id if event.owner else 0,event.selection))
            elif event.type==X.SelectionNotify:self.notifies.put(event)
            elif event.type==X.SelectionRequest:self.answer(event)
    def answer(self,request):
        from Xlib.protocol import event as xevent
        text=self.serving.get(request.selection);prop=request.property or request.target
        if text is None:prop=0
        elif request.target==self.TARGETS:request.requestor.change_property(prop,self.atom('ATOM'),32,[self.TARGETS,self.UTF8])
        elif request.target==self.UTF8:request.requestor.change_property(prop,self.UTF8,8,text.encode())
        else:prop=0
        request.requestor.send_event(xevent.SelectionNotify(time=request.time,requestor=request.requestor,selection=request.selection,target=request.target,property=prop));self.d.flush()
    def own(self,selection,text):
        self.serving[selection]=text;self.window.set_selection_owner(selection,self.X.CurrentTime);self.d.flush()
    def read(self,selection,timeout=.5):
        while not self.notifies.empty():self.notifies.get()
        self.window.convert_selection(selection,self.UTF8,self.PROPERTY,self.X.CurrentTime);self.d.flush()
        try:event=self.notifies.get(timeout=timeout)
        except queue.Empty:return {'timeout':True}
        if not event.property:return {'refused':True}
        value=self.window.get_full_property(self.PROPERTY,self.X.AnyPropertyType)
        return {'text':bytes(value.value).decode('utf-8','replace') if value else None}
    def decode(self,since):
        """Rebuild text from raw keycodes, tracking Shift the way a fallback buffer would."""
        from Xlib import XK
        shift=False;out=[];names=[]
        for _,pressed,code in [r for r in self.raw if r[0]>=since]:
            sym=self.d.keycode_to_keysym(code,0)
            if sym in (XK.XK_Shift_L,XK.XK_Shift_R):shift=pressed;continue
            if not pressed:continue
            value=self.d.keycode_to_keysym(code,1 if shift else 0);names.append(XK.keysym_to_string(value) or hex(value))
            if 0x20<=value<0x100:out.append(chr(value))
        return ''.join(out),names
    def focus_class(self):
        """WM_CLASS of the client toplevel holding X input focus (below Mutter's frame)."""
        window=self.d.get_input_focus().focus
        while window and not isinstance(window,int) and window.id!=self.root.id:
            parent=window.query_tree().parent
            if parent.id==self.root.id or (parent.get_wm_class() or [''])[0]=='mutter-x11-frames':return window.get_wm_class()
            window=parent
        return None
    def owner(self,selection):return self.d.get_selection_owner(selection).id
    def windows(self):
        found=[]
        def walk(window):
            for child in window.query_tree().children:
                try:
                    pid=child.get_full_property(self.atom('_NET_WM_PID'),self.X.AnyPropertyType)
                    kinds=child.get_full_property(self.atom('_NET_WM_WINDOW_TYPE'),self.X.AnyPropertyType)
                    if pid:found.append({'id':child.id,'pid':pid.value[0],'wmClass':child.get_wm_class(),'name':child.get_wm_name(),'windowType':[self.d.get_atom_name(a) for a in kinds.value] if kinds else []})
                except Exception:pass
                walk(child)
        walk(self.root);return found

# ---- fixture apps ----
class App:
    def __init__(self,kind,name,extra_env=None):
        self.kind,self.name,self.seq=kind,name,0;self.command(focus='normal')
        env=os.environ.copy()
        if kind=='swing':args=['java','-cp',str(root/'java'),'Swing',name]
        else:args=[sys.executable,str(HERE/'apps.py'),kind,name]
        if kind=='qt':env['QT_QPA_PLATFORM']='xcb'
        if kind=='gtk':env['GDK_BACKEND']='x11'
        env.update(extra_env or {});self.x11=env.get('GDK_BACKEND')!='wayland'
        self.process=spawn(name,args,env);wait(lambda:self.state()['seq']==self.seq,timeout=30)
    def state(self):return json.loads((root/f'{self.name}-state.json').read_text())
    def command(self,focus=None,**sets):
        self.seq+=1;lines=[f'seq={self.seq}',f'focus={focus or ""}',*[f'set.{k}='+base64.b64encode(v.encode()).decode() for k,v in sets.items()]]
        path=root/f'{self.name}-cmd.txt';temporary=path.with_suffix('.tmp');temporary.write_text('\n'.join(lines)+'\n');temporary.replace(path)
        if hasattr(self,'process'):wait(lambda:self.state()['seq']==self.seq)
    def activate(self,field='normal'):
        call({'action':'activate','title':self.name})
        if not self.x11:
            wait(lambda:call({})['focus']==self.name);time.sleep(.3)
            if field:self.command(focus=field);wait(lambda:self.state()['focus']==field)
            return
        wait(lambda:call({})['focus']==self.name and (lambda info,cls:cls is not None and info['pid']==self.state()['pid'] and list(cls)==[info['wmClassInstance'],info['wmClass']])(call({'action':'focusInfo'}),x.focus_class()))
        # A harmless Shift must reach XWayland before the test types anything.
        for _ in range(40):
            count=len(x.raw);keys(tap(SHIFT))
            try:wait(lambda:len(x.raw)>count,timeout=.3,interval=.01);break
            except RuntimeError:pass
        else:raise RuntimeError('Keyboard path to XWayland not ready')
        if field:self.command(focus=field);wait(lambda:self.state()['focus']==field)
    def reset(self,field='normal',text=''):self.activate(field);self.command(focus=field,**{field:text});wait(lambda:self.state()[field]==text)
    def info(self):return call({'action':'focusInfo'})

class Terminal(App):
    """xterm running rawtty.py; state is the byte stream the program received."""
    def __init__(self,name):
        self.name,self.x11,self.output=name,True,root/'xterm-bytes.json'
        self.process=spawn(name,['xterm','-T',name,'-e',sys.executable,str(HERE/'rawtty.py'),str(self.output)])
        wait(lambda:any(w['title']==name for w in call({})['windows']),timeout=30)
    def state(self):return {'pid':self.process.pid}
    def received(self):
        try:return bytes(json.loads(self.output.read_text())['bytes'])
        except FileNotFoundError:return b''
    def command(self,focus=None,**sets):pass

# ---- selection-verified replacement ----
SENTINEL='⁣waystroke-sentinel'
def codes(events):return [(pressed,x.d.keysym_to_keycode(keyval)) for keyval,pressed in events]
def align(start,ours):
    """Split raw events since `start` into ours (in order) and foreign ones.

    XWayland has one keyboard device for every Wayland source, so foreign keys
    are recognised by content. Returns foreign presses as (position, keycode),
    position being how many of our events had been delivered before it."""
    i=0;foreign=[]
    for _,pressed,code in x.raw[start:]:
        if i<len(ours) and ours[i]==(pressed,code):i+=1
        elif pressed:foreign.append((i,code))
    return i,foreign
def printable(code):
    value=x.d.keycode_to_keysym(code,0);return chr(value) if 0x20<=value<0x7f else None
def select_verified(keyword,count,timeout,during=None):
    x.own(x.PRIMARY,SENTINEL);mark=len(x.owners);raw=len(x.raw);t0=time.monotonic()
    keys(shifted(LEFT,count))
    if during:during()
    # Barrier: every selection key has reached the client once its raw event is seen.
    try:barrier=wait(lambda:x.raw[raw+2*count+1][0] if len(x.raw)>raw+2*count+1 else None,timeout=timeout,interval=.001);barrier=round((barrier-t0)*1000,1)
    except RuntimeError:barrier=None
    try:owner=wait(lambda:[o for o in x.owners[mark:] if o[1]!=x.window.id],timeout=timeout,interval=.001)[0];claimed=round((owner[0]-t0)*1000,1)
    except RuntimeError:claimed=None
    # Tk, Swing and GTK answer selection requests ahead of queued key handling,
    # so read until the selection equals the keyword. With single-code-point
    # keywords a shorter, intermediate selection can never equal it.
    primary=None;seen=[]
    while claimed is not None and barrier is not None and time.monotonic()<t0+timeout:
        primary=x.read(x.PRIMARY,timeout=max(.01,t0+timeout-time.monotonic()))
        if not seen or seen[-1]!=primary.get('text'):seen.append(primary.get('text'))
        if primary.get('text')==keyword:break
        time.sleep(.002)
    return raw,t0,{'barrierMs':barrier,'ownerMs':claimed,'selections':seen,'verifiedMs':round((time.monotonic()-t0)*1000,1),'matched':bool(primary) and primary.get('text')==keyword}
def attempt(keyword,count,replacement=None,mode='type',timeout=.3,during=None,before_edit=None,repair=True):
    """Claim PRIMARY, select back `count` positions, verify, then edit or restore.

    Claiming first forces any exporting widget to take PRIMARY again, so the
    owner change proves it processed the selection keys (Tk keeps ownership
    otherwise and sends no notification)."""
    raw,t0,r=select_verified(keyword,count,timeout,during)
    selection=codes(shifted(LEFT,count))
    if not (r['matched'] and replacement is not None):
        keys(shifted(RIGHT,count));r['action']='restored';r['foreign']=len(align(raw,selection)[1]);return r
    if before_edit:before_edit()
    # Tk's Ctrl+V inserts at the caret without replacing the selection, so
    # paste mode deletes the selection first.
    edit=typed(replacement) if mode=='type' else [*tap(BACKSPACE),*control(ord('v'))]
    if mode!='type':x.own(x.CLIPBOARD,replacement)
    keys(edit);r['action']='replaced';ours=selection+codes(edit)
    try:wait(lambda:align(raw,ours)[0]==len(ours),timeout=1,interval=.001)
    except RuntimeError:r['action']='edit not observed';return r
    time.sleep(.02);_,foreign=align(raw,ours)
    # Keys delivered after the trigger but before our edit finished landed in
    # the selection or inside the replacement; later ones are already in order.
    harmful=[(position,code) for position,code in foreign if position<len(ours)]
    r['foreign']=len(foreign);r['harmful']=len(harmful)
    if not harmful or not repair:return r
    chars=[printable(code) for _,code in harmful]
    if mode!='type' or any(position<len(selection) for position,_ in harmful) or None in chars:
        r['action']='replaced; interleaved input not repairable';return r
    # Rebuild what the client now holds from the delivery order, then
    # replace that verified span with replacement followed by the user's keys.
    region='';edits=iter(replacement);delivered=len(selection)
    marks=sorted((position,char) for (position,_),char in zip(harmful,chars))
    for index,(keyval,pressed) in enumerate(edit):
        while marks and marks[0][0]<=len(selection)+index:region+=marks.pop(0)[1]
        if pressed:region+=next(edits)
    region+=''.join(char for _,char in marks)
    fixed=attempt(region,len(region),replacement+''.join(chars),timeout=timeout,repair=False)
    r['repair']={'clientHeld':region,'typedAfter':''.join(chars),**{k:v for k,v in fixed.items() if k in('matched','action','harmful')}}
    return r
def settle(app,field,expected,timeout=3):
    try:wait(lambda:app.state()[field]==expected,timeout=timeout);return app.state()[field]
    except RuntimeError:return app.state()[field]

def suite(app):
    """Layer-2 preconditions for one XWayland toolkit."""
    r={'window':None};app.activate();r['window']=app.info()
    app.reset();since=time.monotonic();keys(typed('hi aBc'));settle(app,'normal','hi aBc')
    r['rawKeys']={'decoded':x.decode(since)[0],'text':app.state()['normal']}
    app.reset();keys(typed('hi abc'));settle(app,'normal','hi abc')
    r['typeReplace']=attempt('abc',3,'2003');r['typeReplace']['final']=settle(app,'normal','hi 2003')
    keys(tap(32));r['typeReplace']['afterSpace']=settle(app,'normal','hi 2003 ')
    keys(control(ord('z')));time.sleep(.4);r['undoAfterReplace']=app.state()['normal']
    app.reset();keys(typed('abc'));settle(app,'normal','abc')
    r['pasteReplace']=attempt('abc',3,'中文👍','paste');r['pasteReplace']['final']=settle(app,'normal','中文👍')
    app.reset();keys(typed('abc'));settle(app,'normal','abc');before=len(app.state()['activated'])
    r['enterOrder']=attempt('abc',3,'2003');keys(tap(RETURN))
    try:wait(lambda:len(app.state()['activated'])>before,timeout=3)
    except RuntimeError:pass
    r['enterOrder']['activated']=app.state()['activated'][before:]
    app.reset('password');keys(typed('abc'));settle(app,'password','abc')
    r['password']=attempt('abc',3,'2003');keys(typed('Z'));r['password']['final']=settle(app,'password','abcZ')
    app.reset();keys(typed('abd'));settle(app,'normal','abd')
    r['mismatch']=attempt('abc',3,'2003');keys(typed('Z'));r['mismatch']['final']=settle(app,'normal','abdZ')
    app.reset(text='x中文👍🏽')
    r['graphemes']=attempt('中文👍🏽',3);keys(typed('Z'));r['graphemes']['final']=settle(app,'normal','x中文👍🏽Z')
    app.reset(text='ab')
    r['lineStart']=attempt('abc',3,'2003');keys(typed('Z'));r['lineStart']['final']=settle(app,'normal','abZ')
    app.reset();keys(typed('abc'));settle(app,'normal','abc');os.kill(app.process.pid,signal.SIGSTOP)
    try:r['frozen']=attempt('abc',3,'2003')
    finally:os.kill(app.process.pid,signal.SIGCONT)
    keys(typed('Z'));r['frozen']['final']=settle(app,'normal','abcZ',timeout=5)
    app.reset();keys(typed('abc'));settle(app,'normal','abc')
    r['userTypesDuringCheck']=attempt('abc',3,'2003',during=lambda:keys(typed('x'),'keys2'),repair=False);time.sleep(.5);r['userTypesDuringCheck']['final']=app.state()['normal']
    app.reset();keys(typed('abc'));settle(app,'normal','abc')
    r['userTypesDuringCheckRepaired']=attempt('abc',3,'2003',during=lambda:keys(typed('x'),'keys2'));r['userTypesDuringCheckRepaired']['final']=settle(app,'normal','2003x')
    app.reset();keys(typed('abc'));settle(app,'normal','abc')
    r['userTypesBeforeEditRepaired']=attempt('abc',3,'2003',before_edit=lambda:keys(typed('xy'),'keys2'));r['userTypesBeforeEditRepaired']['final']=settle(app,'normal','2003xy')
    for name,count in [('graphemeRoundTrip1',1),('graphemeRoundTrip2',2)]:
        app.reset(text='x中文👍🏽');raw,_,probe=select_verified('\0',count,.15);keys(shifted(RIGHT,count));keys(typed('Z'))
        probe['final']=settle(app,'normal','x中文👍🏽Z');r[name]=probe
    timings=[]
    for _ in range(10):
        app.reset();keys(typed('abc'));settle(app,'normal','abc');t0=time.monotonic()
        result=attempt('abc',3,'2003');settle(app,'normal','2003');result['appliedMs']=round((time.monotonic()-t0)*1000,1);timings.append(result)
    r['timings']={'barrierMs':[t['barrierMs'] for t in timings],'ownerMs':[t['ownerMs'] for t in timings],'verifiedMs':[t['verifiedMs'] for t in timings],'appliedMs':[t['appliedMs'] for t in timings],'allMatched':all(t['matched'] for t in timings)}
    # Visual evidence: hold the verified selection briefly for a screenshot.
    app.reset();keys(typed('hi abc'));settle(app,'normal','hi abc')
    x.own(x.PRIMARY,SENTINEL);mark=len(x.owners);keys(shifted(LEFT,3))
    try:wait(lambda:[o for o in x.owners[mark:] if o[1]!=x.window.id],timeout=1,interval=.001)
    except RuntimeError:pass
    tag='selection-'+app.kind;call({'action':'screenshot','tag':tag})
    try:wait(lambda:(root/(tag+'.png')).stat().st_size>1000,timeout=5)
    except RuntimeError:pass
    keys(shifted(RIGHT,3));return r

# ---- AT-SPI (layer 1) ----
def a11y_bus():return Gio.DBusConnection.new_for_address_sync(os.environ['AT_SPI_BUS_ADDRESS'],Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT|Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,None,None)
def a11y_call(bus,name,path,interface,method,args=None,reply=None):return bus.call_sync(name,path,interface,method,args,GLib.VariantType(reply) if reply else None,Gio.DBusCallFlags.NONE,3000,None).unpack()
def accessible(app,field):
    """Find the app by PID on the accessibility bus, then its focused editable node."""
    bus=a11y_bus();ACC='org.a11y.atspi.Accessible'
    apps=a11y_call(bus,'org.a11y.atspi.Registry','/org/a11y/atspi/accessible/root',ACC,'GetChildren',reply='(a(so))')[0]
    match=None
    for name,path in apps:
        try:
            if a11y_call(bus,'org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','GetConnectionUnixProcessID',GLib.Variant('(s)',(name,)),'(u)')[0]==app.process.pid:match=(name,path)
        except GLib.Error:pass
    if not match:return {'registered':False}
    stack=[match];visited=0
    while stack and visited<600:
        node=stack.pop();visited+=1
        try:
            states=a11y_call(bus,*node,ACC,'GetState',reply='(au)')[0];flag=lambda bit:bool(states[bit//32]>>(bit%32)&1)
            if flag(12):
                role=a11y_call(bus,*node,ACC,'GetRoleName',reply='(s)')[0];interfaces=a11y_call(bus,*node,ACC,'GetInterfaces',reply='(as)')[0]
                out={'registered':True,'role':role,'editable':flag(7),'states':[bit for bit in range(64) if flag(bit)],'interfaces':interfaces}
                if field=='password' and 'org.a11y.atspi.Text' in interfaces:out['exposedText']=a11y_call(bus,*node,'org.a11y.atspi.Text','GetText',GLib.Variant('(ii)',(0,-1)),'(s)')[0]
                children=a11y_call(bus,*node,ACC,'GetChildren',reply='(a(so))')[0]
                if children:out['childRoles']=[a11y_call(bus,*child,ACC,'GetRoleName',reply='(s)')[0] for child in children]
                if field=='normal' and 'org.a11y.atspi.Text' in interfaces:
                    out['text']=a11y_call(bus,*node,'org.a11y.atspi.Text','GetText',GLib.Variant('(ii)',(0,-1)),'(s)')[0]
                    out['caret']=a11y_call(bus,*node,'org.freedesktop.DBus.Properties','Get',GLib.Variant('(ss)',('org.a11y.atspi.Text','CaretOffset')),'(v)')[0]
                if field=='normal' and 'org.a11y.atspi.EditableText' in interfaces:
                    out['delete']=a11y_call(bus,*node,'org.a11y.atspi.EditableText','DeleteText',GLib.Variant('(ii)',(0,3)),'(b)')[0]
                    out['insert']=a11y_call(bus,*node,'org.a11y.atspi.EditableText','InsertText',GLib.Variant('(isi)',(0,'2003',4)),'(b)')[0]
                    out['appText']=settle(app,'normal','2003')
                return out
            stack.extend(a11y_call(bus,*node,ACC,'GetChildren',reply='(a(so))')[0])
        except GLib.Error as error:return {'registered':True,'error':error.message}
    return {'registered':True,'focusedNode':False,'visited':visited}
def layer1(app):
    r={}
    app.reset();keys(typed('abc'));settle(app,'normal','abc');r['normal']=accessible(app,'normal')
    app.reset('password');keys(typed('abc'));settle(app,'password','abc');r['password']=accessible(app,'password')
    return r
def set_a11y(enabled):connection.call_sync('org.a11y.Bus','/org/a11y/bus','org.freedesktop.DBus.Properties','Set',GLib.Variant('(ssv)',('org.a11y.Status','IsEnabled',GLib.Variant('b',enabled))),None,Gio.DBusCallFlags.NONE,3000,None)

try:
    spawn('a11y-bus',['/usr/libexec/at-spi-bus-launcher','--launch-immediately','--a11y=0','--screen-reader=0'])
    def a11y_address():return connection.call_sync('org.a11y.Bus','/org/a11y/bus','org.a11y.Bus','GetAddress',None,GLib.VariantType('(s)'),Gio.DBusCallFlags.NONE,1000,None).unpack()[0]
    os.environ['AT_SPI_BUS_ADDRESS']=wait(a11y_address)
    for schema,key,value in [('org.gnome.shell','enabled-extensions',"['waystroke-probe@local']"),('org.gnome.shell','disable-user-extensions','false'),('org.gnome.desktop.interface','enable-hot-corners','false')]:subprocess.run(['gsettings','set',schema,key,value],check=True)
    spawn('shell',['gnome-shell','--headless','--wayland','--devkit',f'--wayland-display={DISPLAY_NAME}'])
    wait(lambda:call({}))
    viewer_env=os.environ.copy();viewer_env['XDG_RUNTIME_DIR']=viewer_env['WAYSTROKE_OUTER_RUNTIME'];viewer_env['WAYLAND_DISPLAY']=viewer_env['WAYSTROKE_OUTER_DISPLAY']
    spawn('viewer',['/usr/libexec/mutter-devkit'],viewer_env);wait(lambda:call({})['monitors']>0)
    # Devkit forwards clipboard data to the outer desktop; disable it first.
    import xml.etree.ElementTree as ET
    def disable_viewer_clipboard():
        base='/org/gnome/Mutter/RemoteDesktop/Session'
        xml=connection.call_sync('org.gnome.Mutter.RemoteDesktop',base,'org.freedesktop.DBus.Introspectable','Introspect',None,GLib.VariantType('(s)'),Gio.DBusCallFlags.NONE,3000,None).unpack()[0]
        paths=[base+'/'+node.attrib['name'] for node in ET.fromstring(xml).findall('node')]
        for path in paths:connection.call_sync('org.gnome.Mutter.RemoteDesktop',path,'org.gnome.Mutter.RemoteDesktop.Session','DisableClipboard',None,None,Gio.DBusCallFlags.NONE,3000,None)
        return paths
    results['clipboardForwardingDisabled']=wait(disable_viewer_clipboard)
    wait(lambda:not call({})['startingUp']);call({'action':'normal'})
    snapshot=call({});os.environ.update(DISPLAY=snapshot['xDisplay'],XAUTHORITY=snapshot['xAuthority'])
    activation=Gio.DBusConnection.new_for_address_sync(os.environ['AT_SPI_BUS_ADDRESS'],Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT|Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,None,None)
    activation.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','UpdateActivationEnvironment',GLib.Variant('(a{ss})',({name:os.environ[name] for name in ['DISPLAY','XAUTHORITY','XDG_RUNTIME_DIR']},)),None,Gio.DBusCallFlags.NONE,3000,None)
    spawn('a11y-registry',['/usr/libexec/at-spi2-registryd'])
    # Real sessions keep the user's IBus variables; X11 clients locate the
    # private daemon through this file.
    os.environ['IBUS_ADDRESS_FILE']=str(wait(lambda:next(iter((root/'config/ibus/bus').glob('*')),None)))
    x=XHelper();results['xinput']=x.version
    subprocess.run(['javac','-d',str(root/'java'),str(HERE/'Swing.java')],check=True)
    only=[arg.split('=',1)[1] for arg in sys.argv if arg.startswith('--only=')]
    selected=lambda name:not only or name in only[0].split(',')
    # A: accessibility switches. The bus starts with IsEnabled=false.
    if selected('layer1'):
        a={'isEnabledAtStart':connection.call_sync('org.a11y.Bus','/org/a11y/bus','org.freedesktop.DBus.Properties','GetAll',GLib.Variant('(s)',('org.a11y.Status',)),None,Gio.DBusCallFlags.NONE,3000,None).unpack()[0]}
        # The probe activates windows by title substring, so each app closes
        # before the next one starts.
        def checked(app):
            try:return layer1(app)
            finally:os.killpg(app.process.pid,signal.SIGTERM);wait(lambda:app.name not in [w['title'] for w in call({})['windows']])
        qt=App('qt','A11y Qt Default');a['qtDefault']=layer1(qt)
        set_a11y(True);time.sleep(1);a['qtDefaultAfterRuntimeEnable']=checked(qt)
        a['qtStatusEnabled']=checked(App('qt','A11y Qt Status'))
        set_a11y(False);time.sleep(1)
        a['qtEnvironment']=checked(App('qt','A11y Qt Env',{'QT_LINUX_ACCESSIBILITY_ALWAYS_ON':'1'}))
        a['gtkX11Reference']=checked(App('gtk','A11y GTK'))
        a['tk']=checked(App('tk','A11y Tk'))
        a['swingWithoutBridge']=checked(App('swing','A11y Swing'))
        results['layer1']=a;save()
    # B: selection-verified replacement preconditions.
    if selected('layer2'):
        b={}
        for kind in ['tk','qt','swing','gtk']:
            try:b[kind]=suite(App(kind,'Fallback '+kind.capitalize()))
            except Exception as error:b[kind]={'error':repr(error)}
            results['layer2']=b;save()
        native=App('gtk','Fallback Native',{'GDK_BACKEND':'wayland'});native.reset();count=len(x.raw)
        keys(typed('abc'));settle(native,'normal','abc');time.sleep(.3)
        b['nativeFocusRawEvents']={'text':native.state()['normal'],'rawEventsSeen':len(x.raw)-count}
        term=Terminal('Fallback XTerm');term.activate(None);keys(typed('abc'))
        wait(lambda:term.received()==b'abc',timeout=5)
        t={'window':term.info(),'attempt':attempt('abc',3,'2003')};time.sleep(.5)
        t['bytes']=term.received().decode('latin-1');t['xWindows']=[w for w in x.windows() if w['pid']==term.process.pid]
        b['xterm']=t;results['layer2']=b;save()
    # B8: what the user sees before, during and after a verified replacement.
    if selected('visual'):
        from PIL import Image
        v={}
        def shot(tag,app):
            path=root/(tag+'.png');call({'action':'screenshot','tag':tag});wait(lambda:path.stat().st_size>1000,timeout=5);time.sleep(.2)
            rect=next(w['rect'] for w in call({})['windows'] if w['title']==app.name);scale=Image.open(path).width/call({})['stageSize'][0]
            Image.open(path).crop([int(c*scale) for c in (rect['x'],rect['y'],rect['x']+rect['width'],rect['y']+rect['height'])]).save(root/(tag+'-window.png'))
        for kind in ['tk','qt','swing']:
            app=App(kind,'Visual '+kind.capitalize());app.reset();keys(typed('hi abc'));settle(app,'normal','hi abc');time.sleep(.3);shot(kind+'-1-before',app)
            _,_,held=select_verified('abc',3,1);time.sleep(.3);shot(kind+'-2-selected',app)
            keys(typed('2003'));settle(app,'normal','hi 2003');time.sleep(.3);shot(kind+'-3-after',app)
            v[kind]={'selected':held['matched'],'final':app.state()['normal']}
            os.killpg(app.process.pid,signal.SIGTERM)
        results['visual']=v;save()
    # A4: does Chromium/Electron pick native Wayland and text-input by default?
    if selected('browsers'):
        c={};(root/'fixture.txt').write_text('\n')
        variants=[('chrome-default','Fallback Chrome',['google-chrome',f'--user-data-dir={root}/chrome','--no-first-run','--no-default-browser-check','--password-store=basic','data:text/html,<title>Fallback Chrome</title><input autofocus>']),
                  ('code-default','fixture.txt',['code',f'--user-data-dir={root}/code',f'--extensions-dir={root}/code-ext','--disable-extensions','--skip-release-notes','--skip-welcome','--disable-workspace-trust','--new-window',str(root/'fixture.txt')])]
        for key,title,args in variants:
            process=spawn(key,args)
            try:
                window=wait(lambda:next((w for w in call({})['windows'] if title in w['title']),None),timeout=40)
                time.sleep(4 if key.startswith('chrome') else 10);call({'action':'activate','title':title});wait(lambda:title in (call({})['focus'] or ''));time.sleep(1)
                keys(typed('abc'));time.sleep(1);ime=call({})['ime']
                c[key]={'clientType':window['clientType'],'title':window['title'],'imeFocus':ime['hasFocus'],'surrounding':ime['surrounding'],'purpose':ime['purpose']}
            except Exception as error:c[key]={'error':repr(error)}
            finally:
                try:os.killpg(process.pid,signal.SIGTERM)
                except ProcessLookupError:pass
            time.sleep(2);results['browsers']=c;save()
    results['complete']=True
finally:
    save();print(json.dumps(results,ensure_ascii=False,indent=1)[:20000])
    for p in reversed(processes):
        try:os.killpg(p.pid,signal.SIGCONT);os.killpg(p.pid,signal.SIGTERM)
        except ProcessLookupError:pass
    # The shell can hang on exit with glamor disabled; never leave it running.
    for p in processes:
        try:p.wait(timeout=5)
        except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
