#!/usr/bin/env python3
"""Root controller ONLY for the disposable RPM test container's inputd service.
Runs the actual GNOME/core/inputd integration without exposing host input nodes.
"""
import json,os,subprocess,tempfile,time
from pathlib import Path
assert Path('/run/.containerenv').exists() and os.geteuid()==0
repo=Path(__file__).resolve().parents[1]
root=Path(tempfile.mkdtemp(prefix='waystroke-inputd-controller-'));root.chmod(0o777)
control=root/'control';log=root/'desktop.log'
subprocess.run(['systemctl','start','waystroke-inputd.service'],check=True)
with log.open('w') as output:
    process=subprocess.Popen(['runuser','-u','tester','--','env',f'WAYSTROKE_INPUTD_TEST_CONTROL={control}','XDG_RUNTIME_DIR=/run/user/1000','python3',str(repo/'scripts/check-gnome.py'),'--release','--phase-f','--phase-f-inputd'],stdout=output,stderr=subprocess.STDOUT)
    previous=None;deadline=time.monotonic()+120
    while process.poll() is None and time.monotonic()<deadline:
        if control.exists():
            command=control.read_text()
            if command!=previous:
                assert command in ['stop','start'],command
                subprocess.run(['systemctl',command,'waystroke-inputd.service'],check=True)
                previous=command
        time.sleep(.05)
    if process.poll() is None:process.terminate();process.wait(timeout=5);raise RuntimeError(f'GNOME integration timed out; see {log}')
assert process.returncode==0,log.read_text()[-6000:]
line=next(line for line in log.read_text().splitlines() if line.startswith('Desktop extension artifacts:'))
result=Path(line.split(':',1)[1].strip())/'results.json'
print(result.read_text())
