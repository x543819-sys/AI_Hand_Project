"""Real PPT export + Tk summary flow. Model replies are explicitly simulated.

Creates/closes only a unique fixture. No camera, model API, or user deck access.
"""
from pathlib import Path
import io
import json
import sys
import tempfile
import time
import tkinter as tk
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pythoncom
import win32com.client
import numpy as np
from PIL import Image, ImageGrab
from airpresent.app import App
from airpresent.desktop import enable_dpi_awareness
from airpresent.gestures import Gesture, Observation
from airpresent.presentation import PresentationTarget
from airpresent.tracker import Frame


def main():
    enable_dpi_awareness()
    pythoncom.CoInitialize()
    doc = show = root = app = None
    output = Path(__file__).resolve().parents[1] / "screenshots"
    output.mkdir(exist_ok=True)
    try:
        office = win32com.client.Dispatch("PowerPoint.Application")
        doc = office.Presentations.Add(True)
        doc.PageSetup.SlideWidth = 720
        doc.PageSetup.SlideHeight = 540
        slide = doc.Slides.Add(1, 12)
        box = slide.Shapes.AddTextbox(1, 50, 60, 600, 350)
        box.TextFrame.TextRange.Text = "AirPresent\n智能演示辅助助手\n\n稳定手势翻页\n当前页视觉摘要\n悬浮控制与状态反馈"
        box.TextFrame.TextRange.Font.Size = 30
        with tempfile.TemporaryDirectory() as temp:
            path = output / ("summary_test_" + uuid.uuid4().hex[:8] + ".pptx")
            doc.SaveAs(str(path))
            doc.SlideShowSettings.ShowType = 2
            show = doc.SlideShowSettings.Run()
            root = tk.Tk()
            app = App(root, Path(temp))
            app.presentation.select(PresentationTarget("PowerPoint.Application", str(path), path.name))
            app.ready = True
            app.toggle_control()
            app.open_summary()
            panel = app.summary_panel
            assert not app.controller.active
            def pump():
                deadline = time.monotonic() + 10
                ticks = 0
                while app.summary_worker.busy and time.monotonic() < deadline:
                    root.update()
                    ticks += 1
                    time.sleep(.01)
                assert not app.summary_worker.busy, panel.status.cget("text")
                return ticks
            panel.start(True)
            pump()
            assert "仅本地预览" in panel.status.cget("text"), panel.status.cget("text")
            assert "第 1 页" in panel.source
            class FakeClient:
                fail = True
                def summarize(self, config, key, png):
                    with Image.open(io.BytesIO(png)) as image:
                        assert image.size == (1280, 960), image.size
                    time.sleep(.25)
                    if self.fail:
                        raise RuntimeError("测试：模拟网络失败，可重试")
                    return "[测试响应，非真实模型输出]\n\n主题：智能演示辅助助手。\n\n关键点：稳定翻页、当前页摘要、悬浮反馈。"
            client = FakeClient()
            app.summary_worker.client = client
            panel.key.set("test-not-a-real-key")
            panel.start()
            pump()
            assert "模拟网络失败" in panel.status.cget("text")
            client.fail = False
            panel.start()
            rgb = np.zeros((480, 640, 3), dtype=np.uint8)
            frame_count = app.frame_count
            for _ in range(5):
                app._handle_frame(Frame(rgb, Observation(Gesture.VICTORY), time.monotonic(), 30, 20))
            assert app.frame_count == frame_count + 5
            assert not app.controller.active, "Scissors resumed while summary open"
            ticks = pump()
            assert ticks > 5, "UI did not refresh during simulated slow response"
            assert "非真实模型输出" in panel.text.get("1.0", "end")
            assert "test-not-a-real-key" not in panel.settings_path.read_text(encoding="utf-8")
            panel.copy()
            assert panel.window.clipboard_get().startswith(panel.source)
            panel.window.update()
            ImageGrab.grab(bbox=(panel.window.winfo_rootx(), panel.window.winfo_rooty(),
                                panel.window.winfo_rootx() + panel.window.winfo_width(),
                                panel.window.winfo_rooty() + panel.window.winfo_height())).save(output / "summary_test.png")
            panel.close(True)
            assert app.summary_panel is None and app.controller.active
            result = {"real_ppt_page_export": True, "aspect_ratio_4_3_preserved": True,
                      "model_response": "simulated, no API call", "failure_retry": True,
                      "frames_continue": True, "gesture_resume_blocked_during_summary": True,
                      "key_not_saved": True, "manual_resume": True}
            (output / "summary_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            print("PASS:", json.dumps(result), flush=True)
    finally:
        if app:
            app.close()
            for _ in range(20):
                try:
                    root.update()
                    time.sleep(.02)
                except tk.TclError:
                    break
        if show:
            try:
                show.View.Exit()
            except Exception:
                pass
        if doc:
            doc.Saved = True
            doc.Close()
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    main()
