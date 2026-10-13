#!/usr/bin/python3
"""Privileged, explicitly armed mouse probe. Never reads keyboard-only input streams."""
import argparse
import collections
import json
import os
import re
import selectors
import signal
import socket
import struct
import time
from pathlib import Path

from evdev import InputDevice, UInput, ecodes as E, list_devices
from routing import Router

PREFIX = 'WayStroke Input Probe'
SOCKET = '/run/waystroke-input-probe/control.sock'


def mouse_caps(device):
    caps = device.capabilities()
    keys = caps.get(E.EV_KEY, [])
    axes = caps.get(E.EV_REL, [])
    if device.name.startswith(PREFIX):
        raise ValueError('Cannot intercept the probe virtual mouse')
    if not {E.BTN_LEFT, E.BTN_RIGHT}.issubset(keys) or not {E.REL_X, E.REL_Y}.issubset(axes):
        raise ValueError('Select a relative mouse with left and right buttons')
    absolute = caps.get(E.EV_ABS, [])
    absolute_codes = {entry[0] for entry in absolute}
    positioning_axes = {E.ABS_X, E.ABS_Y, E.ABS_MT_SLOT, E.ABS_MT_POSITION_X, E.ABS_MT_POSITION_Y}
    if absolute_codes & positioning_axes:
        raise ValueError('Absolute-position touchpads/tablets are not supported by this relative-mouse probe')
    mirrored = {E.EV_KEY: keys, E.EV_REL: axes}
    if absolute:
        mirrored[E.EV_ABS] = absolute
    return mirrored


class Server:
    def __init__(self, uid, path=SOCKET):
        self.uid = uid
        self.selector = selectors.DefaultSelector()
        self.mouse = self.virtual = self.router = None
        self.records = collections.deque(maxlen=20)
        self.serial = 0
        self.note = 'Idle; no mouse is intercepted'
        self.deadline = self.heartbeat = 0
        self.start_deadline = 0
        self.start_sequence = None
        self.owner = None
        self.running = True
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.path = Path(path)
        self.path.unlink(missing_ok=True)
        self.socket.bind(path)
        os.chmod(path, 0o600)
        os.chown(path, uid, -1)
        self.socket.listen(4)
        self.socket.setblocking(False)
        self.selector.register(self.socket, selectors.EVENT_READ, 'listener')

    def record(self, value):
        self.serial += 1
        self.records.append(dict(value, sequence=self.serial))
        if value['result'] == 'begin':
            self.start_sequence = self.serial
            self.start_deadline = time.monotonic() + .25

    def status(self):
        return {'protocolVersion': 2, 'startSequence': self.start_sequence, 'awaitingStart': bool(self.router and self.router.awaiting_start), 'armed': self.mouse is not None, 'device': self.mouse.path if self.mouse else None,
                'note': self.note, 'remaining': max(0, round(self.deadline-time.monotonic()))
                if self.mouse else 0, 'records': list(self.records), 'ownerPid': self.owner}

    def devices(self):
        found, rejected = [], []
        for path in sorted(list_devices()):
            axes_path = Path('/sys/class/input') / Path(path).name / 'device/capabilities/rel'
            if not axes_path.exists():
                continue
            axes = int(axes_path.read_text().strip().replace(' ', ''), 16)
            if axes & 3 != 3:
                continue
            device = InputDevice(path)
            try:
                mouse_caps(device)
                found.append({'path': path, 'name': device.name, 'phys': device.phys})
            except ValueError as error:
                if not device.name.startswith(PREFIX):
                    rejected.append({'path': path, 'name': device.name, 'reason': str(error)})
            finally:
                device.close()
        return {'devices': found, 'rejected': rejected}

    def disarm(self, note):
        try:
            if self.router:
                self.router.release()
        finally:
            if self.mouse:
                self.selector.unregister(self.mouse)
                # Closing the device releases EVIOCGRAB, including after an error.
                self.mouse.close()
            if self.virtual:
                self.virtual.close()
            self.mouse = self.virtual = self.router = None
            self.owner = None
            self.start_deadline = 0
            self.start_sequence = None
            self.note = note

    def arm(self, request, pid):
        if self.mouse:
            raise ValueError('A probe is already active; stop it before selecting another mouse')
        path = str(request['device'])
        if not re.fullmatch(r'/dev/input/event[0-9]+', path):
            raise ValueError('Device must be a /dev/input/eventN mouse')
        duration = int(request.get('seconds', 60))
        if not 5 <= duration <= 120:
            raise ValueError('Duration must be between 5 and 120 seconds')
        device = InputDevice(path)
        virtual = None
        try:
            caps = mouse_caps(device)
            if device.active_keys():
                raise ValueError('Release all mouse buttons before starting')
            virtual = UInput(caps, name=PREFIX, vendor=device.info.vendor,
                             product=device.info.product, version=device.info.version,
                             bustype=device.info.bustype, phys='waystroke/input-probe')
            # Allow udev/Mutter to notice the new device before exclusive interception.
            time.sleep(.5)
            device.grab()
            if device.active_keys():
                raise ValueError('Mouse button pressed during setup; release it and try again')
            self.selector.register(device, selectors.EVENT_READ, 'mouse')
        except Exception:
            device.close()
            if virtual:
                virtual.close()
            raise
        self.mouse, self.virtual = device, virtual
        self.router = Router(virtual.write, self.record, bind_start=bool(request.get('bind_start', False)))
        self.owner = pid
        self.records.clear()
        self.note = 'Active: ordinary clicks replay; drawn right-button strokes are consumed'
        self.deadline = time.monotonic() + duration
        self.heartbeat = time.monotonic() + 3
        self.record({'result': 'armed', 'device': path})

    def request(self, q, pid):
        if not isinstance(q, dict):
            raise ValueError('Request must be a JSON object')
        action = q.get('action')
        if action == 'devices':
            return self.devices()
        if action == 'status':
            return self.status()
        if action == 'arm':
            self.arm(q, pid)
        elif action == 'bound':
            if not self.mouse or pid != self.owner or q.get('sequence') != self.start_sequence:
                raise ValueError('Start binding does not belong to this client/gesture')
            self.start_deadline = 0
            self.router.acknowledge_start()
        elif action == 'poll':
            if not self.mouse:
                return self.status()
            if pid != self.owner:
                raise ValueError('This client does not own the active probe')
            self.heartbeat = time.monotonic() + 3
        elif action == 'disarm':
            self.disarm('Stopped; physical mouse released')
        else:
            raise ValueError('Unknown request')
        return self.status()

    def handle(self, connection):
        credentials = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        pid, uid, _gid = struct.unpack('3i', credentials)
        if uid != self.uid:
            raise PermissionError('Only the configured desktop user can control this probe')
        packet = connection.recv(4096)
        if not packet:
            return False
        try:
            response = self.request(json.loads(packet), pid)
        except (ValueError, OSError, KeyError, TypeError) as error:
            response = {'error': str(error)}
        connection.send(json.dumps(response).encode())
        return True

    def run(self):
        try:
            while self.running:
                for key, _ in self.selector.select(.01 if self.start_deadline else .2):
                    if key.data == 'listener':
                        connection, _ = self.socket.accept()
                        connection.setblocking(False)
                        self.selector.register(connection, selectors.EVENT_READ, 'client')
                    elif key.data == 'client':
                        try:
                            keep = self.handle(key.fileobj)
                        except (OSError, ValueError, PermissionError):
                            keep = False
                        if not keep:
                            self.selector.unregister(key.fileobj)
                            key.fileobj.close()
                    else:
                        if key.fileobj is not self.mouse:
                            continue
                        try:
                            for event in self.mouse.read():
                                self.router.feed(event.type, event.code, event.value)
                        except (OSError, RuntimeError) as error:
                            self.disarm(f'Input stopped: {error}')
                if self.mouse and self.start_deadline and time.monotonic() >= self.start_deadline:
                    self.disarm("Window binding timed out; physical mouse released")
                if self.mouse and time.monotonic() >= min(self.deadline, self.heartbeat):
                    self.disarm('Probe timeout/client disconnected; physical mouse released')
        finally:
            self.disarm('Service stopped; physical mouse released')
            for key in list(self.selector.get_map().values()):
                key.fileobj.close()
            self.selector.close()
            self.path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--uid', type=int, required=True)
    args = parser.parse_args()
    if args.uid == 0:
        parser.error('Select a non-root desktop user')
    server = Server(args.uid)
    def stop(_signum, _frame):
        server.running = False
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    server.run()


if __name__ == '__main__':
    main()
