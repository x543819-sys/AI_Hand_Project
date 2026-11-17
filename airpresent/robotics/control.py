"""Operator permission is separate from temporary tracking availability."""
import math
import threading
from ..gestures import Gesture, Observation


def valid_point(point):
    return isinstance(point,(tuple,list)) and len(point)==2 and all(type(v) in (int,float) and math.isfinite(v) and 0<=v<=1 for v in point)


def hand_input(frame, now):
    if frame is None:
        return Observation(), 0, '等待摄像头画面；将整只手放在画面中间'
    age=(now-frame.timestamp)*1000
    if not 0<=age<=250:
        return Observation(), 0, '画面暂时卡顿，机械臂已停住；恢复后先松开，再捏合'
    observation=frame.observation
    if observation.gesture==Gesture.NONE:
        return Observation(), 0, '未检测到手；将整只手放回画面中间'
    for point in (observation.pointer, observation.palm):
        if point is not None and not valid_point(point):
            return Observation(), 0, '手靠近画面边缘；请把整只手移回画面中间'
    if observation.pointer is None and observation.palm is None:
        return Observation(), 0, '手部坐标不可用；请调整手掌角度'
    return observation, age, ''


class Operator:
    def __init__(self):
        self.lock=threading.Lock()
        self.enabled=False;self.mode='xy';self.source='hand';self.jog=None
        self.reason='先按住右侧方向按钮，确认仿真能动；再打开摄像头'

    def snapshot(self):
        with self.lock:return self.enabled,self.mode,self.source,self.jog,self.reason

    def enable(self):
        with self.lock:
            self.enabled=True;self.source='hand';self.jog=None;self.reason=''

    def pause(self, reason='你已暂停控制；点击“启用手势”继续'):
        with self.lock:
            self.enabled=False;self.jog=None;self.reason=reason

    def plane(self, mode):
        with self.lock:
            self.mode=mode;self.enabled=False;self.jog=None
            self.reason='控制平面已切换；点击“启用手势”，再松开手指'

    def press(self, direction):
        with self.lock:
            self.enabled=False;self.source='buttons';self.jog=direction;self.reason=''

    def release(self, reason='按钮已松开，机械臂停止；可继续按住其他方向'):
        with self.lock:
            if self.source=='buttons' and self.jog is not None:
                self.jog=None;self.reason=reason
