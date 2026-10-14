"""Actual GTK TextView output, independent of the page-local test area."""
from gi.repository import Gio,GLib

def check(call,core,wait,connection,key,state,results,native):
    snapshot=core('GetConfig');config=snapshot['config'];config['settings']['textEnabled']=True;config['exclusions']=[]
    config['snippets']=[{'id':'multiline','key':'abc','value':'2003\n中文','enabled':True,'applicationId':None,'trigger':'confirm','caseSensitive':True,'boundary':True,'preserve':True}]
    committed=core('CommitConfig',{'requestId':'multiline','expectedRevision':snapshot['revision'],'config':config})
    wait(lambda:call({'operation':'textInfo'})['revision']==committed['revision'])
    def focus(field):
        generation=call({'operation':'textInfo'})['generation']
        connection.call_sync('org.waystroke.Client','/org/waystroke/Client','org.waystroke.Client','Focus',GLib.Variant('(s)',('Probe A:'+field,)),None,Gio.DBusCallFlags.NONE,3000,None)
        wait(lambda:call({'operation':'textInfo'})['generation']!=generation)
    def control(value):
        call({'action':'key','keyval':0xffe3,'pressed':True},False);key(value);call({'action':'key','keyval':0xffe3,'pressed':False},False)
    focus('multiline')
    for char in 'abc':key(ord(char))
    wait(lambda:state()['multiline']=='abc');key(32)
    wait(lambda:state()['multiline']=='2003\n中文 ')
    prefix='nativeGtk' if native else 'accessibleGtk'
    results[prefix+'Multiline']=state()['multiline']
    results[prefix+'MultilineContext']=call({'operation':'textInfo'})
    if not native:
        wait(lambda:call({'operation':'textInfo'})['accessibleUndo']);control(ord('z'))
        wait(lambda:state()['multiline']=='abc ');results[prefix+'MultilineUndo']=True
    focus('normal');control(ord('a'));key(0xff08);wait(lambda:state()['text']=='')
    snapshot=core('GetConfig');snapshot['config']['snippets'][0].update(key='abc ',value='2003',trigger='immediate')
    committed=core('CommitConfig',{'requestId':'space-keyword','expectedRevision':snapshot['revision'],'config':snapshot['config']})
    wait(lambda:call({'operation':'textInfo'})['revision']==committed['revision'])
    for char in 'abc':key(ord(char))
    wait(lambda:state()['text']=='abc');key(32);wait(lambda:state()['text']=='2003')
    results[prefix+'ImmediateSpaceKeyword']=True
    control(ord('a'));key(0xff08);wait(lambda:state()['text']=='')
    snapshot=core('GetConfig');snapshot['config']['snippets'][0].update(key='abc',value='2003',trigger='immediate')
    committed=core('CommitConfig',{'requestId':'after-multiline','expectedRevision':snapshot['revision'],'config':snapshot['config']})
    wait(lambda:call({'operation':'textInfo'})['revision']==committed['revision'])
