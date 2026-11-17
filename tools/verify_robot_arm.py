"""Windows-to-WSL integration check with synthetic hands and real Gazebo."""
from pathlib import Path
import json
import math
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from airpresent.robotics.session import Session
from airpresent.robotics.wire import Client
from airpresent.gestures import Gesture, Observation


def pose(x=.5,y=.5,pinch=False):
    return Observation(Gesture.PINCH_NEXT if pinch else Gesture.UNKNOWN,(x,y),pinch_released=not pinch)


def main():
    root=Path(__file__).resolve().parents[1]
    report=root/'screenshots';report.mkdir(exist_ok=True)
    session=client=None
    result={'camera_opened':False,'input':'synthetic','simulator':'real Gazebo','transport':'Windows TCP to WSL ROS2'}
    try:
        session=Session(root,gui=False)
        deadline=time.monotonic()+100
        while time.monotonic()<deadline:
            try:
                endpoint=session.endpoint()
                if endpoint:
                    if client is None:client=Client(*endpoint)
                    state=client.send(Observation())
                    if state['ready']:break
            except (OSError,ValueError,ConnectionError):
                if client:client.close();client=None
                result['startup_reconnects']=result.get('startup_reconnects',0)+1
            time.sleep(.05)
        else:raise AssertionError('Arm did not become ready: '+str(session.folder))
        def send_for(observation,seconds,enabled=True,mode='xy'):
            deadline=time.monotonic()+seconds
            while time.monotonic()<deadline:
                state=client.send(observation,enabled,mode)
                time.sleep(.04)
            return state
        initial=state['actual_tip'];result['initial_tip']=initial
        state=send_for(pose(),.25)
        send_for(pose(pinch=True),.25)
        state=send_for(pose(.5,.62,True),3.)
        moved=state['actual_tip'];result.update(moved_tip=moved,actual_q=state['actual_q'])
        assert moved[1]<initial[1]-.015,(initial,moved,state)
        if state['tf_tip']:
            result['tf_fk_error']=math.dist(state['tf_tip'],state['actual_tip'])
            assert result['tf_fk_error']<.015,state
        state=send_for(pose(),.5)
        stopped=state['actual_tip']
        state=send_for(pose(),.7)
        result['release_drift']=math.dist(stopped,state['actual_tip'])
        assert result['release_drift']<.012,state
        send_for(pose(pinch=True),.25)
        state=send_for(pose(.5,.61,True),.8)
        before_disconnect=state['actual_tip'];client.close();client=None
        time.sleep(.8)
        client=Client(*session.endpoint());state=client.send(Observation())
        result['disconnect_drift']=math.dist(before_disconnect,state['actual_tip'])
        assert result['disconnect_drift']<.018,state
        assert not state['deadman'],state
        send_for(pose(),.25,mode='xz');send_for(pose(pinch=True),.25,mode='xz')
        before_z=state['actual_tip'][2]
        state=send_for(pose(.5,.41,True),2.5,mode='xz')
        result['z_motion']=state['actual_tip'][2]-before_z
        assert result['z_motion']>.005,state
        send_for(Observation(),.4,enabled=False)
        result['status']='PASS'
        print(json.dumps(result),flush=True)
    finally:
        (report/'robot_arm_result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        if client:client.close()
        if session:
            print('Session logs:',str(session.folder),flush=True)
            session.close()


if __name__=='__main__':main()
