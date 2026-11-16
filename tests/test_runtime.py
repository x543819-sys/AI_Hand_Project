"""Actual model inference and camera-worker cleanup, using no real camera."""

from pathlib import Path
from queue import Empty
import time
import unittest
from unittest.mock import patch

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from airpresent.config import Settings
from airpresent.gestures import Gesture
from airpresent.tracker import CameraWorker, ensure_model


PROJECT = Path(__file__).resolve().parents[1]
MODEL = PROJECT / "models" / "hand_landmarker.task"


@unittest.skipUnless(MODEL.exists(), "Download the official model first")
class RuntimeTests(unittest.TestCase):
    def test_model_in_video_mode_with_no_hand(self):
        options = vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(MODEL)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
        )
        with vision.HandLandmarker.create_from_options(options) as model:
            for stamp in (0, 33, 66):
                image = mp.Image(image_format=mp.ImageFormat.SRGB,
                                 data=np.zeros((480, 640, 3), dtype=np.uint8))
                self.assertFalse(model.detect_for_video(image, stamp).hand_landmarks)

    def test_camera_read_failure_releases_resources(self):
        class FakeCapture:
            def __init__(self):
                self.count = 0
                self.released = False

            def isOpened(self):
                return True

            def set(self, *args):
                return True

            def read(self):
                self.count += 1
                if self.count <= 3:
                    return True, np.zeros((480, 640, 3), dtype=np.uint8)
                return False, None

            def release(self):
                self.released = True

        capture = FakeCapture()
        worker = CameraWorker(Settings(), MODEL)
        with patch.object(cv2, "VideoCapture", return_value=capture):
            worker.start()
            worker.thread.join(timeout=10)
        self.assertFalse(worker.running)
        self.assertTrue(capture.released)
        messages = []
        while not worker.messages.empty():
            messages.append(worker.messages.get_nowait()[0])
        self.assertIn("ready", messages)
        self.assertIn("error", messages)
        self.assertEqual(messages[-1], "stopped")
        frame = worker.latest()
        self.assertIsNotNone(frame)
        self.assertEqual(frame.observation.gesture, Gesture.NONE)
        self.assertEqual(frame.rgb.shape, (480, 640, 3))
        self.assertIsNone(worker.latest())

    def test_bundled_model_never_needs_network(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected network access")):
            self.assertEqual(ensure_model(MODEL), MODEL)


if __name__ == "__main__":
    unittest.main()
