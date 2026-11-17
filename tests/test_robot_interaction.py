from types import SimpleNamespace
import unittest
from airpresent.gestures import Gesture,GestureClassifier,Observation
from airpresent.robotics.control import Operator,hand_input
from airpresent.robotics.intent import HandVelocity
from airpresent.robotics.wire import Jog,decode
from airpresent.robotics.kinematics import simulation_dt,HOME,fk,step
from test_core import hand


class InteractionTests(unittest.TestCase):
    def test_slow_or_stalled_simulation_cannot_accumulate_wall_time_targets(self):
        self.assertEqual(simulation_dt(10.,10.),0.)
        self.assertEqual(simulation_dt(10.,9.),0.)
        self.assertEqual(simulation_dt(None,10.),0.)
        dt=simulation_dt(10.,10.005)
        point=fk(HOME);target,_=step(point,(0,.025,0),dt)
        self.assertAlmostEqual(target[1]-point[1],.000125)
        self.assertLessEqual(simulation_dt(10.,11.),.05)

    def test_edge_coordinates_stop_without_revoking_operator_permission(self):
        operator=Operator();operator.enable()
        for x in [-.001,1.01,float('nan')]:
            frame=SimpleNamespace(timestamp=1.,observation=Observation(Gesture.PINCH_NEXT,(x,.5),(.5,.5)))
            observation,age,hint=hand_input(frame,1.02)
            self.assertEqual(observation.gesture,Gesture.NONE)
            self.assertEqual(age,0);self.assertIn('边缘',hint)
            self.assertTrue(operator.snapshot()[0])

    def test_tracking_gap_does_not_revoke_permission_but_disconnect_does(self):
        operator=Operator();operator.enable()
        frame=SimpleNamespace(timestamp=1.,observation=Observation(Gesture.PINCH_NEXT,(.5,.5)))
        self.assertEqual(hand_input(frame,1.3)[0].gesture,Gesture.NONE)
        self.assertTrue(operator.snapshot()[0])
        operator.pause('连接中断：测试')
        hand_input(frame,1.01)
        self.assertFalse(operator.snapshot()[0]);self.assertIn('连接中断',operator.snapshot()[4])
        operator.enable();self.assertEqual(operator.snapshot()[4],'')

    def test_camera_gap_requires_release_before_motion_returns(self):
        motion=HandVelocity();motion.enable(True)
        opened=Observation(Gesture.PALM,(.5,.5),(.5,.5),pinch_released=True)
        pinched=Observation(Gesture.PINCH_NEXT,(.5,.5),(.5,.5),pinch_released=False)
        motion.update(opened,0);self.assertEqual(motion.phase,'ready')
        motion.update(pinched,.02);self.assertEqual(motion.phase,'confirm')
        motion.update(pinched,.16);self.assertEqual(motion.phase,'center')
        motion.update(Observation(),.18);self.assertTrue(motion.enabled)
        motion.update(pinched,.20);self.assertEqual(motion.phase,'release')
        self.assertFalse(motion.sample(.21).deadman)

    def test_palm_stability_ignores_fingertip_motion(self):
        motion=HandVelocity();motion.enable(True)
        motion.update(Observation(Gesture.PALM,(.5,.5),(.5,.5),pinch_released=True),0)
        for t,x in [(.01,.5),(.15,.6),(.17,.7)]:
            motion.update(Observation(Gesture.PINCH_NEXT,(x,.5),(.5,.5),pinch_released=False),t)
        self.assertEqual(motion.sample(.17).linear,(0.,0.,0.))
        self.assertEqual(motion.phase,'center')
        motion.update(Observation(Gesture.PINCH_NEXT,(.7,.5),(.6,.5),pinch_released=False),.19)
        self.assertGreater(motion.sample(.19).linear[0],0)

    def test_robot_index_pinch_is_not_blocked_by_nearby_middle_finger(self):
        points=hand((1,1,1,1));points[8]=(-.3,-1.6);points[12]=(-.25,-1.6);points[4]=(-.275,-1.6)
        self.assertEqual(GestureClassifier().classify(points).gesture,Gesture.UNKNOWN)
        self.assertEqual(GestureClassifier(index_only=True).classify(points).gesture,Gesture.PINCH_NEXT)

    def test_manual_press_release_and_mode_change_are_exclusive(self):
        operator=Operator();operator.enable();operator.press('y+')
        self.assertEqual(operator.snapshot()[:4],(False,'xy','buttons','y+'))
        operator.release();self.assertIsNone(operator.snapshot()[3])
        operator.enable();self.assertEqual(operator.snapshot()[:4],(True,'xy','hand',None))
        operator.plane('xz');self.assertFalse(operator.snapshot()[0]);self.assertIn('切换',operator.snapshot()[4])

    def test_authenticated_manual_direction_is_bounded_not_arbitrary_velocity(self):
        p={'token':'test','seq':1,'stamp':100.,'age_ms':0,'enabled':True,'mode':'xy','source':'buttons','jog':'z+'}
        self.assertEqual(decode(p,'test',0,100.)[3],Jog('z+'))
        p['enabled']=False;self.assertEqual(decode(p,'test',0,100.)[3],Jog(None))
        p['enabled']=True;p['jog']=[0,1,2]
        with self.assertRaises(ValueError):decode(p,'test',0,100.)

    def test_palm_is_preserved_and_validated_over_wire(self):
        p={'token':'test','seq':1,'stamp':100.,'age_ms':0,'enabled':True,'mode':'xy',
           'observation':{'gesture':Gesture.PINCH_NEXT.value,'pointer':[.7,.5],'palm':[.5,.5]}}
        self.assertEqual(decode(p,'test',0,100.)[3].palm,(.5,.5))
        p['observation']['palm']=[-1,.5]
        with self.assertRaises(ValueError):decode(p,'test',0,100.)
