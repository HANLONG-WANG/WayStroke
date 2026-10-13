"""Mouse-only routing for the capability probe; no action/shape engine."""
import math
from evdev import ecodes as E


class Router:
    def __init__(self, emit, record, threshold=24, bind_start=False):
        self.emit = emit
        self.record = record
        self.threshold = threshold  # raw evdev counts, deliberately not screen pixels
        self.pending = None
        self.held = set()
        self.swallowed = set()
        self.forwarded = set()
        self.dx = self.dy = 0
        self.bind_start = bind_start
        self.awaiting_start = False
        self.queued = []

    def acknowledge_start(self):
        if not self.awaiting_start:
            raise ValueError("No start is awaiting binding")
        queued, self.queued = self.queued, []
        self.awaiting_start = False
        for event in queued:
            self.feed(*event)

    def forward(self, kind, code, value):
        self.emit(kind, code, value)
        if kind == E.EV_KEY:
            if value:
                self.forwarded.add(code)
            else:
                self.forwarded.discard(code)

    def motion_frame(self):
        if self.pending and (self.dx or self.dy):
            p = self.pending
            p['length'] += math.hypot(self.dx, self.dy)
            p['x'] += self.dx
            p['y'] += self.dy
            p['points'] += 1
        self.dx = self.dy = 0

    def feed(self, kind, code, value):
        if kind == E.EV_SYN and code == E.SYN_DROPPED:
            raise RuntimeError("Input queue overflow; releasing the mouse. Restart the probe.")
        if self.awaiting_start:
            self.queued.append((kind, code, value))
            return
        if kind == E.EV_SYN:
            if code == E.SYN_REPORT:
                self.motion_frame()
                self.forward(kind, code, value)
            return
        if kind == E.EV_REL:
            if code == E.REL_X:
                self.dx += value
            elif code == E.REL_Y:
                self.dy += value
            self.forward(kind, code, value)
            return
        if kind == E.EV_ABS:
            # Non-position axes (e.g. a gaming mouse's volume control) are passthrough.
            self.forward(kind, code, value)
            return
        if kind != E.EV_KEY:
            return
        if not E.BTN_MOUSE <= code < E.BTN_JOYSTICK:
            # Gaming mice can advertise keyboard macros on their mouse interface.
            # Preserve those source events without using them for gesture recognition.
            self.forward(kind, code, value)
            return
        if value == 2:
            return
        if code in self.swallowed:
            if value == 0:
                self.swallowed.remove(code)
                self.held.discard(code)
            return
        previously_held = bool(self.held)
        if value:
            self.held.add(code)
        else:
            self.held.discard(code)
        if code == E.BTN_RIGHT and value == 1 and not previously_held:
            self.motion_frame()
            self.pending = {'length': 0., 'x': 0, 'y': 0, 'points': 0,
                            'buttons': [], 'buffer': []}
        if self.pending:
            self.pending['buffer'].append((kind, code, value))
            if code == E.BTN_RIGHT and value == 1 and self.bind_start:
                self.forward(E.EV_SYN, E.SYN_REPORT, 0)
                self.awaiting_start = True
                self.record({'result': 'begin'})
            if code != E.BTN_RIGHT and value and code not in self.pending['buttons']:
                self.pending['buttons'].append(code)
            if code == E.BTN_RIGHT and value == 0:
                self.motion_frame()
                p = self.pending
                stroke = p['length'] >= self.threshold
                if stroke:
                    self.swallowed.update(self.held)
                else:
                    for event in p['buffer']:
                        self.forward(*event)
                        self.forward(E.EV_SYN, E.SYN_REPORT, 0)
                self.record({'result': 'stroke' if stroke else 'click',
                             'distance': round(p['length'], 1), 'dx': p['x'], 'dy': p['y'],
                             'motionFrames': p['points'], 'auxiliaryButtons': p['buttons']})
                self.pending = None
        else:
            self.forward(kind, code, value)

    def release(self):
        # Do not replay a half-finished gesture on cancellation.
        for code in list(self.forwarded):
            self.forward(E.EV_KEY, code, 0)
        self.forward(E.EV_SYN, E.SYN_REPORT, 0)
        self.pending = None
        self.awaiting_start = False
        self.queued.clear()
