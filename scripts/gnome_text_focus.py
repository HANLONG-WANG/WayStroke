"""Hold one real RPC before dispatch, then change the actual GTK field."""
from gi.repository import Gio,GLib

def check(call,core,wait,connection,key,state,results,native):
    snapshot=core('GetConfig');config=snapshot['config']
    config['settings']['textEnabled']=True;config['exclusions']=[]
    config['snippets']=[{'id':'focus','key':'abc','value':'2003','enabled':True,'applicationId':None,'trigger':'immediate','caseSensitive':True,'boundary':True,'preserve':True}]
    committed=core('CommitConfig',{'requestId':'focus-race','expectedRevision':snapshot['revision'],'config':config})
    wait(lambda:call({'operation':'textInfo'})['revision']==committed['revision'])
    if not native:wait(lambda:core('GetAccessibleTextStatus')['immediateReady'])
    def focus(field):
        generation=call({'operation':'textInfo'})['generation']
        connection.call_sync('org.waystroke.Client','/org/waystroke/Client','org.waystroke.Client','Focus',GLib.Variant('(s)',('Probe A:'+field,)),None,Gio.DBusCallFlags.NONE,3000,None)
        wait(lambda:state().get('active')==field)
        if native:wait(lambda:call({'operation':'textInfo'})['generation']!=generation)
    def control(value):
        call({'action':'key','keyval':0xffe3,'pressed':True},False);key(value);call({'action':'key','keyval':0xffe3,'pressed':False},False)
    for field in ['second','normal']:
        focus(field);control(ord('a'));key(0xff08)
        wait(lambda:state()['second' if field=='second' else 'text']=='')
        for char in 'ab':key(ord(char))
        wait(lambda:state()['second' if field=='second' else 'text']=='ab')
    before=core('GetAccessibleTextStatus')['inputKeys'] if not native else None
    call({'operation':'fixtureHoldText','method':'TestTextRule' if native else 'NoteAccessibleInput'})
    key(ord('c'));wait(lambda:call({'operation':'fixtureHeldText'}))
    focus('second');call({'operation':'fixtureReleaseText'})
    wait(lambda:not call({'operation':'fixtureHeldText'}) and not call({'operation':'textInfo'})['processing'])
    if not native:assert core('GetAccessibleTextStatus')['inputKeys']==before,'Old field input source was rebound to the new field'
    original='abc' if native else 'ab'
    assert state()['text']==original and state()['second']=='ab',state()
    results['nativeInFlightSameWindowFocusCancelled' if native else 'accessibleInFlightSameWindowFocusCancelled']=True
    key(ord('c'));wait(lambda:state()['second']=='2003')
    assert state()['text']==original,state()
    results['nativeNewFieldStillExpands' if native else 'accessibleNewFieldStillExpands']=True
    focus('normal');control(ord('a'));key(0xff08);wait(lambda:state()['text']=='')
    if native:
        for char in 'ab':key(ord(char))
        wait(lambda:state()['text']=='ab')
        call({'operation':'fixtureHoldText','method':'TestTextRule'})
        key(ord('c'))
        try:wait(lambda:call({'operation':'fixtureHeldText'}))
        except Exception:
            results['configInputFailure']={'client':state(),'text':call({'operation':'textInfo'})};raise
        for char in 'xyz':key(ord(char))
        snapshot=core('GetConfig');config=snapshot['config'];config['settings']['textEnabled']=False
        committed=core('CommitConfig',{'requestId':'config-queued-input','expectedRevision':snapshot['revision'],'config':config})
        wait(lambda:call({'operation':'textInfo'})['revision']==committed['revision'])
        call({'operation':'fixtureReleaseText'})
        wait(lambda:state()['text']=='abcxyz' and not call({'operation':'textInfo'})['processing'])
        results['nativeConfigChangePreservesQueuedRealInput']=True
