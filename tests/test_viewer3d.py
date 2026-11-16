import math
from pathlib import Path
import unittest
from airpresent.gestures import Gesture, Observation
from airpresent.viewer3d.motion import Motion
from airpresent.viewer3d.server import Runtime


def hand(x=.5,y=.5,pinch=False):
    return Observation(Gesture.PINCH_NEXT if pinch else Gesture.UNKNOWN, (x,y), pinch_released=not pinch)


class MotionTests(unittest.TestCase):
    def setUp(self):
        self.m=Motion();self.m.enable(True)
    def grab(self, time=0):
        self.m.update(hand(),time)
        self.m.update(hand(pinch=True),time+.01)
        self.m.update(hand(pinch=True),time+.15)
    def test_initially_held_contact_cannot_move(self):
        for i in range(20):self.m.update(hand(.5+i*.01,pinch=True),i*.02)
        self.assertEqual(self.m.yaw,0)
    def test_small_pinch_drag_and_release_hold_pose(self):
        self.grab();self.m.update(hand(.6,.53,True),.2)
        self.assertAlmostEqual(self.m.yaw,.6)
        before=self.m.snapshot()
        self.m.update(hand(.8,.8),.25)
        self.m.update(hand(.2,.3),.3)
        self.assertEqual(self.m.yaw,before['yaw'])
    def test_missing_hand_and_reentry_cannot_jump(self):
        self.grab();self.m.update(hand(.55,.5,True),.2)
        yaw=self.m.yaw
        self.m.update(Observation(),.25)
        self.m.update(hand(.8,.2,True),.3)
        self.assertEqual(self.m.yaw,yaw)
        self.assertTrue(self.m.active)
    def test_tracking_jump_and_stale_gap_disarm(self):
        self.grab();self.m.update(hand(.9,.1,True),.2)
        self.assertFalse(self.m.armed)
        self.grab(.3);self.m.update(hand(.6,.5,True),1)
        self.assertFalse(self.m.armed)
    def test_switch_modes_requires_release(self):
        self.grab();self.m.set_mode('zoom');self.m.update(hand(.5,.4,True),.2)
        self.assertEqual(self.m.scale,1)
    def test_zoom_and_pan_are_bounded(self):
        self.m.set_mode('zoom');self.grab()
        for i in range(1,10):self.m.update(hand(.5,.5-i*.1,True),.15+i*.02)
        self.assertEqual(self.m.scale,3)
        self.m.set_mode('pan');self.grab(1)
        self.m.update(hand(.6,.4,True),1.2)
        self.assertAlmostEqual(self.m.pan_x,.4)
        self.assertAlmostEqual(self.m.pan_y,.4)
    def test_selection_is_once_per_hold(self):
        self.m.set_mode('select');self.grab()
        for i in range(30):self.m.update(hand(pinch=True),.2+i*.02)
        self.assertEqual(self.m.selection_id,1)
        self.grab(1);self.assertEqual(self.m.selection_id,2)
    def test_unknown_pose_can_release_and_nan_does_not_move(self):
        self.grab();self.m.update(hand(float('nan'),.5,True),.2)
        self.assertEqual(self.m.yaw,0)
        self.assertFalse(self.m.armed)


class RuntimeTests(unittest.TestCase):
    def test_startup_and_controls_do_not_open_camera(self):
        def fail(*args):raise AssertionError('camera opened')
        runtime=Runtime(Path('.'),fail)
        self.assertIsNone(runtime.worker)
        runtime.command({'action':'mode','value':'zoom'})
        with self.assertRaises(ValueError):runtime.command({'action':'enable','value':True})
        runtime.close()
    def test_invalid_config_does_not_mutate_mode(self):
        runtime=Runtime(Path('.'))
        for data in ({'action':'mode','value':'bad'}, {'action':'sensitivity','value':float('nan')},{'action':'start','camera':-1}):
            with self.assertRaises(ValueError):runtime.command(data)
        self.assertEqual(runtime.motion.mode,'rotate')
