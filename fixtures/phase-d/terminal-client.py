"""Only disposable input; no shell evaluation or real credentials."""
import getpass,json,readline,sys,termios,tty
from pathlib import Path
root=Path(sys.argv[1]);original=termios.tcgetattr(0)
for mode in ['canonical-space','canonical-enter','readline','password-space','password-enter','immediate','space-keyword','consume-space','undo','navigation','focus-boundary','space-only','enter-only','consume-enter','disabled','excluded','generated','generated-keyboard','ime','ime-confirm','ime-immediate','paste-middle','paste-external','raw']:
    termios.tcsetattr(0,termios.TCSANOW,original)
    (root/'terminal-stage').write_text(mode)
    print('WayStroke fixed input fixture: '+mode,flush=True)
    if mode.startswith('password'):
        value=getpass.getpass('Disposable password fixture: ')
        result={'length':len(value),'matchesExpected':value==('2003 ' if mode.endswith('space') else '2003')}
    elif mode in ['readline','navigation','focus-boundary','undo']:
        value=input('Readline: ');result={'value':value}
    elif mode=='raw':
        tty.setraw(0);data=bytearray()
        while True:
            byte=sys.stdin.buffer.read(1)
            if byte in [b'\r',b'\n']:break
            data.extend(byte)
        result={'bytes':list(data)}
    else:
        value=sys.stdin.readline().rstrip('\n');result={'value':value}
    path=root/('terminal-'+mode+'.json');temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(result));temporary.replace(path)
termios.tcsetattr(0,termios.TCSANOW,original)
(root/'terminal-stage').write_text('complete')
import time
time.sleep(20)
