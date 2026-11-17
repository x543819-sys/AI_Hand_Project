"""Camera and MediaPipe run on one worker; Tk only consumes the latest frame."""

from dataclasses import dataclass
import hashlib
from pathlib import Path
from queue import Empty, Full, Queue
import threading
import time
import urllib.request

from .config import Settings
from .gestures import Gesture, GestureClassifier, Observation, distance


MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
MODEL_SHA256 = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"
CONNECTIONS = ((0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7),
               (7, 8), (5, 9), (9, 10), (10, 11), (11, 12), (9, 13),
               (13, 14), (14, 15), (15, 16), (13, 17), (0, 17),
               (17, 18), (18, 19), (19, 20))


def ensure_model(path: Path):
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == MODEL_SHA256:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".download")
    try:
        with urllib.request.urlopen(MODEL_URL, timeout=30) as response:
            with temporary.open("wb") as output:
                while chunk := response.read(1024 * 256):
                    output.write(chunk)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != MODEL_SHA256:
            raise RuntimeError("模型文件校验失败，请重新下载固定版本模型")
        temporary.replace(path)
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"手部模型下载失败。请按 README 手动下载到 {path}。详情：{exc}") from exc
    return path


@dataclass
class Frame:
    rgb: object
    observation: Observation
    timestamp: float
    fps: float
    inference_ms: float


class CameraWorker:
    def __init__(self, settings: Settings, model_path: Path, classifier_factory=GestureClassifier):
        self.settings = settings
        self.model_path = model_path
        self.classifier_factory = classifier_factory
        self.frames = Queue(maxsize=1)
        self.messages = Queue()
        self.stop_event = threading.Event()
        self.thread = None

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self):
        self.thread = threading.Thread(target=self._run, name="camera-tracker", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def latest(self):
        try:
            return self.frames.get_nowait()
        except Empty:
            return None

    def _run(self):
        cap = landmarker = None
        try:
            self.messages.put(("status", "正在加载手部检测模型…"))
            import cv2
            import mediapipe as mp
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision

            ensure_model(self.model_path)
            if self.stop_event.is_set():
                return
            options = vision.HandLandmarkerOptions(
                base_options=python.BaseOptions(model_asset_path=str(self.model_path)),
                running_mode=vision.RunningMode.VIDEO,
                num_hands=1,
                min_hand_detection_confidence=self.settings.detection_confidence,
                min_hand_presence_confidence=self.settings.detection_confidence,
                min_tracking_confidence=self.settings.tracking_confidence,
            )
            landmarker = vision.HandLandmarker.create_from_options(options)
            self.messages.put(("status", "正在打开摄像头…"))
            cap = cv2.VideoCapture(self.settings.camera_index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(self.settings.camera_index)
            if not cap.isOpened():
                raise RuntimeError("摄像头打不开。请检查编号、Windows 摄像头权限及其他软件占用。")
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
            classifier = self.classifier_factory()
            previous = time.monotonic()
            last_stamp = -1
            failures = 0
            self.messages.put(("ready", "摄像头已连接 · 当前为暂停状态"))
            while not self.stop_event.is_set():
                ok, bgr = cap.read()
                if not ok:
                    failures += 1
                    if failures >= 5:
                        raise RuntimeError("摄像头画面读取中断，请重新连接。")
                    time.sleep(0.02)
                    continue
                failures = 0
                if self.settings.mirror:
                    bgr = cv2.flip(bgr, 1)
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                capture_time = time.monotonic()
                stamp = max(last_stamp + 1, int(capture_time * 1000))
                last_stamp = stamp
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                start = time.perf_counter()
                result = landmarker.detect_for_video(image, stamp)
                inference_ms = (time.perf_counter() - start) * 1000
                h, w = rgb.shape[:2]
                observation = Observation()
                if result.hand_landmarks:
                    points = [(lm.x * w, lm.y * h) for lm in result.hand_landmarks[0]]
                    raw = classifier.classify(points)
                    if raw.pointer is not None and raw.palm is not None:
                        # Track the palm itself, not a forced wrist/fingertip flick.
                        motion = (raw.palm[0] / w, raw.palm[1] / h)
                        palm_width = max(distance(points[5], points[17]), distance(points[0], points[9]) * 0.7) / w
                        observation = Observation(
                            raw.gesture,
                            (raw.pointer[0] / w, raw.pointer[1] / h),
                            (raw.palm[0] / w, raw.palm[1] / h), motion, palm_width, raw.pinch_released,
                        )
                    for a, b in CONNECTIONS:
                        cv2.line(rgb, tuple(map(int, points[a])), tuple(map(int, points[b])),
                                 (88, 221, 183), 2, cv2.LINE_AA)
                    for x, y in points:
                        cv2.circle(rgb, (int(x), int(y)), 4, (230, 255, 247), -1, cv2.LINE_AA)
                    cv2.circle(rgb, tuple(map(int, points[8])), 10, (78, 232, 191), 2, cv2.LINE_AA)
                    if raw.gesture in (Gesture.PINCH_NEXT, Gesture.PINCH_PREVIOUS):
                        tip = 8 if raw.gesture == Gesture.PINCH_NEXT else 12
                        for index in (4, tip):
                            cv2.circle(rgb, tuple(map(int, points[index])), 10, (255, 203, 110), 2, cv2.LINE_AA)
                else:
                    classifier.classify(None)
                margin = self.settings.roi_margin
                cv2.rectangle(rgb, (int(w * margin), int(h * margin)),
                              (int(w * (1 - margin)), int(h * (1 - margin))), (84, 130, 136), 1)
                now = time.monotonic()
                fps = 1 / max(now - previous, 0.001)
                previous = now
                frame = Frame(rgb, observation, capture_time, fps, inference_ms)
                # A size-one queue prevents old camera frames from accumulating.
                try:
                    self.frames.get_nowait()
                except Empty:
                    pass
                try:
                    self.frames.put_nowait(frame)
                except Full:
                    pass
        except Exception as exc:
            self.messages.put(("error", str(exc)))
        finally:
            if cap is not None:
                cap.release()
            if landmarker is not None:
                landmarker.close()
            self.messages.put(("stopped", "摄像头已关闭"))
