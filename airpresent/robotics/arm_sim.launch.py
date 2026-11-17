"""Launch the project's simulation-only arm through the installed ROS plugins."""
import json
import os
import shlex
from pathlib import Path
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    session=Path(os.environ['AIRHAND_ARM_SESSION'])
    settings=json.loads(session.read_text(encoding='utf-8'))
    folder=session.parent
    gui_args=''
    if settings['gui'] and (folder/'gui.config').exists():
        gui_args=' --gui-config '+shlex.quote(str(folder/'gui.config'))
    gazebo=IncludeLaunchDescription(PythonLaunchDescriptionSource(str(Path(get_package_share_directory('ros_gz_sim'))/'launch/gz_sim.launch.py')),
        launch_arguments={'gz_args':('-r -v 1 empty.sdf'+gui_args if settings['gui'] else '-s -r -v 1 empty.sdf')}.items())
    description=(folder/'arm.urdf').read_text(encoding='utf-8')
    robot=Node(package='robot_state_publisher',executable='robot_state_publisher',parameters=[{'robot_description':description,'use_sim_time':True}])
    spawn=Node(package='ros_gz_sim',executable='create',arguments=['-topic','robot_description','-name','airhand_arm','-allow_renaming','false'])
    joint=Node(package='controller_manager',executable='spawner',arguments=['airhand_joint_states'])
    arm=Node(package='controller_manager',executable='spawner',arguments=['airhand_arm_controller','--param-file',str(folder/'controllers.yaml')])
    clock=Node(package='ros_gz_bridge',executable='parameter_bridge',arguments=['/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock'])
    return LaunchDescription([gazebo,robot,spawn,clock,
        RegisterEventHandler(OnProcessExit(target_action=spawn,on_exit=[joint])),
        RegisterEventHandler(OnProcessExit(target_action=joint,on_exit=[arm]))])
