"""A raw terminal input sink; no shell command execution from typed test text."""
import json,os,sys,termios,tty
from pathlib import Path
root=Path(sys.argv[1]) if len(sys.argv)>1 else Path(os.environ['WAYSTROKE_PROBE_DIR']);old=termios.tcgetattr(0);content=''
if len(sys.argv)>2 and sys.argv[2] in ('password','password-fast'):
 import getpass,time,threading
 def observe_fixture_echo():
  for _ in range(100):
   echo=bool(termios.tcgetattr(0)[3]&termios.ECHO)
   if not echo:
    (root/'terminal-password-ready.json').write_text(json.dumps({'ready':True,'echoEnabled':echo}));return
   time.sleep(.05)
 threading.Thread(target=observe_fixture_echo,daemon=True).start()
 value=getpass.getpass('Disposable password prompt (synthetic text only): ')
 (root/'terminal-password.json').write_text(json.dumps({'length':len(value),'echoEnabled':bool(termios.tcgetattr(0)[3]&termios.ECHO)}))
 time.sleep(0 if sys.argv[2]=='password-fast' else 20)
 sys.exit(0)
if len(sys.argv)>2 and sys.argv[2]=='readline':
 import readline,time
 (root/'terminal.json').write_text(json.dumps({'ready':True}))
 value=input('WayStroke line-editor fixture (no shell execution): ')
 (root/'terminal-line.json').write_text(json.dumps({'line':value},ensure_ascii=False))
 print('Captured fixture line; waiting for cleanup.',flush=True)
 time.sleep(20)
 sys.exit(0)
(root/'terminal.json').write_text(json.dumps({'input':content}))
print('WayStroke terminal fixture: only synthetic text, no shell commands',flush=True)
try:
 tty.setraw(0)
 while True:
  value=os.read(0,4096)
  content+=value.decode('utf-8',errors='replace');(root/'terminal.json').write_text(json.dumps({'input':content},ensure_ascii=False))
  os.write(1,value)
finally:termios.tcsetattr(0,termios.TCSANOW,old)
