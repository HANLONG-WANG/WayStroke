#!/usr/bin/env python3
"""Observe core gesture events for own Probe windows; never control input."""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
from gi.repository import Gio,GLib
parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=int,default=300);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--load-on-first-stroke',action='store_true',help='Start one 30-second CPU worker after the first own Probe stroke');args=parser.parse_args()
bus=Gio.bus_get_sync(Gio.BusType.SESSION,None);loop=GLib.MainLoop();started=time.monotonic();origins={};events=[];cpu_samples=[]
def find_shell():
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            cmd=(p/'cmdline').read_bytes().decode().split('\0')
            if Path(cmd[0]).name=='gnome-shell' and '--headless' not in cmd:return p
        except (FileNotFoundError,PermissionError,IndexError):pass
    return None
shell=find_shell();last_cpu=None;last_time=None;worker=None
result={'startedAt':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'events':events,'shellCpuSamples':cpu_samples,'scope':'Own Probe windows only; no keyboard contents or input control'}
def save():
    args.output.parent.mkdir(parents=True,exist_ok=True)
    temporary=args.output.with_suffix(args.output.suffix+'.tmp');temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2));temporary.replace(args.output)
def changed(connection,sender,path,interface,signal,parameters):
    global worker
    event=json.loads(parameters.unpack()[0]);kind=event.get('event');sequence=event.get('sequence')
    if kind=='capability':
        runtime=event['runtime'];events.append({'elapsedMs':round((time.monotonic()-started)*1000,1),'event':kind,'inputArmed':runtime['inputArmed'],'locked':runtime['locked'],'selectedDeviceId':runtime['selectedDeviceId'],'devices':runtime['devices'],'reason':runtime['status']['reason']});save();print(kind,runtime['inputArmed'],runtime['locked'],flush=True);return
    if kind=='gestureStarted':
        context=event['context'];origins[sequence]=context.get('applicationId')=='org.waystroke.ProbeClient'
        if not origins[sequence]:return
        if args.load_on_first_stroke and 'load' not in result:
            affinity=os.sched_getaffinity(0);processor=int((shell/'stat').read_text().split(') ',1)[1].split()[36]) if shell else min(affinity)
            if processor not in affinity:processor=min(affinity)
            code="import time;deadline=time.monotonic()+30;value=1\nwhile time.monotonic()<deadline:value=(value*1664525+1013904223)&0xffffffff"
            worker=subprocess.Popen(['taskset','-c',str(processor),sys.executable,'-c',code])
            result['load']={'workerPid':worker.pid,'cpu':processor,'startedMs':time.monotonic()*1000,'durationSeconds':30,'scope':'One CPU worker, initially on the Shell main thread CPU; Shell affinity unchanged'}
            print('30-second CPU worker started',processor,flush=True)
    elif kind=='strokeReady':
        if not origins.get(sequence):return
    elif kind=='recognition':
        if not origins.get(event['timing']['sequence']):return
    elif kind in ['executionQueued','executionStarted','executionFinished']:
        if event['execution']['context'].get('applicationId')!='org.waystroke.ProbeClient':return
    elif kind not in ['gestureError','canceled','lock']:return
    events.append({'elapsedMs':round((time.monotonic()-started)*1000,1),**event});save()
    print(kind,sequence if sequence is not None else '',flush=True)
def sample():
    global last_cpu,last_time
    now=time.monotonic()
    if shell:
        try:
            fields=(shell/'stat').read_text().split(') ',1)[1].split();value=(int(fields[11])+int(fields[12]))/os.sysconf('SC_CLK_TCK')
            if last_cpu is not None:cpu_samples.append({'elapsedMs':round((now-started)*1000,1),'oneCorePercent':round((value-last_cpu)/(now-last_time)*100,1)})
            last_cpu=value;last_time=now
        except FileNotFoundError:loop.quit();return False
    if worker and worker.poll() is not None and 'finishedMs' not in result['load']:
        result['load']['finishedMs']=now*1000;result['load']['exitCode']=worker.returncode
    save()
    if now-started>=args.seconds:loop.quit();return False
    return True
bus.signal_subscribe('io.github.waystroke.Core','io.github.waystroke.Core1','RuntimeChanged','/io/github/waystroke/Core',None,Gio.DBusSignalFlags.NONE,changed)
GLib.timeout_add(1000,sample);save();print('Monitoring own test windows:',args.output,flush=True)
try:loop.run()
finally:
    if worker and worker.poll() is None:worker.terminate();worker.wait(timeout=5)
    save()
