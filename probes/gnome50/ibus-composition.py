"""Record only composition visibility on the disposable IBus, never text/key data."""
import json,os
from pathlib import Path
import gi
gi.require_version('IBus','1.0')
from gi.repository import IBus,Gio,GLib
root=Path(os.environ['WAYSTROKE_PROBE_DIR'])
if os.environ['XDG_RUNTIME_DIR']!=str(root/'runtime'):raise RuntimeError('Disposable session required')
bus=IBus.Bus.new();connection=bus.get_connection();rule="type='signal',interface='org.freedesktop.IBus.InputContext',eavesdrop='true'"
accepted=bus.add_match(rule);log=(root/'ibus-composition.jsonl').open('w')
def event(_connection,_sender,path,_interface,member,args,*_):
 if member in ['UpdatePreeditText','UpdatePreeditTextWithMode']:
  value={'member':member,'context':path,'visible':args.get_child_value(2).get_boolean()}
 elif member in ['ShowPreeditText','HidePreeditText','CommitText']:
  value={'member':member,'context':path}
 else:return
 log.write(json.dumps(value)+'\n');log.flush()
def message_filter(connection,message,incoming,*_):
 if incoming and message.get_message_type()==Gio.DBusMessageType.SIGNAL and message.get_interface()=='org.freedesktop.IBus.InputContext':event(connection,message.get_sender(),message.get_path(),message.get_interface(),message.get_member(),message.get_body())
 return message
connection.add_filter(message_filter)
(root/'ibus-composition-ready').write_text(json.dumps({'matchAccepted':accepted}))
GLib.MainLoop().run()
