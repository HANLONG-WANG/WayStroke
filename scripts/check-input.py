#!/usr/bin/env python3
"""Installed inputd checks: preparation/release only; never grab or inject input."""
import json,socket,time,subprocess
from pathlib import Path
class Client:
    def __init__(self):
        self.socket=socket.socket(socket.AF_UNIX);self.socket.settimeout(4);self.socket.connect('/run/waystroke/control.sock');self.reader=self.socket.makefile('r');self.sequence=0;self.lease=None
        self.call({'type':'hello','version':1})
    def call(self,request):
        self.sequence+=1;self.socket.sendall((json.dumps({'requestId':self.sequence,'leaseId':self.lease,'request':request})+'\n').encode())
        while True:
            packet=json.loads(self.reader.readline())
            if packet['type']=='reply' and packet['requestId']==self.sequence:
                result=packet['result'];assert result['status']=='ok',result
                return result['value']
    def prepare(self,device):
        self.lease=self.call({'type':'acquire','deviceId':device['id']})['leaseId']
    def close(self):
        self.reader.close();self.socket.close()
def devices(lease):
    return [(path,(path/'device/name').read_text().strip()) for path in Path('/sys/class/input').glob('event*') if lease in (path/'device/name').read_text()]
def wait(condition,timeout=2):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        value=condition()
        if value:return value
        time.sleep(.02)
    raise AssertionError('Input preparation/release condition timed out')
results={'physicalGrab':False,'inputInjected':False}
client=Client()
try:
    mice=client.call({'type':'listDevices'})['devices'];assert len(mice)==1,'This host check expects exactly one relative mouse'
    mouse=mice[0];results['device']=mouse;client.prepare(mouse);lease=client.lease
    def ready():
        entries=devices(lease)
        if len(entries)!=2:return None
        properties=[]
        for path,name in entries:
            if not Path('/dev/input/'+path.name).exists():return None
            raw=subprocess.run(['udevadm','info','--query=property','--path',str(path)],capture_output=True,text=True,check=True).stdout
            if 'ID_INPUT_KEYBOARD=1' not in raw:return None
            properties.append({'name':name,'node':'/dev/input/'+path.name,'keyboard':True,'mouse':'ID_INPUT_MOUSE=1' in raw})
        return properties
    results['preparedDevices']=wait(ready);client.call({'type':'release'});wait(lambda:not devices(lease));results['explicitRelease']=True
    client.prepare(mouse);lease=client.lease;client.close();client=None;wait(lambda:not devices(lease));results['controllerDisconnectReleases']=True
    client=Client();client.prepare(mouse);lease=client.lease;began=time.monotonic();packet=json.loads(client.reader.readline());assert packet['type']=='notice' and packet['notice']['type']=='released',packet
    results['leaseTimeoutMs']=round((time.monotonic()-began)*1000,1);assert 2800<results['leaseTimeoutMs']<3500
    wait(lambda:not devices(lease));results['leaseTimeoutReleases']=True
finally:
    if client:client.close()
print(json.dumps(results,ensure_ascii=False,indent=2))
