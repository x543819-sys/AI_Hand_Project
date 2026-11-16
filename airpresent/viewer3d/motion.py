"""Clutched relative motion, independent of camera and rendering."""
import math
from ..gestures import Gesture


class Motion:
    def __init__(self):
        self.active = False
        self.mode = "rotate"
        self.sensitivity = 1.0
        self.reset()

    def reset(self):
        self.yaw, self.pitch, self.scale = 0., 0., 1.
        self.pan_x = self.pan_y = 0.
        self.selection_id = 0
        self.cursor = None
        self.release()
        self.status = "先开启摄像头，再启用手势"

    def release(self):
        self.armed = False
        self.anchor = None
        self.candidate = None
        self.previous_time = None
        self.previous_point = None

    def enable(self, value):
        self.active = bool(value)
        self.release()
        self.status = "请先分开指尖" if value else "手势已暂停 · 鼠标仍可操作"

    def set_mode(self, mode):
        if mode not in ("rotate", "zoom", "pan", "select"):
            raise ValueError("未知操作模式")
        self.mode = mode
        self.release()

    def update(self, observation, now):
        if not self.active:
            return
        p = observation.pointer
        self.cursor = p
        if observation.gesture == Gesture.NONE or p is None or not all(math.isfinite(v) for v in p):
            self.release()
            self.cursor = None
            self.status = "等待手部 · 模型保持原位"
            return
        if self.previous_time is not None and now - self.previous_time > .3:
            self.release()
        self.previous_time = now
        if observation.pinch_released is True:
            self.anchor = self.candidate = None
            self.previous_point = None
            self.armed = True
            self.status = "已就绪 · 捏合后小幅移动"
            return
        if observation.gesture != Gesture.PINCH_NEXT:
            self.anchor = self.candidate = None
            self.previous_point = None
            self.status = "松开指尖即可重新就绪"
            return
        if not self.armed:
            self.status = "请先松开指尖"
            return
        if self.previous_point is not None and math.dist(p, self.previous_point) > .18:
            self.release()
            self.status = "跟踪跳变 · 请松开后重试"
            return
        self.previous_point = p
        if self.candidate is None:
            self.candidate = now
        if self.anchor is None:
            if now - self.candidate < .12:
                self.status = "确认捏合…"
                return
            self.anchor = (p, (self.yaw, self.pitch, self.scale, self.pan_x, self.pan_y))
            if self.mode == "select":
                self.selection_id += 1
        point, start = self.anchor
        dx, dy = p[0] - point[0], p[1] - point[1]
        dx = 0 if abs(dx) < .003 else dx
        dy = 0 if abs(dy) < .003 else dy
        gain = self.sensitivity
        if self.mode == "rotate":
            self.yaw = start[0] + dx * 6 * gain
            self.pitch = max(-1.35, min(1.35, start[1] + dy * 5 * gain))
        elif self.mode == "zoom":
            self.scale = max(.3, min(3., start[2] * math.exp(-dy * 4 * gain)))
        elif self.mode == "pan":
            self.pan_x = max(-2., min(2., start[3] + dx * 4 * gain))
            self.pan_y = max(-2., min(2., start[4] - dy * 4 * gain))
        self.status = {"rotate": "正在旋转", "zoom": "正在缩放", "pan": "正在平移", "select": "已选取 · 松开后可再选"}[self.mode]

    def snapshot(self):
        return {k: getattr(self, k) for k in ("active", "mode", "sensitivity", "yaw", "pitch", "scale",
                                             "pan_x", "pan_y", "cursor", "selection_id", "status")}
