"""Regression: G304 ABS_VOLUME must not be mistaken for absolute pointer axes."""
import unittest
from evdev import AbsInfo, ecodes as E
from daemon import mouse_caps


class Device:
    name = 'Logitech G304'
    def __init__(self, absolute):
        self.absolute = absolute
    def capabilities(self):
        return {E.EV_KEY: [E.BTN_LEFT, E.BTN_RIGHT, E.KEY_A],
                E.EV_REL: [E.REL_X, E.REL_Y, E.REL_WHEEL],
                E.EV_ABS: [(axis, AbsInfo(0, 0, 255, 0, 0, 0)) for axis in self.absolute]}


class DeviceTests(unittest.TestCase):
    def test_g304_volume_axis_is_preserved(self):
        caps = mouse_caps(Device([E.ABS_VOLUME]))
        self.assertEqual(caps[E.EV_ABS][0][0], E.ABS_VOLUME)
        self.assertIn(E.KEY_A, caps[E.EV_KEY])

    def test_absolute_pointer_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Absolute-position'):
            mouse_caps(Device([E.ABS_X, E.ABS_Y]))


if __name__ == '__main__':
    unittest.main()
