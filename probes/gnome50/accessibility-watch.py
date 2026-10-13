"""One fixed automatic replacement, on a private test window only."""
import json,os,sys
from pathlib import Path
import gi
gi.require_version('Atspi','2.0')
from gi.repository import Atspi,GLib
root=Path(os.environ['WAYSTROKE_PROBE_DIR'])
if os.environ['XDG_RUNTIME_DIR']!=str(root/'runtime'):raise RuntimeError('Disposable session required')
title=sys.argv[1];Atspi.set_timeout(1500,1500)
log=(root/'a11y-watch.jsonl').open('w');counts={'replacements':0,'passwordSkipped':0}
def record(item):log.write(json.dumps(item,ensure_ascii=False)+'\n');log.flush()
def owned(node):
 while node:
  if node.get_role()==Atspi.Role.FRAME and node.get_name()==title:return True
  node=node.get_parent()
 return False
def inspect(node):
 if not owned(node) or not node.get_state_set().contains(Atspi.StateType.FOCUSED):return False
 if node.get_role()==Atspi.Role.PASSWORD_TEXT:
  counts['passwordSkipped']+=1;record({'event':'password-skipped','counts':dict(counts)});return False
 if 'Text' not in node.get_interfaces() or 'EditableText' not in node.get_interfaces():return False
 cursor=Atspi.Text.get_caret_offset(node)
 if cursor<4 or Atspi.Text.get_text(node,cursor-4,cursor)!='abc ':return False
 deleted=Atspi.EditableText.delete_text(node,cursor-4,cursor)
 inserted=Atspi.EditableText.insert_text(node,cursor-4,'2003 ',5)
 Atspi.Text.set_caret_offset(node,cursor+1);counts['replacements']+=1
 record({'event':'replacement','deleted':deleted,'inserted':inserted,'counts':dict(counts)});return False
def event(e):
 # Never inspect or log event.any_data, which can contain input text.
 GLib.timeout_add(50,inspect,e.source)
listener=Atspi.EventListener.new(event)
listener.register('object:text-changed')
(root/'a11y-watch-ready').write_text('ready')
Atspi.event_main()
