"""Static fingertip contacts: one click per close/release cycle."""

from .gestures import Gesture


class PinchPager:
    def __init__(self, settings):
        self.settings = settings
        self.last_fire = float("-inf")
        self.reset()

    def reset(self):
        self.armed = False
        self.latched = False
        self.candidate = None
        self.since = None
        self.release_since = None
        self.progress = 0.0

    def update(self, gesture, now, released=None):
        direction = {Gesture.PINCH_NEXT: "next", Gesture.PINCH_PREVIOUS: "previous"}.get(gesture)
        if direction is not None:
            self.release_since = None
            if not self.armed or self.latched:
                self.progress = 0.0
                return None
            if self.candidate != direction:
                self.candidate, self.since = direction, now
            self.progress = min(1.0, max(0.0, (now - self.since) * 1000 / self.settings.pinch_hold_ms))
            cooled = (now - self.last_fire) * 1000 >= self.settings.pinch_cooldown_ms
            if self.progress >= 1 and cooled:
                self.last_fire = now
                self.latched = True
                self.armed = False
                return direction
            return None
        self.candidate = self.since = None
        self.progress = 0.0
        if released is False or (released is None and gesture in (Gesture.NONE, Gesture.UNKNOWN, Gesture.PINCH)):
            # Uncertain tracking is not proof that fingertips were released.
            self.release_since = None
            return None
        if self.release_since is None:
            self.release_since = now
        if (now - self.release_since) * 1000 >= self.settings.pinch_release_ms:
            self.armed = True
            self.latched = False
        return None
