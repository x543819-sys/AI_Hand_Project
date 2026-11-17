"""Linux-only runtime verification using official ROS/Gazebo demos.

Starts and stops only its own processes. No camera or physical hardware.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import rclpy
from rclpy.action import ActionClient
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import String
from sensor_msgs.msg import JointState
from rosgraph_msgs.msg import Clock
from control_msgs.action import FollowJointTrajectory
from trajectory_msgs.msg import JointTrajectoryPoint
from controller_manager_msgs.srv import ListControllers

ROOT=Path(os.environ.get('AIRHAND_ROS_REPORT_DIR',str(Path(__file__).resolve().parents[1]/'sessions'/'ros_checks')))
ROOT.mkdir(parents=True,exist_ok=True)


def stop_process(process):
    if process is None or process.poll() is not None:
        return
    os.killpg(process.pid,signal.SIGINT)
    try:process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGTERM)
        process.wait(timeout=10)


def spin_until(node,condition,seconds):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        rclpy.spin_once(node,timeout_sec=.1)
        if condition():return True
    return False


def main():
    result={"camera_opened":False,"hardware_connected":False,"domain":os.environ.get('ROS_DOMAIN_ID')}
    talker=simulation=node=None
    rclpy.init()
    try:
        node=rclpy.create_node('airhand_environment_probe')
        messages=[]
        sub=node.create_subscription(String,'/chatter',lambda m:messages.append(m.data),10)
        with (ROOT/'ros_talker_test.log').open('w') as log:
            talker=subprocess.Popen(['ros2','run','demo_nodes_cpp','talker'],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            assert spin_until(node,lambda:len(messages)>=3,20),'ROS C++ to Python communication failed'
            result['cpp_talker_to_python_listener']=len(messages)
            stop_process(talker);talker=None
        node.destroy_subscription(sub)
        joints=[];clocks=[]
        node.create_subscription(JointState,'/joint_states',lambda m:joints.append(m),qos_profile_sensor_data)
        node.create_subscription(Clock,'/clock',lambda m:clocks.append(m.clock.sec+m.clock.nanosec*1e-9),qos_profile_sensor_data)
        with (ROOT/'gazebo_cart_test.log').open('w') as log:
            simulation=subprocess.Popen(['ros2','launch','gz_ros2_control_demos','cart_example_position.launch.py','gz_args:=-s'],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            client=ActionClient(node,FollowJointTrajectory,'/joint_trajectory_controller/follow_joint_trajectory')
            assert spin_until(node,lambda:client.server_is_ready() and bool(joints) and bool(clocks),60),'Gazebo controller or feedback not ready'
            listing=node.create_client(ListControllers,'/controller_manager/list_controllers')
            assert listing.wait_for_service(timeout_sec=10),'Controller manager service unavailable'
            active=False
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                query=listing.call_async(ListControllers.Request())
                assert spin_until(node,query.done,5),'Controller lifecycle query timed out'
                active=any(c.name=='joint_trajectory_controller' and c.state=='active' for c in query.result().controller)
                if active:break
                time.sleep(.1)
            assert active,'Trajectory controller never became active'
            result['controller_lifecycle_active']=True
            node.destroy_client(listing)
            def actual():
                m=joints[-1]
                return m.position[m.name.index('slider_to_cart')]
            before=actual()
            target=-.4 if before>.1 else .4
            result.update(joint_before=before,joint_target=target)
            goal=FollowJointTrajectory.Goal()
            goal.trajectory.joint_names=['slider_to_cart']
            point=JointTrajectoryPoint();point.positions=[target];point.time_from_start.sec=3
            goal.trajectory.points=[point]
            pending=client.send_goal_async(goal)
            assert spin_until(node,pending.done,10),'Goal response timed out'
            handle=pending.result();assert handle.accepted,'Controller rejected the target'
            done=handle.get_result_async()
            assert spin_until(node,done.done,25),'Controller result timed out'
            response=done.result()
            result['controller_result_code']=response.result.error_code
            assert response.result.error_code==0,f'Controller error {response.result.error_code}'
            confirmed=spin_until(node,lambda:abs(actual()-target)<.04,5)
            result['joint_after']=actual()
            assert confirmed,f'Joint state did not confirm target: actual={actual()}, target={target}'
            after=actual()
            assert abs(after-before)>.15,'No actual motion was observed'
            assert clocks[-1]>clocks[0],'Simulation clock did not advance'
            result.update(gazebo_headless=True,controller_action_success=True,joint_before=before,
                          joint_target=target,joint_after=after,joint_state_samples=len(joints),
                          simulation_time_advanced=clocks[-1]-clocks[0])
            client.destroy()
            stop_process(simulation);simulation=None
        result['status']='PASS'
    except Exception as exc:
        result.update(status='FAILED',error=str(exc))
        raise
    finally:
        stop_process(talker);stop_process(simulation)
        if node:node.destroy_node()
        rclpy.shutdown()
        (ROOT/'ros_runtime_result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result),flush=True)


if __name__=='__main__':main()
