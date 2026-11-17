import json
import math
import time
import unittest
from airpresent.robotics.kinematics import HOME,LIMITS,fk,ik,step
from airpresent.robotics.wire import decode
from unittest.mock import patch
from airpresent.robotics.wire import Client
from airpresent.gestures import Observation


class ArmKinematicsTests(unittest.TestCase):
    def test_fk_ik_roundtrip_without_branch_flips(self):
        for yaw in [-.4,0,.4]:
            for shoulder in [.4,.65,.9]:
                q=(yaw,shoulder,-1.2);point=fk(q);found=ik(point)
                if .14<=point[2]<=.60 and .2<=math.hypot(*point[:2])<=.49:
                    self.assertIsNotNone(found)
                    self.assertLess(math.dist(q,found),1e-8)
    def test_workspace_and_invalid_points_are_rejected(self):
        for point in [(2,0,.2),(.3,0,-.1),(float('nan'),0,.2),(0,0,.4)]:self.assertIsNone(ik(point))
        self.assertIsNotNone(ik(fk(HOME)))
    def test_small_bounded_cartesian_step(self):
        p=fk(HOME);desired,q=step(p,(0,.02,0),.05)
        self.assertAlmostEqual(desired[1],.001)
        self.assertLess(math.dist(fk(q),desired),1e-8)
        self.assertIsNone(step(p,(0,.02,0),2))


class WireTests(unittest.TestCase):
    def packet(self):
        return {'token':'test-session','seq':1,'stamp':100.,'age_ms':20,'enabled':True,'mode':'xy',
                'observation':{'gesture':'调整手势','pointer':[.5,.5],'released':True}}
    def test_valid_packet_and_hello(self):
        self.assertEqual(decode(self.packet(),'test-session',0,100.)[0],1)
        self.assertIsNone(decode({'token':'test-session','hello':True},'test-session',0,100.))
    def test_replay_auth_age_and_numbers_are_rejected(self):
        for key,value in [('token','wrong'),('seq',0),('stamp',90.),('stamp',float('nan')),('age_ms',300),('enabled','true'),('mode','bad')]:
            p=self.packet();p[key]=value
            with self.assertRaises(ValueError):decode(p,'test-session',0,100.)
    def test_nonfinite_or_outside_points_are_rejected(self):
        for point in [[float('nan'),.5],[2,.5],[.5],['x',.5]]:
            p=self.packet();p['observation']['pointer']=point
            with self.assertRaises(ValueError):decode(p,'test-session',0,100.)

    def test_clock_refresh_tracks_vm_drift_but_ignores_slow_responses(self):
        client=Client.__new__(Client);client.seq=0;client.token='test-session';client.offset=80.
        sent=[]
        client.exchange=lambda packet: sent.append(packet) or {'server_time':190.01}
        with patch('airpresent.robotics.wire.time.monotonic',side_effect=[100.,100.02]):client.send(Observation())
        self.assertAlmostEqual(sent[-1]['stamp'],180.)
        self.assertAlmostEqual(client.offset,90.)
        with patch('airpresent.robotics.wire.time.monotonic',side_effect=[101.,101.3]):client.send(Observation())
        self.assertAlmostEqual(client.offset,90.)
