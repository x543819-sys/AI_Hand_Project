"""Verify native keys only against a disposable window owned by this test."""

import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import subprocess
import sys
import time
import tkinter as tk
from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from airpresent.desktop import KeyboardOutput, PointerOverlay, enable_dpi_awareness


def fixture():
    enable_dpi_awareness()
    root = tk.Tk()
    root.title("AirPresent temporary key test")
    root.geometry("300x100+50+50")
    root.bind("<Right>", lambda event: print("RIGHT", flush=True))
    root.bind("<Left>", lambda event: print("LEFT", flush=True))
    root.update()
    user32 = ctypes.windll.user32
    user32.GetParent.argtypes = (wintypes.HWND,)
    user32.GetParent.restype = wintypes.HWND
    print(json.dumps({"hwnd": user32.GetParent(root.winfo_id())}), flush=True)
    root.after(20000, root.destroy)
    root.mainloop()


def verify():
    process = subprocess.Popen([sys.executable, __file__, "--fixture"], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    root = None
    try:
        hwnd = json.loads(process.stdout.readline())["hwnd"]
        enable_dpi_awareness()
        root = tk.Tk()
        root.geometry("400x180+500+50")
        root.update()
        output = KeyboardOutput()
        pointer = PointerOverlay(root)
        user32 = ctypes.windll.user32
        user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.15)
        if user32.GetForegroundWindow() != hwnd:
            raise RuntimeError("Fixture focus could not be acquired; no keys were sent")
        pointer.show((0.5, 0.5))
        root.update()
        time.sleep(0.1)
        assert user32.GetForegroundWindow() == hwnd, "Pointer overlay stole keyboard focus"
        for _ in range(15):
            pointer.hide()
            root.update()
            assert not pointer.is_visible(), "Pause did not hide native pointer"
            pointer.show((0.5, 0.5))
            root.update()
            assert pointer.is_visible(), "Resume did not show native pointer"
            assert user32.GetForegroundWindow() == hwnd, "Resume stole focus"
        # Simulate the OS hiding a window while its cached Python flag is true.
        pointer.user32.ShowWindow(pointer._handle(), 0)
        assert pointer.visible and not pointer.is_visible()
        pointer.show((0.5, 0.5))
        root.update()
        assert pointer.is_visible(), "Pointer did not recover from external hide"
        for operation in (root.iconify, root.deiconify, root.iconify, root.deiconify):
            operation()
            root.update()
            user32.SetForegroundWindow(hwnd)
            pointer.hide()
            pointer.show((0.5, 0.5))
            root.update()
            assert pointer.is_visible(), "Minimizing/restoring panel hid pointer"
            assert user32.GetForegroundWindow() == hwnd, "Pointer stole focus after panel state change"
        time.sleep(0.1)
        root.update()
        x, y = root.winfo_screenwidth() // 2, root.winfo_screenheight() // 2
        pixel = ImageGrab.grab(bbox=(x, y, x + 1, y + 1)).getpixel((0, 0))[:3]
        assert pixel == (199, 255, 231), f"Pointer center was not actually rendered: {pixel}"
        assert output.send_page("next")
        assert process.stdout.readline().strip() == "RIGHT"
        assert user32.GetForegroundWindow() == hwnd, "Fixture lost focus; refusing to send a second key"
        assert output.send_page("previous")
        assert process.stdout.readline().strip() == "LEFT"
        pointer.close()
        print("PASS: 15 hide/show cycles, external-hide recovery, panel minimize/restore preserve visibility and focus; test window received right/left keys")
    finally:
        if root is not None:
            root.destroy()
        process.terminate()
        process.communicate(timeout=5)


if __name__ == "__main__":
    fixture() if "--fixture" in sys.argv else verify()
