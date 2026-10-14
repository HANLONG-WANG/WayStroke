"""Formal browser text checks inside check-gnome's private mutter-devkit session."""
import json,shutil,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

def check(repo,root,spawn,call,core,wait,results,kind):
    state={};focus={'field':'normal'}
    fixture=(repo/'probes/gnome50/browser-fixture.html').read_text().replace("const events=[];let requested","let composing=false;document.addEventListener('compositionstart',()=>composing=true);document.addEventListener('compositionend',()=>composing=false);const events=[];let requested").replace('JSON.stringify({normal:', 'JSON.stringify({composing,normal:').encode()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            self.send_response(200);self.end_headers()
            self.wfile.write(json.dumps(focus).encode() if self.path=='/focus' else fixture)
        def do_POST(self):
            state.update(json.loads(self.rfile.read(int(self.headers['Content-Length']))));self.send_response(204);self.end_headers()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    def save(request_id,snapshot):
        committed=core('CommitConfig',{'requestId':request_id,'expectedRevision':snapshot['revision'],'config':snapshot['config']})
        wait(lambda:call({'operation':'textInfo'}).get('revision')==committed['revision'])
    try:
        spawn('core',[str(repo/'target/debug/waystroke-core')]);snapshot=wait(lambda:core('GetConfig'))
        snapshot['config']['snippets']=[{'id':'browser','key':'abc','value':'2003\n中文','enabled':True,'applicationId':None,'trigger':'confirm','caseSensitive':True,'boundary':True,'preserve':True}]
        save('browser',snapshot)
        wait(lambda:call({'operation':'textInfo'})['enabled'])
        wait(lambda:call({'operation':'textInfo'})['actionMode']==1)
        url=f'http://127.0.0.1:{server.server_port}/'
        if kind=='firefox':
            profile=root/'firefox-profile';profile.mkdir();(profile/'user.js').write_text('user_pref("browser.aboutwelcome.enabled",false);\nuser_pref("browser.shell.checkDefaultBrowser",false);\nuser_pref("datareporting.policy.firstRunURL","");\nuser_pref("browser.startup.homepage_override.mstone","ignore");\n')
            spawn('firefox',['firefox','--no-remote','--profile',str(profile),url])
        else:
            runtime=root/'electron';runtime.mkdir()
            for item in Path('/usr/share/code').iterdir():
                if item.name not in ['code','resources']:(runtime/item.name).symlink_to(item)
            shutil.copy2('/usr/share/code/code',runtime/'electron');appdir=runtime/'resources/app';appdir.mkdir(parents=True)
            (appdir/'package.json').write_text(json.dumps({'name':'waystroke-input-fixture','version':'1.0.0','main':'main.js'}))
            (appdir/'main.js').write_text("const {app,BrowserWindow}=require('electron');app.whenReady().then(()=>{const w=new BrowserWindow({width:1100,height:750,webPreferences:{sandbox:true}});w.loadURL(%s);});" % json.dumps(url))
            spawn('electron',[str(runtime/'electron'),'--ozone-platform=wayland','--enable-wayland-ime','--wayland-text-input-version=3'])
        wait(lambda:state.get('active')=='normal')
        call({'action':'activate','title':'WayStroke compatibility fixture'},False)
        wait(lambda:call({'action':'snapshot'},False)['focus'] and call({'action':'snapshot'},False)['focus'].startswith('WayStroke compatibility fixture'))
        def key(value):
            for pressed in [True,False]:call({'action':'key','keyval':value,'pressed':pressed},False)
        def type_text(text):
            for char in text:key(ord(char));time.sleep(.025)
        def control(value):
            call({'action':'key','keyval':0xffe3,'pressed':True},False);key(value);call({'action':'key','keyval':0xffe3,'pressed':False},False)
        def clear(field):
            control(ord('a'));key(0xff08)
            wait(lambda:state.get(field)=='')
        focus['field']='multiline';wait(lambda:state.get('active')=='multiline')
        wait(lambda:call({'action':'snapshot'},False)['ime']['hasFocus'])
        type_text('abc');wait(lambda:state.get('multiline')=='abc')
        results['beforeFirstConfirm']={'shell':call({'action':'snapshot'},False)['ime'],'text':call({'operation':'textInfo'})}
        key(32);wait(lambda:state.get('multiline')=='2003\n中文 ')
        results[kind+'MultilineConfirm']=dict(state)
        clear('multiline')
        snapshot=core('GetConfig');snapshot['config']['snippets'][0].update(value='2003')
        save('browser-single-line',snapshot)
        type_text('abc ');wait(lambda:state.get('multiline')=='2003 ')
        wait(lambda:call({'operation':'textInfo'})['undo']);control(ord('z'));wait(lambda:state.get('multiline')=='abc ')
        results[kind+'AdjacentUndo']=True
        clear('multiline')
        snapshot=core('GetConfig');snapshot['config']['snippets'][0].update(trigger='immediate')
        save('browser-immediate',snapshot)
        type_text('abc');wait(lambda:state.get('multiline')=='2003');results[kind+'Immediate']=True
        clear('multiline')
        snapshot=core('GetConfig');snapshot['config']['snippets'][0].update(key='你好',trigger='confirm',preserve=False)
        save('browser-ime',snapshot)
        call({'action':'source','id':'rime'},False);wait(lambda:call({'action':'snapshot'},False)['ime']['engine']=='rime')
        type_text('nihao');wait(lambda:call({'action':'snapshot'},False)['ime']['preedit'])
        assert '2003' not in state.get('multiline','') and not call({'operation':'textInfo'})['pending']
        results[kind+'ImePreeditProtected']=True
        key(32);wait(lambda:not state.get('composing',True) and any(ord(char)>127 for char in state.get('multiline','')))
        wait(lambda:not call({'action':'snapshot'},False)['ime']['preedit'])
        committed=state['multiline'];results[kind+'ImeCommittedKeyword']=committed
        snapshot=core('GetConfig');snapshot['config']['snippets'][0]['key']=committed
        save('browser-ime-keyword',snapshot)
        assert not call({'operation':'textInfo'})['pending'];results[kind+'ImeConsumedConfirmation']=True
        key(32);wait(lambda:state.get('multiline')=='2003');results[kind+'ImeConfirmedExpansion']=True
        clear('multiline')
        snapshot=core('GetConfig');snapshot['config']['snippets'][0].update(trigger='immediate')
        save('browser-ime-immediate',snapshot)
        type_text('nihao');wait(lambda:call({'action':'snapshot'},False)['ime']['preedit']);key(32)
        wait(lambda:state.get('multiline')=='2003');results[kind+'ImeImmediateCommit']=True
        call({'action':'source','id':'us'},False);wait(lambda:call({'action':'snapshot'},False)['ime']['source']=='us')
        snapshot=core('GetConfig');snapshot['config']['snippets'][0].update(key='abc',preserve=True)
        save('browser-ascii',snapshot)
        focus['field']='password';wait(lambda:state.get('active')=='password')
        wait(lambda:call({'action':'snapshot'},False)['ime']['purpose']==8)
        type_text('abc ');wait(lambda:state.get('passwordLength')==4);assert not call({'operation':'textInfo'})['undo'];results[kind+'PasswordSkipped']=True
        focus['field']='editable';wait(lambda:state.get('active')=='editable')
        clear('editable')
        type_text('abc');wait(lambda:state.get('editable')=='2003');results[kind+'ContentEditable']=True
        results['complete']=True
    except Exception:
        results['browserOnFailure']=dict(state);results['inputOnFailure']=call({'action':'snapshot'},False);results['textOnFailure']=call({'operation':'textInfo'});results['runtimeOnFailure']=core('GetRuntime');raise
    finally:server.shutdown();server.server_close()
