#!/usr/bin/env python3
"""Disposable XWayland text fixtures: normal and password fields, file-driven."""
import base64,json,os,sys
from pathlib import Path
kind,name=sys.argv[1],sys.argv[2];root=Path(os.environ['WAYSTROKE_PROBE_DIR'])
command=root/f'{name}-cmd.txt';state_path=root/f'{name}-state.json'
state={'seq':-1,'normal':'','password':'','focus':None,'activated':[],'pid':os.getpid()}
def read_command():
    try:lines=command.read_text().splitlines()
    except FileNotFoundError:return None
    q=dict(line.split('=',1) for line in lines if '=' in line)
    return {'seq':int(q['seq']),'focus':q.get('focus') or None,'set':{k[4:]:base64.b64decode(v).decode() for k,v in q.items() if k.startswith('set.')},'cursor':q.get('cursor') or None}
def tick(apply,snapshot):
    q=read_command()
    if q and q['seq']!=state['seq']:apply(q);state['seq']=q['seq']
    snapshot();temporary=state_path.with_suffix('.tmp');temporary.write_text(json.dumps(state,ensure_ascii=False));temporary.replace(state_path)

if kind=='qt':
    from PySide6.QtWidgets import QApplication,QWidget,QLineEdit,QVBoxLayout
    from PySide6.QtCore import QTimer
    app=QApplication(sys.argv);window=QWidget();window.setWindowTitle(name);layout=QVBoxLayout(window)
    fields={'normal':QLineEdit(),'password':QLineEdit()};fields['password'].setEchoMode(QLineEdit.EchoMode.Password)
    for key,field in fields.items():layout.addWidget(field);field.setAccessibleName(key)
    fields['normal'].returnPressed.connect(lambda:state['activated'].append(fields['normal'].text()))
    def apply(q):
        for key,value in q['set'].items():fields[key].setText(value);fields[key].end(False)
        if q['focus']:fields[q['focus']].setFocus()
    def snapshot():
        for key,field in fields.items():state[key]=field.text()
        state['focus']=next((key for key,field in fields.items() if field.hasFocus()),None)
    timer=QTimer();timer.timeout.connect(lambda:tick(apply,snapshot));timer.start(30)
    window.resize(420,140);window.show();app.exec()
elif kind in ['tk','copy-only']:
    import tkinter as tk
    window=tk.Tk(className='WeChat' if kind=='copy-only' else 'Tk');window.title(name)
    state['confirmKeys']=[]
    window.bind('<KeyPress>',lambda event:state['confirmKeys'].append([event.keysym,event.state]) if event.keysym in ['Return','space'] else None)
    fields={'normal':tk.Entry(window,width=40),'password':tk.Entry(window,width=40,show='*')}
    for field in fields.values():field.pack(padx=12,pady=10)
    if kind=='copy-only':
        for field in fields.values():field.configure(exportselection=False)
        def copy(event):
            if event.widget is fields['normal'] and event.widget.selection_present():
                window.clipboard_clear();window.clipboard_append(event.widget.get()[event.widget.index('sel.first'):event.widget.index('sel.last')])
            return 'break'
        fields['normal'].bind('<Control-c>',copy);fields['password'].bind('<Control-c>',lambda event:'break')
    fields['normal'].bind('<Return>',lambda event:state['activated'].append(fields['normal'].get()))
    def apply(q):
        for key,value in q['set'].items():
            field=fields[key];field.delete(0,'end');field.insert(0,value);field.icursor(field.index('end')-int(q['cursor'] or 0));field.selection_clear()
        if q['focus']:fields[q['focus']].focus_set()
    def snapshot():
        for key,field in fields.items():state[key]=field.get()
        focus=window.focus_get();state['focus']=next((key for key,field in fields.items() if field is focus),None)
    def loop():tick(apply,snapshot);window.after(30,loop)
    loop();window.mainloop()
elif kind=='gtk':
    import gi;gi.require_version('Gtk','4.0')
    from gi.repository import Gtk,GLib
    Gtk.init();window=Gtk.Window(title=name,default_width=420);box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
    fields={'normal':Gtk.Entry(),'password':Gtk.PasswordEntry()}
    for field in fields.values():box.append(field)
    fields['normal'].connect('activate',lambda entry:state['activated'].append(entry.get_text()))
    window.set_child(box);window.present()
    def apply(q):
        for key,value in q['set'].items():fields[key].set_text(value);fields[key].set_position(-1)
        if q['focus']:fields[q['focus']].grab_focus_without_selecting() if q['focus']=='normal' else fields[q['focus']].grab_focus()
        for key in q['set']:fields[key].set_position(-1)
    def snapshot():
        for key,field in fields.items():state[key]=field.get_text()
        focus=window.get_focus();state['focus']=next((key for key,field in fields.items() if focus and (focus is field or focus.is_ancestor(field))),None)
    def loop():tick(apply,snapshot);return True
    GLib.timeout_add(30,loop);loop_main=GLib.MainLoop();window.connect('close-request',lambda w:loop_main.quit());loop_main.run()
else:raise SystemExit('unknown fixture kind')
