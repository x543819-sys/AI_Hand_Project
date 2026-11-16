"""One asynchronous page request at a time, with bounded Office-busy retries."""

from dataclasses import dataclass
from queue import Queue, Empty
import threading
import time

from .presentation import PresentationOutput, PresentationBusy


@dataclass(frozen=True)
class PageRequest:
    target: object
    direction: str
    manual: bool


class AsyncPageOutput:
    def __init__(self, service_factory=PresentationOutput, retry_seconds=1.6):
        self.service_factory = service_factory
        self.retry_seconds = retry_seconds
        self.events = Queue()
        self.stop = threading.Event()
        self.thread = None
        self.busy = False

    def submit(self, target, direction, manual=False):
        if self.busy or self.stop.is_set():
            return False
        request = PageRequest(target, direction, manual)
        self.busy = True
        self.thread = threading.Thread(target=self._send, args=(request,), name="ppt-output", daemon=True)
        self.thread.start()
        return True

    def _send(self, request):
        service = None
        result = error = None
        try:
            service = self.service_factory()
            service.select(request.target)
            deadline = time.monotonic() + self.retry_seconds
            while not self.stop.is_set():
                try:
                    result = service.send_page(request.direction)
                    break
                except PresentationBusy as exc:
                    if time.monotonic() >= deadline:
                        error = exc
                        break
                    self.stop.wait(0.08)
        except Exception as exc:
            error = exc
        finally:
            try:
                if service is not None:
                    service.close()
            except Exception as exc:
                if error is None:
                    error = exc
            finally:
                self.events.put((request, result, error))

    def poll(self):
        try:
            item = self.events.get_nowait()
        except Empty:
            return None
        self.busy = False
        return item

    def close(self):
        self.stop.set()
