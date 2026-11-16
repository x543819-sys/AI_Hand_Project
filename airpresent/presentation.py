"""Control a selected PowerPoint/WPS slide show and read back its page number."""

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import time
import threading


class PresentationBusy(RuntimeError):
    """Office rejected a call temporarily; retry without disabling control."""


def is_busy_error(exc):
    values = [getattr(exc, "hresult", None)]
    if getattr(exc, "args", ()):
        values.append(exc.args[0])
        if len(exc.args) > 2 and isinstance(exc.args[2], tuple) and len(exc.args[2]) > 5:
            values.append(exc.args[2][5])
    return any(isinstance(value, int) and value & 0xFFFFFFFF in (0x80010001, 0x80010109, 0x8001010A)
               for value in values)


@dataclass(frozen=True)
class PresentationTarget:
    progid: str
    path: str
    name: str


@dataclass(frozen=True)
class PageResult:
    changed: bool
    message: str
    before: int
    after: int


class PresentationOutput:
    def __init__(self):
        self.target = None
        self.connection_errors = []
        self._local = threading.local()

    @contextmanager
    def _com(self):
        import pythoncom
        if not getattr(self._local, "initialized", False):
            pythoncom.CoInitialize()
            self._local.initialized = True
        import win32com.client
        yield win32com.client

    def close(self):
        if getattr(self._local, "initialized", False):
            import pythoncom
            pythoncom.CoUninitialize()
            self._local.initialized = False

    def list_targets(self):
        found = []
        seen = set()
        self.connection_errors = []
        with self._com() as client:
            for progid in ("PowerPoint.Application", "KWPP.Application"):
                try:
                    app = client.gencache.EnsureDispatch(client.GetActiveObject(progid))
                    for index in range(1, app.Presentations.Count + 1):
                        presentation = app.Presentations.Item(index)
                        try:
                            window = presentation.SlideShowWindow
                            int(window.View.Slide.SlideIndex)
                            path = str(presentation.FullName)
                            if path.casefold() not in seen:
                                found.append(PresentationTarget(progid, path, str(presentation.Name)))
                                seen.add(path.casefold())
                        except Exception:
                            continue
                except Exception as exc:
                    self.connection_errors.append(f"{progid}: {exc}")
                    # An absent application or absent slide show is normal.
                    continue
        return found

    def select(self, target):
        self.target = target

    def _window(self, client):
        if self.target is None:
            raise RuntimeError("尚未连接 PPT。请先开始放映，再点击“连接 PPT”。")
        try:
            app = client.gencache.EnsureDispatch(client.GetActiveObject(self.target.progid))
            for index in range(1, app.Presentations.Count + 1):
                presentation = app.Presentations.Item(index)
                if str(presentation.FullName) == self.target.path:
                    window = presentation.SlideShowWindow
                    return window
        except Exception as exc:
            if is_busy_error(exc):
                raise PresentationBusy("PPT 正忙，正在等待切页") from exc
            raise RuntimeError("无法访问已连接的放映，请重新连接 PPT。") from exc
        raise RuntimeError("已连接的放映已经关闭，请重新开始放映并连接。")

    def send_page(self, direction):
        if direction not in ("next", "previous"):
            raise ValueError("Unknown page direction")
        try:
            with self._com() as client:
                window = self._window(client)
                view = window.View
                before = int(view.Slide.SlideIndex)
                count = int(window.Presentation.Slides.Count)
                desired = max(1, min(count, before + (1 if direction == "next" else -1)))
                if desired == before:
                    return PageResult(False, "已在最后一页" if direction == "next" else "已在第一页", before, before)
                view.GotoSlide(desired)
                after = int(view.Slide.SlideIndex)
                deadline = time.monotonic() + 0.35
                while after != desired and time.monotonic() < deadline:
                    time.sleep(0.02)
                    after = int(view.Slide.SlideIndex)
                return PageResult(after == desired,
                                  f"已确认 PPT：{before} → {after} 页" if after == desired
                                  else "已请求翻页，但未确认页码变化", before, after)
        except RuntimeError:
            raise
        except Exception as exc:
            if is_busy_error(exc):
                raise PresentationBusy("PPT 正忙，正在等待切页") from exc
            raise RuntimeError(f"PPT 翻页失败，请确认处于放映状态：{exc}") from exc

    def export_current_slide(self, path: Path):
        """Extension point for the proposed gesture-triggered AI summary.

        Exports only the selected presentation's current slide. It does not
        capture the desktop/camera or send any data to an API.
        """
        with self._com() as client:
            window = self._window(client)
            path = path.resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            slide = window.View.Slide
            setup = window.Presentation.PageSetup
            height = max(1, round(1280 * float(setup.SlideHeight) / float(setup.SlideWidth)))
            slide.Export(str(path), "PNG", 1280, height)
            return {"presentation": self.target.name, "slide": int(slide.SlideIndex), "path": str(path)}
