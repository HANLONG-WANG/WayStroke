"""Test Return confirmation with the private X11 AT-SPI key listener."""
import json,os,sys
from pathlib import Path
import gi
gi.require_version('Atspi','2.0')
from gi.repository import Atspi
root=Path(os.environ['WAYSTROKE_PROBE_DIR'])
if os.environ['XDG_RUNTIME_DIR']!=str(root/'runtime'):raise RuntimeError('Disposable session required')
Atspi.set_timeout(500,500);title=sys.argv[1];log=(root/'a11y-enter.jsonl').open('w')
def record(q):log.write(json.dumps(q)+'\n');log.flush()
def walk(node):
 yield node
 for i in range(node.get_child_count()):
  child=node.get_child_at_index(i)
  if child:yield from walk(child)
def key(e,*_):
 record({'event':'return','type':int(e.type)})
 for frame in walk(Atspi.get_desktop(0)):
  if frame.get_role()!=Atspi.Role.FRAME or frame.get_name()!=title:continue
  for node in walk(frame):
   if not node.get_state_set().contains(Atspi.StateType.FOCUSED):continue
   if node.get_role()==Atspi.Role.PASSWORD_TEXT:record({'event':'password-skipped'});return False
   if 'EditableText' not in node.get_interfaces():continue
   cursor=Atspi.Text.get_caret_offset(node)
   if cursor==3 and Atspi.Text.get_text(node,0,3)=='abc':
    deleted=Atspi.EditableText.delete_text(node,0,3);inserted=Atspi.EditableText.insert_text(node,0,'2003',4);Atspi.Text.set_caret_offset(node,4);record({'event':'replacement','deleted':deleted,'inserted':inserted});return False
 return False
listener=Atspi.DeviceListener.new(key)
definition=Atspi.KeyDefinition();definition.keysym=0xff0d;definition.keycode=0;definition.keystring='';definition.modifiers=0
ok=Atspi.register_keystroke_listener(listener,[definition],0,1<<int(Atspi.EventType.KEY_PRESSED_EVENT),Atspi.KeyListenerSyncType.SYNCHRONOUS|Atspi.KeyListenerSyncType.CANCONSUME|Atspi.KeyListenerSyncType.ALL_WINDOWS)
(root/'a11y-enter-ready').write_text(json.dumps({'registered':ok}))
Atspi.event_main()
