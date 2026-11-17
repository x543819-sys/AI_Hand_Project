"""ROS/Gazebo-only target integrator with actual JointState feedback."""
import json
import math
from pathlib import Path
import socket
import threading
import time

from .intent import HandVelocity, Intent
from .kinematics import JOINTS, fk, step, simulation_dt
from .wire import MAX_PACKET, decode, Jog, JOG_VELOCITIES


def main():
    import argparse
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import JointState
    from rosgraph_msgs.msg import Clock
    from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
    from controller_manager_msgs.srv import ListControllers
    from tf2_ros import Buffer, TransformListener
    parser=argparse.ArgumentParser();parser.add_argument('--session',required=True);args=parser.parse_args()
    file=Path(args.session);cfg=json.loads(file.read_text(encoding='utf-8'))
    class Bridge(Node):
        def __init__(self):
            super().__init__('airhand_sim_bridge')
            self.lock=threading.RLock();self.motion=HandVelocity();self.q=None;self.qtime=0
            self.target_q=None;self.target=None;self.moving=False;self.active=False
            self.source='hand';self.jog=None;self.jog_time=0;self.jog_blocked=False;self.guard_reason=''
            self.command_velocity=(0.,0.,0.)
            self.sim_time=None;self.previous_sim_time=None
            self.query=None;self.status='等待仿真控制器';self.last_tick=time.monotonic()
            self.last_input=0;self.report_time=0;self.stopping=threading.Event()
            self.pub=self.create_publisher(JointTrajectory,'/airhand_arm_controller/joint_trajectory',10)
            self.create_subscription(JointState,'/joint_states',self.feedback,qos_profile_sensor_data)
            self.create_subscription(Clock,'/clock',self.clock_feedback,qos_profile_sensor_data)
            self.manager=self.create_client(ListControllers,'/controller_manager/list_controllers')
            self.tf=Buffer();self.tf_listener=TransformListener(self.tf,self)
            self.create_timer(.5,self.lifecycle);self.create_timer(.05,self.tick)
            self.server=socket.socket();self.server.bind((cfg['host'],0));self.server.listen(1);self.server.settimeout(.2)
            (file.parent/'endpoint.json').write_text(json.dumps({'host':cfg['host'],'port':self.server.getsockname()[1]}),encoding='utf-8')
            threading.Thread(target=self.network,daemon=True).start()

        def feedback(self,msg):
            if not all(n in msg.name for n in JOINTS):return
            q=tuple(msg.position[msg.name.index(n)] for n in JOINTS)
            if not all(math.isfinite(v) for v in q):return
            with self.lock:self.q=q;self.qtime=time.monotonic()

        def clock_feedback(self,msg):
            self.sim_time=msg.clock.sec+msg.clock.nanosec*1e-9

        def lifecycle(self):
            if self.query is not None:
                if not self.query.done():return
                try:self.active=any(c.name=='airhand_arm_controller' and c.state=='active' for c in self.query.result().controller)
                except Exception:self.active=False
                self.query=None
            if self.manager.service_is_ready():self.query=self.manager.call_async(ListControllers.Request())

        def snapshot(self):
            with self.lock:
                now=time.monotonic();ready=self.active and self.q is not None and now-self.qtime<.3 and self.sim_time is not None
                try:
                    t=self.tf.lookup_transform('world','tool_link',rclpy.time.Time()).transform.translation
                    tf_tip=(t.x,t.y,t.z)
                except Exception:tf_tip=None
                return {'server_time':now,'ready':ready,'active_controller':self.active,'actual_q':self.q,
                    'actual_tip':fk(self.q) if self.q else None,'tf_tip':tf_tip,'target_tip':self.target,'deadman':self.moving,
                    'phase':self.motion.phase,'anchor':self.motion.anchor,'command_velocity':self.command_velocity,
                    'source':self.source,'guard_reason':self.guard_reason,
                    'sim_time':self.sim_time,
                    'status':self.status,'input_age_ms':round((now-self.last_input)*1000) if self.last_input else None,
                    'feedback_age_ms':round((now-self.qtime)*1000) if self.qtime else None}

        def halt(self):
            with self.lock:
                self.motion.enable(False);self.jog=None

        def network(self):
            while not self.stopping.is_set():
                try:conn,_=self.server.accept()
                except socket.timeout:continue
                except OSError:break
                # Motion watchdog remains 200ms. A rendering/scheduling hiccup
                # need not tear down an otherwise authenticated transport.
                conn.settimeout(2.);previous=-1
                try:
                    with conn,conn.makefile('rb') as stream:
                        while not self.stopping.is_set():
                            raw=stream.readline(MAX_PACKET+1)
                            if not raw or len(raw)>MAX_PACKET:
                                self.get_logger().warning('Input stream ended; bytes='+str(len(raw)))
                                break
                            packet=json.loads(raw)
                            try:decoded=decode(packet,cfg['token'],previous,time.monotonic())
                            except (ValueError,TypeError) as exc:
                                self.halt()
                                conn.sendall(json.dumps({'error':str(exc)[:160]}).encode()+b'\n')
                                break
                            if decoded is not None:
                                seq,enabled,mode,observation=decoded;previous=seq
                                with self.lock:
                                    now=time.monotonic()
                                    if isinstance(observation,Jog):
                                        if self.source!='buttons':self.target=self.target_q=None
                                        self.source='buttons';self.motion.enable(False)
                                        if observation.direction!=self.jog:self.guard_reason='';self.jog_blocked=False
                                        self.jog=observation.direction;self.jog_time=now
                                    else:
                                        if self.source!='hand':self.target=self.target_q=None
                                        self.source='hand';self.jog=None
                                        if self.motion.mode!=mode:self.motion.set_mode(mode)
                                        if self.motion.enabled!=enabled:self.motion.enable(enabled)
                                        self.motion.update(observation,now)
                                        if observation.pinch_released is True or not enabled:self.guard_reason=''
                                    self.last_input=now
                            state=self.snapshot();state['server_time']=time.monotonic()
                            answer=json.dumps(state,allow_nan=False).encode()+b'\n'
                            conn.sendall(answer)
                except Exception as exc:
                    print('Bridge input stopped: '+type(exc).__name__+': '+str(exc),flush=True)
                finally:
                    self.halt()

        def tick(self):
            with self.lock:
                now=time.monotonic()
                dt=simulation_dt(self.previous_sim_time,self.sim_time)
                self.previous_sim_time=self.sim_time
                if not self.active or self.q is None or now-self.qtime>.3 or self.sim_time is None:
                    self.motion.clear();self.jog=None;self.target_q=self.target=None;self.moving=False;self.command_velocity=(0.,0.,0.)
                    self.status='等待控制器 active 与新鲜关节反馈';return
                if self.source=='buttons':
                    if now-self.jog_time>.2:self.jog=None
                    velocity=JOG_VELOCITIES[self.jog] if not self.jog_blocked else (0.,0.,0.)
                    intent=Intent(velocity,deadman=self.jog is not None and not self.jog_blocked)
                else:intent=self.motion.sample(now)
                self.command_velocity=intent.linear
                moving=intent.deadman and any(abs(v)>1e-8 for v in intent.linear)
                actual=fk(self.q)
                if self.target is None:self.target=actual;self.target_q=self.q
                if moving:
                    if math.dist(actual,self.target)>.045:
                        self.motion.clear();self.target=actual;self.target_q=self.q;self.status='跟踪误差较大，已停住；请松开'
                        self.guard_reason=self.status;self.jog_blocked=True
                        moving=False
                    else:
                        proposal=step(self.target,intent.linear,dt) if dt>0 else (self.target,self.target_q)
                        if proposal is None:
                            self.motion.clear();self.target=actual;self.target_q=self.q;moving=False;self.status='达到工作区或关节边界；请松开'
                            self.guard_reason=self.status;self.jog_blocked=True
                        else:
                            target,q=proposal
                            if max(abs(a-b) for a,b in zip(q,self.target_q))>.025:
                                self.motion.clear();self.target=actual;self.target_q=self.q;moving=False;self.status='关节步长过大，已停住'
                                self.guard_reason=self.status;self.jog_blocked=True
                            else:self.target,self.target_q=target,q;self.status='按钮移动中' if self.source=='buttons' else '捏合移动中 · Gazebo 实际反馈'
                else:
                    if self.moving:self.target,self.target_q=actual,self.q
                    self.status=self.guard_reason or ('已停住 · 请先松开再捏合' if self.motion.enabled else '机械臂已停止 · 仿真反馈正常')
                self.moving=moving
                if not moving:self.command_velocity=(0.,0.,0.)
                msg=JointTrajectory();msg.joint_names=list(JOINTS)
                point=JointTrajectoryPoint();point.positions=list(self.target_q);point.velocities=[0.,0.,0.];point.time_from_start.nanosec=120_000_000
                msg.points=[point];self.pub.publish(msg)
                if now-self.report_time>.5:
                    p=file.parent/'feedback.json';temp=p.with_suffix('.tmp');temp.write_text(json.dumps(self.snapshot()),encoding='utf-8');temp.replace(p);self.report_time=now

        def close(self):
            self.halt();self.stopping.set();self.server.close()
    rclpy.init();node=Bridge()
    print('Bridge ROS node ready',flush=True)
    try:rclpy.spin(node)
    except KeyboardInterrupt:pass
    except RuntimeError:
        if rclpy.ok():raise
    finally:
        print('Bridge ROS node stopping',flush=True)
        node.close();node.destroy_node()
        if rclpy.ok():rclpy.shutdown()


if __name__=='__main__':main()
