"""Drive the actual Tk sender and Gazebo with explicit synthetic camera frames."""
import argparse,json,math,faulthandler
from pathlib import Path
import sys,time,tkinter as tk,_tkinter
from queue import Queue
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image,ImageDraw,ImageFont,ImageGrab
from airpresent.desktop import enable_dpi_awareness
from airpresent.gestures import Gesture,Observation
from airpresent.tracker import Frame
from airpresent.robotics.ui import Workbench


def main():
    trace=Path(__file__).resolve().parents[1]/'screenshots'/'interaction_trace.log';trace.parent.mkdir(exist_ok=True)
    trace_file=trace.open('w');faulthandler.dump_traceback_later(30,repeat=True,file=trace_file)
    parser=argparse.ArgumentParser();parser.add_argument('--gui',action='store_true');args=parser.parse_args()
    enable_dpi_awareness();root=tk.Tk();app=Workbench(root,gui=args.gui)
    folder=Path(__file__).resolve().parents[1]/'screenshots';folder.mkdir(exist_ok=True)
    result={'input':'synthetic camera frames through actual Tk sender','camera_opened':False,'simulator':'real Gazebo'}
    image=Image.new('RGB',(640,480),'#162530');draw=ImageDraw.Draw(image)
    font=ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc',20)
    draw.text((22,18),'合成手势测试（非摄像头）',font=font,fill='#b9cbd8')
    for x in range(0,640,40):draw.line((x,65,x,480),fill='#223846')
    for y in range(80,480,40):draw.line((0,y,640,y),fill='#223846')
    rgb=np.array(image)
    class SyntheticCamera:
        running=True
        def __init__(self):self.messages=Queue();self.observation=Observation();self.stale=False
        def latest(self):return Frame(rgb,self.observation,time.monotonic()-(.35 if self.stale else 0),30.,20.)
        def stop(self):self.running=False
    camera=SyntheticCamera()
    def pose(x=.5,y=.5,pinch=False):
        return Observation(Gesture.PINCH_NEXT if pinch else Gesture.PALM,(x,y),(x,y),pinch_released=not pinch)
    def pump(seconds,observation=None,stale=False):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if observation is not None:camera.observation=observation;camera.stale=stale
            for _ in range(10):
                if not root.tk.dooneevent(_tkinter.DONT_WAIT):break
            time.sleep(.02)
        return app.feedback
    def wait_phase(phase,observation):
        deadline=time.monotonic()+4
        while time.monotonic()<deadline:
            pump(.1,observation)
            if app.feedback.get('source')=='hand' and app.feedback.get('phase')==phase:return
        raise AssertionError((app.control.get(),app.operator.snapshot(),app.feedback))
    try:
        deadline=time.monotonic()+120
        while not app.feedback.get('ready'):
            pump(.05)
            if app.closed.is_set() or time.monotonic()>deadline:raise AssertionError(app.status.get())
        root.attributes('-topmost',True);root.lift();root.focus_force();pump(.15)
        print('Stage: controller ready',flush=True)
        assert app.camera is None and not app.enabled
        initial=app.feedback['actual_tip']
        app.render_arm()
        def end_marker(canvas):
            ids=[i for i in canvas.find_withtag('arm_feedback') if canvas.type(i)=='oval']
            return canvas.coords(ids[-1])
        initial_marker=end_marker(app.preview)
        button=app.jog_buttons['y-']
        clicked=time.monotonic();first_motion=None
        button.invoke()  # Standard command, without suppressing widget bindings.
        button.event_generate('<Leave>')
        print('Stage: click step',flush=True)
        deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            pump(.15)
            if first_motion is None and abs(app.feedback['actual_tip'][1]-initial[1])>.001:first_motion=time.monotonic()-clicked
            if app.operator.snapshot()[3] is None:break
        moved=app.feedback['actual_tip']
        result['manual_y_motion']=moved[1]-initial[1]
        assert moved[1]<initial[1]-.008,(app.operator.snapshot(),app.control.get(),app.feedback)
        result['step_completed']=app.operator.snapshot()[3] is None
        assert result['step_completed'],app.operator.snapshot()
        result['simulation_rate']=app.feedback.get('_sim_rate')
        result['first_motion_seconds']=first_motion;result['step_seconds']=time.monotonic()-clicked
        app.render_arm();result['main_marker_pixels']=math.dist(initial_marker,end_marker(app.preview))
        assert result['main_marker_pixels']>1,'Actual arm view did not move'
        pump(.6)
        stopped=app.feedback['actual_tip'];pump(.6)
        result['manual_release_drift']=math.dist(stopped,app.feedback['actual_tip'])
        assert result['manual_release_drift']<.01
        app.open_monitor();pump(.2)
        assert app.monitor.window.winfo_viewable() and app.monitor.window.attributes('-topmost')
        monitor_before=end_marker(app.monitor.canvas);before=app.feedback['actual_tip']
        app.monitor.buttons[2].invoke()  # y+ from the floating controls.
        deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            pump(.15)
            if app.operator.snapshot()[3] is None:break
        assert app.feedback['actual_tip'][1]>before[1]+.008
        assert math.dist(monitor_before,end_marker(app.monitor.canvas))>1
        result['floating_step_and_view']='PASS'
        window=app.monitor.window
        ImageGrab.grab(bbox=(window.winfo_rootx(),window.winfo_rooty(),window.winfo_rootx()+window.winfo_width(),window.winfo_rooty()+window.winfo_height())).save(folder/'robot_floating.png')
        app.camera=camera
        pump(.25,pose());app.enable_button.invoke();wait_phase('ready',pose())
        print('Stage: hand ready',flush=True)
        assert app.enabled,app.control.get()
        wait_phase('center',pose(pinch=True))
        time.sleep(.45)  # UI stalls while the independent camera/sender stay live.
        pump(.2,pose(pinch=True))
        assert app.enabled and app.feedback['phase']=='center',(app.control.get(),app.feedback)
        result['ui_stall_kept_clutch']=True
        before=app.feedback['actual_tip']
        deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            pump(.15,pose(.5,.62,True))
            if app.feedback['actual_tip'][1]<before[1]-.015:break
        result['hand_y_motion']=app.feedback['actual_tip'][1]-before[1]
        assert result['hand_y_motion']<-.01,(app.control.get(),app.feedback)
        # Reproduce the user's out-of-frame coordinate without dropping TCP or enable.
        pump(.55,pose(1.02,.5,True))
        assert app.enabled and app.feedback.get('ready'),app.status.get()
        assert '边缘' in app.hint.get(),app.hint.get()
        assert not app.feedback['deadman']
        result['edge_kept_enabled']=True
        pump(.35,pose(pinch=True));assert app.feedback['phase']=='release'
        pump(.3,pose());pump(.3,pose(pinch=True))
        before=app.feedback['actual_tip'];pump(2.,pose(.5,.61,True))
        assert app.feedback['actual_tip'][1]<before[1]-.004
        # A transient camera delay must stop motion without revoking permission.
        pump(.55,pose(pinch=True),stale=True)
        assert app.enabled and not app.feedback['deadman']
        assert '卡顿' in app.hint.get(),app.hint.get()
        result['stale_kept_enabled']=True
        pump(.3,pose(pinch=True));assert app.feedback['phase']=='release'
        pump(.3,pose());pump(.35,pose(pinch=True))
        assert app.feedback['phase']=='center'
        max_tick_age=0
        for i in range(30):
            pump(.4,pose(.5,.54 if (i//5)%2==0 else .46,True))
            max_tick_age=max(max_tick_age,app.feedback['tick_age_ms'])
            assert app.feedback['ready'] and app.feedback['tick_age_ms']<250,app.feedback
        result['continuous_control_seconds']=12;result['max_tick_age_ms']=max_tick_age
        pump(.3,pose());pump(.35,pose(pinch=True))
        app.monitor.close();pump(.2,pose(pinch=True))
        app.render_state();root.attributes('-topmost',True);pump(.1,pose(pinch=True))
        ImageGrab.grab(bbox=(root.winfo_rootx(),root.winfo_rooty(),root.winfo_rootx()+root.winfo_width(),root.winfo_rooty()+root.winfo_height())).save(folder/'robot_interaction.png')
        app.pause();pump(.3,pose(pinch=True));assert not app.enabled and not app.feedback['deadman']
        result['status']='PASS';print(json.dumps(result),flush=True)
    finally:
        (folder/'robot_interaction_result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        app.close()
        while not app.closed.is_set():
            try:root.update()
            except tk.TclError:break
            time.sleep(.05)
        try:root.destroy()
        except tk.TclError:pass
        faulthandler.cancel_dump_traceback_later();trace_file.close()


if __name__=='__main__':main()
