"""Own native test window: mouse button counts and maximized state, no text input."""
import gi,json,sys
from pathlib import Path
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib
root=Path(sys.argv[1]);points=json.loads((root/'guide.json').read_text())
state={'rightPress':0,'rightRelease':0,'rightDown':False,'maximized':False,'closed':False}
app=Gtk.Application(application_id='io.github.waystroke.PhaseF')
def save():
    temporary=root/'client.tmp';temporary.write_text(json.dumps(state));temporary.replace(root/'client.json')
def activate(app):
    window=Gtk.ApplicationWindow(application=app,title='WayStroke F 鼠标恢复验收',default_width=900,default_height=650)
    box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,margin_top=20,margin_bottom=20,margin_start=20,margin_end=20)
    title=Gtk.Label(label='鼠标恢复验收：等待操作指引',wrap=True);box.append(title)
    box.append(Gtk.Label(label='绘制时：在本窗口按住右键，从绿点沿紫线到橙点，再松开。',wrap=True))
    area=Gtk.DrawingArea(hexpand=True,vexpand=True);box.append(area)
    def draw(area,context,width,height):
        xs=[p[0] for p in points];ys=[p[1] for p in points];scale=min((width-100)/max(max(xs)-min(xs),1),(height-100)/max(max(ys)-min(ys),1))
        path=[((x-(min(xs)+max(xs))/2)*scale+width/2,(y-(min(ys)+max(ys))/2)*scale+height/2) for x,y in points]
        context.set_source_rgb(.38,.38,.81);context.set_line_width(5);context.move_to(*path[0])
        for point in path[1:]:context.line_to(*point)
        context.stroke()
        for point,color in [(path[0],(.1,.65,.3)),(path[-1],(.95,.5,.1))]:
            context.set_source_rgb(*color);context.arc(*point,9,0,6.283185);context.fill()
    area.set_draw_func(draw)
    status=Gtk.Label();box.append(status);window.set_child(box)
    click=Gtk.GestureClick(button=3)
    def pressed(*args):state['rightPress']+=1;state['rightDown']=True;save()
    def released(*args):state['rightRelease']+=1;state['rightDown']=False;save()
    click.connect('pressed',pressed);click.connect('released',released);area.add_controller(click)
    def update():
        state['maximized']=window.is_maximized();status.set_text(f"普通右键按下/释放：{state['rightPress']} / {state['rightRelease']}    窗口最大化：{'是' if state['maximized'] else '否'}")
        phase=root/'instruction.txt'
        if phase.exists():title.set_text(phase.read_text())
        save();return True
    def close(*args):state['closed']=True;save();return False
    window.connect('close-request',close);GLib.timeout_add(100,update);window.present();save()
app.connect('activate',activate);app.run([])
