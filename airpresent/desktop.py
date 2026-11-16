"""Windows keyboard output and a click-through pointer overlay."""

import ctypes
from ctypes import wintypes
import os
import tkinter as tk


def enable_dpi_awareness():
    if os.name == "nt":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (OSError, AttributeError):
            ctypes.windll.user32.SetProcessDPIAware()


class KeyboardOutput:
    def __init__(self):
        self.user32 = ctypes.WinDLL("user32", use_last_error=True) if os.name == "nt" else None
        if self.user32:
            self.user32.GetForegroundWindow.restype = wintypes.HWND
            self.user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
            self.user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
            self.user32.GetAsyncKeyState.restype = ctypes.c_short

    def foreground_is_self(self):
        if not self.user32:
            return True
        pid = wintypes.DWORD()
        hwnd = self.user32.GetForegroundWindow()
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value == os.getpid()

    def escape_pressed(self):
        return bool(self.user32 and self.user32.GetAsyncKeyState(0x1B) & 0x8000)

    def send_page(self, direction):
        if not self.user32:
            raise RuntimeError("实际翻页输出仅支持 Windows")
        if self.foreground_is_self():
            return False
        key = 0x27 if direction == "next" else 0x25
        # Union includes MOUSEINPUT to preserve the native INPUT structure size.
        class Mouse(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                        ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]

        class Key(ctypes.Structure):
            _fields_ = [("vk", wintypes.WORD), ("scan", wintypes.WORD),
                        ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("extra", ctypes.c_size_t)]

        class Data(ctypes.Union):
            _fields_ = [("mouse", Mouse), ("key", Key)]

        class Input(ctypes.Structure):
            _anonymous_ = ("data",)
            _fields_ = [("type", wintypes.DWORD), ("data", Data)]

        inputs = (Input * 2)()
        inputs[0].type = inputs[1].type = 1
        inputs[0].key = Key(key, 0, 0x0001, 0, 0)
        inputs[1].key = Key(key, 0, 0x0001 | 0x0002, 0, 0)
        self.user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int)
        self.user32.SendInput.restype = wintypes.UINT
        if self.user32.SendInput(2, inputs, ctypes.sizeof(Input)) != 2:
            error = ctypes.get_last_error()
            raise RuntimeError(f"Windows 未接受翻页按键（错误 {error}）。请确认 PPT 与本程序均以普通权限运行。")
        return True


class PointerOverlay:
    """A 36px transparent, non-activating window on the primary display."""

    def __init__(self, root):
        self.root = root
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.configure(bg="#010203")
        if os.name == "nt":
            self.window.attributes("-transparentcolor", "#010203")
        self.canvas = tk.Canvas(self.window, width=36, height=36, bg="#010203",
                                highlightthickness=0)
        self.canvas.pack()
        self.canvas.create_oval(3, 3, 33, 33, outline="#59e3b4", width=2)
        self.canvas.create_oval(14, 14, 22, 22, fill="#c7ffe7", outline="")
        self.window.geometry("36x36+0+0")
        self.window.update_idletasks()
        if os.name == "nt":
            user32 = ctypes.windll.user32
            user32.GetParent.argtypes = (wintypes.HWND,)
            user32.GetParent.restype = wintypes.HWND
            hwnd = user32.GetParent(self.window.winfo_id())
            get_style = user32.GetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.GetWindowLongW
            set_style = user32.SetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.SetWindowLongW
            get_style.argtypes = (wintypes.HWND, ctypes.c_int)
            get_style.restype = ctypes.c_ssize_t
            set_style.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
            set_style.restype = ctypes.c_ssize_t
            style = get_style(hwnd, -20)
            set_style(hwnd, -20, style | 0x00080000 | 0x00000020 | 0x08000000 | 0x00000080)
        self.visible = False
        self.user32 = ctypes.WinDLL("user32", use_last_error=True) if os.name == "nt" else None
        if self.user32:
            self.user32.GetParent.argtypes = (wintypes.HWND,)
            self.user32.GetParent.restype = wintypes.HWND
            self.user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
            self.user32.IsWindowVisible.argtypes = (wintypes.HWND,)
            self.user32.IsWindowVisible.restype = wintypes.BOOL
            self.user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                                ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT)
            self.user32.SetWindowPos.restype = wintypes.BOOL

    def _handle(self):
        return self.user32.GetParent(self.window.winfo_id()) or self.window.winfo_id()

    def is_visible(self):
        return bool(self.user32.IsWindowVisible(self._handle())) if self.user32 else bool(self.window.winfo_ismapped())

    def show(self, point):
        x = round(point[0] * (self.root.winfo_screenwidth() - 1))
        y = round(point[1] * (self.root.winfo_screenheight() - 1))
        x = max(0, min(self.root.winfo_screenwidth() - 36, x - 18))
        y = max(0, min(self.root.winfo_screenheight() - 36, y - 18))
        self.window.geometry(f"36x36+{x}+{y}")
        if self.window.state() == "withdrawn":
            self.window.deiconify()
            self.window.update_idletasks()
        if self.user32:
            # A Python flag cannot establish actual visibility or z-order.
            # Restore without activation on every requested display, including
            # after pause/resume, minimization, and an external window change.
            hwnd = self._handle()
            self.user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
            if not self.user32.SetWindowPos(hwnd, wintypes.HWND(-1), x, y, 36, 36, 0x0010 | 0x0040):
                raise RuntimeError(f"指示点显示失败（Windows 错误 {ctypes.get_last_error()}）")
        else:
            self.window.lift()
        self.visible = True

    def hide(self):
        if self.user32:
            self.user32.ShowWindow(self._handle(), 0)
        elif self.visible:
            self.window.withdraw()
        self.visible = False

    def close(self):
        self.window.destroy()
