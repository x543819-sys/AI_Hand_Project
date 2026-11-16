"""Tk configuration regression checks; no camera, Office or external API."""
import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageGrab
import time
from airpresent.app import App
from airpresent.desktop import enable_dpi_awareness
from airpresent.presentation import PresentationTarget


def main():
    enable_dpi_awareness()
    root = tk.Tk()
    app = None
    try:
        with tempfile.TemporaryDirectory() as folder:
            app = App(root, Path(folder))
            app.open_summary()
            panel = app.summary_panel
            panel.key.set("test-not-real-official")
            panel.provider.set("星图 Token Plan")
            panel.change_provider()
            assert panel.key.get() == "", "Key was carried into another provider"
            assert panel.base_url.get() == "https://ai.csdn.net/api/model/token/v1"
            assert "Credits" in panel.billing.cget("text")
            panel.provider.set("星图 按量付费")
            panel.change_provider()
            assert "余额" in panel.billing.cget("text")
            assert panel.base_url.get() == "https://ai.csdn.net/api/model/v1"
            panel.provider.set("自定义兼容服务")
            panel.change_provider()
            assert panel.url_entry.cget("state") == "normal"
            panel.model.set("test-vision")
            panel.base_url.set("https://example.com/v1")
            panel.key.set("test-not-real-custom")
            class Capture:
                busy = False
                def submit(self, target, config, key, preview):
                    assert config.endpoint == "https://example.com/v1/chat/completions"
                    self.config = config
                def cancel(self):
                    pass
            capture = Capture()
            panel.worker = capture
            app.presentation.select(PresentationTarget("ppt", "test", "test.pptx"))
            panel.start()
            stored = panel.settings_path.read_text(encoding="utf-8")
            assert "test-not-real-custom" not in stored
            assert json.loads(stored)["base_url"] == "https://example.com/v1"
            panel.close()
            app.open_summary()
            panel = app.summary_panel
            assert panel.base_url.get() == "https://example.com/v1"
            panel.provider.set("星图 Token Plan")
            panel.change_provider()
            assert "kimi-k3" in panel.model_choice.cget("values")
            panel.window.geometry("760x650")
            panel.preview_image = Image.new("RGB", (1280, 720), "white")
            panel.resize_preview()
            root.update()
            panel.resize_preview()
            root.update()
            bottom = panel.resume_button.winfo_rooty() + panel.resume_button.winfo_height()
            assert bottom <= panel.window.winfo_rooty() + panel.window.winfo_height(), "Bottom controls clipped"
            panel.window.lift()
            root.update()
            time.sleep(.5)
            output = Path(__file__).resolve().parents[1] / "screenshots" / "xingtu.png"
            output.parent.mkdir(exist_ok=True)
            ImageGrab.grab(bbox=(panel.window.winfo_rootx(), panel.window.winfo_rooty(),
                                panel.window.winfo_rootx()+panel.window.winfo_width(),
                                panel.window.winfo_rooty()+panel.window.winfo_height())).save(output)
            panel.close()
            app.close()
            root.update()
            print("PASS: billing routes, key isolation, custom URL, config roundtrip, no key persistence")
    finally:
        try:
            if root.winfo_exists():
                root.destroy()
        except tk.TclError:
            pass


if __name__ == "__main__":
    main()
