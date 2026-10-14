"""Real private-session lifecycle checks; no main desktop services are changed."""
import json,os,signal
from pathlib import Path
from gi.repository import Gio,GLib

def check(repo,root,processes,spawn,call,core,wait,connection,focus,reset_field,key,state,results):
    snapshot=core('GetConfig');config=snapshot['config'];config['settings']['textEnabled']=True;config['exclusions']=[]
    config['snippets']=[{'id':'lifecycle','key':'abc','value':'2003','enabled':True,'applicationId':None,'trigger':'immediate','caseSensitive':True,'boundary':True,'preserve':True}]
    saved=core('CommitConfig',{'requestId':'lifecycle','expectedRevision':snapshot['revision'],'config':config})
    wait(lambda:call({'operation':'textInfo'})['revision']==saved['revision'])
    def expand():
        focus();reset_field()
        for char in 'abc':key(ord(char))
        wait(lambda:state()['text']=='2003' and call({'operation':'textInfo'})['undo'])
    expand()
    worker=next(p for p in processes if p.args==[str(repo/'target/debug/waystroke-core')]);worker.terminate();worker.wait(timeout=5)
    wait(lambda:not call({'operation':'textInfo'})['enabled'])
    info=call({'operation':'textInfo'});assert not info['undo'] and not info['pending'] and not info['nativeExpected'];results['coreDisconnectClearsText']=True
    spawn('core-restarted',[str(repo/'target/debug/waystroke-core')]);wait(lambda:core('GetConfig'))
    wait(lambda:call({'operation':'textInfo'})['enabled']);expand();results['coreReconnectRestoresText']=True
    focus('password');wait(lambda:call({'operation':'textInfo'})['sensitive'])
    candidates=[]
    for process in Path('/proc').iterdir():
        if not process.name.isdecimal():continue
        try:
            if (process/'comm').read_text().strip()!='ibus-daemon':continue
            env=(process/'environ').read_bytes().split(b'\0')
            if ('XDG_RUNTIME_DIR='+str(root/'runtime')).encode() in env:candidates.append(int(process.name))
        except (FileNotFoundError,ProcessLookupError,PermissionError):continue
    assert len(candidates)==1,candidates
    os.kill(candidates[0],signal.SIGTERM)
    wait(lambda:not call({'operation':'textInfo'})['ibusConnected'])
    info=call({'operation':'textInfo'});assert info['sensitive'] and not info['snapshot'] and not info['undo'] and info['terminalLength']==0;results['ibusDisconnectPreservesPasswordProtection']=True
    spawn('ibus-restarted',['ibus-daemon','--panel','disable']);wait(lambda:call({'operation':'textInfo'})['ibusConnected'])
    # Refocus after the replacement input context has connected.
    focus();reset_field();expand();results['ibusReconnectRestoresText']=True
    connection.call_sync('org.gnome.ScreenSaver','/org/gnome/ScreenSaver','org.gnome.ScreenSaver','SetActive',GLib.Variant('(b)',(True,)),None,Gio.DBusCallFlags.NONE,3000,None)
    wait(lambda:core('GetRuntime')['locked'])
    runtime=core('GetRuntime');assert not runtime['text']['undoAvailable'] and runtime['text']['state']=='locked';results['actualPrivateLockDisablesText']=True
    connection.call_sync('org.gnome.ScreenSaver','/org/gnome/ScreenSaver','org.gnome.ScreenSaver','SetActive',GLib.Variant('(b)',(False,)),None,Gio.DBusCallFlags.NONE,3000,None)
    wait(lambda:not core('GetRuntime')['locked'])
    wait(lambda:call({'operation':'textInfo'})['enabled'])
    info=call({'operation':'textInfo'});assert not info['undo'] and not info['pending'] and not info['nativeExpected'];results['actualPrivateLockClearsText']=True
    expand();results['privateUnlockRestoresText']=True
