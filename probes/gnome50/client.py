"""Only own GTK windows and synthetic test text; no host input monitoring."""
import json,os,gi
from pathlib import Path
from gi.repository import GLib
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,Gio
root=Path(os.environ['WAYSTROKE_PROBE_DIR']); state={};prefix=os.environ.get('WAYSTROKE_CLIENT_PREFIX','Probe')
app=Gtk.Application(application_id='org.waystroke.'+prefix+'Client')
windows=[]
def update():
 (root/('client.json' if prefix=='Probe' else prefix+'-client.json')).write_text(json.dumps(state,ensure_ascii=False));return True
def activate(app):
 for name in [prefix+' A',prefix+' B']:
  win=Gtk.ApplicationWindow(application=app,title=name,default_width=420,default_height=260)
  box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
  entry=Gtk.Entry();entry.set_name('probe-normal');entry.set_placeholder_text('Normal text')
  password=Gtk.Entry(visibility=False,input_purpose=Gtk.InputPurpose.PASSWORD);password.set_placeholder_text('Password purpose')
  box.append(entry);box.append(password);win.set_child(box)
  state[name]={'text':'','password':'','rightPress':0,'rightRelease':0,'activate':0,'activatedText':'','passwordActivate':0,'passwordActivatedLength':0}
  entry.connect('activate',lambda e,n=name:state[n].update(activate=state[n]['activate']+1,activatedText=e.get_text()))
  entry.connect('changed',lambda e,n=name:state[n].update(text=e.get_text()))
  password.connect('activate',lambda e,n=name:state[n].update(passwordActivate=state[n]['passwordActivate']+1,passwordActivatedLength=len(e.get_text())))
  password.connect('changed',lambda e,n=name:state[n].update(password=e.get_text()))
  area=Gtk.DrawingArea(hexpand=True,vexpand=True);box.append(area)
  gesture=Gtk.GestureClick(button=3)
  gesture.connect('pressed',lambda *args,n=name:state[n].update(rightPress=state[n]['rightPress']+1))
  gesture.connect('released',lambda *args,n=name:state[n].update(rightRelease=state[n]['rightRelease']+1))
  area.add_controller(gesture);win.present();entry.grab_focus();windows.append((win,entry,password))
 obj=Gio.DBusNodeInfo.new_for_xml('<node><interface name="org.waystroke.Client"><method name="Focus"><arg type="s" direction="in"/></method></interface></node>')
 def method(connection,sender,path,interface,method,parameters,invocation):
  title,kind=parameters.unpack()[0].split(':');w,e,p=next(x for x in windows if x[0].get_title()==title);(p if kind=='password' else e).grab_focus();invocation.return_value(None)
 connection=Gio.bus_get_sync(Gio.BusType.SESSION,None);connection.register_object('/org/waystroke/Client',obj.interfaces[0],method,None,None)
 Gio.bus_own_name_on_connection(connection,('org.waystroke.Client' if prefix=='Probe' else 'org.waystroke.'+prefix+'Client'),Gio.BusNameOwnerFlags.NONE,None,None)
 GLib.timeout_add(80,update)
app.connect('activate',activate);app.run([])
