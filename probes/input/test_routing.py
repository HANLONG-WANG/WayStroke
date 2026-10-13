"""Focused tests of the input routing that can otherwise disrupt mouse use."""
import unittest
from evdev import ecodes as E
from routing import Router


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.events, self.results = [], []
        self.router = Router(lambda *event: self.events.append(event), self.results.append)

    def feed(self, *events):
        for event in events:
            self.router.feed(*event)
        self.router.feed(E.EV_SYN, E.SYN_REPORT, 0)

    def test_click_replays_and_pointer_keeps_moving(self):
        self.feed((E.EV_KEY,E.BTN_RIGHT,1))
        self.assertNotIn((E.EV_KEY,E.BTN_RIGHT,1),self.events)
        self.feed((E.EV_REL,E.REL_X,2),(E.EV_REL,E.REL_Y,2))
        self.feed((E.EV_KEY,E.BTN_RIGHT,0))
        keys=[event for event in self.events if event[0]==E.EV_KEY]
        self.assertEqual(keys,[(E.EV_KEY,E.BTN_RIGHT,1),(E.EV_KEY,E.BTN_RIGHT,0)])
        self.assertIn((E.EV_REL,E.REL_X,2),self.events)
        self.assertEqual(self.results[0]['result'],'click')

    def test_stroke_consumes_buttons_including_late_auxiliary_release(self):
        self.feed((E.EV_KEY,E.BTN_RIGHT,1),(E.EV_KEY,E.BTN_SIDE,1))
        self.feed((E.EV_REL,E.REL_X,40))
        self.feed((E.EV_KEY,E.BTN_RIGHT,0))
        self.feed((E.EV_KEY,E.BTN_SIDE,0))
        self.assertFalse(any(event[0]==E.EV_KEY for event in self.events))
        self.assertEqual(self.results[0]['auxiliaryButtons'],[E.BTN_SIDE])
        self.assertEqual(self.results[0]['result'],'stroke')
        self.assertFalse(self.router.held)

    def test_mouse_keyboard_macro_is_preserved_during_stroke(self):
        self.feed((E.EV_KEY,E.BTN_RIGHT,1))
        self.feed((E.EV_KEY,E.KEY_F13,1),(E.EV_KEY,E.KEY_F13,0),(E.EV_REL,E.REL_X,40))
        self.feed((E.EV_KEY,E.BTN_RIGHT,0))
        keys=[event for event in self.events if event[0]==E.EV_KEY]
        self.assertEqual(keys,[(E.EV_KEY,E.KEY_F13,1),(E.EV_KEY,E.KEY_F13,0)])

    def test_stop_releases_forwarded_button_and_does_not_replay_pending_right(self):
        self.feed((E.EV_KEY,E.BTN_LEFT,1))
        self.router.release()
        self.assertIn((E.EV_KEY,E.BTN_LEFT,0),self.events)
        self.router = Router(lambda *event:self.events.append(event),self.results.append)
        self.feed((E.EV_KEY,E.BTN_RIGHT,1))
        self.router.release()
        self.assertNotIn((E.EV_KEY,E.BTN_RIGHT,1),self.events)


if __name__ == '__main__':
    unittest.main()
