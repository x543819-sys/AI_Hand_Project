"""Validated settings, kept next to the entry point for a portable project."""

from dataclasses import asdict, dataclass, fields
import json
import math
from pathlib import Path


@dataclass
class Settings:
    camera_index: int = 0
    mirror: bool = True
    detection_confidence: float = 0.65
    tracking_confidence: float = 0.6
    stable_ms: int = 280
    resume_ms: int = 350
    pause_ms: int = 900
    fist_pause_enabled: bool = False
    lost_pause_enabled: bool = False
    live_output: bool = True
    page_gesture: str = "pinch"
    pinch_hold_ms: int = 160
    pinch_release_ms: int = 120
    pinch_cooldown_ms: int = 300
    palm_distance: float = 0.22
    palm_speed: float = 0.6
    palm_window_ms: int = 500
    palm_settle_ms: int = 180
    cooldown_ms: int = 650
    flick_distance: float = 0.08
    flick_speed: float = 0.65
    flick_window_ms: int = 260
    flick_settle_ms: int = 160
    swipe_distance: float = 0.20
    swipe_window_ms: int = 650
    smoothing: float = 0.55
    roi_margin: float = 0.12
    lost_pause_ms: int = 1500

    def validate(self):
        for key in ("camera_index", "stable_ms", "resume_ms", "pause_ms", "cooldown_ms",
                    "swipe_window_ms", "lost_pause_ms", "flick_window_ms", "flick_settle_ms",
                    "palm_window_ms", "palm_settle_ms", "pinch_hold_ms", "pinch_release_ms", "pinch_cooldown_ms"):
            value = getattr(self, key)
            if type(value) is not int:
                raise ValueError(f"{key} 必须是整数")
        if not 0 <= self.camera_index <= 9:
            raise ValueError("摄像头编号应在 0–9 之间")
        if type(self.mirror) is not bool:
            raise ValueError("mirror 必须是布尔值")
        if type(self.fist_pause_enabled) is not bool:
            raise ValueError("fist_pause_enabled 必须是布尔值")
        if type(self.lost_pause_enabled) is not bool:
            raise ValueError("lost_pause_enabled 必须是布尔值")
        if type(self.live_output) is not bool:
            raise ValueError("live_output 必须是布尔值")
        if self.page_gesture not in ("pinch", "palm"):
            raise ValueError("翻页方式必须为 pinch 或 palm")
        if not 80 <= self.pinch_hold_ms <= 800 or not 80 <= self.pinch_release_ms <= 500:
            raise ValueError("捏合确认应在 80–800ms，松开确认应在 80–500ms")
        if not 150 <= self.pinch_cooldown_ms <= 1500:
            raise ValueError("捏合翻页间隔应在 150–1500ms")
        for key in ("detection_confidence", "tracking_confidence", "smoothing"):
            value = getattr(self, key)
            if not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 < value <= 1:
                raise ValueError(f"{key} 应在 0–1 之间，且大于 0")
        if not 0 <= self.roi_margin <= 0.35:
            raise ValueError("活动区边距应在 0–0.35 之间")
        if not 0.08 <= self.swipe_distance <= 0.5:
            raise ValueError("挥动距离应在 0.08–0.5 之间")
        if not 100 <= self.stable_ms <= 1000 or not 150 <= self.resume_ms <= 3000:
            raise ValueError("手势确认时间超出范围")
        if not 500 <= self.pause_ms <= 3000:
            raise ValueError("握拳暂停确认应在 500–3000 毫秒之间")
        if not 300 <= self.cooldown_ms <= 3000:
            raise ValueError("翻页间隔应在 300–3000 毫秒之间")
        if not 0.03 <= self.flick_distance <= 0.3 or not 0.2 <= self.flick_speed <= 3.0:
            raise ValueError("甩手幅度应在 0.03–0.3，速度应在 0.2–3 之间")
        if not 100 <= self.flick_window_ms <= 500 or not 100 <= self.flick_settle_ms <= 500:
            raise ValueError("甩手检测窗口和停稳时间应在 100–500 毫秒之间")
        if not 0.1 <= self.palm_distance <= 1.0 or not 0.2 <= self.palm_speed <= 3.0:
            raise ValueError("拨动幅度应在 0.1–1 个手掌宽度，速度应在 0.2–3 手掌宽度/秒")
        if not 250 <= self.palm_window_ms <= 1000 or not 100 <= self.palm_settle_ms <= 600:
            raise ValueError("拨动检测窗口或停稳时间超出范围")
        if not 200 <= self.swipe_window_ms <= 1500 or not 500 <= self.lost_pause_ms <= 10000:
            raise ValueError("运动窗口或丢手暂停时间超出范围")
        return self

    @classmethod
    def load(cls, path: Path):
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("设置文件必须是 JSON 对象")
        if "lost_pause_enabled" not in data:
            data["fist_pause_enabled"] = False
        if "flick_distance" not in data:
            # Migrate only the previous defaults; keep individually tuned values.
            if data.get("cooldown_ms") == 900:
                data["cooldown_ms"] = 650
            if data.get("smoothing") == 0.32:
                data["smoothing"] = 0.55
        names = {field.name for field in fields(cls)}
        return cls(**{key: value for key, value in data.items() if key in names}).validate()

    def save(self, path: Path):
        self.validate()
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
