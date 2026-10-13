"""Inspect/edit only disposable fixture windows on the private accessibility bus."""
import argparse,json,os
import gi
gi.require_version('Atspi','2.0')
from gi.repository import Atspi
parser=argparse.ArgumentParser();parser.add_argument('title');parser.add_argument('--replace',action='store_true');parser.add_argument('--confirm',choices=['space','enter'],default='space');args=parser.parse_args();keyword='abc ' if args.confirm=='space' else 'abc';replacement='2003 ' if args.confirm=='space' else '2003'
root=os.environ.get('WAYSTROKE_PROBE_DIR')
if not root or os.environ.get('XDG_RUNTIME_DIR')!=root+'/runtime':raise RuntimeError('Disposable session required')
Atspi.set_timeout(1500,1500)
def walk(node):
 yield node
 for i in range(node.get_child_count()):
  child=node.get_child_at_index(i)
  if child:yield from walk(child)
frames=[node for node in walk(Atspi.get_desktop(0)) if node.get_name()==args.title and node.get_role()==Atspi.Role.FRAME]
result={'title':args.title,'frames':len(frames),'nodes':[]}
for frame in frames:
 for node in walk(frame):
  states=node.get_state_set();focused=states.contains(Atspi.StateType.FOCUSED);role=node.get_role();interfaces=node.get_interfaces()
  item={'role':node.get_role_name(),'name':node.get_name(),'focused':focused,'interfaces':interfaces,'attributes':node.get_attributes()}
  if focused and role!=Atspi.Role.PASSWORD_TEXT and 'Text' in interfaces:
   text=node.get_text_iface();value=Atspi.Text.get_text(text,0,-1);cursor=Atspi.Text.get_caret_offset(text);item.update(text=value,cursor=cursor)
   if args.replace:
    if 'EditableText' not in interfaces:item['replacementError']='No EditableText interface'
    elif value[max(0,cursor-len(keyword)):cursor]!=keyword:item['replacementError']='Expected fixture keyword missing'
    else:
     editable=node.get_editable_text_iface();item['deleted']=Atspi.EditableText.delete_text(editable,cursor-len(keyword),cursor);item['inserted']=Atspi.EditableText.insert_text(editable,cursor-len(keyword),replacement,len(replacement));Atspi.Text.set_caret_offset(text,cursor-len(keyword)+len(replacement));item['after']=Atspi.Text.get_text(text,0,-1)
  elif focused and role==Atspi.Role.PASSWORD_TEXT:item['replacementError']='Password role; no text read or edit'
  result['nodes'].append(item)
print(json.dumps(result,ensure_ascii=False))
