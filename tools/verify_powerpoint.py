"""Verify actual slide indices using a private, temporary three-slide show.

No user presentation is opened. Only this script's own presentation is closed.
"""

from pathlib import Path
import sys
import time
import uuid
import tkinter as tk
import ctypes

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pythoncom
import win32com.client
from airpresent.presentation import PresentationOutput


def main():
    pythoncom.CoInitialize()
    app = presentation = show = panel = None
    output = None
    try:
        try:
            app = win32com.client.GetActiveObject("PowerPoint.Application")
        except pythoncom.com_error:
            app = win32com.client.Dispatch("PowerPoint.Application")
        app.Visible = True
        presentation = app.Presentations.Add(True)
        for index in range(1, 4):
            slide = presentation.Slides.Add(index, 12)  # ppLayoutBlank
            box = slide.Shapes.AddTextbox(1, 60, 80, 600, 160)
            box.TextFrame.TextRange.Text = f"AirPresent integration fixture - page {index}"
        folder = ROOT / "screenshots" / "powerpoint_test"
        folder.mkdir(parents=True, exist_ok=True)
        fixture = folder / ("airpresent_test_" + uuid.uuid4().hex[:8] + ".pptx")
        presentation.SaveAs(str(fixture))
        settings = presentation.SlideShowSettings
        settings.ShowType = 2  # ppShowTypeWindow
        show = settings.Run()
        time.sleep(0.5)
        if show is None:
            show = presentation.SlideShowWindow
        output = PresentationOutput()
        targets = [target for target in output.list_targets() if target.name == fixture.name]
        if not targets:
            print("Direct presentation count:", app.Presentations.Count, flush=True)
            print("Direct test slide:", show.View.Slide.SlideIndex, "Name:", presentation.Name, flush=True)
            print("Connection errors:", output.connection_errors, flush=True)
        assert len(targets) == 1, f"Own test show not found: {targets}"
        output.select(targets[0])
        assert show.View.Slide.SlideIndex == 1
        panel = tk.Tk()
        panel.title("AirPresent private integration test")
        panel.geometry("420x160+80+80")
        panel.focus_force()
        panel.update()
        result = output.send_page("next")
        assert result.changed and (result.before, result.after) == (1, 2), result
        assert show.View.Slide.SlideIndex == 2
        result = output.send_page("previous")
        assert result.changed and (result.before, result.after) == (2, 1), result
        assert show.View.Slide.SlideIndex == 1
        boundary = output.send_page("previous")
        assert not boundary.changed and boundary.after == 1
        snapshot = output.export_current_slide(folder / "current_slide.png")
        assert snapshot["slide"] == 1 and Path(snapshot["path"]).stat().st_size > 1000
        print("PASS: real PowerPoint page 1 -> 2 -> 1 with test panel open; first-page boundary; current-slide PNG export")
    finally:
        if panel is not None:
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
        if app is not None:
            try:
                if app.Presentations.Count == 0:
                    app.Quit()
            except Exception:
                pass
        if output is not None:
            output.close()
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    main()
