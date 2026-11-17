"""Windows camera workbench with explicit operator, tracking and motion states."""
from pathlib import Path
import math
from queue import Queue, Empty
import threading
import time
import tkinter as tk
from tkinter import ttk

from ..config import Settings
from ..gestures import Gesture, Observation, GestureClassifier
from ..tracker import CameraWorker
from .control import Operator, hand_input, valid_point
from .session import Session
from .wire import Client
from .kinematics import L1,HEIGHT,fk


PHASES={
    'release':('先松开拇指和食指','将两指分开；看到“可以捏合”后再捏合。'),
    'ready':('可以捏合了','拇指与食指接触，保持片刻；先不要移动手掌。'),
    'confirm':('正在确认捏合…','保持拇指与食指接触，等待原点圆圈出现。'),
    'center':('捏合成功 · 已建立原点','保持捏合，将手掌偏离圆圈；离圆圈越远，速度越快。'),
    'moving':('正在移动机械臂','保持捏合继续移动；回到圆圈减速，松开手指停止。'),
    'no_hand':('手势已启用 · 等待手进入画面','整只手入镜后，先松开，再捏合拇指与食指。'),
    'outside':('手势已启用 · 手移出画面','把整只手移回画面中间，先松开，再重新捏合。'),
    'wrong_finger':('当前捏的是中指','请分开手指，改用拇指与食指捏合。'),
    'jump':('跟踪跳变 · 机械臂已停住','把手移回画面中间，先松开，再捏合。'),
    'timeout':('画面暂时中断 · 机械臂已停住','画面恢复后，先松开，再捏合；不用重新点击启用。'),
    'disabled':('等待手势指令','先松开拇指与食指，再重新捏合。'),
}


class Workbench:
    def __init__(self, root, project=None, gui=False, session_factory=Session, client_factory=Client):
        self.root=root;self.project=Path(project or Path(__file__).resolve().parents[2])
        self.gui=gui;self.session_factory=session_factory;self.client_factory=client_factory
        self.camera=None;self.frame=None;self.operator=Operator();self.feedback={}
        self.events=Queue();self.stop=threading.Event();self.closed=threading.Event()
        self.closing=False;self.photo=None;self.last_render=0;self.local_hint=''
        self.camera_error=''
        self.sim_session=None
        self.arm_key=None
        root.tk.call('tk','scaling',96/72)
        root.title('AirHand · 机械臂控制台 v0.9.1');root.geometry('1160x820');root.minsize(1040,760)
        root.configure(bg='#111b26');root.protocol('WM_DELETE_WINDOW',self.close)
        style=ttk.Style(root);style.theme_use('clam')
        style.configure('TButton',padding=8,font=('Microsoft YaHei UI',10))
        self.status=tk.StringVar(value='正在启动 Gazebo；摄像头默认关闭…')
        self.control=tk.StringVar(value='等待仿真就绪')
        self.hint=tk.StringVar(value='先按住右侧方向按钮试动，确认模型能响应。')
        self.camera_status=tk.StringVar(value='摄像头未打开')
        self.metrics=tk.StringVar(value='等待实际关节反馈');self.motion=tk.StringVar(value='速度指令：0 cm/s')
        self._label(root,'机械臂控制台',size=19,color='#65e0bc').pack(anchor='w',padx=22,pady=(16,8))
        self.banner=self._label(root,variable=self.control,size=17,color='#65e0bc');self.banner.pack(anchor='w',padx=22)
        self._label(root,variable=self.hint,size=11).pack(anchor='w',padx=22,pady=(5,12))
        body=tk.Frame(root,bg='#111b26');body.pack(fill='both',expand=True,padx=22,pady=(0,10))
        left=tk.Frame(body,bg='#111b26');left.pack(side='left',fill='both',expand=True)
        right=tk.Frame(body,bg='#111b26',width=322);right.pack(side='right',fill='y',padx=(18,0));right.pack_propagate(False)
        self.preview=tk.Canvas(left,bg='#0b121b',highlightthickness=0,width=640,height=420)
        self.preview.pack(fill='both',expand=True);self.preview.bind('<Configure>',lambda event:self.idle_preview(force=True))
        self._label(left,variable=self.camera_status).pack(anchor='w',pady=(8,5))
        row=tk.Frame(left,bg='#111b26');row.pack(fill='x',pady=(0,8))
        self._label(row,'摄像头').pack(side='left')
        self.index=tk.StringVar(value='0');ttk.Spinbox(row,from_=0,to=9,width=3,textvariable=self.index).pack(side='left',padx=8)
        self.camera_button=ttk.Button(row,text='打开摄像头',command=self.toggle_camera);self.camera_button.pack(side='left')
        ttk.Button(row,text='停止所有控制 / 空格',command=self.pause).pack(side='left',padx=8)
        self._label(left,'画面右移 → 伸出 X+  |  上移 → 侧移 Y+ / 升高 Z+；按基座坐标控制。',size=10).pack(anchor='w')
        self._label(right,'1  先按住按钮试动',size=13,color='#ffffff').pack(anchor='w')
        self._label(right,'不需要摄像头 · 松开按钮即停止',size=10).pack(anchor='w',pady=(3,7))
        self.gui_button=ttk.Button(right,text='打开 Gazebo 3D（可选）',command=self.open_gui,state='disabled')
        self.gui_button.pack(fill='x',pady=(0,5))
        grid=tk.Frame(right,bg='#111b26');grid.pack(fill='x')
        self.jog_buttons={}
        for i,(direction,title) in enumerate([('x+','伸出 X+'),('x-','收回 X−'),('y+','侧移 Y+'),('y-','侧移 Y−'),('z+','抬高 Z+'),('z-','降低 Z−')]):
            button=ttk.Button(grid,text=title,state='disabled',takefocus=False)
            button.grid(row=i//2,column=i%2,sticky='ew',padx=2,pady=3)
            button.bind('<ButtonPress-1>',lambda event,d=direction:self.press_jog(d))
            button.bind('<ButtonRelease-1>',lambda event:self.operator.release('鼠标按键已松开，机械臂停止'))
            button.bind('<Leave>',lambda event:self.operator.release('鼠标移出按钮，已停止；请将鼠标留在按钮上按住'))
            self.jog_buttons[direction]=button
        grid.columnconfigure((0,1),weight=1)
        self._label(right,'2  再启用摄像头手势',size=13,color='#ffffff').pack(anchor='w',pady=(17,7))
        self.enable_button=ttk.Button(right,text='先打开摄像头',command=self.toggle_control,state='disabled')
        self.enable_button.pack(fill='x')
        self.plane=tk.StringVar(value='XY · 伸出 / 侧移')
        plane=ttk.Combobox(right,textvariable=self.plane,state='readonly',values=['XY · 伸出 / 侧移','XZ · 伸出 / 升降'])
        plane.pack(fill='x',pady=(9,7));plane.bind('<<ComboboxSelected>>',self.change_mode)
        self._label(right,'松开两指 → 捏合食指 → 等原点圆圈\n保持捏合偏移手掌 → 松开即停\n短暂丢手只停止运动，启用保持有效',size=10).pack(anchor='w')
        self._label(right,'实际机械臂反馈',size=13,color='#ffffff').pack(anchor='w',pady=(18,8))
        self._label(right,variable=self.metrics,size=11).pack(anchor='w')
        self._label(right,variable=self.motion,size=10,color='#65e0bc').pack(anchor='w',pady=(8,0))
        footer=self._label(root,variable=self.status,size=10);footer.configure(wraplength=1100)
        footer.pack(fill='x',padx=22,pady=(0,14))
        root.bind('<space>',lambda event:self.pause());root.bind('<Escape>',lambda event:self.pause())
        root.bind_all('<ButtonRelease-1>',lambda event:self.operator.release('鼠标已松开，机械臂停止'),add='+')
        root.bind('<FocusOut>',self.focus_out)
        root.bind('<Unmap>',lambda event:self.operator.release('控制台已隐藏，按钮控制停止') if event.widget==self.root else None)
        self.worker=threading.Thread(target=self.network,name='robot-simulation',daemon=False);self.worker.start()
        root.after(40,self.poll)

    @property
    def enabled(self):return self.operator.snapshot()[0]

    @property
    def mode(self):return self.operator.snapshot()[1]

    def _label(self,parent,text='',variable=None,size=11,color='#b9cbd8'):
        return tk.Label(parent,text=text,textvariable=variable,bg='#111b26',fg=color,
            font=('Microsoft YaHei UI',size),anchor='w',justify='left')

    def idle_preview(self,force=False):
        if self.frame is None:
            if not force and self.preview.find_withtag('idle'):return
            self.preview.delete('all')
            self.preview.create_text(self.preview.winfo_width()/2,max(100,self.preview.winfo_height()/2-60),
                text='先按住右侧按钮，确认机械臂能动\n\n然后打开摄像头 → 启用手势',
                fill='#a2b4c5',font=('Microsoft YaHei UI',15),justify='center',tags='idle')

    def pause(self):self.operator.pause()

    def enable(self):
        if self.feedback.get('ready') and (self.frame is not None or self.camera and self.camera.running):self.operator.enable()

    def toggle_control(self):
        if self.enabled:self.pause()
        else:self.enable()

    def change_mode(self,event=None):self.operator.plane('xz' if self.plane.get().startswith('XZ') else 'xy')

    def press_jog(self,direction):
        if self.feedback.get('ready') and not self.closed.is_set():self.operator.press(direction)

    def open_gui(self):
        if self.sim_session:
            try:self.sim_session.request_gui();self.status.set('正在打开 Gazebo 3D；若卡顿，可关闭 3D 窗口继续用控制台。')
            except Exception as exc:self.operator.pause(str(exc))

    def focus_out(self,event=None):
        if self.root.focus_get() is None:self.operator.release('窗口失去焦点，按钮控制已停止；回到控制台后再按住')

    def toggle_camera(self):
        self.operator.pause('摄像头准备好后，点击“启用手势”');self.frame=None
        if self.camera and self.camera.running:
            self.camera.stop();self.camera_button.configure(state='disabled');return
        try:index=int(self.index.get());assert 0<=index<=9
        except (ValueError,AssertionError):self.camera_status.set('摄像头编号应为 0–9');return
        self.camera_error=''
        self.camera=CameraWorker(Settings(camera_index=index),self.project/'models'/'hand_landmarker.task',
            classifier_factory=lambda:GestureClassifier(index_only=True))
        self.camera.start();self.camera_button.configure(text='关闭摄像头',state='disabled')

    def network(self):
        session=client=None
        try:
            session=self.session_factory(self.project,gui=self.gui);self.sim_session=session;self.events.put(('session',str(session.folder)))
            deadline=time.monotonic()+120
            while not self.stop.is_set():
                try:
                    if client is None:
                        endpoint=session.endpoint()
                        if not endpoint:
                            if time.monotonic()>deadline:raise RuntimeError('仿真启动超时，请查看会话日志')
                            self.stop.wait(.1);continue
                        client=self.client_factory(*endpoint)
                    enabled,mode,source,jog,_=self.operator.snapshot()
                    camera=self.camera
                    if camera is not None:
                        latest=camera.latest()
                        if latest is not None:self.frame=latest
                    if source=='buttons':state=client.send_jog(jog);hint=''
                    else:
                        observation,age,hint=hand_input(self.frame,time.monotonic())
                        # Tracking gaps stop motion, preserving operator permission.
                        state=client.send(observation,enabled,mode,age)
                    state['_local_hint']=hint;self.events.put(('feedback',state));self.stop.wait(.05)
                except (OSError,ValueError,ConnectionError) as exc:
                    reason='连接中断，已停止：'+str(exc)+'；恢复后需重新启用'
                    self.operator.pause(reason);self.events.put(('error',reason))
                    if client:client.close();client=None
                    session.endpoint();self.stop.wait(.7)
        except Exception as exc:
            self.operator.pause('仿真已退出：'+str(exc));self.events.put(('error',str(exc)))
        finally:
            self.operator.pause('控制台已关闭')
            if client:
                try:client.send_jog(None)
                except Exception:pass
                client.close()
            if session:session.close()
            self.closed.set()

    def render_state(self):
        enabled,mode,source,jog,reason=self.operator.snapshot();state=self.feedback
        ready=state.get('ready') and not self.closed.is_set() and not self.closing
        camera_available=self.frame is not None or self.camera and self.camera.running
        self.enable_button.configure(state='normal' if ready and camera_available else 'disabled',
            text='停用手势' if enabled else '启用手势' if camera_available else '先打开摄像头')
        for button in self.jog_buttons.values():button.configure(state='normal' if ready else 'disabled')
        self.gui_button.configure(state='normal' if ready else 'disabled')
        color='#65e0bc'
        if self.closing:title='正在停止仿真…';hint='请等待窗口自动关闭。'
        elif not ready:
            title='等待仿真反馈' if not self.closed.is_set() else '仿真已退出'
            hint=reason if '连接中断' in reason or '仿真已退出' in reason else '控制器就绪后，右侧方向按钮会亮起。'
            color='#edbf70'
        elif state.get('guard_reason'):
            title='机械臂已停住 · '+state['guard_reason'];hint='手势请先松开；按钮请松开后换一个方向。';color='#edbf70'
        elif source=='buttons' and jog:
            title='按钮控制：'+jog+' · 按住移动';hint='松开鼠标停止；想用手势时点击“启用手势”。'
        elif not enabled:
            title='手势未启用 · 按钮可以使用';hint=reason
        elif self.local_hint:
            title='手势已启用 · 机械臂暂时停住';hint=self.local_hint;color='#edbf70'
        elif state.get('source')!='hand':
            title='手势已启用 · 正在等待指令确认';hint='将手保持在画面中间，先松开拇指与食指。'
        else:title,hint=PHASES.get(state.get('phase','release'),PHASES['release'])
        self.control.set(title);self.hint.set(hint);self.banner.configure(fg=color)
        tip=state.get('actual_tip');q=state.get('actual_q');target=state.get('target_tip')
        if tip and q:
            text='末端 / m\nX % .3f    Y % .3f    Z % .3f\n关节 / rad\n% .3f  / % .3f  / % .3f'%(*tip,*q)
            self.metrics.set(text)
        v=state.get('command_velocity',(0,0,0))
        text='速度 / cm/s：X %+.1f  Y %+.1f  Z %+.1f'%tuple(x*100 for x in v)
        if target:text+='\n目标 / m：% .3f / % .3f / % .3f'%tuple(target)
        self.motion.set(text)

    def render_frame(self):
        frame=self.frame
        if frame is None:self.idle_preview();return
        if frame.timestamp-self.last_render<1/15:return
        from PIL import Image,ImageTk
        image=Image.fromarray(frame.rgb);image.thumbnail((max(1,self.preview.winfo_width()),max(1,self.preview.winfo_height())))
        w,h=image.size;left=(self.preview.winfo_width()-w)/2;top=(self.preview.winfo_height()-h)/2
        self.photo=ImageTk.PhotoImage(image);self.preview.delete('all');self.preview.create_image(left,top,anchor='nw',image=self.photo)
        anchor=self.feedback.get('anchor') if self.enabled else None
        palm=frame.observation.palm or frame.observation.pointer
        if valid_point(anchor) and valid_point(palm):
            ax,ay=left+anchor[0]*w,top+anchor[1]*h;px,py=left+palm[0]*w,top+palm[1]*h
            r=.02*w
            self.preview.create_oval(ax-r,ay-r,ax+r,ay+r,outline='#ffcf6e',width=3)
            self.preview.create_text(ax,ay-28,text='原点 · 回到这里减速',fill='#ffcf6e',font=('Microsoft YaHei UI',11))
            self.preview.create_line(ax,ay,px,py,fill='#65e0bc',width=4,arrow='last')
            self.preview.create_oval(px-7,py-7,px+7,py+7,fill='#65e0bc',outline='')
        gesture=frame.observation.gesture
        name='拇指食指已捏合' if gesture==Gesture.PINCH_NEXT else '当前捏的是中指' if gesture==Gesture.PINCH_PREVIOUS else '未检测到手' if gesture==Gesture.NONE else '手指已松开'
        age=max(0,(time.monotonic()-frame.timestamp)*1000)
        self.camera_status.set(f'{name} · {frame.fps:.0f} FPS · 画面年龄 {age:.0f} ms')
        self.last_render=frame.timestamp

    def render_arm(self):
        q=self.feedback.get('actual_q')
        if q is None:return
        width=self.preview.winfo_width();height=self.preview.winfo_height()
        large=self.frame is None
        key=(tuple(round(v,4) for v in q),width,height,large)
        if key==self.arm_key and self.preview.find_withtag('arm_feedback'):return
        self.arm_key=key;self.preview.delete('arm_feedback')
        x0=8 if large else max(8,width-270)
        y0=max(8,height*.42) if large else max(8,height-204);tags='arm_feedback'
        self.preview.create_rectangle(x0,y0,width-8,height-8,fill='#172936',outline='#3d5968',tags=tags)
        self.preview.create_text(x0+12,y0+18,anchor='w',text='Gazebo 实际姿态（关节回读）',fill='#b9cbd8',font=('Microsoft YaHei UI',10),tags=tags)
        yaw,shoulder,_=q
        elbow=(L1*math.cos(shoulder)*math.cos(yaw),L1*math.cos(shoulder)*math.sin(yaw),HEIGHT+L1*math.sin(shoulder))
        points=[(0.,0.,0.),(0.,0.,HEIGHT),elbow,fk(q)]
        scale=min(480,(height-y0-35)/.5) if large else 245
        projected=[(x0+85+scale*(x-.65*y),height-30-scale*(z+.3*y)) for x,y,z in points]
        for i,(a,b) in enumerate(zip(projected,projected[1:])):
            self.preview.create_line(*a,*b,fill=('#6f8795','#65e0bc','#b9cbd8')[i],width=10,tags=tags)
        for x,y in projected:self.preview.create_oval(x-5,y-5,x+5,y+5,fill='#ffcf6e',outline='',tags=tags)

    def poll(self):
        try:
            while True:
                kind,data=self.events.get_nowait()
                if kind=='feedback':
                    self.feedback=data;self.local_hint=data.get('_local_hint','')
                    self.status.set('ROS / Gazebo：'+data['status'])
                elif kind=='session':self.status.set('会话日志：'+data)
                elif kind=='error':self.status.set(data);self.feedback={}
        except Empty:pass
        if self.camera:
            try:
                while True:
                    kind,message=self.camera.messages.get_nowait();self.camera_status.set(message)
                    if kind=='ready':self.camera_button.configure(state='normal')
                    if kind in ('error','stopped'):
                        if kind=='error':self.camera_error=message
                        self.operator.pause((self.camera_error or message)+'；重新打开摄像头后再启用');self.frame=None
                        self.camera_button.configure(text='打开摄像头',state='normal')
            except Empty:pass
        self.render_state();self.render_frame();self.render_arm()
        if self.closing and self.closed.is_set():self.root.destroy();return
        self.root.after(40,self.poll)

    def close(self):
        if self.closing:return
        self.closing=True;self.operator.pause();self.stop.set()
        if self.camera:self.camera.stop()


def main():
    from ..desktop import enable_dpi_awareness
    enable_dpi_awareness();root=tk.Tk();Workbench(root);root.mainloop()


if __name__=='__main__':main()
