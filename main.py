"""AirPresent entry point. Camera starts only after an explicit UI action."""

import argparse
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description="AirPresent 手势演示助手")
    parser.add_argument("--download-model", action="store_true", help="下载手部模型后退出")
    args = parser.parse_args()
    project_dir = Path(__file__).resolve().parent
    if args.download_model:
        from airpresent.tracker import ensure_model
        path = ensure_model(project_dir / "models" / "hand_landmarker.task")
        print(f"Model ready: {path}")
        return
    try:
        import tkinter as tk
        from airpresent.app import App
        from airpresent.desktop import enable_dpi_awareness
    except ImportError as exc:
        print(f"Missing dependency: {exc}\nRun setup.bat to prepare the project environment.")
        sys.exit(1)
    enable_dpi_awareness()
    root = tk.Tk()
    app = App(root, project_dir)
    root.mainloop()


if __name__ == "__main__":
    main()
