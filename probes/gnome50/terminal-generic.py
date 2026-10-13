"""Fixed input fixture: no shell evaluation, record only own test outcomes."""
import json,sys,termios,tty,readline,getpass
from pathlib import Path
root=Path(sys.argv[1]);original=termios.tcgetattr(0)
for mode in ['canonical','canonical-enter','readline','password','password-enter','ime','raw']:
 termios.tcsetattr(0,termios.TCSANOW,original)
 kind=mode.split('-')[0]
 if kind in ['canonical','ime']:
  # Python input uses readline if imported, so use canonical stdin directly here.
  (root/'generic-stage').write_text(mode);print('Canonical fixture:',flush=True);value=sys.stdin.readline().rstrip('\n')
 elif kind=='readline':
  (root/'generic-stage').write_text(mode);value=input('Readline fixture: ')
 elif kind=='password':
  (root/'generic-stage').write_text(mode);value=getpass.getpass('Disposable password fixture: ')
 else:
  tty.setraw(0);(root/'generic-stage').write_text(mode);data=bytearray()
  while True:
   char=sys.stdin.buffer.read(1)
   if char in [b'\r',b'\n']:break
   data.extend(char)
  value=data.decode('utf-8',errors='replace')
 if kind=='password':result={'length':len(value),'matchesExpected':value==('2003' if mode.endswith('-enter') else '2003 ')}
 else:result={'value':value}
 (root/('generic-'+mode+'.json')).write_text(json.dumps(result))
termios.tcsetattr(0,termios.TCSANOW,original);(root/'generic-stage').write_text('complete')
import time;time.sleep(20)
