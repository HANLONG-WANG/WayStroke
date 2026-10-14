"""Native GTK's actual Rime composition, confirmation and committed insertion."""
def check(call,core,wait,key,state,results):
    def save(name,**values):
        snapshot=core('GetConfig');config=snapshot['config'];config['settings']['textEnabled']=True;config['exclusions']=[]
        config['snippets'][0].update(values)
        committed=core('CommitConfig',{'requestId':name,'expectedRevision':snapshot['revision'],'config':config})
        wait(lambda:call({'operation':'textInfo'})['revision']==committed['revision'])
    def control(value):
        call({'action':'key','keyval':0xffe3,'pressed':True},False);key(value);call({'action':'key','keyval':0xffe3,'pressed':False},False)
    def clear():
        control(ord('a'));key(0xff08);wait(lambda:state()['text']=='')
    def compose():
        for char in 'nihao':key(ord(char))
        wait(lambda:call({'action':'snapshot'},False)['ime']['preedit'])
    clear();save('native-ime',key='你好',value='中文',trigger='confirm',preserve=False)
    call({'action':'source','id':'rime'},False);wait(lambda:call({'action':'snapshot'},False)['ime']['engine']=='rime')
    compose();assert state()['text']=='' and not call({'operation':'textInfo'})['pending']
    results['nativeGtkImePreeditProtected']=True
    key(32);wait(lambda:any(ord(c)>127 for c in state()['text']) and not call({'action':'snapshot'},False)['ime']['preedit'])
    keyword=state()['text'];results['nativeGtkImeKeyword']=keyword
    save('native-ime-keyword',key=keyword);key(32);wait(lambda:state()['text']=='中文')
    results['nativeGtkImeConfirmedExpansion']=True
    clear();save('native-ime-immediate',trigger='immediate');compose();key(32)
    wait(lambda:state()['text']=='中文');results['nativeGtkImeImmediateCommit']=True
    # Ownership must also survive IBus's asynchronous CommitText callback.
    window=call({'operation':'focusedWindow'})
    def owned_composition():
        for char in 'nihao':call({'operation':'keyInput','window':window,'key':char,'value':'按下并释放'})
        wait(lambda:call({'action':'snapshot'},False)['ime']['preedit'])
        call({'operation':'keyInput','window':window,'key':'Space','value':'按下并释放'})
        wait(lambda:any(ord(c)>127 for c in state()['text']) and not call({'action':'snapshot'},False)['ime']['preedit'])
    clear();save('learn-own-ime',key='abc');owned_composition();owned_keyword=state()['text']
    clear();save('own-ime',key=owned_keyword,value='2003');owned_composition()
    wait(lambda:state()['text']==owned_keyword);results['nativeOwnKeyboardImeInputSuppressed']=True
    call({'action':'source','id':'us'},False);wait(lambda:call({'action':'snapshot'},False)['ime']['engine']=='xkb:us::eng')
    clear();save('after-native-ime',key='abc',value='2003',trigger='immediate',preserve=True)
