"""Tk control panel. Starting the app alone never opens the camera."""

from collections import deque
import csv
from datetime import datetime
from pathlib import Path
from queue import Empty
import subprocess
import sys
import time
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from .config import Settings
from .controller import Controller
from .desktop import KeyboardOutput, PointerOverlay
from .presentation import PresentationOutput
from .page_output import AsyncPageOutput
from .floating import FloatingControls
from .summary import SummaryWorker
from .summary_ui import SummaryPanel
from .gestures import Gesture, Observation
from .tracker import CameraWorker


BG = "#10151d"
CARD = "#19212c"
INNER = "#111a24"
LINE = "#2b3746"
TEXT = "#edf4fc"
MUTED = "#92a3b9"
GREEN = "#64e4b8"
AMBER = "#f3c47b"
FONT = "Microsoft YaHei UI"


class App:
    def __init__(self, root, project_dir: Path, page_service_factory=None):
        self.root = root
        # Keep font metrics aligned with the panel's pixel layout on high-DPI
        # Windows desktops; the default Tk scaling can otherwise crop controls.
        root.tk.call("tk", "scaling", 4 / 3)
        self.project_dir = project_dir
        self.settings_path = project_dir / "settings.json"
        load_error = None
        try:
            self.settings = Settings.load(self.settings_path)
        except (ValueError, TypeError, OSError) as exc:
            self.settings = Settings()
            load_error = f"设置文件无法读取，已使用默认参数：{exc}"
        self.controller = Controller(self.settings)
        self.worker = None
        self.ready = False
        self.stopping = False
        self.closing = False
        self.last_frame_time = None
        self.had_error = False
        self.keyboard = KeyboardOutput()
        self.presentation = PresentationOutput()
        self.page_output = AsyncPageOutput(page_service_factory or PresentationOutput)
        self.floating = None
        self.summary_panel = None
        self.summary_worker = SummaryWorker()
        self.ai_keys = {}
        self.viewer3d_process = None
        self.viewer3d_launching = False
        self.last_observation = Observation()
        self.frame_warning = None
        self.last_feedback = ""
        self.feedback_until = 0
        self.overlay = PointerOverlay(root)
        self.live_output = tk.BooleanVar(value=self.settings.live_output)
        self.pointer_enabled = tk.BooleanVar(value=True)
        self.page = 1
        self.swipes = 0
        self.confirmed_pages = 0
        self.frame_count = 0
        self.fps_values = deque(maxlen=30)
        self.inference_values = []
        self.events = []
        self.tracking_trace = deque(maxlen=1800)
        self.started_at = None
        self.elapsed_seconds = 0.0
        self.stop_started = None
        self._build()
        self.floating = FloatingControls(root, lambda: self.test_page("previous"), self.toggle_control,
                                          self.test_next_page, self.restore_main, self.open_summary)
        self._refresh_output_ui()
        self._placeholder()
        self._refresh_floating()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Escape>", lambda event: self.pause("键盘暂停"))
        self.root.after(25, self._poll)
        if load_error:
            self.log(load_error)

    def _build(self):
        root = self.root
        root.title("AirPresent · 手势演示助手")
        root.geometry("1180x880")
        root.minsize(1040, 860)
        root.configure(bg=BG)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=INNER, background=LINE,
                        foreground=TEXT, arrowcolor=MUTED, borderwidth=0, padding=5)
        style.map("TCombobox", fieldbackground=[("readonly", INNER)],
                  foreground=[("readonly", TEXT)])
        style.configure("TSpinbox", fieldbackground=INNER, background=LINE,
                        foreground=TEXT, arrowcolor=MUTED, padding=5)
        style.configure("TProgressbar", troughcolor=INNER, background=GREEN,
                        borderwidth=0, lightcolor=GREEN, darkcolor=GREEN)
        outer = tk.Frame(root, bg=BG)
        outer.pack(fill="both", expand=True, padx=28, pady=(22, 16))
        header = tk.Frame(outer, bg=BG)
        header.pack(fill="x", pady=(0, 18))
        tk.Label(header, text="◉", font=(FONT, 30), fg=GREEN, bg=BG).pack(side="left", padx=(0, 12))
        title = tk.Frame(header, bg=BG)
        title.pack(side="left")
        tk.Label(title, text="AirPresent", font=(FONT, 25, "bold"), fg=TEXT, bg=BG).pack(anchor="w")
        tk.Label(title, text="手势演示助手  /  让讲解更自由", font=(FONT, 10), fg=MUTED, bg=BG).pack(anchor="w")
        self.mode_label = tk.Label(header, text="●  预览练习", bg="#21382f", fg=GREEN,
                                   font=(FONT, 10), padx=15, pady=8)
        self.mode_label.pack(side="right", anchor="center")
        self._button(header, "3D 工作台", self.launch_3d).pack(side="right", padx=(0, 8))
        self._button(header, "AI 摘要", self.open_summary).pack(side="right", padx=(0, 8))
        self._button(header, "悬浮控制", self.show_floating_controls).pack(side="right", padx=(0, 12))
        body = tk.Frame(outer, bg=BG)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=0, minsize=306)
        body.rowconfigure(0, weight=1)
        left = tk.Frame(body, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        right = tk.Frame(body, bg=BG, width=306)
        right.grid(row=0, column=1, sticky="nsew")
        self._preview(left)
        self._practice(left)
        self._controls(right)
        self._gestures(right)
        footer = tk.Frame(outer, bg=BG)
        footer.pack(fill="x", pady=(10, 0))
        tk.Label(footer, text="本地处理 · 不上传摄像头画面", fg=MUTED, bg=BG, font=(FONT, 9)).pack(side="left")
        tk.Label(footer, text="Esc 随时暂停   ·   v0.8", fg=MUTED, bg=BG, font=(FONT, 9)).pack(side="right")
        # Reserve the footer before distributing the remaining height.
        body.pack_forget()
        footer.pack_forget()
        footer.pack(side="bottom", fill="x", pady=(10, 0))
        body.pack(fill="both", expand=True)

    def _card(self, parent):
        return tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)

    def _button(self, parent, text, command, primary=False, **kwargs):
        return tk.Button(parent, text=text, command=command, font=(FONT, 10, "bold"),
                         bg=GREEN if primary else LINE, fg=BG if primary else TEXT,
                         activebackground="#87efce" if primary else "#3b4b5e",
                         activeforeground=BG if primary else TEXT, disabledforeground="#5d7083",
                         relief="flat", bd=0, padx=14, pady=7, cursor="hand2", **kwargs)

    def _preview(self, parent):
        card = self._card(parent)
        card.pack(fill="both", expand=True)
        bar = tk.Frame(card, bg=CARD)
        bar.pack(fill="x", padx=16, pady=12)
        tk.Label(bar, text="实时画面", font=(FONT, 11, "bold"), bg=CARD, fg=TEXT).pack(side="left")
        self.camera_badge = tk.Label(bar, text="●  未连接", font=(FONT, 9), bg=CARD, fg=MUTED)
        self.camera_badge.pack(side="right")
        self.canvas = tk.Canvas(card, bg="#0c131c", height=285, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=12)
        self.canvas.bind("<Configure>", lambda event: self._placeholder() if not self.ready else None)
        status = tk.Frame(card, bg=CARD)
        status.pack(fill="x", padx=16, pady=(10, 4))
        self.gesture_label = tk.Label(status, text="等待手势", bg=CARD, fg=TEXT, font=(FONT, 12, "bold"))
        self.gesture_label.pack(side="left")
        self.control_label = tk.Label(status, text="控制已暂停", bg=CARD, fg=AMBER, font=(FONT, 9))
        self.control_label.pack(side="right")
        self.progress = ttk.Progressbar(card, maximum=1.0)
        self.progress.pack(fill="x", padx=16, pady=(4, 12))
        metrics = tk.Frame(card, bg=INNER)
        metrics.pack(fill="x")
        self.metric_labels = []
        for index, (label, initial) in enumerate((("处理帧率", "— FPS"), ("单帧推理", "— ms"), ("识别 / 确认翻页", "0 / 0"))):
            block = tk.Frame(metrics, bg=INNER)
            block.pack(side="left", fill="x", expand=True, padx=16, pady=10)
            value = tk.Label(block, text=initial, fg=TEXT, bg=INNER, font=(FONT, 16, "bold"))
            value.pack(anchor="w")
            tk.Label(block, text=label, fg=MUTED, bg=INNER, font=(FONT, 9)).pack(anchor="w")
            self.metric_labels.append(value)

    def _practice(self, parent):
        card = self._card(parent)
        card.pack(fill="x", pady=(14, 0))
        line = tk.Frame(card, bg=CARD)
        line.pack(fill="x", padx=16, pady=(12, 4))
        tk.Label(line, text="翻页练习", font=(FONT, 11, "bold"), fg=TEXT, bg=CARD).pack(side="left")
        self.page_label = tk.Label(line, text="01 / 05", font=(FONT, 11, "bold"), fg=GREEN, bg=CARD)
        self.page_label.pack(side="right")
        self.slide_title = tk.Label(card, text="准备好，让手势接管翻页", font=(FONT, 14, "bold"), fg=TEXT, bg=CARD)
        self.slide_title.pack(anchor="w", padx=16, pady=(5, 4))
        self.slide_detail = tk.Label(card, text="拇指捏食指下一页，捏中指上一页；松开后可再次触发。", font=(FONT, 9), fg=MUTED, bg=CARD)
        self.slide_detail.pack(anchor="w", padx=16, pady=(0, 13))
        connection = tk.Frame(card, bg=CARD)
        connection.pack(fill="x", padx=16, pady=(0, 12))
        self.target_label = tk.Label(connection, text="未连接 PPT 放映", font=(FONT, 9), fg=AMBER, bg=CARD,
                                     anchor="w", width=25)
        self.target_label.pack(side="left", fill="x", expand=True)
        self._button(connection, "连接 PPT", self.connect_presentation).pack(side="left", padx=(6, 6))
        self.test_next_button = self._button(connection, "测试下一页", self.test_next_page, state="disabled")
        self.test_next_button.pack(side="left")
        self.test_previous_button = self._button(connection, "测试上一页", lambda: self.test_page("previous"), state="disabled")
        self.test_previous_button.pack(side="left", padx=(6, 0))

    def _controls(self, parent):
        card = self._card(parent)
        card.pack(fill="x")
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="x", padx=16, pady=12)
        tk.Label(inner, text="演示控制", font=(FONT, 12, "bold"), bg=CARD, fg=TEXT).pack(anchor="w", pady=(0, 8))
        camera_row = tk.Frame(inner, bg=CARD)
        camera_row.pack(fill="x", pady=(0, 6))
        tk.Label(camera_row, text="摄像头", font=(FONT, 10), bg=CARD, fg=MUTED).pack(side="left")
        self.camera_var = tk.StringVar(value=str(self.settings.camera_index))
        self.camera_choice = ttk.Combobox(camera_row, textvariable=self.camera_var,
                                          values=list(range(10)), width=4, state="readonly")
        self.camera_choice.pack(side="right")
        self.start_button = self._button(inner, "开启摄像头", self.toggle_camera, primary=True)
        self.start_button.pack(fill="x", pady=(0, 8))
        self.active_button = self._button(inner, "启用控制", self.toggle_control, state="disabled")
        self.active_button.pack(fill="x")
        self._check(inner, "控制已连接的 PPT（取消为练习）", self.live_output, self.change_output)
        self._check(inner, "显示屏幕指示点", self.pointer_enabled, self.change_pointer)
        self.status_label = tk.Label(inner, text="先在 PPT 中开始放映，再点击左侧“连接 PPT”。", font=(FONT, 9),
                                     bg=CARD, fg=MUTED, wraplength=260, justify="left")
        self.status_label.pack(anchor="w", pady=(6, 6))
        actions = tk.Frame(inner, bg=CARD)
        actions.pack(fill="x")
        self._button(actions, "参数设置", self.open_settings).pack(side="left", expand=True, fill="x", padx=(0, 6))
        self._button(actions, "导出诊断", self.export_session).pack(side="left", expand=True, fill="x")

    def _check(self, parent, text, variable, command):
        tk.Checkbutton(parent, text=text, variable=variable, command=command,
                       bg=CARD, fg=TEXT, activebackground=CARD, activeforeground=TEXT,
                       selectcolor=INNER, font=(FONT, 9), anchor="w", bd=0,
                       highlightthickness=0).pack(fill="x", pady=(7, 0))

    def _gestures(self, parent):
        card = self._card(parent)
        card.pack(fill="both", expand=True, pady=(14, 0))
        tk.Label(card, text="手势指南", font=(FONT, 11, "bold"), bg=CARD, fg=TEXT).pack(anchor="w", padx=16, pady=(10, 5))
        self.guide_details = {}
        self.guide_titles = {}
        for code, title, detail in (("01", "剪刀手 · 启用", ""),
                                    ("02", "捏合 · 翻页", ""),
                                    ("03", "伸出食指 · 指示", "直接跟随，无需等待确认"),
                                    ("04", "握拳 / Esc · 暂停", "")):
            row = tk.Frame(card, bg=CARD)
            row.pack(fill="x", padx=16, pady=3)
            tk.Label(row, text=code, font=(FONT, 10, "bold"), fg=GREEN, bg=INNER, padx=7, pady=5).pack(side="left", padx=(0, 10))
            content = tk.Frame(row, bg=CARD)
            content.pack(side="left")
            title_label = tk.Label(content, text=title, font=(FONT, 10), fg=TEXT, bg=CARD)
            title_label.pack(anchor="w")
            self.guide_titles[code] = title_label
            label = tk.Label(content, text=detail, font=(FONT, 8), fg=MUTED, bg=CARD)
            label.pack(anchor="w")
            self.guide_details[code] = label
        self.page_hint_label = tk.Label(card, text="", font=(FONT, 9), fg=AMBER, bg=CARD)
        self.page_hint_label.pack(anchor="w", padx=16, pady=(6, 6))
        self._refresh_guide()
        tk.Frame(card, bg=LINE, height=1).pack(fill="x", padx=16)
        tk.Label(card, text="最近动态", font=(FONT, 9), fg=MUTED, bg=CARD).pack(anchor="w", padx=16, pady=(9, 4))
        self.log_label = tk.Label(card, text="就绪，等待开启摄像头。", font=(FONT, 9), fg=TEXT, bg=CARD,
                                  justify="left", anchor="nw", wraplength=260)
        self.log_label.pack(fill="both", expand=True, padx=16, pady=(0, 12))

    def _refresh_guide(self):
        self.guide_details["01"].config(text=f"保持约 {self.settings.resume_ms / 1000:g} 秒，开始控制")
        detail = (f"握紧保持 {self.settings.pause_ms / 1000:g} 秒；Esc 立即暂停"
                  if self.settings.fist_pause_enabled else "启用一次连续操作；Esc 或按钮暂停")
        self.guide_details["04"].config(text=detail)
        self.guide_titles["04"].config(text="握拳 / Esc · 暂停" if self.settings.fist_pause_enabled else "Esc / 按钮 · 暂停")
        pinch = self.settings.page_gesture == "pinch"
        self.guide_titles["02"].config(text="捏合 · 翻页" if pinch else "手掌轻拨 · 翻页")
        self.guide_details["02"].config(text="拇指＋食指下一页；＋中指上一页" if pinch else "掌心右拨下一页，左拨上一页")
        self.page_hint_label.config(text="捏住只翻一次，分开后可再捏。" if pinch else "轻拨一下翻一页，停稳后可再拨。")

    def _placeholder(self):
        canvas = self.canvas
        w, h = max(canvas.winfo_width(), 400), max(canvas.winfo_height(), 240)
        canvas.delete("all")
        for x in range(0, w, 36):
            canvas.create_line(x, 0, x, h, fill="#15212c")
        for y in range(0, h, 36):
            canvas.create_line(0, y, w, y, fill="#15212c")
        cx, cy = w / 2, h / 2 - 32
        canvas.create_oval(cx - 38, cy - 38, cx + 38, cy + 38, outline="#36534e", width=2)
        canvas.create_rectangle(cx - 18, cy - 12, cx + 12, cy + 12, outline=GREEN, width=2)
        canvas.create_polygon(cx + 12, cy - 7, cx + 25, cy - 14, cx + 25, cy + 14,
                              cx + 12, cy + 7, outline=GREEN, fill="", width=2)
        canvas.create_text(cx, cy + 72, text="你的下一场演示，从这里开始", fill=TEXT, font=(FONT, 15, "bold"))
        canvas.create_text(cx, cy + 105, text="点击「开启摄像头」，查看手部追踪画面", fill=MUTED, font=(FONT, 10))
        margin = self.settings.roi_margin
        canvas.create_rectangle(w * margin, h * margin, w * (1 - margin), h * (1 - margin),
                                outline="#294337", dash=(6, 5))

    def log(self, message):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_label.config(text=f"{stamp}  {message}")
        self.last_feedback = message
        self.feedback_until = time.monotonic() + 2
        self._refresh_floating()

    def show_floating_controls(self):
        self.floating.show()
        self._refresh_floating()
        if self.ready:
            self.root.iconify()

    def restore_main(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _refresh_floating(self):
        if self.floating is None or self.closing:
            return
        active = self.controller.active
        busy = self.page_output.busy or self.summary_worker.busy
        if self.summary_panel is not None:
            status = "摘要窗口已打开 · 手势暂停"
        elif not self.ready:
            status = "摄像头未开启"
        elif not active:
            status = "已暂停"
        elif busy:
            status = "正在切页 · 保持启用"
        elif self.frame_warning:
            status = "等待画面 · 保持启用"
        elif self.last_observation.gesture == Gesture.NONE:
            status = "等待手部 · 保持启用"
        elif self.settings.page_gesture == "pinch" and self.controller.pinch.latched:
            status = "保持启用 · 松开指尖"
        elif self.settings.page_gesture == "pinch" and not self.controller.pinch.armed:
            status = "保持启用 · 先分开指尖"
        else:
            status = "已启用 · 可连续翻页"
        detail = self.last_feedback if time.monotonic() < self.feedback_until else self.last_observation.gesture.value
        can_page = not self.live_output.get() or self.presentation.target is not None
        self.floating.set_status(status, detail, active, self.ready, can_page, busy)
        state = "normal" if self.presentation.target is not None and not busy else "disabled"
        self.test_next_button.config(state=state)
        self.test_previous_button.config(state=state)

    def _record(self, action, detail=""):
        self.events.append({"time": datetime.now().isoformat(timespec="milliseconds"),
                            "action": action, "mode": "live" if self.live_output.get() else "preview",
                            "detail": detail})

    def toggle_camera(self):
        if self.worker:
            self.stop_camera()
            return
        self.settings.camera_index = int(self.camera_var.get())
        self.worker = CameraWorker(self.settings, self.project_dir / "models" / "hand_landmarker.task")
        self.ready = False
        self.stopping = self.had_error = False
        self.stop_started = None
        self.last_frame_time = None
        self.started_at = time.monotonic()
        self.start_button.config(text="取消连接")
        self.camera_choice.config(state="disabled")
        self.status_label.config(text="正在准备摄像头和手部模型…")
        self.worker.start()

    def stop_camera(self):
        self.pause("摄像头已停止")
        self.ready = False
        if self.worker:
            self.stopping = True
            self.stop_started = time.monotonic()
            self.worker.stop()
            self.start_button.config(text="正在关闭…", state="disabled")
            self.active_button.config(state="disabled")

    def launch_3d(self):
        if self.viewer3d_launching or (self.viewer3d_process and self.viewer3d_process.poll() is None):
            self.log("3D 工作台已在启动或运行，请查看浏览器标签页。")
            return
        self.viewer3d_launching = True
        started = time.monotonic()
        if self.worker:
            self.stop_camera()
        self.floating.hide()

        def launch():
            if self.closing:
                self.viewer3d_launching = False
                return
            if self.worker and self.worker.running:
                if time.monotonic() - started > 4:
                    self.viewer3d_launching = False
                    self.log("摄像头尚未释放，请关闭当前助手后运行 run_3d.bat。")
                    return
                self.root.after(100, launch)
                return
            try:
                self.viewer3d_process = subprocess.Popen([sys.executable, "-m", "airpresent.viewer3d.server"],
                    cwd=self.project_dir, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                self.log("3D 工作台将在浏览器打开，摄像头需在工作台内手动开启。")
            except OSError as exc:
                self.log(f"3D 工作台未启动：{exc}")
            self.viewer3d_launching = False
        launch()

    def open_summary(self):
        if self.summary_panel is not None:
            self.summary_panel.window.deiconify()
            self.summary_panel.window.lift()
            return
        if self.summary_worker.busy:
            self.log("上一次摘要请求正在结束，请稍候。")
            return
        self.pause("打开摘要，手势翻页已暂停。")
        self.summary_panel = SummaryPanel(self, self.summary_worker)
        self._refresh_floating()

    def toggle_control(self):
        if self.summary_panel is not None:
            self.open_summary()
            return
        if not self.ready:
            return
        if self.controller.active:
            self.pause("手动暂停")
        else:
            if self.live_output.get() and self.presentation.target is None:
                self.log("尚未连接 PPT；请先连接并点击“测试下一页”。")
                self.status_label.config(text="未连接放映。取消“控制已连接的 PPT”可使用练习模式。")
                return
            self.controller.set_active(True, time.monotonic())
            self.floating.show()
            self._record("resume", "button")
            self.log("控制已启用，请先分开指尖，再捏合翻页。" if self.settings.page_gesture == "pinch"
                     else "轻拨控制已启用。")
            self._state()

    def pause(self, reason):
        was_active = self.controller.active
        self.controller.set_active(False, time.monotonic())
        self.overlay.hide()
        if was_active:
            self._record("pause", reason)
            self.log(reason)
        self._state()

    def change_output(self):
        self.pause("输出模式已切换，请重新启用控制。")
        self.settings.live_output = self.live_output.get()
        try:
            self.settings.save(self.settings_path)
        except OSError as exc:
            self.log(f"模式未能保存：{exc}")
        self._refresh_output_ui()

    def _refresh_output_ui(self):
        live = self.live_output.get()
        self.mode_label.config(text="●  PPT 控制" if live else "●  仅练习，不控制 PPT", fg=AMBER if live else GREEN,
                               bg="#3e3221" if live else "#21382f")
        self.status_label.config(text="请先连接正在放映的 PPT，使用“测试下一页”确认页码变化。" if live
                                 else "仅练习，不会改变真实 PPT 页码。所选模式会保存。")

    def connect_presentation(self):
        self.pause("连接 PPT")
        try:
            targets = self.presentation.list_targets()
        except (ImportError, RuntimeError) as exc:
            self.log(f"连接不可用，请先运行 setup.bat：{exc}")
            return
        if not targets:
            self.target_label.config(text="未找到放映：请先按 F5", fg=AMBER)
            self.status_label.config(text="请在 PowerPoint 或 WPS 中开始放映，再点击“连接 PPT”。")
            return

        def select(target):
            self.presentation.select(target)
            self.live_output.set(True)
            self.change_output()
            self.target_label.config(text=f"已连接：{target.name[:24]}", fg=GREEN)
            self.test_next_button.config(state="normal")
            self.test_previous_button.config(state="normal")
            self.log("PPT 已连接，请先点击“测试下一页”确认。")
            self.floating.show()

        if len(targets) == 1:
            select(targets[0])
            return
        window = tk.Toplevel(self.root)
        window.title("选择正在放映的 PPT")
        window.transient(self.root)
        window.configure(bg=CARD)
        choices = tk.Listbox(window, width=62, height=min(8, len(targets)), font=(FONT, 10), bg=INNER, fg=TEXT)
        choices.pack(padx=16, pady=16)
        for target in targets:
            choices.insert("end", target.name)
        choices.selection_set(0)

        def confirm():
            index = choices.curselection()
            if index:
                select(targets[index[0]])
                window.destroy()
        self._button(window, "连接所选放映", confirm, primary=True).pack(padx=16, pady=(0, 16), fill="x")

    def test_next_page(self):
        self.test_page("next")

    def test_page(self, direction):
        if not self.live_output.get():
            self.live_output.set(True)
            self.change_output()
        self._page_action(direction, manual=True)

    def change_pointer(self):
        if not self.pointer_enabled.get():
            self.overlay.hide()

    def _state(self):
        active = self.controller.active
        self.control_label.config(text="控制已启用" if active else "控制已暂停", fg=GREEN if active else AMBER)
        self.active_button.config(text="暂停控制" if active else "启用控制", state="normal" if self.ready else "disabled")
        self._refresh_floating()

    def _show_frame(self, frame):
        image = Image.fromarray(frame.rgb)
        w, h = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        image.thumbnail((w, h), Image.Resampling.BILINEAR)
        self.photo = ImageTk.PhotoImage(image)
        self.canvas.delete("all")
        self.canvas.create_image(w / 2, h / 2, image=self.photo)
        self.frame_count += 1
        self.fps_values.append(frame.fps)
        self.inference_values.append(frame.inference_ms)
        self.metric_labels[0].config(text=f"{sum(self.fps_values) / len(self.fps_values):.1f} FPS")
        self.metric_labels[1].config(text=f"{frame.inference_ms:.0f} ms")

    def _handle_frame(self, frame):
        # Drop stale results, including a slow model's very first frame.
        now = time.monotonic()
        if now - frame.timestamp > 0.5:
            self.frame_warning = "画面延迟"
            self.overlay.hide()
            self.controller.reset_motion()
            self.control_label.config(text="等待新画面 · 保持启用", fg=AMBER)
            self._refresh_floating()
            return
        self.last_frame_time = now
        self.frame_warning = None
        self.last_observation = frame.observation
        self._show_frame(frame)
        if self.keyboard.escape_pressed():
            self.pause("Esc 暂停")
            return
        if self.summary_panel is not None:
            self.gesture_label.config(text=frame.observation.gesture.value)
            self._refresh_floating()
            return
        result = self.controller.update(frame.observation, frame.timestamp)
        if result.active and self.live_output.get() and self.presentation.target is None:
            self.pause("请先连接 PPT，或选择练习模式。")
            return
        self.gesture_label.config(text=frame.observation.gesture.value)
        self.progress["value"] = result.progress if frame.observation.gesture in (
            Gesture.FIST, Gesture.VICTORY, Gesture.PINCH_NEXT, Gesture.PINCH_PREVIOUS) else 0
        if frame.observation.gesture == Gesture.FIST and not self.settings.fist_pause_enabled:
            self.gesture_label.config(text="握拳 · 暂停已关闭")
            self.progress["value"] = 0
        self._state()
        if (frame.observation.gesture == Gesture.FIST and result.active
                and self.settings.fist_pause_enabled):
            self.control_label.config(text="准备暂停 · 松开取消", fg=AMBER)
        elif frame.observation.gesture == Gesture.VICTORY and not result.active:
            self.control_label.config(text="准备启用 · 保持剪刀手", fg=GREEN)
        elif result.active and result.pointer:
            self.control_label.config(text="指示点跟随中", fg=GREEN)
        elif result.active and self.settings.page_gesture == "pinch":
            pager = self.controller.pinch
            if pager.latched:
                text = "本次已触发 · 松开指尖"
            elif not pager.armed:
                text = "先分开指尖"
            elif frame.observation.gesture in (Gesture.PINCH_NEXT, Gesture.PINCH_PREVIOUS):
                text = "确认下一页…" if frame.observation.gesture == Gesture.PINCH_NEXT else "确认上一页…"
            else:
                text = "捏合已就绪"
            self.control_label.config(text=text, fg=GREEN)
        elif result.active and frame.observation.gesture in (Gesture.PALM, Gesture.UNKNOWN):
            self.control_label.config(text="停稳后可再拨" if self.controller.flick.latched else "轻拨已就绪", fg=GREEN)
        for event in result.events:
            self._record(event)
            if event in ("next", "previous"):
                self._page_action(event)
            elif event == "resume":
                self.log("剪刀手确认：控制已启用。")
            elif event == "pause":
                self.log("握拳确认：控制已暂停。")
            elif event == "lost_pause":
                self.log("手部离开画面，已自动暂停。")
        try:
            if result.pointer and result.active and self.pointer_enabled.get():
                self.overlay.show(result.pointer)
            else:
                self.overlay.hide()
        except (RuntimeError, tk.TclError) as exc:
            self.pointer_enabled.set(False)
            self.overlay.hide()
            self.log(f"指示点已关闭，翻页保持启用：{exc}")
            self._record("pointer_error", str(exc))
        self.tracking_trace.append({
            "time": datetime.now().isoformat(timespec="milliseconds"),
            "gesture": frame.observation.gesture.name,
            "active": self.controller.active,
            "pointer_requested": result.pointer is not None,
            "pointer_visible": self.overlay.is_visible(),
            "flick_waiting_for_settle": self.controller.flick.latched,
            "page_gesture": self.settings.page_gesture,
            "pinch_armed": self.controller.pinch.armed,
            "pinch_latched": self.controller.pinch.latched,
            "pinch_released": frame.observation.pinch_released,
            "frame_age_ms": round((time.monotonic() - frame.timestamp) * 1000, 1),
            "inference_ms": round(frame.inference_ms, 1),
            "fps": round(frame.fps, 1),
        })

    def _page_action(self, direction, manual=False):
        if self.summary_worker.busy:
            self.log("正在读取或总结页面，请等待完成。")
            return
        if not manual:
            self.swipes += 1
        self.metric_labels[2].config(text=f"{self.swipes} / {self.confirmed_pages}")
        label = "下一页" if direction == "next" else "上一页"
        if self.live_output.get():
            if self.presentation.target is None:
                self.log("请先连接 PPT。")
                return
            if not self.page_output.submit(self.presentation.target, direction, manual):
                self.log("上一条切页请求仍在处理，请稍候。")
                return
            self.log(f"正在请求{label}，控制保持启用。")
            return
        else:
            self.page = max(1, min(5, self.page + (1 if direction == "next" else -1)))
            slides = (("准备好，让手势接管翻页", "拇指捏食指下一页，捏中指上一页；松开再翻"),
                      ("先让识别稳定下来", "关节角度判断 + 手掌比例归一化 + 时间确认"),
                      ("确认一次，只翻一页", "捏合后松开，或在设置中选择旧版轻拨"),
                      ("把重点，指给观众看", "伸出食指移动指示点；握拳或 Esc 暂停"),
                      ("从演示，走向完整作品", "记录性能、测试误触发，再接入真实的放映场景"))
            self.page_label.config(text=f"{self.page:02d} / 05")
            self.slide_title.config(text=slides[self.page - 1][0])
            self.slide_detail.config(text=slides[self.page - 1][1])
        self.metric_labels[2].config(text=f"{self.swipes} / {self.confirmed_pages}")
        self.log(f"练习：{label}。真实 PPT 未改变。")

    def _poll_output(self):
        item = self.page_output.poll()
        if item is None:
            return
        request, result, error = item
        if error is not None:
            self.log(f"切页暂未成功，可松开重试：{error}")
            self._record("output_error", str(error))
            return
        if result is None:
            return
        self._record("page_confirmed" if result.changed else "page_unchanged", result.message)
        if request.target != self.presentation.target or not self.live_output.get():
            return
        if result.changed and not request.manual:
            self.confirmed_pages += 1
        self.page_label.config(text=f"PPT 第 {result.after} 页")
        self.slide_title.config(text=result.message)
        self.slide_detail.config(text="页码由后台读取；启用状态不因一次切页而改变。")
        self.metric_labels[2].config(text=f"{self.swipes} / {self.confirmed_pages}")
        self.log(result.message)

    def _poll(self):
        if self.closing and self.worker and self.worker.running and time.monotonic() - self.close_started < 3:
            self.root.after(40, self._poll)
            return
        if self.closing:
            self.overlay.close()
            self.floating.close()
            self.page_output.close()
            self.presentation.close()
            self.root.destroy()
            return
        if self.controller.active and self.keyboard.escape_pressed():
            self.pause("Esc 暂停")
        self._poll_output()
        if self.summary_panel is None:
            while self.summary_worker.poll() is not None:
                pass
        if self.worker:
            try:
                while True:
                    kind, message = self.worker.messages.get_nowait()
                    if kind == "ready" and not self.stopping:
                        self.ready = True
                        self.last_frame_time = time.monotonic()
                        self.start_button.config(text="关闭摄像头")
                        self.camera_badge.config(text="●  已连接", fg=GREEN)
                        self._state()
                    elif kind == "error":
                        self.had_error = True
                        self.pause("摄像头或模型异常")
                        self.log(message)
                    if kind != "stopped" or not self.had_error:
                        self.status_label.config(text=message)
                    if kind == "error":
                        self.status_label.config(text=message)
            except Empty:
                pass
            frame = self.worker.latest()
            if frame is not None and self.ready and not self.stopping:
                self._handle_frame(frame)
            if self.ready and self.last_frame_time is not None and time.monotonic() - self.last_frame_time > 0.65:
                self.frame_warning = "等待新画面"
                self.overlay.hide()
                self.controller.reset_motion()
                self.gesture_label.config(text="等待新画面")
            if not self.worker.running:
                self.pause("摄像头已关闭")
                if self.started_at is not None:
                    self.elapsed_seconds += time.monotonic() - self.started_at
                    self.started_at = None
                self.worker = None
                self.ready = self.stopping = False
                self.start_button.config(text="开启摄像头", state="normal")
                self.camera_choice.config(state="readonly")
                self.camera_badge.config(text="●  未连接", fg=MUTED)
                self.gesture_label.config(text="等待手势")
                self._state()
                self._placeholder()
        self._refresh_floating()
        self.root.after(25, self._poll)

    def open_settings(self):
        if self.worker:
            self.log("请先关闭摄像头，再调整参数。")
            return
        self.pause("打开参数设置")
        window = tk.Toplevel(self.root)
        window.title("参数设置 · AirPresent")
        window.configure(bg=CARD)
        window.resizable(False, False)
        window.transient(self.root)
        window.grab_set()
        fields = (("剪刀手启用（毫秒）", "resume_ms", 150, 3000, 50),
                  ("握拳暂停（毫秒）", "pause_ms", 500, 3000, 100),
                  ("捏合确认（毫秒）", "pinch_hold_ms", 80, 800, 20),
                  ("松开确认（毫秒）", "pinch_release_ms", 80, 500, 20),
                  ("捏合间隔（毫秒）", "pinch_cooldown_ms", 150, 1500, 50),
                  ("光标跟手程度", "smoothing", 0.05, 1, 0.05),
                  ("活动区边距", "roi_margin", 0, 0.35, 0.01))
        values = {}
        for row, (label, key, low, high, step) in enumerate(fields):
            tk.Label(window, text=label, font=(FONT, 10), bg=CARD, fg=TEXT).grid(row=row, column=0, padx=20, pady=10, sticky="w")
            value = tk.StringVar(value=str(getattr(self.settings, key)))
            ttk.Spinbox(window, from_=low, to=high, increment=step, textvariable=value, width=10).grid(row=row, column=1, padx=20)
            values[key] = value
        mirror = tk.BooleanVar(value=self.settings.mirror)
        mode = tk.StringVar(value="捏合翻页" if self.settings.page_gesture == "pinch" else "手掌轻拨（旧版）")
        tk.Label(window, text="翻页方式", font=(FONT, 10), bg=CARD, fg=TEXT).grid(row=7, column=0, padx=20, pady=10, sticky="w")
        ttk.Combobox(window, textvariable=mode, values=("捏合翻页", "手掌轻拨（旧版）"), state="readonly", width=17).grid(row=7, column=1, padx=20)
        fist_pause = tk.BooleanVar(value=self.settings.fist_pause_enabled)
        lost_pause = tk.BooleanVar(value=self.settings.lost_pause_enabled)
        tk.Checkbutton(window, text="开启握拳长按暂停（可关闭）", variable=fist_pause, bg=CARD, fg=TEXT,
                       selectcolor=INNER, activebackground=CARD, activeforeground=TEXT,
                       font=(FONT, 10)).grid(row=8, column=0, columnspan=2, padx=20, pady=8, sticky="w")
        tk.Checkbutton(window, text="镜像画面（像照镜子一样）", variable=mirror, bg=CARD, fg=TEXT,
                       selectcolor=INNER, activebackground=CARD, activeforeground=TEXT,
                       font=(FONT, 10)).grid(row=10, column=0, columnspan=2, padx=20, pady=8, sticky="w")
        tk.Checkbutton(window, text="丢手后自动暂停（默认关闭）", variable=lost_pause, bg=CARD, fg=TEXT,
                       selectcolor=INNER, activebackground=CARD, activeforeground=TEXT,
                       font=(FONT, 10)).grid(row=9, column=0, columnspan=2, padx=20, pady=8, sticky="w")
        tk.Label(window, text="捏合无需移动手掌，松开后才能再次触发。\n选择旧版轻拨时沿用原有轻拨参数。\n修改后需重新开启摄像头。", bg=CARD, fg=MUTED,
                 font=(FONT, 9), justify="left").grid(row=11, column=0, columnspan=2, padx=20, pady=8, sticky="w")

        def save():
            from dataclasses import replace
            try:
                updated = replace(self.settings, **{key: (int(var.get()) if key.endswith("_ms") else float(var.get()))
                                                    for key, var in values.items()}, mirror=mirror.get(),
                                  fist_pause_enabled=fist_pause.get(),
                                  lost_pause_enabled=lost_pause.get(),
                                  page_gesture="pinch" if mode.get() == "捏合翻页" else "palm")
                updated.save(self.settings_path)
            except (ValueError, OSError) as exc:
                messagebox.showerror("参数无法保存", str(exc), parent=window)
                return
            self.settings = updated
            self.controller = Controller(updated)
            self._refresh_guide()
            self._placeholder()
            self.log("参数已保存，下一次开启摄像头时生效。")
            window.destroy()

        self._button(window, "保存参数", save, primary=True).grid(row=12, column=0, columnspan=2, padx=20, pady=(8, 20), sticky="ew")

    def export_session(self):
        folder = self.project_dir / "sessions"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = folder / f"session_{stamp}.csv"
        elapsed = self.elapsed_seconds
        if self.started_at is not None:
            elapsed += time.monotonic() - self.started_at
        inference = sorted(self.inference_values)
        p95 = inference[min(len(inference) - 1, int(len(inference) * 0.95))] if inference else 0
        try:
            folder.mkdir(exist_ok=True)
            with path.open("w", newline="", encoding="utf-8-sig") as output:
                writer = csv.writer(output)
                writer.writerow(["metric", "value", "unit"])
                writer.writerows((("camera_session_time", round(elapsed, 3), "s"),
                                  ("processed_frames", self.frame_count, "frames"),
                                  ("recognized_swipes", self.swipes, "count"),
                                  ("inference_mean", round(sum(inference) / len(inference), 2) if inference else 0, "ms"),
                                  ("inference_p95", round(p95, 2), "ms")))
                writer.writerow([])
                writer.writerow(["time", "action", "mode", "detail"])
                for event in self.events:
                    writer.writerow([event[key] for key in ("time", "action", "mode", "detail")])
            trace_path = folder / f"tracking_{stamp}.csv"
            if self.tracking_trace:
                with trace_path.open("w", newline="", encoding="utf-8-sig") as output:
                    writer = csv.DictWriter(output, fieldnames=list(self.tracking_trace[0]))
                    writer.writeheader()
                    writer.writerows(self.tracking_trace)
        except OSError as exc:
            messagebox.showerror("导出失败", str(exc), parent=self.root)
            return
        self.log(f"记录已导出到 sessions/{path.name}")
        self.status_label.config(text=f"已导出事件和最近 {len(self.tracking_trace)} 帧的诊断记录，不含摄像头图像。")

    def close(self):
        self.closing = True
        self.summary_worker.cancel()
        if self.summary_panel is not None:
            self.summary_panel.close()
        self.ai_keys.clear()
        self.page_output.close()
        self.floating.hide()
        self.close_started = time.monotonic()
        self.pause("退出程序")
        if self.worker:
            self.worker.stop()
        try:
            self.settings.camera_index = int(self.camera_var.get())
            self.settings.save(self.settings_path)
        except (ValueError, OSError):
            pass
        # Keep Tk responsive until the worker has released the camera/model.
        self.root.withdraw()
