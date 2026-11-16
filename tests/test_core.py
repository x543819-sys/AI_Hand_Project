"""Offline behavioral tests: geometry, timing, interruption and repeat prevention."""

from dataclasses import replace
import json
import math
from pathlib import Path
import tempfile
import unittest

from airpresent.config import Settings
from airpresent.controller import Controller
from airpresent.gestures import (Gesture, GestureClassifier, Observation,
                                 PointerFilter, angle, map_pointer)


def hand(extended):
    points = [(0.0, 0.0)] * 21
    points[1:5] = [(-0.35, -0.15), (-0.7, -0.25), (-1.0, -0.4), (-1.25, -0.55)]
    for base, x, y, straight in zip((5, 9, 13, 17), (-0.6, -0.2, 0.2, 0.6),
                                    (-0.7, -0.8, -0.75, -0.6), extended):
        points[base] = (x, y)
        points[base + 1] = (x, y - 0.3)
        points[base + 2] = (x, y - 0.6) if straight else (x + 0.05, y - 0.08)
        points[base + 3] = (x, y - 0.9) if straight else (x + 0.02, y + 0.08)
    return points


def obs(gesture, x=0.5, y=0.5):
    return Observation(gesture, (x, y), (x, y))


class GeometryTests(unittest.TestCase):
    def test_expected_static_gestures(self):
        for extended, expected in (((1, 0, 0, 0), Gesture.POINT),
                                   ((1, 1, 0, 0), Gesture.VICTORY),
                                   ((1, 1, 1, 1), Gesture.PALM),
                                   ((0, 0, 0, 0), Gesture.FIST),
                                   ((0, 1, 0, 1), Gesture.UNKNOWN)):
            with self.subTest(expected=expected):
                self.assertEqual(GestureClassifier().classify(hand(extended)).gesture, expected)

    def test_rotation_scale_translation_and_reflection(self):
        for degrees in (0, 45, 90, 180, 270):
            for flip in (-1, 1):
                radians = math.radians(degrees)
                c, s = math.cos(radians), math.sin(radians)
                points = [(30 + 12 * (c * x * flip - s * y), 50 + 12 * (s * x * flip + c * y))
                          for x, y in hand((1, 0, 0, 0))]
                with self.subTest(degrees=degrees, flip=flip):
                    self.assertEqual(GestureClassifier().classify(points).gesture, Gesture.POINT)

    def test_pinch_hysteresis_and_reset(self):
        classifier = GestureClassifier()
        points = hand((1, 1, 0, 0))
        x, y = points[8]
        points[4] = (x - 0.15, y)
        self.assertEqual(classifier.classify(points).gesture, Gesture.PINCH_NEXT)
        points[4] = (x - 0.25, y)
        self.assertEqual(classifier.classify(points).gesture, Gesture.PINCH_NEXT)
        classifier.classify(None)
        self.assertEqual(classifier.classify(points).gesture, Gesture.VICTORY)

    def test_missing_or_invalid_points(self):
        classifier = GestureClassifier()
        self.assertEqual(classifier.classify([]).gesture, Gesture.NONE)
        self.assertEqual(classifier.classify([(0, 0)] * 20).gesture, Gesture.NONE)
        self.assertEqual(classifier.classify([(float("nan"), 0)] * 21).gesture, Gesture.NONE)
        self.assertEqual(classifier.classify([(0, 0)] * 21).gesture, Gesture.UNKNOWN)

    def test_relaxed_bent_fingers_are_not_a_fist(self):
        points = hand((0, 0, 0, 0))
        for base in (5, 9, 13, 17):
            x, y = points[base]
            points[base + 3] = (x + 0.25, y - 0.42)
        self.assertEqual(GestureClassifier().classify(points).gesture, Gesture.UNKNOWN)

    def test_all_four_fingers_must_be_curled_to_pause(self):
        points = hand((0, 0, 0, 0))
        x, y = points[9]
        points[12] = (x + 0.25, y - 0.42)
        self.assertNotEqual(GestureClassifier().classify(points).gesture, Gesture.FIST)

    def test_angle_and_pointer_clamping(self):
        self.assertAlmostEqual(angle((0, 0), (1, 0), (2, 0)), 180)
        self.assertAlmostEqual(angle((0, 0), (1, 0), (1, 1)), 90)
        self.assertEqual(map_pointer((-1, 2), 0.12), (0, 1))
        self.assertEqual(map_pointer((0.5, 0.5), 0.12), (0.5, 0.5))

    def test_smoothing_is_time_adjusted(self):
        a, b = PointerFilter(), PointerFilter()
        a.update((0, 0), 0)
        b.update((0, 0), 0)
        pa = a.update((1, 1), 1 / 30)
        b.update((1, 1), 1 / 60)
        pb = b.update((1, 1), 1 / 30)
        self.assertAlmostEqual(pa[0], pb[0])
        a.reset()
        self.assertEqual(a.update((0.8, 0.3), 1), (0.8, 0.3))


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(page_gesture="palm", fist_pause_enabled=True, lost_pause_enabled=True)
        self.controller = Controller(self.settings)

    def test_starts_paused_and_ignores_swipes(self):
        self.assertFalse(self.controller.active)
        results = [self.controller.update(obs(Gesture.PALM, x), t)
                   for t, x in ((0, 0.2), (0.2, 0.3), (0.4, 0.7))]
        self.assertFalse(any(result.events for result in results))

    def test_resume_requires_stable_hold(self):
        self.controller.update(obs(Gesture.VICTORY), 0)
        self.assertFalse(self.controller.update(obs(Gesture.VICTORY), 0.2).active)
        result = self.controller.update(obs(Gesture.VICTORY), 0.4)
        self.assertEqual(result.events, ("resume",))
        self.assertTrue(result.active)
        for t in (1, 1.8, 2.8):
            self.assertEqual(self.controller.update(obs(Gesture.VICTORY), t).events, ())

    def test_unstable_resume_resets_timer(self):
        self.controller.update(obs(Gesture.VICTORY), 0)
        self.controller.update(obs(Gesture.UNKNOWN), 0.2)
        self.controller.update(obs(Gesture.VICTORY), 0.3)
        self.assertFalse(self.controller.update(obs(Gesture.VICTORY), 0.5).active)

    def test_fist_pauses_after_confirmation(self):
        self.controller.set_active(True, 0)
        self.controller.update(obs(Gesture.FIST), 1)
        self.assertTrue(self.controller.update(obs(Gesture.FIST), 1.15).active)
        self.assertTrue(self.controller.update(obs(Gesture.FIST), 1.4).active)
        result = self.controller.update(obs(Gesture.FIST), 1.95)
        self.assertFalse(result.active)
        self.assertEqual(result.events, ("pause",))

    def test_brief_fist_does_not_pause_and_releasing_cancels(self):
        self.controller.set_active(True, 0)
        self.controller.update(obs(Gesture.FIST), 1)
        result = self.controller.update(obs(Gesture.FIST), 1.55)
        self.assertTrue(result.active)
        self.assertEqual(result.events, ())
        self.controller.update(obs(Gesture.POINT), 1.6)
        self.controller.update(obs(Gesture.FIST), 1.7)
        self.assertTrue(self.controller.update(obs(Gesture.FIST), 2.3).active)
        self.assertEqual(self.controller.update(obs(Gesture.FIST), 2.65).events, ("pause",))

    def test_pause_is_independent_of_general_confirmation(self):
        controller = Controller(replace(self.settings, stable_ms=100, pause_ms=1200))
        controller.set_active(True, 0)
        controller.update(obs(Gesture.FIST), 1)
        self.assertTrue(controller.update(obs(Gesture.FIST), 1.8).active)
        self.assertEqual(controller.update(obs(Gesture.FIST), 2.3).events, ("pause",))

    def test_fist_pause_can_be_disabled(self):
        controller = Controller(replace(self.settings, fist_pause_enabled=False))
        controller.set_active(True, 0)
        controller.update(obs(Gesture.FIST), 1)
        for t in (2, 3, 5):
            result = controller.update(obs(Gesture.FIST), t)
            self.assertTrue(result.active)
            self.assertEqual(result.events, ())
        controller.update(Observation(), 5.1)
        self.assertEqual(controller.update(Observation(), 6.6).events, ("lost_pause",))

    def test_interrupted_fist_cannot_accumulate_pause_time(self):
        self.controller.set_active(True, 0)
        self.controller.update(obs(Gesture.FIST), 1)
        self.controller.update(obs(Gesture.FIST), 1.6)
        self.controller.update(obs(Gesture.UNKNOWN), 1.65)
        self.controller.update(obs(Gesture.FIST), 1.7)
        self.assertTrue(self.controller.update(obs(Gesture.FIST), 2.3).active)

    def test_missing_hand_hides_pointer_then_pauses(self):
        self.controller.set_active(True, 0)
        self.controller.update(obs(Gesture.POINT), 0.1)
        self.assertIsNotNone(self.controller.update(obs(Gesture.POINT), 0.5).pointer)
        result = self.controller.update(Observation(), 0.6)
        self.assertIsNone(result.pointer)
        self.assertTrue(result.active)
        result = self.controller.update(Observation(), 2.1)
        self.assertEqual(result.events, ("lost_pause",))
        self.assertFalse(result.active)

    def _swipe(self, direction="next", start=1):
        xs = (0.2, 0.225, 0.25) if direction == "next" else (0.8, 0.775, 0.75)
        results = [self.controller.update(obs(Gesture.PALM, x), start + dt)
                   for dt, x in zip((0, 0.06, 0.12), xs)]
        return results[-1]

    def test_right_and_left_swipes(self):
        for direction in ("next", "previous"):
            self.controller = Controller(self.settings)
            self.controller.set_active(True, 0)
            self.assertEqual(self._swipe(direction).events, (direction,))

    def test_holding_palm_cannot_repeat_even_after_cooldown(self):
        self.controller.set_active(True, 0)
        self.assertEqual(self._swipe().events, ("next",))
        for t, x in ((2.5, 0.1), (2.7, 0.4), (2.9, 0.8), (4, 0.2), (4.5, 0.7)):
            self.assertEqual(self.controller.update(obs(Gesture.PALM, x), t).events, ())

    def test_release_rearms_swipe(self):
        self.controller.set_active(True, 0)
        self._swipe()
        for t in (1.4, 1.45, 1.65):
            self.controller.update(obs(Gesture.PALM, 0.3), t)
        self.assertEqual(self._swipe("previous", 2.1).events, ("previous",))

    def test_cooldown_still_applies_after_release(self):
        self.controller.set_active(True, 0)
        self._swipe()
        self.controller.update(obs(Gesture.UNKNOWN), 1.45)
        self.assertEqual(self._swipe("previous", 1.5).events, ())

    def test_vertical_motion_is_not_a_swipe(self):
        self.controller.set_active(True, 0)
        for t, x, y in ((1, 0.2, 0.2), (1.2, 0.3, 0.4), (1.4, 0.5, 0.8)):
            self.assertEqual(self.controller.update(obs(Gesture.PALM, x, y), t).events, ())

    def test_slow_drift_is_not_a_swipe(self):
        self.controller.set_active(True, 0)
        for i in range(40):
            self.assertEqual(self.controller.update(obs(Gesture.PALM, 0.2 + i * 0.004), i * 0.1).events, ())

    def test_pointer_appears_immediately_and_pause_stops_it(self):
        self.controller.set_active(True, 0)
        self.assertIsNotNone(self.controller.update(obs(Gesture.POINT), 1).pointer)
        self.assertIsNotNone(self.controller.update(obs(Gesture.POINT), 1.4).pointer)
        self.assertIsNone(self.controller.update(obs(Gesture.UNKNOWN), 1.6).pointer)
        self.controller.set_active(False, 1.6)
        self.assertIsNone(self.controller.update(obs(Gesture.POINT), 2).pointer)

    def test_pause_resume_restores_pointer_on_first_point_frame(self):
        for t in range(20):
            self.controller.set_active(True, t)
            self.assertIsNotNone(self.controller.update(obs(Gesture.POINT), t + 0.01).pointer)
            self.controller.set_active(False, t + 0.02)
            self.assertIsNone(self.controller.update(obs(Gesture.POINT), t + 0.03).pointer)

    def test_uncertain_label_briefly_freezes_pointer_without_extending_loss(self):
        self.controller.set_active(True, 0)
        point = self.controller.update(obs(Gesture.POINT, 0.4), 1).pointer
        self.assertEqual(self.controller.update(obs(Gesture.UNKNOWN, 0.9), 1.06).pointer, point)
        self.assertIsNone(self.controller.update(obs(Gesture.UNKNOWN), 1.2).pointer)
        self.controller.update(obs(Gesture.POINT), 1.3)
        self.assertIsNone(self.controller.update(Observation(), 1.31).pointer)

    def test_fast_pointing_never_flips_page(self):
        self.controller.set_active(True, 0)
        for t, x in ((1, 0.2), (1.06, 0.3), (1.12, 0.5)):
            self.assertEqual(self.controller.update(obs(Gesture.POINT, x), t).events, ())

    def test_flick_survives_a_brief_uncertain_static_label(self):
        self.controller.set_active(True, 0)
        self.controller.update(obs(Gesture.PALM, 0.2), 1)
        self.controller.update(obs(Gesture.UNKNOWN, 0.225), 1.06)
        self.assertEqual(self.controller.update(obs(Gesture.PALM, 0.25), 1.12).events, ("next",))

    def test_fingertip_flick_without_palm_movement_does_not_flip(self):
        self.controller.set_active(True, 0)
        results = [self.controller.update(Observation(Gesture.PALM, (x, 0.5), (0.5, 0.5), (x, 0.5)), t)
                   for t, x in ((1, 0.2), (1.06, 0.25), (1.12, 0.3))]
        self.assertFalse(any(result.events for result in results))

    def test_small_gentle_palm_swipe_in_narrow_view(self):
        self.controller.set_active(True, 0)
        results = [self.controller.update(Observation(Gesture.PALM, (x, 0.5), (x, 0.5), None, 0.1), t)
                   for t, x in ((1, 0.2), (1.15, 0.214), (1.3, 0.228))]
        self.assertEqual(results[-1].events, ("next",))

    def test_recoil_never_triggers_reverse_page(self):
        self.controller.set_active(True, 0)
        self._swipe()
        for t, x in ((1.18, 0.25), (1.24, 0.2), (1.3, 0.15), (2, 0.3), (2.06, 0.2), (2.12, 0.1)):
            self.assertEqual(self.controller.update(obs(Gesture.PALM, x), t).events, ())

    def test_flick_works_with_two_samples_at_lower_frame_rate(self):
        self.controller.set_active(True, 0)
        self.controller.update(obs(Gesture.PALM, 0.2), 1)
        self.assertEqual(self.controller.update(obs(Gesture.PALM, 0.3), 1.08).events, ("next",))

    def test_pointing_clears_palm_motion_anchor(self):
        self.controller.set_active(True, 0)
        self.controller.update(obs(Gesture.PALM, 0.2), 1)
        self.controller.update(obs(Gesture.POINT, 0.2), 1.03)
        self.controller.update(obs(Gesture.UNKNOWN, 0.3), 1.09)
        self.assertEqual(self.controller.update(obs(Gesture.UNKNOWN, 0.4), 1.15).events, ())


class SettingsTests(unittest.TestCase):
    def test_roundtrip_and_missing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            self.assertEqual(Settings.load(path), Settings())
            settings = replace(Settings(), camera_index=2, smoothing=0.5)
            settings.save(path)
            self.assertEqual(Settings.load(path), settings)

    def test_invalid_values_rejected(self):
        for changes in ({"smoothing": 0}, {"camera_index": -1}, {"mirror": "false"},
                        {"cooldown_ms": 0}, {"roi_margin": 0.6},
                        {"detection_confidence": float("nan")}, {"resume_ms": "700"},
                        {"pause_ms": 280}, {"pause_ms": "900"}, {"fist_pause_enabled": "false"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(Settings(), **changes).validate()

    def test_non_object_json_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            path.write_text(json.dumps([1, 2]), encoding="utf-8")
            with self.assertRaises(ValueError):
                Settings.load(path)

    def test_old_settings_file_gets_new_pause_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            path.write_text(json.dumps({"resume_ms": 500, "stable_ms": 200}), encoding="utf-8")
            settings = Settings.load(path)
            self.assertEqual(settings.resume_ms, 500)
            self.assertEqual(settings.pause_ms, 900)
            self.assertFalse(settings.fist_pause_enabled)

    def test_old_defaults_migrate_but_custom_settings_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            for cooldown, smoothing, expected in ((900, 0.32, (650, 0.55)),
                                                   (1200, 0.25, (1200, 0.25))):
                path.write_text(json.dumps({"cooldown_ms": cooldown, "smoothing": smoothing,
                                            "camera_index": 2}), encoding="utf-8")
                settings = Settings.load(path)
                self.assertEqual((settings.cooldown_ms, settings.smoothing), expected)
                self.assertEqual(settings.camera_index, 2)
                self.assertEqual(settings.flick_distance, 0.08)


if __name__ == "__main__":
    unittest.main()
