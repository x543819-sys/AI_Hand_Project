import math
import unittest
from airpresent.gestures import Gesture, Observation
from airpresent.robotics.intent import HandVelocity


def pose(x=.5,y=.5,pinch=False):
    return Observation(Gesture.PINCH_NEXT if pinch else Gesture.UNKNOWN,(x,y),pinch_released=not pinch)


class RobotIntentTests(unittest.TestCase):
    def grab(self, m, t=0):
        m.update(pose(),t);m.update(pose(pinch=True),t+.01);m.update(pose(pinch=True),t+.14)
    def test_disabled_and_initial_contact_are_zero(self):
        m=HandVelocity();self.grab(m);self.assertFalse(m.sample(.15).deadman)
        m.enable(True)
        for i in range(10):m.update(pose(.5+i*.01,pinch=True),.2+i*.02)
        self.assertEqual(m.sample(.39).linear,(0.,0.,0.))
    def test_pinch_displacement_maps_to_bounded_velocity(self):
        m=HandVelocity();m.enable(True);self.grab(m)
        m.update(pose(.61,.39,True),.16);v=m.sample(.16)
        self.assertTrue(v.deadman);self.assertGreater(v.linear[0],0);self.assertGreater(v.linear[1],0)
        self.assertLessEqual(math.sqrt(sum(x*x for x in v.linear)),.04+1e-9)
    def test_release_and_lost_hand_stop_immediately(self):
        m=HandVelocity();m.enable(True);self.grab(m);m.update(pose(.6,.5,True),.16)
        m.update(pose(),.17);self.assertEqual(m.sample(.17).linear,(0.,0.,0.))
        self.grab(m,.2);m.update(Observation(),.35);self.assertFalse(m.sample(.35).deadman)
    def test_watchdog_requires_new_release(self):
        m=HandVelocity();m.enable(True);self.grab(m);m.update(pose(.6,.5,True),.16)
        self.assertFalse(m.sample(.5).deadman)
        m.update(pose(.7,.5,True),.51);self.assertFalse(m.sample(.51).deadman)
    def test_plane_change_disarms_and_depth_is_explicit(self):
        m=HandVelocity();m.enable(True);self.grab(m);m.set_mode('xz')
        m.update(pose(.6,.4,True),.16);self.assertFalse(m.sample(.16).deadman)
        self.grab(m,.2);m.update(pose(.6,.4,True),.36)
        self.assertEqual(m.sample(.36).linear[1],0.)
        self.assertGreater(m.sample(.36).linear[2],0.)
    def test_invalid_and_jumping_inputs_stop(self):
        m=HandVelocity();m.enable(True);self.grab(m)
        m.update(pose(.9,.1,True),.16);self.assertFalse(m.sample(.16).deadman)
        self.grab(m,.2);m.update(pose(float('nan'),.5,True),.36);self.assertFalse(m.sample(.36).deadman)
        self.grab(m,.4);self.assertFalse(m.sample(.1).deadman)
