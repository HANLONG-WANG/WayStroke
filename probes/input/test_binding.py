"""Ordering needed to bind the start window before subsequent pointer motion."""
import unittest
from evdev import ecodes as E
from routing import Router


class BindingTests(unittest.TestCase):
    def test_pointer_motion_and_release_wait_for_start_ack(self):
        emitted, records = [], []
        router=Router(lambda *event:emitted.append(event),records.append,bind_start=True)
        router.feed(E.EV_KEY,E.BTN_RIGHT,1)
        router.feed(E.EV_REL,E.REL_X,80)
        router.feed(E.EV_SYN,E.SYN_REPORT,0)
        router.feed(E.EV_KEY,E.BTN_RIGHT,0)
        self.assertEqual(records,[{'result':'begin'}])
        self.assertNotIn((E.EV_REL,E.REL_X,80),emitted)
        router.acknowledge_start()
        self.assertIn((E.EV_REL,E.REL_X,80),emitted)
        self.assertEqual(records[-1]['result'],'stroke')
        self.assertFalse(any(event[0]==E.EV_KEY for event in emitted))

    def test_cancel_drops_queued_click_instead_of_replaying_it(self):
        emitted=[]
        router=Router(lambda *event:emitted.append(event),lambda record:None,bind_start=True)
        router.feed(E.EV_KEY,E.BTN_RIGHT,1)
        router.feed(E.EV_KEY,E.BTN_RIGHT,0)
        router.release()
        self.assertFalse(router.awaiting_start)
        self.assertFalse(router.queued)
        self.assertFalse(any(event[0]==E.EV_KEY for event in emitted))


if __name__=='__main__':unittest.main()
