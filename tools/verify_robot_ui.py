"""Open actual Gazebo and the Windows workbench without opening a camera."""
import json
from pathlib import Path
import sys
import time,_tkinter
import tkinter as tk
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import ImageGrab
import win32gui
from airpresent.desktop import enable_dpi_awareness
from airpresent.robotics.ui import Workbench


def main():
    enable_dpi_awareness();root=tk.Tk();app=Workbench(root,gui=False)
    def pump(seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            for _ in range(10):
                if not root.tk.dooneevent(_tkinter.DONT_WAIT):break
            time.sleep(.02)
    folder=Path(__file__).resolve().parents[1]/'screenshots';folder.mkdir(exist_ok=True)
    try:
        deadline=time.monotonic()+120
        while not app.feedback.get('ready'):
            pump(.05)
            if app.closed.is_set() or time.monotonic()>deadline:raise AssertionError(app.status.get())
        assert app.camera is None and not app.enabled
        app.enable();assert not app.enabled
        root.attributes('-topmost',True);root.update_idletasks();pump(.5)
        ImageGrab.grab(bbox=(root.winfo_rootx(),root.winfo_rooty(),root.winfo_rootx()+root.winfo_width(),root.winfo_rooty()+root.winfo_height())).save(folder/'robot_workbench.png')
        app.plane.set('XZ · 伸出 / 升降');app.change_mode();assert app.mode=='xz' and not app.enabled
        existing=[]
        win32gui.EnumWindows(lambda handle,_:existing.append(handle) if win32gui.IsWindowVisible(handle) and 'Gazebo' in win32gui.GetWindowText(handle) else None,None)
        app.open_gui()
        ready_time=time.monotonic()
        while time.monotonic()-ready_time<12:pump(.05)
        windows=[]
        win32gui.EnumWindows(lambda handle,_: windows.append(handle) if handle not in existing and win32gui.IsWindowVisible(handle) and 'Gazebo' in win32gui.GetWindowText(handle) else None,None)
        if windows:
            root.iconify();pump(.1)
            try:win32gui.SetForegroundWindow(windows[0])
            except Exception:pass
            time.sleep(.6)
            ImageGrab.grab(bbox=win32gui.GetWindowRect(windows[0])).save(folder/'gazebo_arm.png')
            root.deiconify()
        root.attributes('-topmost',True);pump(.4)
        assert windows,'Optional Gazebo GUI did not open'
        for handle in windows:win32gui.PostMessage(handle,16,0,0)
        pump(3)
        assert app.feedback.get('ready') and not app.closed.is_set(),'Closing optional GUI stopped the physics server'
        result={'status':'PASS','camera_opened':False,'actual_feedback':app.feedback,'gui_requested':True,'gazebo_windows':len(windows),'gui_close_kept_physics':True}
        (folder/'robot_ui_result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print('PASS: real Gazebo + workbench, actual feedback, camera off',flush=True)
    finally:
        app.close()
        while not app.closed.is_set():pump(.05)
        try:root.destroy()
        except tk.TclError:pass


if __name__=='__main__':main()
