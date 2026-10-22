#!/usr/bin/env python3
"""Record the raw bytes a terminal program receives; fixed test input only."""
import json,os,sys,termios,tty
out=sys.argv[1];received=bytearray();tty.setraw(0)
try:
    while True:
        chunk=os.read(0,64)
        if not chunk:break
        received+=chunk
        with open(out+'.tmp','w') as f:json.dump({'bytes':list(received)},f)
        os.replace(out+'.tmp',out)
finally:termios.tcsetattr(0,termios.TCSADRAIN,termios.tcgetattr(0))
