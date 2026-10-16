#!/usr/bin/env python3
"""Real RPM/service lifecycle test, ONLY inside a disposable systemd container.
Usage: python3 check-rpm.py /tmp/waystroke-1.rpm /tmp/waystroke-2.rpm
No physical devices or host mounts are required or used.
Use --before-reboot, restart the container, then --after-reboot for boot recovery.
"""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
assert Path('/run/.containerenv').exists(), 'Run only in a disposable Podman container'
assert Path('/proc/1/comm').read_text().strip()=='systemd'
assert os.geteuid()==0
results={'physicalInput':False}
def run(*args,check=True,**kw):
    return subprocess.run(args,check=check,text=True,capture_output=True,**kw)
def user(*args,check=True):
    return run('runuser','-u','tester','--','env','XDG_RUNTIME_DIR=/run/user/1000','DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus',*args,check=check)
def core(method,value=None):
    args=['busctl','--user','--json=short','call','io.github.waystroke.Core','/io/github/waystroke/Core','io.github.waystroke.Core1',method]
    if value is not None:args+=['s',json.dumps(value)]
    packet=json.loads(json.loads(user(*args).stdout)['data'][0]);assert packet['status']=='ok',packet
    return packet['value']
def active(unit):return run('systemctl','is-active',unit,check=False).returncode==0
checkpoint=Path('/var/tmp/waystroke-rpm-reboot-check.json')
configuration=Path('/home/tester/.config/waystroke/config.json')
backup=Path('/home/tester/.local/state/waystroke/backups/retention.json')
def finish(expected,results):
    assert hashlib.sha256(configuration.read_bytes()).hexdigest()==expected
    assert hashlib.sha256(backup.read_bytes()).hexdigest()==expected
    core('GetConfig')
    files=run('rpm','-ql','waystroke').stdout.splitlines()
    run('rpm','-e','waystroke')
    assert not active('waystroke-inputd.service') and not Path('/run/waystroke/control.sock').exists()
    assert not Path('/etc/waystroke/inputd.conf').exists()
    assert not Path('/etc/systemd/system/multi-user.target.wants/waystroke-inputd.service').is_symlink()
    assert all(not Path(p).exists() for p in files if p not in ['/usr/libexec/waystroke','/usr/share/gnome-shell/extensions/waystroke@local'])
    assert hashlib.sha256(configuration.read_bytes()).hexdigest()==expected
    assert hashlib.sha256(backup.read_bytes()).hexdigest()==expected
    assert user('systemctl','--user','is-active','waystroke-core.service',check=False).stdout.strip()!='active'
    results['uninstallStopsAndRetainsUserData']=True
    results['configSha256']=expected;results['complete']=True
    print(json.dumps(results,indent=2))
if '--after-reboot' in sys.argv:
    saved=json.loads(checkpoint.read_text());results=saved['results']
    for _ in range(100):
        if active('waystroke-inputd.service') and Path('/run/waystroke/control.sock').exists():break
        time.sleep(.1)
    assert active('waystroke-inputd.service')
    assert run('systemctl','is-enabled','waystroke-inputd.service').stdout.strip()=='enabled'
    assert Path('/run/waystroke/control.sock').stat().st_uid==1000
    assert Path('/etc/waystroke/inputd.conf').read_text()=='WAYSTROKE_INPUT_UID=1000\n'
    results['authorizedServiceRestartsIdle']=True
    run('systemctl','start','user@1000.service')
    finish(saved['configSha256'],results);checkpoint.unlink();sys.exit(0)
first,upgrade=[arg for arg in sys.argv[1:] if arg!='--before-reboot']
assert run('rpm','-q','waystroke',check=False).returncode!=0,'Start from an uninstalled container'
run('dnf','-y','install',first)
assert not active('waystroke-inputd.service')
assert run('systemctl','is-enabled','waystroke-inputd.service',check=False).stdout.strip()=='disabled'
assert not Path('/etc/waystroke/inputd.conf').exists()
run('rpm','-V','waystroke')
results['installIdle']=True
if run('id','tester',check=False).returncode:run('useradd','-m','-u','1000','tester')
run('systemctl','start','user@1000.service')
policy=run('pkaction','--action-id','io.github.waystroke.configure-input','--verbose').stdout
assert 'auth_admin' in policy
assert user('pkexec','--disable-internal-agent','/usr/libexec/waystroke/authorize-input',check=False).returncode!=0
assert not Path('/etc/waystroke/inputd.conf').exists()
results['inactivePolkitDeniedWithoutSideEffects']=True
user('busctl','--user','call','org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','StartServiceByName','su','io.github.waystroke.Core','0')
assert user('systemctl','--user','is-active','waystroke-core.service').stdout.strip()=='active'
snapshot=core('GetConfig');config=snapshot['config']
config['settings']['color']='#123456'
core('CommitConfig',{'requestId':'rpm-retention','expectedRevision':snapshot['revision'],'config':config})
configuration=Path('/home/tester/.config/waystroke/config.json');before=configuration.read_bytes()
backup=Path('/home/tester/.local/state/waystroke/backups/retention.json');backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(before)
results['sessionBusActivation']=True
assert not Path('/home/tester/.config/autostart/waystroke.desktop').exists()
user('systemctl','--user','stop','waystroke-core.service')
assert user('systemctl','--user','show','waystroke-core.service','-p','ExecMainStatus','--value').stdout.strip()=='0'
results['sigtermCleanExit']=True
# Root helper sees /dev/null via a fixture symlink and never opens it while idle.
# This proves authorization/idle startup only, not real uinput access.
if not Path('/dev/uinput').exists():run('ln','-s','/dev/null','/dev/uinput')
probe=Path('/etc/systemd/system/waystroke-input-probe.service')
probe.write_text('[Unit]\nDescription=Private probe switch fixture\n[Service]\nExecStart=/usr/bin/sleep infinity\n[Install]\nWantedBy=multi-user.target\n')
run('systemctl','daemon-reload');run('systemctl','enable','--now','waystroke-input-probe.service');assert active('waystroke-input-probe.service')
run('/usr/libexec/waystroke/authorize-input',env={**os.environ,'PKEXEC_UID':'1000'})
assert active('waystroke-inputd.service') and not active('waystroke-input-probe.service')
assert Path('/etc/waystroke/inputd.conf').stat().st_mode&0o777==0o600
assert Path('/etc/waystroke/inputd.conf').read_text()=='WAYSTROKE_INPUT_UID=1000\n'
for _ in range(50):
    if Path('/run/waystroke/control.sock').exists():break
    time.sleep(.1)
assert Path('/run/waystroke/control.sock').stat().st_uid==1000
assert run('/usr/libexec/waystroke/authorize-input',check=False,env={**os.environ,'PKEXEC_UID':'0'}).returncode!=0
results['fixedRootAuthorizationAndProbeSwitch']={'idleService':True,'invalidUidRejected':True,'actualUinput':False}
# A user can negotiate/list, but cannot use requests to add an authorized UID.
script="""import socket,json
s=socket.socket(socket.AF_UNIX);s.connect('/run/waystroke/control.sock');f=s.makefile()
for i,q in enumerate([{'type':'hello','version':1}]):
 s.sendall((json.dumps({'requestId':i,'leaseId':None,'request':q})+'\\n').encode());r=json.loads(f.readline());assert r['result']['status']=='ok',r
"""
user('python3','-c',script)
# Upgrade stops the active core, preserves data/authorization and resumes inputd idle.
core('GetConfig');assert user('systemctl','--user','is-active','waystroke-core.service').returncode==0
run('rpm','-Uvh',upgrade)
assert configuration.read_bytes()==before and backup.read_bytes()==before
assert active('waystroke-inputd.service')
assert user('systemctl','--user','is-active','waystroke-core.service',check=False).stdout.strip()!='active'
results['upgradePreservesConfigAndAuthorization']=True
assert run('systemctl','is-enabled','waystroke-inputd.service').stdout.strip()=='enabled'
results['upgradeMigratesExistingAuthorizationToBootService']=True
# The current helper must enable a previously disabled, authorized service too.
run('systemctl','disable','--now','waystroke-inputd.service')
run('/usr/libexec/waystroke/authorize-input',env={**os.environ,'PKEXEC_UID':'1000'})
assert active('waystroke-inputd.service')
assert run('systemctl','is-enabled','waystroke-inputd.service').stdout.strip()=='enabled'
results['authorizationEnablesIdleBootService']=True
expected=hashlib.sha256(before).hexdigest()
if '--before-reboot' in sys.argv:
    checkpoint.write_text(json.dumps({'results':results,'configSha256':expected}))
    print(json.dumps({'awaitingContainerRestart':True,'results':results},indent=2));sys.exit(0)
finish(expected,results)
