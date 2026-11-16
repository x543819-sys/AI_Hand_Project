"""Small palm-relative lateral swipes, with a settle phase to reject recoil."""

from collections import deque
import math

from .gestures import Gesture


class FlickDetector:
    def __init__(self, settings):
        self.settings = settings
        self.last_fire = float("-inf")
        self.reset()

    def reset(self):
        self.path = deque()
        self.last_palm = float("-inf")
        self.last_sample = None
        self.latched = False
        self.still_since = None

    def update(self, observation, now):
        if observation.gesture == Gesture.PALM:
            self.last_palm = now
        # Motion blur may briefly change the static label to UNKNOWN. Index
        # pointing, pinching, fists, and resume gestures never drive page output.
        eligible = (observation.gesture == Gesture.PALM or
                    (observation.gesture == Gesture.UNKNOWN and now - self.last_palm <= 0.4))
        point = observation.palm
        scale = max(0.04, min(0.8, observation.palm_width))
        if not eligible or point is None:
            if observation.gesture not in (Gesture.PALM, Gesture.UNKNOWN):
                self.last_palm = float("-inf")
            self.path.clear()
            self.last_sample = None
            self.still_since = None
            return None
        previous = self.last_sample
        self.last_sample = (now, point)
        if previous is not None and now - previous[0] > 0.35:
            self.path.clear()
            self.still_since = None
            previous = None
        if self.latched:
            speed = (math.dist(point, previous[1]) / max(now - previous[0], 1e-6)
                     if previous else float("inf"))
            if speed <= 0.25 * scale:
                if self.still_since is None:
                    self.still_since = now
                elif (now - self.still_since) * 1000 >= self.settings.palm_settle_ms:
                    self.latched = False
                    self.path.clear()
                    self.path.append((now, *point, scale))
            else:
                self.still_since = None
            return None
        self.path.append((now, *point, scale))
        while self.path and (now - self.path[0][0]) * 1000 > self.settings.palm_window_ms:
            self.path.popleft()
        if len(self.path) < 2 or (now - self.last_fire) * 1000 < self.settings.cooldown_ms:
            return None
        # Evaluate recent segments: a slow lead-in does not mask a fast flick.
        points = list(self.path)
        for start in range(len(points) - 1):
            timestamp, x, y, initial_scale = points[start]
            dt = now - timestamp
            if dt < 0.04:
                continue
            dx, dy = point[0] - x, point[1] - y
            travel = sum(abs(b[1] - a[1]) for a, b in zip(points[start:], points[start + 1:]))
            if (abs(dx) >= max(0.012, self.settings.palm_distance * initial_scale)
                    and abs(dx) / dt >= self.settings.palm_speed * initial_scale
                    and abs(dy) <= abs(dx) * 0.7 and abs(dx) >= travel * 0.8):
                self.last_fire = now
                self.latched = True
                self.still_since = None
                self.path.clear()
                return "next" if dx > 0 else "previous"
        return None
