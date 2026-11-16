"""Integration smoke checks without accessing a camera or other applications."""

from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2
import mediapipe as mp
import numpy as np
from PIL import ImageGrab
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from airpresent.app import App
from airpresent.desktop import enable_dpi_awareness
from airpresent.gestures import Gesture, Observation
from airpresent.tracker import Frame
from airpresent.presentation import PresentationTarget, PageResult


class IntegrationChecks(unittest.TestCase):
    def test_real_model_with_empty_image(self):
        options = vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(ROOT / "models" / "hand_landmarker.task")),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
        )
        with vision.HandLandmarker.create_from_options(options) as landmarker:
            for stamp in (0, 33, 66):
                image = mp.Image(image_format=mp.ImageFormat.SRGB,
                                 data=np.zeros((480, 640, 3), dtype=np.uint8))
                result = landmarker.detect_for_video(image, stamp)
                self.assertEqual(result.hand_landmarks, [])

    def test_gui_and_frame_pipeline(self):
        enable_dpi_awareness()
        root = tk.Tk()
        with tempfile.TemporaryDirectory() as folder:
            dispatch = {"callback": lambda direction: PageResult(True, "已确认 PPT：1 → 2 页", 1, 2)}
            class FakeOutput:
                def select(self, target):
                    pass
                def send_page(self, direction):
                    return dispatch["callback"](direction)
                def close(self):
                    pass
            app = App(root, Path(folder), page_service_factory=FakeOutput)

            def wait_output():
                deadline = time.monotonic() + 2
                while app.page_output.busy and time.monotonic() < deadline:
                    app._poll_output()
                    root.update()
                    time.sleep(0.01)
                self.assertFalse(app.page_output.busy)
            root.update()
            self.assertIsNone(app.worker)
            self.assertTrue(app.live_output.get())
            self.assertFalse(app.controller.active)
            self.assertFalse(app.overlay.visible)
            self.assertIn("0.35", app.guide_details["01"].cget("text"))
            self.assertIn("连续", app.guide_details["04"].cget("text"))
            self.assertGreaterEqual(app.canvas.winfo_width(), 600)
            self.assertEqual(str(app.active_button["state"]), "disabled")
            self.assertLessEqual(app.log_label.winfo_rooty() + app.log_label.winfo_height(),
                                 root.winfo_rooty() + root.winfo_height() - 20)
            self.assertLessEqual(app.test_next_button.winfo_rooty() + app.test_next_button.winfo_height(),
                                 root.winfo_rooty() + root.winfo_height() - 40)

            # Screenshot only this generated app, with no camera or fake metrics.
            root.attributes("-topmost", True)
            root.update()
            time.sleep(0.4)
            root.update()
            output = ROOT / "screenshots" / "preview.png"
            output.parent.mkdir(exist_ok=True)
            ImageGrab.grab(bbox=(root.winfo_rootx(), root.winfo_rooty(),
                                root.winfo_rootx() + root.winfo_width(),
                                root.winfo_rooty() + root.winfo_height())).save(output)

            app.ready = True
            app.toggle_control()
            self.assertFalse(app.controller.active)
            app.live_output.set(False)
            app.change_output()
            app.toggle_control()
            self.assertTrue(app.controller.active)
            app._page_action("next")
            self.assertEqual(app.page, 2)
            app._page_action("previous")
            self.assertEqual(app.page, 1)
            app.live_output.set(True)
            app.change_output()
            self.assertFalse(app.controller.active)
            app.presentation.select(PresentationTarget("PowerPoint.Application", "C:/fixture.pptx", "fixture.pptx"))
            dispatch["callback"] = lambda direction: PageResult(True, "已确认 PPT：1 → 2 页", 1, 2)
            app.test_next_page()
            wait_output()
            self.assertIn("第 2 页", app.page_label.cget("text"))
            self.assertIn("已确认", app.slide_title.cget("text"))
            app.live_output.set(False)
            app.change_output()
            app.keyboard.escape_pressed = lambda: False
            app.toggle_control()
            rgb = np.zeros((480, 640, 3), dtype=np.uint8)
            obs = Observation(Gesture.POINT, (0.5, 0.5), (0.5, 0.5))
            now = time.monotonic()
            app.controller.update(obs, now - 0.4)
            app._handle_frame(Frame(rgb, obs, now, 30, 20))
            root.update()
            self.assertTrue(app.overlay.visible)
            app._handle_frame(Frame(rgb, Observation(), time.monotonic(), 30, 20))
            self.assertFalse(app.overlay.visible)
            fist = Observation(Gesture.FIST, (0.5, 0.5), (0.5, 0.5))
            app.settings.fist_pause_enabled = True
            now = time.monotonic()
            app.controller.update(fist, now - 0.4)
            app._handle_frame(Frame(rgb, fist, now, 30, 20))
            self.assertTrue(app.controller.active)
            self.assertIn("松开取消", app.control_label.cget("text"))
            app._handle_frame(Frame(rgb, obs, time.monotonic() - 1, 30, 20))
            self.assertTrue(app.controller.active)
            app.controller.set_active(True, time.monotonic())
            app.keyboard.escape_pressed = lambda: True
            app._handle_frame(Frame(rgb, obs, time.monotonic(), 30, 20))
            self.assertFalse(app.controller.active)

            app.export_session()
            exported = list((Path(folder) / "sessions").glob("session_*.csv"))
            self.assertEqual(len(exported), 1)
            self.assertIn("inference_p95", exported[0].read_text(encoding="utf-8-sig"))
            traces = list((Path(folder) / "sessions").glob("tracking_*.csv"))
            self.assertEqual(len(traces), 1)
            self.assertIn("pointer_visible", traces[0].read_text(encoding="utf-8-sig"))

            # No priming frame or window switch after a pause/resume cycle.
            app.keyboard.escape_pressed = lambda: False
            for _ in range(12):
                app.controller.set_active(True, time.monotonic())
                app._handle_frame(Frame(rgb, obs, time.monotonic(), 30, 20))
                root.update()
                self.assertTrue(app.overlay.is_visible())
                app.pause("test")
                root.update()
                self.assertFalse(app.overlay.is_visible())

            # End-to-end new gesture -> controller -> page output routing.
            calls = []
            def page_result(direction):
                calls.append(direction)
                return PageResult(True, "已确认测试页码变化", 1 if direction == "next" else 2,
                                  2 if direction == "next" else 1)
            dispatch["callback"] = page_result
            app.live_output.set(True)
            app.change_output()
            app.toggle_control()
            for command, expected in ((Gesture.PINCH_NEXT, "next"), (Gesture.PINCH_PREVIOUS, "previous")):
                neutral = Observation(Gesture.PALM, (0.5, 0.5), (0.5, 0.5))
                app._handle_frame(Frame(rgb, neutral, time.monotonic(), 30, 20))
                time.sleep(0.14)
                app._handle_frame(Frame(rgb, neutral, time.monotonic(), 30, 20))
                contact = Observation(command, (0.5, 0.5), (0.5, 0.5))
                app._handle_frame(Frame(rgb, contact, time.monotonic(), 30, 20))
                time.sleep(0.18)
                app._handle_frame(Frame(rgb, contact, time.monotonic(), 30, 20))
                wait_output()
                self.assertEqual(calls[-1], expected)
                count = len(calls)
                app._handle_frame(Frame(rgb, contact, time.monotonic(), 30, 20))
                self.assertEqual(len(calls), count)
            self.assertEqual(calls, ["next", "previous"])

            def fail_output(direction):
                raise RuntimeError("temporary output error")
            dispatch["callback"] = fail_output
            app.test_next_page()
            wait_output()
            self.assertTrue(app.controller.active)
            dispatch["callback"] = page_result
            app.test_next_page()
            wait_output()
            self.assertTrue(app.controller.active)

            app.floating.show()
            root.update()
            self.assertTrue(app.floating.window.winfo_ismapped())
            app.show_floating_controls()
            root.update()
            self.assertTrue(app.floating.window.winfo_ismapped())
            app.floating.collapse()
            root.update()
            self.assertEqual(app.floating.window.winfo_width(), 54)
            icon_window = app.floating.window
            ImageGrab.grab(bbox=(icon_window.winfo_rootx(), icon_window.winfo_rooty(),
                                icon_window.winfo_rootx() + icon_window.winfo_width(),
                                icon_window.winfo_rooty() + icon_window.winfo_height())).save(ROOT / "screenshots" / "floating_icon.png")
            app.floating.icon.invoke()
            root.update()
            self.assertFalse(app.floating.collapsed)
            app.floating.buttons[1].invoke()
            self.assertFalse(app.controller.active)
            app.floating.buttons[1].invoke()
            self.assertTrue(app.controller.active)
            app.restore_main()
            root.update()
            app.floating.show()
            root.update()
            time.sleep(0.1)
            widget = app.floating.window
            ImageGrab.grab(bbox=(widget.winfo_rootx(), widget.winfo_rooty(),
                                widget.winfo_rootx() + widget.winfo_width(),
                                widget.winfo_rooty() + widget.winfo_height())).save(ROOT / "screenshots" / "floating.png")

            app.ready = False
            app.open_settings()
            root.update()
            windows = [child for child in root.winfo_children() if isinstance(child, tk.Toplevel)
                       and child not in (app.overlay.window, app.floating.window)]
            self.assertEqual(len(windows), 1)
            checkboxes = [child for child in windows[0].winfo_children() if isinstance(child, tk.Checkbutton)]
            fist_checkbox = next(child for child in checkboxes if "握拳" in child.cget("text"))
            fist_checkbox.invoke()
            save_button = [child for child in windows[0].winfo_children()
                           if isinstance(child, tk.Button)][0]
            save_button.invoke()
            root.update()
            self.assertTrue((Path(folder) / "settings.json").exists())
            self.assertFalse(app.settings.fist_pause_enabled)
            self.assertIn("连续", app.guide_details["04"].cget("text"))

            app.close()
            root.update()
            time.sleep(0.04)
            root.update()


if __name__ == "__main__":
    unittest.main(verbosity=2)
