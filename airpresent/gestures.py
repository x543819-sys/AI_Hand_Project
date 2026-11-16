"""Geometry only: no camera, GUI or OS imports, so it can be tested offline."""

from dataclasses import dataclass
from enum import Enum
import math


class Gesture(str, Enum):
    NONE = "未检测到手"
    UNKNOWN = "调整手势"
    POINT = "食指指示"
    PALM = "张开手掌"
    FIST = "握拳暂停"
    VICTORY = "剪刀手启用"
    PINCH = "捏合"
    PINCH_NEXT = "拇指＋食指 · 下一页"
    PINCH_PREVIOUS = "拇指＋中指 · 上一页"


@dataclass(frozen=True)
class Observation:
    gesture: Gesture = Gesture.NONE
    pointer: tuple[float, float] | None = None
    palm: tuple[float, float] | None = None
    motion: tuple[float, float] | None = None
    palm_width: float = 0.2
    pinch_released: bool | None = None


def distance(a, b):
    return math.dist(a[:2], b[:2])


def angle(a, b, c):
    u = (a[0] - b[0], a[1] - b[1])
    v = (c[0] - b[0], c[1] - b[1])
    denominator = math.hypot(*u) * math.hypot(*v)
    if denominator < 1e-9:
        return 0.0
    cosine = (u[0] * v[0] + u[1] * v[1]) / denominator
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


class GestureClassifier:
    """Joint angles plus palm-relative distances; pinch uses hysteresis.

    Input x/y must use the same units. The tracker corrects the camera aspect
    ratio before calling this class. Out-of-plane occlusion remains a limitation.
    """

    def __init__(self):
        self.pinching = False
        self.pinch_target = None

    def classify(self, landmarks):
        if not landmarks or len(landmarks) != 21:
            self.pinching = False
            self.pinch_target = None
            return Observation()
        if not all(math.isfinite(value) for point in landmarks for value in point[:2]):
            self.pinching = False
            self.pinch_target = None
            return Observation()
        wrist = landmarks[0]
        palm_size = max(distance(landmarks[5], landmarks[17]), distance(wrist, landmarks[9]) * 0.7)
        scale = max(palm_size, 1e-6)
        extended = []
        curled = []
        open_fingers = []
        for base in (5, 9, 13, 17):
            mcp, pip, dip, tip = landmarks[base:base + 4]
            straight = angle(mcp, pip, tip) > 155 and angle(pip, dip, tip) > 150
            outward = distance(tip, wrist) > distance(pip, wrist) + 0.12 * scale
            extended.append(straight and outward)
            open_fingers.append(angle(mcp, pip, tip) > 120
                                and distance(tip, wrist) > distance(pip, wrist) + 0.02 * scale)
            # A relaxed or partly bent finger is not enough evidence of a fist.
            curled.append(angle(mcp, pip, tip) < 105
                          and distance(tip, wrist) < distance(pip, wrist) + 0.12 * scale
                          and distance(tip, mcp) < 0.65 * scale)
        # The thumb often rotates during a fist; use the four long fingers
        # for pause and palm gestures instead of promising universal thumb rules.
        contacts = {}
        for gesture_id, tip, base in ((Gesture.PINCH_NEXT, 8, 5), (Gesture.PINCH_PREVIOUS, 12, 9)):
            # Fingertips near the palm in a fist must not become page clicks.
            outside_palm = distance(landmarks[tip], wrist) > distance(landmarks[base], wrist) + 0.15 * scale
            if outside_palm and palm_size > 1e-6:
                contacts[gesture_id] = distance(landmarks[4], landmarks[tip]) / scale
        if self.pinch_target not in contacts or contacts.get(self.pinch_target, 1) >= 0.28:
            self.pinch_target = None
        ambiguous = False
        if self.pinch_target is None:
            close = sorted((ratio, gesture_id) for gesture_id, ratio in contacts.items() if ratio < 0.18)
            if close:
                ambiguous = len(close) > 1 and close[1][0] - close[0][0] < 0.08
                if not ambiguous:
                    self.pinch_target = close[0][1]
        self.pinching = self.pinch_target is not None
        if self.pinch_target is not None:
            gesture = self.pinch_target
        elif ambiguous:
            gesture = Gesture.UNKNOWN
        elif sum(open_fingers) >= 3:
            gesture = Gesture.PALM
        elif all(curled) and palm_size > 1e-6:
            gesture = Gesture.FIST
        elif extended == [True, True, False, False]:
            gesture = Gesture.VICTORY
        elif extended == [True, False, False, False]:
            gesture = Gesture.POINT
        else:
            gesture = Gesture.UNKNOWN
        palm_points = [landmarks[index] for index in (0, 5, 9, 13, 17)]
        palm = tuple(sum(p[axis] for p in palm_points) / len(palm_points) for axis in (0, 1))
        released = self.pinch_target is None and not ambiguous if palm_size > 1e-6 else None
        return Observation(gesture, tuple(landmarks[8][:2]), palm, pinch_released=released)


class PointerFilter:
    """Time-adjusted EMA: smoothing has approximately the same feel at any FPS."""

    def __init__(self, smoothing=0.32):
        self.smoothing = smoothing
        self.position = None
        self.timestamp = None

    def reset(self):
        self.position = self.timestamp = None

    def update(self, point, now):
        if self.position is None:
            self.position = point
        else:
            delta = max(0.0, now - self.timestamp)
            alpha = 1 - (1 - self.smoothing) ** (delta * 30)
            self.position = tuple(old + alpha * (new - old)
                                  for old, new in zip(self.position, point))
        self.timestamp = now
        return self.position


def map_pointer(point, margin):
    size = 1 - margin * 2
    return tuple(max(0.0, min(1.0, (value - margin) / size)) for value in point)
