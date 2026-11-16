"""Native floating-button clicks against this script's private animated PPT.

The camera is never opened. Only the newly created fixture is modified/closed.
Mouse events are sent only after hit-testing the tool's own floating button.
"""

from pathlib import Path
import json
import os
import sys
import tempfile
import time
import tkinter as tk
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pythoncom
import win32api
import win32con
import win32gui
import win32process
import win32com.client

from airpresent.app import App
from airpresent.desktop import enable_dpi_awareness
from airpresent.gestures import Gesture, Observation
from airpresent.presentation import PresentationOutput


def main():
    enable_dpi_awareness()
    pythoncom.CoInitialize()
    office = presentation = show = ui = panel = None
    discovery = PresentationOutput()
    old_mouse = win32api.GetCursorPos()
    folder = ROOT / "screenshots" / "floating_ppt_test"
    folder.mkdir(parents=True, exist_ok=True)
    result = {}
    try:
        try:
            office = win32com.client.GetActiveObject("PowerPoint.Application")
        except pythoncom.com_error:
            office = win32com.client.Dispatch("PowerPoint.Application")
        office.Visible = True
        presentation = office.Presentations.Add(True)
        first_box = None
        for index in range(1, 4):
            slide = presentation.Slides.Add(index, 12)
            box = slide.Shapes.AddTextbox(1, 60, 80, 600, 160)
            box.TextFrame.TextRange.Text = f"AirPresent floating test - page {index}"
            if index == 1:
                first_box = box
        effect = presentation.Slides.Item(1).TimeLine.MainSequence.AddEffect(first_box, 10, 0, 2)
        effect.Timing.Duration = 5
        fixture = folder / ("airpresent_float_" + uuid.uuid4().hex[:8] + ".pptx")
        presentation.SaveAs(str(fixture))
        full_screen = "--fullscreen" in sys.argv
        presentation.SlideShowSettings.ShowType = 1 if full_screen else 2
        started = time.monotonic()
        show = presentation.SlideShowSettings.Run()
        if show is None:
            show = presentation.SlideShowWindow
        targets = [target for target in discovery.list_targets() if target.name == fixture.name]
        assert len(targets) == 1, "Private fixture target was not found"

        panel = tk.Tk()
        with tempfile.TemporaryDirectory() as settings_folder:
            ui = App(panel, Path(settings_folder))
            ui.presentation.select(targets[0])
            ui.ready = True  # Simulated camera readiness; no device is opened.
            ui.toggle_control()
            ui.last_observation = Observation(Gesture.PALM, pinch_released=True)
            ui.show_floating_controls()
            panel.update()
            candidates = []
            def find_show(hwnd, _):
                if win32gui.IsWindowVisible(hwnd) and fixture.name in win32gui.GetWindowText(hwnd):
                    candidates.append(hwnd)
            win32gui.EnumWindows(find_show, None)
            assert candidates, "Fixture window not found; refusing mouse events"
            # Observe the existing foreground rather than forcing another app
            # to the front. The page operation itself is independent of focus.
            slide_hwnd = win32gui.GetForegroundWindow()
            if win32process.GetWindowThreadProcessId(slide_hwnd)[1] == os.getpid():
                # Simulate the user's explicit switch into this private show.
                # Only a window bearing the fixture's unique name is selected.
                owned_show = next((hwnd for hwnd in candidates if win32gui.GetClassName(hwnd).lower() == "screenclass"), candidates[0])
                win32gui.SetForegroundWindow(owned_show)
                time.sleep(0.1)
                panel.update()
                slide_hwnd = win32gui.GetForegroundWindow()
            assert win32process.GetWindowThreadProcessId(slide_hwnd)[1] != os.getpid(), "No external foreground window for focus check"

            def click_own(button):
                panel.update()
                x = button.winfo_rootx() + button.winfo_width() // 2
                y = button.winfo_rooty() + button.winfo_height() // 2
                hit = win32gui.WindowFromPoint((x, y))
                assert win32process.GetWindowThreadProcessId(hit)[1] == os.getpid(), "Not this test's window; refusing click"
                win32api.SetCursorPos((x, y))
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0)
                panel.update()

            def wait_page(number):
                deadline = time.monotonic() + 3.5
                while time.monotonic() < deadline:
                    panel.update()
                    if not ui.page_output.busy and f"第 {number} 页" in ui.page_label.cget("text"):
                        return
                    time.sleep(0.01)
                raise AssertionError("Page did not update: " + ui.last_feedback)

            click_own(ui.floating.buttons[2])
            wait_page(2)
            first_elapsed = time.monotonic() - started
            assert show.View.Slide.SlideIndex == 2
            assert first_elapsed < 5, "The 5-second animation finished before navigation was confirmed"
            assert ui.controller.active, "Navigation disabled continuous control"
            assert win32gui.GetForegroundWindow() == slide_hwnd, "Floating next-page click stole presentation focus"
            click_own(ui.floating.buttons[0])
            wait_page(1)
            assert ui.controller.active
            click_own(ui.floating.buttons[1])
            assert not ui.controller.active
            click_own(ui.floating.buttons[1])
            assert ui.controller.active
            ui.floating.collapse()
            panel.update()
            assert ui.floating.window.winfo_width() == 54
            click_own(ui.floating.icon)
            assert not ui.floating.collapsed
            assert win32gui.GetForegroundWindow() == slide_hwnd
            result = {"pages": [1, 2, 1], "first_page_switch_from_animation_start_s": round(first_elapsed, 3),
                      "animation_duration_s": 5, "floating_clicks_preserved_focus": True,
                      "continuous_control_after_navigation": True, "camera_opened": False,
                      "full_screen_show": full_screen}
            (folder / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            print("PASS:", json.dumps(result), flush=True)
    finally:
        if ui is not None:
            ui.close()
            for _ in range(30):
                try:
                    panel.update()
                    time.sleep(0.01)
                except tk.TclError:
                    break
        elif panel is not None:
            panel.destroy()
        if show is not None:
            try:
                show.View.Exit()
            except Exception:
                pass
        if presentation is not None:
            try:
                presentation.Saved = True
                presentation.Close()
            except Exception:
                pass
        if office is not None:
            try:
                if office.Presentations.Count == 0:
                    office.Quit()
            except Exception:
                pass
        discovery.close()
        win32api.SetCursorPos(old_mouse)
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    main()
