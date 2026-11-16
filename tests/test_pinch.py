"""Contact geometry and complete static close/release page cycles."""

from dataclasses import replace
import unittest

from airpresent.config import Settings
from airpresent.controller import Controller
from airpresent.gestures import Gesture, GestureClassifier, Observation
from test_core import hand


def observation(gesture):
    return Observation(gesture, (0.5, 0.5), (0.5, 0.5))


class ContactGeometryTests(unittest.TestCase):
    def test_index_and_middle_contacts_have_distinct_directions(self):
        for tip, expected in ((8, Gesture.PINCH_NEXT), (12, Gesture.PINCH_PREVIOUS)):
            points = hand((1, 1, 1, 1))
            points[4] = points[tip]
            self.assertEqual(GestureClassifier().classify(points).gesture, expected)

    def test_fist_contact_does_not_become_a_page_command(self):
        points = hand((0, 0, 0, 0))
        points[4] = points[8]
        self.assertEqual(GestureClassifier().classify(points).gesture, Gesture.FIST)

    def test_ambiguous_two_finger_contact_has_no_direction(self):
        points = hand((1, 1, 1, 1))
        points[8] = (-0.3, -1.6)
        points[12] = (-0.25, -1.6)
        points[4] = (-0.275, -1.6)
        self.assertEqual(GestureClassifier().classify(points).gesture, Gesture.UNKNOWN)

    def test_natural_unknown_pose_can_prove_release_without_victory(self):
        classifier = GestureClassifier()
        points = hand((1, 1, 1, 1))
        points[4] = points[8]
        self.assertEqual(classifier.classify(points).gesture, Gesture.PINCH_NEXT)
        relaxed = hand((1, 0, 1, 0))
        x, y = relaxed[8]
        relaxed[4] = (x - 0.36, y)
        result = classifier.classify(relaxed)
        self.assertEqual(result.gesture, Gesture.UNKNOWN)
        self.assertTrue(result.pinch_released)


class PinchControllerTests(unittest.TestCase):
    def setUp(self):
        self.controller = Controller(Settings())
        self.controller.set_active(True, 0)

    def release(self, start):
        self.controller.update(observation(Gesture.PALM), start)
        self.controller.update(observation(Gesture.PALM), start + 0.14)

    def pinch(self, gesture, start):
        self.controller.update(observation(gesture), start)
        return self.controller.update(observation(gesture), start + 0.18)

    def test_default_mode_is_pinch_and_palm_movement_does_not_page(self):
        self.assertEqual(Settings().page_gesture, "pinch")
        for t, x in ((1, 0.2), (1.1, 0.3), (1.2, 0.5)):
            self.assertEqual(self.controller.update(Observation(Gesture.PALM, (x, 0.5), (x, 0.5)), t).events, ())

    def test_index_next_and_middle_previous(self):
        self.release(0.1)
        self.assertEqual(self.pinch(Gesture.PINCH_NEXT, 0.3).events, ("next",))
        self.release(0.6)
        self.assertEqual(self.pinch(Gesture.PINCH_PREVIOUS, 0.8).events, ("previous",))

    def test_short_contact_does_not_page(self):
        self.release(0.1)
        self.controller.update(observation(Gesture.PINCH_NEXT), 0.3)
        self.assertEqual(self.controller.update(observation(Gesture.PINCH_NEXT), 0.38).events, ())
        self.controller.update(observation(Gesture.PALM), 0.4)
        self.assertEqual(self.controller.update(observation(Gesture.PINCH_NEXT), 0.45).events, ())

    def test_holding_contact_never_repeats(self):
        self.release(0.1)
        self.pinch(Gesture.PINCH_NEXT, 0.3)
        for t in (0.6, 1, 2, 4):
            self.assertEqual(self.controller.update(observation(Gesture.PINCH_NEXT), t).events, ())
            self.assertTrue(self.controller.active)

    def test_switching_fingers_without_release_does_not_page_again(self):
        self.release(0.1)
        self.pinch(Gesture.PINCH_NEXT, 0.3)
        self.assertEqual(self.pinch(Gesture.PINCH_PREVIOUS, 1).events, ())

    def test_unknown_label_does_not_count_as_release(self):
        self.release(0.1)
        self.pinch(Gesture.PINCH_NEXT, 0.3)
        self.controller.update(observation(Gesture.UNKNOWN), 0.6)
        self.controller.update(observation(Gesture.UNKNOWN), 0.8)
        self.assertEqual(self.pinch(Gesture.PINCH_NEXT, 1).events, ())

    def test_lost_hand_and_resume_require_release_first(self):
        self.release(0.1)
        self.pinch(Gesture.PINCH_NEXT, 0.3)
        self.controller.update(Observation(), 0.5)
        self.assertEqual(self.pinch(Gesture.PINCH_NEXT, 0.6).events, ())
        self.controller.set_active(False, 1)
        self.controller.set_active(True, 2)
        self.assertEqual(self.pinch(Gesture.PINCH_NEXT, 2.1).events, ())
        self.release(2.4)
        self.assertEqual(self.pinch(Gesture.PINCH_NEXT, 2.6).events, ("next",))

    def test_geometry_to_controller_with_no_hand_movement(self):
        classifier = GestureClassifier()
        neutral = hand((1, 1, 1, 1))
        for t in (0.1, 0.24):
            self.controller.update(classifier.classify(neutral), t)
        contact = neutral.copy()
        contact[4] = contact[8]
        self.controller.update(classifier.classify(contact), 0.3)
        self.assertEqual(self.controller.update(classifier.classify(contact), 0.48).events, ("next",))

    def test_pinch_settings_validation(self):
        for changes in ({"pinch_hold_ms": 0}, {"pinch_release_ms": 30},
                        {"pinch_cooldown_ms": 0}, {"page_gesture": "invalid"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(Settings(), **changes).validate()

    def test_repeated_pages_without_victory_using_geometry_release(self):
        now = 0.1
        for index in range(8):
            released = Observation(Gesture.UNKNOWN, pinch_released=True)
            self.controller.update(released, now)
            self.controller.update(released, now + 0.14)
            result = self.pinch(Gesture.PINCH_NEXT, now + 0.2)
            self.assertEqual(result.events, ("next",))
            self.assertTrue(result.active)
            now += 0.7

    def test_default_control_survives_fist_and_long_hand_absence(self):
        for gesture, t in ((Gesture.FIST, 1), (Gesture.FIST, 3), (Gesture.NONE, 4), (Gesture.NONE, 8)):
            result = self.controller.update(observation(gesture), t)
            self.assertTrue(result.active)
            self.assertNotIn("pause", result.events)
            self.assertNotIn("lost_pause", result.events)

    def test_unknown_without_release_evidence_still_does_not_rearm(self):
        self.release(0.1)
        self.pinch(Gesture.PINCH_NEXT, 0.3)
        for t in (0.6, 0.8):
            self.controller.update(Observation(Gesture.UNKNOWN, pinch_released=False), t)
        self.assertEqual(self.pinch(Gesture.PINCH_NEXT, 1).events, ())


if __name__ == "__main__":
    unittest.main()
