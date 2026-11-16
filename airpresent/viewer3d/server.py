"""Loopback-only viewer bridge. Camera is opt-in and released on shutdown."""
import base64
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Empty
import secrets
import threading
import time
from urllib.parse import urlsplit
import webbrowser

from ..config import Settings
from ..tracker import CameraWorker
from .motion import Motion

WEB = Path(__file__).parent / "web"


class Runtime:
    def __init__(self, project_dir, worker_factory=CameraWorker):
        self.project_dir = Path(project_dir)
        self.worker_factory = worker_factory
        self.worker = None
        self.motion = Motion()
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.image = None
        self.image_time = 0
        self.frame_time = None
        self.camera_status = "摄像头未开启"
        self.ready = False
        self.had_error = False
        self.revision = 0
        self.fps = 0
        self.last_seen = time.monotonic()

    def command(self, data):
        with self.lock:
            action = data.get("action")
            if action == "start":
                if self.worker is not None:
                    return
                index = data.get("camera", 0)
                if type(index) is not int or not 0 <= index <= 9:
                    raise ValueError("摄像头编号应为 0–9")
                self.worker = self.worker_factory(Settings(camera_index=index), self.project_dir / "models" / "hand_landmarker.task")
                self.ready = False
                self.had_error = False
                self.camera_status = "正在连接摄像头…"
                self.worker.start()
            elif action == "stop":
                self.motion.enable(False)
                self.ready = False
                if self.worker:
                    self.worker.stop()
                self.image = None
                self.camera_status = "正在关闭摄像头" if self.worker else "摄像头未开启"
            elif action == "enable":
                if data.get("value") and not self.ready:
                    raise ValueError("请先开启摄像头并等待连接成功")
                self.motion.enable(bool(data.get("value")))
            elif action == "mode":
                self.motion.set_mode(data.get("value"))
            elif action == "sensitivity":
                value = float(data.get("value", 1))
                if not .4 <= value <= 2:
                    raise ValueError("灵敏度应为 0.4–2")
                self.motion.sensitivity = value
                self.motion.release()
            elif action == "reset":
                self.motion.reset()
                self.revision += 1
            else:
                raise ValueError("未知操作")

    def poll(self):
        with self.lock:
            worker = self.worker
            if worker:
                try:
                    while True:
                        kind, message = worker.messages.get_nowait()
                        if kind != "stopped" or not self.had_error:
                            self.camera_status = message
                        if kind == "ready":
                            self.ready = True
                        elif kind == "error":
                            self.had_error = True
                            self.ready = False
                            self.motion.enable(False)
                except Empty:
                    pass
                frame = worker.latest()
                if frame is not None and self.ready:
                    if time.monotonic() - frame.timestamp <= .3:
                        self.frame_time = frame.timestamp
                        self.fps = round(frame.fps, 1)
                        self.motion.update(frame.observation, frame.timestamp)
                        if time.monotonic() - self.image_time > .1:
                            import cv2
                            small = cv2.resize(frame.rgb, (320, 240))
                            ok, encoded = cv2.imencode(".jpg", cv2.cvtColor(small, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 65])
                            if ok:
                                self.image = base64.b64encode(encoded).decode("ascii")
                                self.image_time = time.monotonic()
                if not worker.running:
                    self.worker = None
                    self.ready = False
                    self.motion.enable(False)
                    self.image = None
                    if not self.had_error:
                        self.camera_status = "摄像头已关闭"
            if self.frame_time and time.monotonic() - self.frame_time > .3:
                self.motion.release()
                self.motion.cursor = None
                if self.motion.active:
                    self.motion.status = "等待新画面 · 模型保持原位"

    def snapshot(self):
        with self.lock:
            return {**self.motion.snapshot(), "ready": self.ready, "camera": self.camera_status,
                    "image": self.image, "image_time": self.image_time, "fps": self.fps, "revision": self.revision}

    def close(self):
        self.stop.set()
        self.command({"action": "stop"})
        if self.worker and self.worker.thread:
            self.worker.thread.join(timeout=3)


def create_server(runtime):
    token = secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, code, data, kind="application/json; charset=utf-8"):
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' blob: data:")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (ConnectionError, OSError):
                pass

        def valid_host(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def do_GET(self):
            if not self.valid_host():
                return self.send(403, {"error": "无效主机"})
            path = urlsplit(self.path).path
            if path == "/api/state":
                if self.headers.get("X-AirHand-Token") != token:
                    return self.send(403, {"error": "无效会话"})
                runtime.last_seen = time.monotonic()
                return self.send(200, runtime.snapshot())
            file = (WEB / ("index.html" if path == "/" else path.lstrip("/"))).resolve()
            if not file.is_relative_to(WEB.resolve()) or not file.is_file():
                return self.send(404, {"error": "未找到文件"})
            kinds = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}
            return self.send(200, file.read_bytes(), kinds.get(file.suffix, "application/octet-stream"))

        def do_POST(self):
            origin = self.headers.get("Origin")
            expected = f"http://127.0.0.1:{self.server.server_port}"
            if not self.valid_host() or (origin and origin != expected):
                return self.send(403, {"error": "无效来源"})
            try:
                length = int(self.headers.get("Content-Length", 0))
                if not 0 < length <= 2048:
                    raise ValueError("请求过大")
                data = json.loads(self.rfile.read(length))
                if self.headers.get("X-AirHand-Token", data.get("token")) != token:
                    return self.send(403, {"error": "无效会话"})
                if self.path != "/api/command":
                    return self.send(404, {"error": "未知接口"})
                runtime.last_seen = time.monotonic()
                if data.get("action") == "exit":
                    runtime.stop.set()
                else:
                    runtime.command(data)
                return self.send(200, {"ok": True})
            except (ValueError, TypeError, AttributeError):
                return self.send(400, {"error": "操作参数不正确，请检查相机编号或模式"})
    return ThreadingHTTPServer(("127.0.0.1", 0), Handler), token


def main():
    runtime = Runtime(Path(__file__).resolve().parents[2])
    server, token = create_server(runtime)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/#{token}"
    print("3D viewer started on loopback. Close with the Exit button or Ctrl+C.", flush=True)
    webbrowser.open(url)
    try:
        while not runtime.stop.wait(.015):
            runtime.poll()
            if time.monotonic() - runtime.last_seen > 60:
                break
    except KeyboardInterrupt:
        pass
    finally:
        runtime.close()
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
