"""Observe modifiers at the GTK client, after Shell/IBus and TextBridge."""
import time

def check(call,core,wait,key,state,focus,reset,results):
    snapshot=core('GetConfig');config=snapshot['config'];config['settings']['terminalTextEnabled']=True
    committed=core('CommitConfig',{'requestId':'modifiers','expectedRevision':snapshot['revision'],'config':config})
    wait(lambda:call({'operation':'textInfo'})['revision']==committed['revision'])
    try:focus()
    except Exception:
        results['modifierFocusFailure']={'snapshot':call({'action':'snapshot'},False),'textInfo':call({'operation':'textInfo'})};raise
    wait(lambda:call({'operation':'textInfo'})['snapshot'])
    results['modifierAdapterPurpose']=call({'action':'snapshot'},False)['ime']['purpose']
    if results['modifierAdapterPurpose']==0:
        plain=[]
        for word,expected in [('abc','2003'),('xyz','xyz')]:
            reset()
            for char in word:key(ord(char))
            wait(lambda:state()['text']==word)
            before=state()['activate'];key(65293)
            wait(lambda:state()['activate']>before)
            assert state()['text']==expected,(word,state())
            plain.append({'word':word,'text':state()['text']})
        results['plainConfirmations']=plain
    checks=[]
    for word in ([''] if results['modifierAdapterPurpose']==10 else ['abc','xyz']):
        for modifier,mask in [(0xffe1,1),(0xfe03,128),(0xffe3,4)]:
            for confirm in [65293,32]:
                reset()
                for char in word:key(ord(char))
                wait(lambda:state()['text']==word)
                count=len(state()['confirmKeys']);before=call({'operation':'textInfo'}).get('confirms') or 0
                event={'action':'keycode','keycode':100} if modifier==0xfe03 else {'action':'key','keyval':modifier}
                call({**event,'pressed':True},False)
                key(confirm)
                call({**event,'pressed':False},False)
                wait(lambda:len(state()['confirmKeys'])>count)
                received=state()['confirmKeys'][count:]
                observed=call({'operation':'textInfo'})['modifiers']
                assert observed['key']==confirm and observed['modifiers']&mask,(word,modifier,observed)
                # GTK4 omits Mod5 from its public modifier enum.
                assert received[0][0]==confirm and (modifier==0xfe03 or received[0][1]&mask),(word,modifier,received)
                assert (call({'operation':'textInfo'}).get('confirms') or 0)==before
                assert '2003' not in state()['text']
                checks.append({'word':word,'modifier':modifier,'received':received,'shell':observed})
    results['modifiedConfirmations']=checks
    if results['modifierAdapterPurpose']==10:return
    reset();before=call({'operation':'textInfo'}).get('confirms') or 0
    call({'action':'source','id':'us'},False);wait(lambda:call({'action':'snapshot'},False)['ime']['source']=='us')
    call({'action':'key','keyval':0xffeb,'pressed':True},False);key(32);time.sleep(.2);call({'action':'key','keyval':0xffeb,'pressed':False},False)
    wait(lambda:call({'action':'snapshot'},False)['ime']['source']=='de')
    assert (call({'operation':'textInfo'}).get('confirms') or 0)==before
    call({'action':'source','id':'us'},False);wait(lambda:call({'action':'snapshot'},False)['ime']['engine']=='xkb:us::eng')
    results['modifiedConfirmations']=checks;results['superSpaceSwitchesSource']=True
