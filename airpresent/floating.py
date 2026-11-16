"""Always-on-top presentation controls, with an optional small icon view."""

import ctypes
from ctypes import wintypes
import os
import time
import tkinter as tk


class FloatingControls:
    def __init__(self, root, previous, toggle, next_page, expand, summary=None):
        self.root = root
        self.expand = expand
        self.visible = False
        self.collapsed = False
        self.last_state = None
        self.last_raise = 0
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.configure(bg="#26394c")
        self.full = tk.Frame(self.window, bg="#19212c", padx=9, pady=6)
        self.full.pack(fill="both", expand=True, padx=1, pady=1)
        bar = tk.Frame(self.full, bg="#19212c")
        bar.pack(fill="x")
        self.status = tk.Label(bar, text="● 助手已暂停", bg="#19212c", fg="#f3c47b",
                               font=("Microsoft YaHei UI", 10, "bold"), anchor="w")
        self.status.pack(side="left", fill="x", expand=True)
        tk.Button(bar, text="收成图标", command=self.collapse, relief="flat", bd=0,
                  bg="#19212c", fg="#92a3b9", font=("Microsoft YaHei UI", 8)).pack(side="right")
        if summary:
            tk.Button(bar, text="AI 摘要", command=summary, relief="flat", bd=0,
                      bg="#19212c", fg="#64e4b8", font=("Microsoft YaHei UI", 8)).pack(side="right", padx=5)
        self.detail = tk.Label(self.full, text="", bg="#19212c", fg="#c3d1e2",
                               font=("Microsoft YaHei UI", 9), anchor="w")
        self.detail.pack(fill="x", pady=(2, 5))
        row = tk.Frame(self.full, bg="#19212c")
        row.pack(fill="x")
        self.buttons = []
        for text, callback in (("◀ 上一页", previous), ("启用", toggle), ("下一页 ▶", next_page), ("展开", expand)):
            button = tk.Button(row, text=text, command=callback, relief="flat", bd=0,
                               bg="#2b3c4f", fg="#edf4fc", activebackground="#40566d",
                               activeforeground="#edf4fc", font=("Microsoft YaHei UI", 9), pady=5)
            button.pack(side="left", fill="x", expand=True, padx=2)
            self.buttons.append(button)
        self.icon = tk.Button(self.window, text="手", command=self.uncollapse, relief="flat", bd=0,
                              bg="#19212c", fg="#f3c47b", activebackground="#25384a",
                              font=("Microsoft YaHei UI", 18, "bold"))
        x = max(0, root.winfo_screenwidth() - 350)
        y = max(0, root.winfo_screenheight() - 180)
        self.window.geometry(f"330x105+{x}+{y}")
        self.window.update_idletasks()
        for widget in (bar, self.status, self.detail):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._drag)
        self._configure_native()

    def _configure_native(self, show=False):
        if os.name != "nt":
            return
        u = ctypes.windll.user32
        u.GetParent.argtypes = (wintypes.HWND,)
        u.GetParent.restype = wintypes.HWND
        hwnd = u.GetParent(self.window.winfo_id()) or self.window.winfo_id()
        getter = u.GetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else u.GetWindowLongW
        setter = u.SetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else u.SetWindowLongW
        getter.argtypes = (wintypes.HWND, ctypes.c_int)
        getter.restype = ctypes.c_ssize_t
        setter.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
        setter.restype = ctypes.c_ssize_t
        setter(hwnd, -20, getter(hwnd, -20) | 0x08000000 | 0x00000080)
        u.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wintypes.UINT)
        flags = 0x0010 | 0x0001 | 0x0002 | (0x0040 if show else 0)
        u.SetWindowPos(hwnd, wintypes.HWND(-1), 0, 0, 0, 0, flags)

    def _start_drag(self, event):
        self.drag_offset = (event.x_root - self.window.winfo_x(), event.y_root - self.window.winfo_y())

    def _drag(self, event):
        dx, dy = self.drag_offset
        self.window.geometry(f"+{max(0, event.x_root - dx)}+{max(0, event.y_root - dy)}")

    def show(self):
        self._configure_native()
        self.window.deiconify()
        self.window.update_idletasks()
        self._configure_native(True)
        self.visible = True

    def collapse(self):
        self.full.pack_forget()
        self.icon.pack(fill="both", expand=True, padx=1, pady=1)
        self.window.geometry("54x54")
        self.collapsed = True

    def uncollapse(self):
        self.icon.pack_forget()
        self.full.pack(fill="both", expand=True, padx=1, pady=1)
        self.window.geometry("330x105")
        self.collapsed = False

    def set_status(self, status, detail, active, ready, can_page, busy):
        now = time.monotonic()
        if self.visible and now - self.last_raise > 0.5:
            self._configure_native(True)
            self.last_raise = now
        state = (status, detail, active, ready, can_page, busy)
        if state == self.last_state:
            return
        self.last_state = state
        color = "#64e4b8" if active and ready else "#f3c47b"
        self.status.config(text="● " + status, fg=color)
        self.detail.config(text=detail[:24])
        self.icon.config(fg=color)
        self.buttons[1].config(text="暂停" if active else "启用", state="normal" if ready else "disabled")
        for index in (0, 2):
            self.buttons[index].config(state="normal" if can_page and not busy else "disabled")

    def close(self):
        self.window.destroy()

    def hide(self):
        self.window.withdraw()
        self.visible = False
