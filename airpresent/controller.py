"""Temporal state machine. Returns events; it never sends keys itself."""

from dataclasses import dataclass

from .config import Settings
from .gestures import Gesture, Observation, PointerFilter, map_pointer
from .flick import FlickDetector
from .pinch import PinchPager


@dataclass(frozen=True)
class ControlResult:
    events: tuple[str, ...]
    pointer: tuple[float, float] | None
    active: bool
    progress: float


class Controller:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.active = False
        self.candidate = Gesture.NONE
        self.since = 0.0
        self.last_seen = None
        self.filter = PointerFilter(settings.smoothing)
        self.flick = FlickDetector(settings)
        self.pinch = PinchPager(settings)
        self.last_pointer = None
        self.last_pointer_time = float("-inf")

    def reset_motion(self):
        self.filter.reset()
        self.flick.reset()
        self.pinch.reset()
        self.last_pointer = None
        self.last_pointer_time = float("-inf")

    def set_active(self, active, now):
        self.active = bool(active)
        self.candidate = Gesture.NONE
        self.since = now
        self.last_seen = now
        self.reset_motion()

    def update(self, observation: Observation, now: float):
        events = []
        gesture = observation.gesture
        if gesture != self.candidate:
            self.candidate, self.since = gesture, now
        elapsed_ms = max(0, (now - self.since) * 1000)
        if gesture == Gesture.VICTORY:
            threshold = self.settings.resume_ms
        elif gesture == Gesture.FIST:
            threshold = self.settings.pause_ms
        else:
            threshold = self.settings.stable_ms
        progress = min(1.0, elapsed_ms / threshold)
        if gesture == Gesture.NONE:
            self.reset_motion()
            if self.settings.lost_pause_enabled and self.active and self.last_seen is not None:
                if (now - self.last_seen) * 1000 >= self.settings.lost_pause_ms:
                    self.set_active(False, now)
                    events.append("lost_pause")
            return ControlResult(tuple(events), None, self.active, 0.0)
        self.last_seen = now
        if (gesture == Gesture.FIST and progress >= 1 and self.active
                and self.settings.fist_pause_enabled):
            self.set_active(False, now)
            events.append("pause")
        elif gesture == Gesture.VICTORY and progress >= 1 and not self.active:
            self.set_active(True, now)
            events.append("resume")
        pointer = None
        if self.active and gesture == Gesture.POINT and observation.pointer:
            mapped = map_pointer(observation.pointer, self.settings.roi_margin)
            pointer = self.filter.update(mapped, now)
            self.last_pointer, self.last_pointer_time = pointer, now
        elif self.active and gesture == Gesture.UNKNOWN and now - self.last_pointer_time <= 0.12:
            # Freeze the last point through a brief uncertain label; never
            # extrapolate it, and hide immediately if the hand is missing.
            pointer = self.last_pointer
        else:
            self.filter.reset()
            self.last_pointer = None
        if self.active:
            if self.settings.page_gesture == "pinch":
                page_event = self.pinch.update(gesture, now, observation.pinch_released)
                if gesture in (Gesture.PINCH_NEXT, Gesture.PINCH_PREVIOUS):
                    progress = self.pinch.progress
            else:
                page_event = self.flick.update(observation, now)
            if page_event:
                events.append(page_event)
        return ControlResult(tuple(events), pointer, self.active, progress)
