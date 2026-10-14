#!/usr/bin/env python3
"""Raster trail benchmark in a temporary GNOME extension copy; no physical input."""
import json,os,shutil,signal,subprocess,sys,tempfile,time
from pathlib import Path
from gi.repository import Gio,GLib
REPO=Path(__file__).resolve().parents[1]
if '--inside' not in sys.argv:
    source=Path(sys.argv[1]) if len(sys.argv)>1 else REPO/'extension/extension.js'
    root=Path(tempfile.mkdtemp(prefix='waystroke-trail-check-'))
    for name in ['runtime','config','data','cache']:(root/name).mkdir(mode=0o700)
    ext=root/'data/gnome-shell/extensions/waystroke@local';ext.mkdir(parents=True)
    shutil.copy(REPO/'extension/metadata.json',ext/'metadata.json')
    shutil.copy(REPO/'extension/clipboard.js',ext/'clipboard.js')
    shutil.copy(REPO/'extension/dialogs.js',ext/'dialogs.js')
    shutil.copy(REPO/'extension/system.js',ext/'system.js')
    fixture="""case 'benchmarkStart': {
        this.beginGesture({sequence:1,color:'#6262cf',trail:true,minimumLength:12,cancelTimeout:1200},this.context());
        GLib.source_remove(this.sampleTimer);this.sampleTimer=0;
        const initialLabelHidden=this.ruleLabel?!this.ruleLabel.visible:null;
        let last=GLib.get_monotonic_time(),start=last,gaps=[],frames=0,index=0,previewEvents=0;
        const originalChanged=this.changed;this.changed=value=>{if(value.event==='previewStroke')previewEvents++;originalChanged.call(this,value)};
        const paint=global.stage.connect('after-paint',()=>frames++);
        this.benchmarkTimer=GLib.timeout_add(GLib.PRIORITY_DEFAULT,8,()=>{
            const now=GLib.get_monotonic_time();gaps.push((now-last)/1000);last=now;
            this.point([300+180*Math.cos(index*.04),300+140*Math.sin(index*.04)]);index++;
            if(this.ruleLabel){this.flushPreview();this.call({operation:'previewGesture',leaseId:this.leaseId,sequence:1,text:index<120?'未匹配':'实机最大化'});}
            if(index===190&&GLib.getenv('WAYSTROKE_CAPTURE_TRAIL')==='1'){const stream=Gio.File.new_for_path(GLib.getenv('WAYSTROKE_PROBE_DIR')+'/trail.png').replace(null,false,Gio.FileCreateFlags.NONE,null);new Shell.Screenshot().screenshot(false,stream).then(()=>stream.close(null)).catch(e=>logError(e));}
            if(now-start<3000000)return GLib.SOURCE_CONTINUE;
            global.stage.disconnect(paint);this.benchmarkResult={samples:index,frames,elapsedMs:(now-start)/1000,maxGapMs:Math.max(...gaps),meanGapMs:gaps.reduce((a,b)=>a+b,0)/gaps.length,tiles:this.tiles?.size??1,previewEvents,initialLabelHidden,label:this.ruleLabel?.text??null,labelPosition:this.ruleLabel?.get_position()??null};this.changed=originalChanged;this.clearGesture();this.benchmarkResult.labelCleared=!this.ruleLabel;this.benchmarkTimer=0;return GLib.SOURCE_REMOVE;
        });return true;
    }
    case 'benchmarkResult':return this.benchmarkResult||null;
    """
    (ext/'extension.js').write_text(source.read_text().replace("case 'windows':",fixture+"case 'windows':",1))
    env=os.environ.copy();env.update(XDG_RUNTIME_DIR=str(root/'runtime'),XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),XDG_CACHE_HOME=str(root/'cache'),GSETTINGS_BACKEND='keyfile',LIBGL_ALWAYS_SOFTWARE='1',GIO_USE_VFS='local',WAYLAND_DISPLAY='waystroke-trail-check-0',WAYSTROKE_PROBE_DIR=str(root))
    env['GI_TYPELIB_PATH']=str(REPO/'target/native')+':/usr/lib64/mutter-18'
    env['LD_LIBRARY_PATH']=str(REPO/'target/native')+':/usr/lib64/mutter-18:/usr/lib64/gnome-shell'
    for key in ['DISPLAY','IBUS_ADDRESS','AT_SPI_BUS_ADDRESS']:env.pop(key,None)
    print('Trail benchmark artifacts:',root,flush=True)
    sys.exit(subprocess.run(['dbus-run-session','--',sys.executable,__file__,'--inside'],env=env).returncode)
root=Path(os.environ['WAYSTROKE_PROBE_DIR']);bus=Gio.bus_get_sync(Gio.BusType.SESSION,None);shell=None;result={}
def call(operation):
    raw=bus.call_sync('io.github.waystroke.Gnome','/io/github/waystroke/Gnome','io.github.waystroke.Gnome1','Call',GLib.Variant('(s)',(json.dumps({'operation':operation}),)),GLib.VariantType('(s)'),Gio.DBusCallFlags.NONE,1000,None).unpack()[0];reply=json.loads(raw);assert reply['status']=='ok',reply;return reply['value']
def wait(fn):
    end=time.monotonic()+15
    while time.monotonic()<end:
        try:
            value=fn()
            if value:return value
        except GLib.Error:pass
        time.sleep(.05)
    raise RuntimeError('Trail benchmark condition timed out')
def cpu():
    fields=Path(f'/proc/{shell.pid}/stat').read_text().split(') ',1)[1].split();return (int(fields[11])+int(fields[12]))/os.sysconf('SC_CLK_TCK')
try:
    subprocess.run(['gsettings','set','org.gnome.shell','enabled-extensions',"['waystroke@local']"],check=True)
    subprocess.run(['gsettings','set','org.gnome.shell','disable-user-extensions','false'],check=True)
    with (root/'shell.log').open('w') as log:shell=subprocess.Popen(['gnome-shell','--headless','--wayland','--no-x11','--wayland-display=waystroke-trail-check-0','--virtual-monitor=2560x1440'],stdout=log,stderr=log,start_new_session=True)
    wait(lambda:call('hello'));time.sleep(.5);before=cpu();call('benchmarkStart');result=wait(lambda:call('benchmarkResult'));result['shellCpuSeconds']=round(cpu()-before,3);result['softwareRendering']=True;result['physicalInput']=False
    assert result['samples']>0 and result['frames']>0,result
    if result['label'] is not None:
        assert result['initialLabelHidden'] and result['label']=='实机最大化' and result['labelCleared'],result
        assert 20<result['previewEvents']<65,result
finally:
    if shell and shell.poll() is None:os.killpg(shell.pid,signal.SIGTERM);shell.wait(timeout=5)
    (root/'results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2),flush=True)
