"""Selection-verified XWayland replacement for apps without accessible text.

Tk and Swing fields (fixtures from probes/xwayland-fallback) have no AT-SPI;
xterm checks the terminal list and the per-window probe limit. Keys come from
the probe's own virtual keyboard, standing in for the user's keyboard.
"""
import base64,json,os,subprocess,sys,time
from pathlib import Path



def check(REPO,root,spawn,call,core,wait,key,results):
    fixtures=REPO/'probes/xwayland-fallback'
    subprocess.run(['javac','-d',str(root/'java'),str(fixtures/'Swing.java')],check=True)
    def save(name,snippets,exclusions=()):
        snapshot=core('GetConfig');config=snapshot['config'];config['settings']['textEnabled']=True
        config['snippets']=[{'id':id,'key':k,'value':v,'enabled':True,'applicationId':None,'trigger':trigger,'caseSensitive':True,'boundary':True,'preserve':True} for id,k,v,trigger in snippets]
        config['exclusions']=list(exclusions)
        committed=core('CommitConfig',{'requestId':name,'expectedRevision':snapshot['revision'],'config':config})
        wait(lambda:call({'operation':'textInfo'})['revision']==committed['revision'])
    rules=[('abc','abc','2003','confirm'),('uni','uni','中文👍','confirm'),('imm','imm','IMMEDIATE','immediate')]
    save('selection',rules)
    def press(keyval,pressed):call({'action':'key','keyval':keyval,'pressed':pressed},False)
    focused=[]
    def typed(text):
        # Space is held by Shell until core answers; later keys would overtake
        # it, so each fixture key waits for the field to show it.
        for char in text:
            expected=focused[0].field(focused[0].active)+char if focused else None
            key(ord(char))
            if focused:
                try:wait(lambda:focused[0].field(focused[0].active)==expected)
                except RuntimeError:
                    results['selectionTypingStuck']={'expected':expected,'actual':focused[0].field(focused[0].active),'status':call({'operation':'textStatus'}),'info':call({'operation':'textInfo'}),'last':core('GetRuntime').get('lastTextResult')}
                    raise
    def control(char):press(0xffe3,True);key(ord(char));press(0xffe3,False)

    class App:
        def __init__(self,kind,name):
            self.name,self.seq=name,0;self.command(focus='normal')
            args=['java','-cp',str(root/'java'),'Swing',name] if kind=='swing' else [sys.executable,str(fixtures/'apps.py'),kind,name]
            self.process=spawn(name,args);wait(lambda:self.state()['seq']==self.seq)
        def state(self):return json.loads((root/f'{self.name}-state.json').read_text())
        def command(self,focus=None,cursor=None,**sets):
            self.seq+=1;path=root/f'{self.name}-cmd.txt'
            lines=[f'seq={self.seq}',f'focus={focus or ""}',f'cursor={cursor or ""}',*[f'set.{k}='+base64.b64encode(v.encode()).decode() for k,v in sets.items()]]
            path.with_suffix('.tmp').write_text('\n'.join(lines)+'\n');path.with_suffix('.tmp').replace(path)
            if hasattr(self,'process'):wait(lambda:self.state()['seq']==self.seq)
        def field(self,name):return self.state()[name]
        def activate(self):
            focused[:]=[self];self.active='normal'
            call({'action':'activate','title':self.name},False);wait(lambda:call({'action':'snapshot'},False)['focus']==self.name)
            wait(lambda:call({'operation':'textGuard'})['clientType']==1)
        def reset(self,field='normal',text=''):
            """Focus the field with fixed text; End also clears core's typed tail."""
            self.active=field
            # Shell replays a held Space only after the next stage frame; an
            # earlier case's replay must land before this one types.
            wait(lambda:not call({'operation':'textInfo'})['processing'])
            self.command(focus=field,**{field:''});wait(lambda:self.state()['focus']==field)
            # The first keys after activation can precede XWayland's focus.
            for _ in range(20):
                key(ord('z'))
                try:wait(lambda:self.field(field).endswith('z'));break
                except RuntimeError:pass
            self.command(focus=field,**{field:text});wait(lambda:self.field(field)==text);key(0xff57)
        def settle(self,field,expected,timeout=3):
            end=time.monotonic()+timeout
            while time.monotonic()<end and self.field(field)!=expected:time.sleep(.05)
            return self.field(field)
    def last():return core('GetRuntime').get('lastTextResult')

    tk=App('tk','Selection Tk');tk.activate()
    for confirm,symbol in [(0xff0d,'Return'),(32,'space')]:
        tk.reset();typed('abc');before=call({'operation':'textInfo'}).get('confirms') or 0;count=len(tk.state()['confirmKeys'])
        press(0xffe1,True);key(confirm);press(0xffe1,False)
        wait(lambda:len(tk.state()['confirmKeys'])>count)
        received=tk.state()['confirmKeys'][count:];assert received[0][0]==symbol and received[0][1]&1,received
        assert (call({'operation':'textInfo'}).get('confirms') or 0)==before
        assert tk.field('normal')==('abc ' if confirm==32 else 'abc')
    results['selectionShiftConfirmationsPassed']=True
    # A Space that matches nothing still waits for core before replay.
    latencies=[]
    for _ in range(10):
        tk.reset();typed('hi');tk.settle('normal','hi');start=time.monotonic();key(32)
        while tk.field('normal')!='hi ' and time.monotonic()-start<2:time.sleep(.005)
        latencies.append(round((time.monotonic()-start)*1000,1))
    results['selectionUnmatchedSpaceMs']=latencies
    status=call({'operation':'textStatus'});results['selectionStatus']=status
    assert '选区校验' in status['reason'],status
    tk.reset();typed('hi abc');tk.settle('normal','hi abc');key(32)
    results['selectionSpace']=tk.settle('normal','hi 2003 ');assert results['selectionSpace']=='hi 2003 ',results
    control('z');results['selectionUndo']=tk.settle('normal','hi abc ');assert results['selectionUndo']=='hi abc ',results
    tk.reset();before=len(tk.state()['activated']);typed('abc');tk.settle('normal','abc');key(0xff0d)
    wait(lambda:len(tk.state()['activated'])>before)
    results['selectionEnterFieldStart']=tk.state()['activated'][before:];assert results['selectionEnterFieldStart']==['2003'],results
    tk.reset();typed('hi uni');tk.settle('normal','hi uni');key(32)
    results['selectionPasteUnicode']=tk.settle('normal','hi 中文👍 ');assert results['selectionPasteUnicode']=='hi 中文👍 ',results
    for text,expected,name in [('xy','xyabc ','selectionWordBoundaryKept'),('!','!2003 ','selectionSeparatorBoundary')]:
        tk.reset(text=text);typed('abc');tk.settle('normal',text+'abc');key(32)
        results[name]=tk.settle('normal',expected);assert results[name]==expected,results
    # Text changed behind the typed tail: the selection differs and is undone.
    # Tk cannot shrink across 👍🏽 before the caret; nothing may be lost.
    for text,cursor,name in [('x中👍🏽',None,'selectionTkEmojiAtEnd'),('x👍🏽yz',2,'selectionTkEmojiMid')]:
        tk.reset();typed('abc');tk.command(focus='normal',cursor=cursor,normal=text);key(32);time.sleep(.6);key(ord('Z'));time.sleep(.4)
        results[name]=tk.field('normal');assert results[name].replace(' ','').replace('Z','')==text.replace(' ',''),results
    # Only two caret steps precede the caret: restoring three would select 'y'.
    assert results['selectionTkEmojiMid']=='x👍🏽 Zyz',results
    tk.reset('password');typed('abc');tk.settle('password','abc');key(32)
    results['selectionPasswordUnchanged']=tk.settle('password','abc ');assert results['selectionPasswordUnchanged']=='abc ',results
    tk.reset();typed('x im');tk.settle('normal','x im');key(ord('m'))
    results['selectionImmediate']=tk.settle('normal','x IMMEDIATE');assert results['selectionImmediate']=='x IMMEDIATE',results
    guard=call({'operation':'textGuard'});application=guard['applicationId'];results['selectionApplication']={'applicationId':application,'wmClass':guard['wmClass']}
    save('selection-excluded',rules,[{'applicationId':application,'gestures':False,'text':False,'compatibility':True}])
    tk.activate();tk.reset();typed('hi abc');tk.settle('normal','hi abc');key(32)
    results['selectionExcludedPassthrough']=tk.settle('normal','hi abc ');assert results['selectionExcludedPassthrough']=='hi abc ',results
    save('selection-restored',rules);tk.activate()
    # The user's next key lands before the held Space is answered, during
    # verification, or during the edit. Each outcome must be one of these, and
    # a key that overwrote an unverified selection must be reported.
    outcomes=[]
    for delay in (0,.01,.02,.03,.04,.05,.06,.08):
        tk.reset();typed('hi abc');tk.settle('normal','hi abc');previous=last()
        press(32,True);press(32,False);time.sleep(delay);key(ord('x'))
        text=tk.settle('normal','hi 2003 x',2);result=last()
        outcomes.append({'delayMs':delay*1000,'text':text,'result':result if result!=previous else None})
    results['selectionUserTypesDuringEdit']=outcomes
    for outcome in outcomes:
        assert outcome['text'] in ('hi 2003 x','hi x ','hi abcx '),outcomes
        if outcome['text']=='hi x ':assert outcome['result']['state']=='failed',outcomes

    swing=App('swing','Selection Swing');swing.activate()
    swing.reset();typed('hi abc');swing.settle('normal','hi abc');key(32)
    results['selectionSwingSpace']=swing.settle('normal','hi 2003 ');assert results['selectionSwingSpace']=='hi 2003 ',results
    control('z');results['selectionSwingUndo']=swing.settle('normal','hi abc ');assert results['selectionSwingUndo']=='hi abc ',results
    swing.reset();typed('hi uni');swing.settle('normal','hi uni');key(32)
    results['selectionSwingPaste']=swing.settle('normal','hi 中文👍 ');assert results['selectionSwingPaste']=='hi 中文👍 ',results
    swing.reset('password');typed('abc');swing.settle('password','abc');key(32)
    results['selectionSwingPassword']=swing.settle('password','abc ');assert results['selectionSwingPassword']=='abc ',results

    # A copy-only editor models the report: keyboard selection remains local.
    # Seed text plus binary/HTML formats; every verification must restore them.
    from gi.repository import Gio,GLib
    bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
    formats={'text/plain;charset=utf-8':list(b'clipboard before'),'text/html':list(b'<b>before</b>'),'application/x-waystroke-test':[0,255,1,128]}
    def clipboard(q):
        return json.loads(bus.call_sync('org.waystroke.Client','/org/waystroke/Client','org.waystroke.Client','Clipboard',GLib.Variant('(s)',(json.dumps(q),)),GLib.VariantType('(s)'),Gio.DBusCallFlags.NONE,3000,None).unpack()[0])
    def restored():
        wait(lambda:not call({'operation':'textInfo'})['processing'])
        for mime,data in formats.items():assert clipboard({'operation':'read','mime':mime})['bytes']==data,mime
    clipboard({'operation':'write','formats':formats})
    copied=App('copy-only','Selection Copy Only');copied.activate()
    results['selectionCopyOnlyClass']=call({'operation':'textGuard'})['wmClass']
    copied.reset();typed('hi abc');version=call({'operation':'clipboardVersion'})['version'];key(32)
    results['selectionCopyOnlySpace']=copied.settle('normal','hi 2003 ');assert results['selectionCopyOnlySpace']=='hi 2003 ',(results,last(),call({'operation':'textInfo'}))
    # One copy reads the keyword and its boundary: the copy plus the restore.
    restored();results['selectionCopyOnlyClipboardChanges']=call({'operation':'clipboardVersion'})['version']-version
    assert results['selectionCopyOnlyClipboardChanges']==2,results['selectionCopyOnlyClipboardChanges']
    control('z');assert copied.settle('normal','hi abc ')=='hi abc ';restored()
    copied.reset();before=len(copied.state()['activated']);typed('abc');key(0xff0d)
    wait(lambda:len(copied.state()['activated'])>before)
    results['selectionCopyOnlyFieldStart']=copied.state()['activated'][before:];assert results['selectionCopyOnlyFieldStart']==['2003'];restored()
    copied.reset();typed('hi uni');key(32)
    assert copied.settle('normal','hi 中文👍 ')=='hi 中文👍 ';restored()
    copied.reset(text='xy');typed('abc');key(32)
    assert copied.settle('normal','xyabc ')=='xyabc ';restored()
    # A stale clipboard equal to the keyword cannot pass the fresh-copy gate.
    formats['text/plain;charset=utf-8']=list(b'c');clipboard({'operation':'write','formats':formats})
    for _ in range(3):
        copied.reset('password');typed('abc');key(32);assert copied.settle('password','abc ')=='abc ';restored()
    results['selectionCopyOnlyNoExport']=last();assert last()['state']=='unsupported',last()
    results['selectionClipboardAllFormatsRestored']=True

    def terminal(name,klass):
        output=root/f'{name}.bytes';spawn(name,['xterm','-class',klass,'-T',name,'-e',sys.executable,str(fixtures/'rawtty.py'),str(output)])
        wait(lambda:any(w['title']==name for w in call({'action':'snapshot'},False)['windows']))
        call({'action':'activate','title':name},False);wait(lambda:call({'action':'snapshot'},False)['focus']==name);time.sleep(.5)
        return lambda:bytes(json.loads(output.read_text())['bytes']) if output.exists() else b''
    focused.clear()
    received=terminal('Selection XTerm','XTerm')
    for count in (1,2):typed('abc');key(32);wait(lambda:received().count(b' ')==count)
    results['selectionTerminalSkipped']=received().decode();assert received()==b'abc abc ',results['selectionTerminalSkipped']
    # A non-terminal class that exports nothing costs one Shift+Left/Right pair
    # per trigger until the window is skipped.
    received=terminal('Selection Plain','PlainX')
    for count in range(1,5):typed('abc');key(32);wait(lambda:received().count(b' ')==count)
    data=received().decode('latin-1');results['selectionNonExporting']={'bytes':data,'last':last()}
    assert data.count('\x1b[1;2D')==3 and data.count('\x1b[1;2C')==3 and data.endswith('abc '),data
    assert results['selectionNonExporting']['last']['state']=='unsupported',results['selectionNonExporting']
