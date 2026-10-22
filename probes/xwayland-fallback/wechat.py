"""Observe only a disposable WeChat instance and fixed fixture selections."""
import os,time

def check(root,spawn,call,wait,x,keys,typed,shifted,control,App):
    home=root/'wechat-home';home.mkdir()
    env=os.environ.copy();env.update(HOME=str(home),QT_QPA_PLATFORM='xcb')
    process=spawn('wechat',['/opt/wechat/wechat'],env)
    time.sleep(8)
    windows=call({})['windows']
    result={'windows':windows,'exit':process.poll()}
    call({'action':'screenshot','tag':'wechat-login'});time.sleep(1)
    result['xWindows']=x.windows()
    result['chatEditorTested']=False  # Logged-out QR screen has no editor.
    for kind in ['qt','copy-only']:
        app=App(kind,'Wechat '+kind+' selection',{'QT_QPA_PLATFORM':'xcb'})
        app.reset();keys(typed('hi abc'));wait(lambda:app.state()['normal']=='hi abc')
        x.own(x.PRIMARY,'primary-before');x.own(x.CLIPBOARD,'clipboard-before');time.sleep(.1)
        mark=len(x.owners);keys(shifted(0xff51,3));observed={}
        for delay in [.15,.85]:
            time.sleep(delay)
            observed[str(delay)]={'owners':x.owners[mark:],'primary':x.read(x.PRIMARY),'clipboard':x.read(x.CLIPBOARD)}
        keys(control(ord('c')));time.sleep(.2)
        result[kind]={'keyboard':observed,'copy':{'primary':x.read(x.PRIMARY),'clipboard':x.read(x.CLIPBOARD)}}
    return result
