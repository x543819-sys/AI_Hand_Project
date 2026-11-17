"""Procedural primitive URDF. No third-party robot meshes are redistributed."""
from pathlib import Path
from xml.sax.saxutils import escape


CONTROLLERS='''controller_manager:
  ros__parameters:
    update_rate: 100
    enforce_command_limits: true
    airhand_joint_states:
      type: joint_state_broadcaster/JointStateBroadcaster
    airhand_arm_controller:
      type: joint_trajectory_controller/JointTrajectoryController
airhand_arm_controller:
  ros__parameters:
    joints: [base_yaw, shoulder, elbow]
    command_interfaces: [position]
    state_interfaces: [position, velocity]
    constraints:
      stopped_velocity_tolerance: 0.05
      goal_time: 2.0
'''


def create_model(folder):
    folder=Path(folder)
    installed=Path('/opt/ros/jazzy/opt/gz_sim_vendor/share/gz/gz-sim8/worlds/empty.sdf')
    if installed.exists():
        world=installed.read_text().replace('<max_step_size>0.001</max_step_size>','<max_step_size>0.005</max_step_size>')
        (folder/'world.sdf').write_text(world,encoding='utf-8')
    # Adapt the locally installed Gazebo GUI at runtime; no vendor file is bundled.
    template=Path('/opt/ros/jazzy/opt/gz_sim_vendor/share/gz/gz-sim8/gui/gui.config')
    if template.is_file():
        import re
        gui=re.sub(r'<camera_pose>.*?</camera_pose>',
                   '<camera_pose>1.2 -1.2 0.9 0 0.4 2.27</camera_pose>',template.read_text())
        gui=gui.replace('show_again="true"','show_again="false"').replace('<dialog_on_exit>true</dialog_on_exit>','<dialog_on_exit>false</dialog_on_exit>')
        (folder/'gui.config').write_text(gui,encoding='utf-8')
    config=folder/'controllers.yaml';config.write_text(CONTROLLERS,encoding='utf-8')
    colors={'base':'0.13 0.18 0.24 1','yaw':'0.3 0.36 0.42 1','upper':'0.18 0.68 0.55 1','fore':'0.68 0.76 0.82 1','tool':'0.95 0.65 0.28 1'}
    def link(name,geom,origin,mass,color):
        return f'''<link name="{name}"><inertial><origin xyz="{origin}"/><mass value="{mass}"/><inertia ixx="0.003" ixy="0" ixz="0" iyy="0.008" iyz="0" izz="0.008"/></inertial><visual><origin xyz="{origin}"/><geometry>{geom}</geometry><material name="{name}_color"><color rgba="{color}"/></material></visual><collision><origin xyz="{origin}"/><geometry>{geom}</geometry></collision></link>'''
    links=link('base_link','<cylinder radius="0.08" length="0.12"/>','0 0 0.06',2,colors['base'])
    links+=link('yaw_link','<cylinder radius="0.055" length="0.08"/>','0 0 0.04',.8,colors['yaw'])
    links+=link('upper_link','<box size="0.28 0.05 0.05"/>','0.14 0 0',.7,colors['upper'])
    links+=link('fore_link','<box size="0.24 0.04 0.04"/>','0.12 0 0',.5,colors['fore'])
    links+=link('tool_link','<sphere radius="0.028"/>','0 0 0',.1,colors['tool'])
    joints='''<joint name="world_fixed" type="fixed"><parent link="world"/><child link="base_link"/></joint>
<joint name="base_yaw" type="revolute"><parent link="base_link"/><child link="yaw_link"/><origin xyz="0 0 0.12"/><axis xyz="0 0 1"/><limit lower="-1.4" upper="1.4" effort="40" velocity="0.5"/><dynamics damping="0.2"/></joint>
<joint name="shoulder" type="revolute"><parent link="yaw_link"/><child link="upper_link"/><origin xyz="0 0 0.08"/><axis xyz="0 -1 0"/><limit lower="-0.7" upper="1.3" effort="40" velocity="0.5"/><dynamics damping="0.2"/></joint>
<joint name="elbow" type="revolute"><parent link="upper_link"/><child link="fore_link"/><origin xyz="0.28 0 0"/><axis xyz="0 -1 0"/><limit lower="-1.8" upper="-0.15" effort="25" velocity="0.5"/><dynamics damping="0.2"/></joint>
<joint name="tool_fixed" type="fixed"><parent link="fore_link"/><child link="tool_link"/><origin xyz="0.24 0 0"/></joint>'''
    control=''
    for name,lo,hi,initial in [('base_yaw',-1.4,1.4,0),('shoulder',-.7,1.3,.65),('elbow',-1.8,-.15,-1.2)]:
        control+=f'<joint name="{name}"><command_interface name="position"><param name="min">{lo}</param><param name="max">{hi}</param></command_interface><state_interface name="position"><param name="initial_value">{initial}</param></state_interface><state_interface name="velocity"/></joint>'
    text=f'''<?xml version="1.0"?><robot name="airhand_arm"><link name="world"/>{links}{joints}<ros2_control name="AirHandGazebo" type="system"><hardware><plugin>gz_ros2_control/GazeboSimSystem</plugin></hardware>{control}</ros2_control><gazebo><plugin filename="gz_ros2_control-system" name="gz_ros2_control::GazeboSimROS2ControlPlugin"><parameters>{escape(str(config))}</parameters></plugin></gazebo></robot>'''
    path=folder/'arm.urdf';path.write_text(text,encoding='utf-8');return path
