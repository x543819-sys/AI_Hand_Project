"""Starts only simulation processes in a dedicated ROS domain and GZ partition."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from .model import create_model


def stop(process):
    # The launch parent can exit before its children. Address only the process
    # group created by this supervisor, even when the parent already exited.
    try:os.killpg(process.pid,signal.SIGINT)
    except ProcessLookupError:return
    try:process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGTERM)
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=3)
    try:os.killpg(process.pid,signal.SIGTERM)
    except ProcessLookupError:pass
    time.sleep(.3)
    try:os.killpg(process.pid,signal.SIGKILL)
    except ProcessLookupError:pass


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--session',required=True);args=parser.parse_args()
    session=Path(args.session).resolve();folder=session.parent
    os.environ['AIRHAND_ARM_SESSION']=str(session)
    cfg=json.loads(session.read_text(encoding='utf-8'))
    assert type(cfg['domain']) is int and 80<=cfg['domain']<=180
    os.environ['ROS_DOMAIN_ID']=str(cfg['domain']);os.environ['ROS_AUTOMATIC_DISCOVERY_RANGE']='LOCALHOST'
    os.environ['GZ_PARTITION']='airhand_arm_'+folder.name
    create_model(folder)
    processes=[]
    try:
        with (folder/'simulation.log').open('w') as simlog,(folder/'bridge.log').open('w') as bridgelog,(folder/'gui.log').open('w') as guilog:
            processes.append(subprocess.Popen(['ros2','launch',str(Path(__file__).with_name('arm_sim.launch.py'))],stdout=simlog,stderr=subprocess.STDOUT,start_new_session=True))
            processes.append(subprocess.Popen([sys.executable,'-m','airpresent.robotics.ros_receiver','--session',str(session)],stdout=bridgelog,stderr=subprocess.STDOUT,start_new_session=True))
            gui_process=None
            while not (folder/'stop').exists():
                if any(p.poll() is not None for p in processes[:2]):raise RuntimeError('A simulation process stopped; inspect session logs')
                request=folder/'open_gui'
                if request.exists():
                    request.unlink()
                    if not cfg['gui'] and (gui_process is None or gui_process.poll() is not None):
                        gui_process=subprocess.Popen(['gz','sim','-g','--gui-config',str(folder/'gui.config')],stdout=guilog,stderr=subprocess.STDOUT,start_new_session=True)
                        processes.append(gui_process)
                time.sleep(.15)
    except KeyboardInterrupt:pass
    finally:
        for p in reversed(processes):stop(p)


if __name__=='__main__':main()
