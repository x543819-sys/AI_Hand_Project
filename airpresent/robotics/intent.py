"""Pure hand-to-velocity logic shared by the ROS 2 simulation adapter.

No ROS imports, networking, joint commands or real hardware access.
Coordinates are explicit base-frame axes, not estimated metric hand depth.
"""
from dataclasses import dataclass, asdict
import math
from ..gestures import Gesture


@dataclass(frozen=True)
class Intent:
    linear: tuple = (0., 0., 0.)
    angular: tuple = (0., 0., 0.)
    deadman: bool = False

    def as_dict(self):
        return asdict(self)


class HandVelocity:
    def __init__(self, max_speed=.04, timeout=.2):
        if not math.isfinite(max_speed) or not 0 < max_speed <= .1:
            raise ValueError('Invalid simulation speed')
        if not math.isfinite(timeout) or not .05 <= timeout <= .5:
            raise ValueError('Invalid input timeout')
        self.max_speed, self.timeout = max_speed, timeout
        self.enabled = False
        self.mode = 'xy'
        self.last_time = None
        self.clear()

    def clear(self, phase='release'):
        self.armed = False
        self.anchor = self.candidate = self.previous = None
        self.intent = Intent()
        self.phase = phase

    def enable(self, enabled):
        self.enabled = bool(enabled)
        self.clear('release' if self.enabled else 'disabled')

    def set_mode(self, mode):
        if mode not in ('xy', 'xz'):
            raise ValueError('Choose xy or xz')
        self.mode = mode
        self.clear()

    def update(self, observation, now):
        if not math.isfinite(now):
            self.clear()
            return
        p = observation.palm if observation.palm is not None else observation.pointer
        if self.last_time is not None and (now < self.last_time or now - self.last_time > self.timeout):
            self.clear()
        self.last_time = now
        if not self.enabled:
            self.clear('disabled')
            return
        if observation.gesture == Gesture.NONE or p is None:
            self.clear('no_hand')
            return
        if len(p) != 2 or not all(math.isfinite(v) and 0 <= v <= 1 for v in p):
            self.clear('outside')
            return
        if observation.pinch_released is True:
            self.clear()
            self.armed = True
            self.phase = 'ready'
            return
        if not self.armed or observation.gesture != Gesture.PINCH_NEXT:
            self.clear('wrong_finger' if observation.gesture == Gesture.PINCH_PREVIOUS else 'release')
            return
        if self.previous is not None and math.dist(p, self.previous) > .18:
            self.clear('jump')
            return
        self.previous = p
        if self.candidate is None:
            self.candidate = now
        if now - self.candidate < .12:
            self.phase = 'confirm'
            return
        if self.anchor is None:
            self.anchor = p
        def axis(value):
            value = math.copysign(max(0., abs(value) - .02), value)
            return max(-1., min(1., value / .15))
        x, y = axis(p[0] - self.anchor[0]), axis(self.anchor[1] - p[1])
        norm = max(1., math.hypot(x, y))
        x, y = x / norm * self.max_speed, y / norm * self.max_speed
        self.intent = Intent((x, y, 0.) if self.mode == 'xy' else (x, 0., y), deadman=True)
        self.phase = 'moving' if x or y else 'center'

    def sample(self, now):
        if (not self.enabled or self.last_time is None or not math.isfinite(now)
                or now < self.last_time or now - self.last_time > self.timeout):
            self.clear('timeout' if self.enabled else 'disabled')
        return self.intent
