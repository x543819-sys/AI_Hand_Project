from queue import Empty
import threading
import time
import unittest

from airpresent.page_output import AsyncPageOutput
from airpresent.presentation import PageResult, PresentationBusy, is_busy_error


class AsyncOutputTests(unittest.TestCase):
    def await_result(self, worker):
        deadline = time.monotonic() + 2
        item = worker.poll()
        while item is None and time.monotonic() < deadline:
            time.sleep(0.005)
            item = worker.poll()
        self.assertIsNotNone(item)
        return item

    def test_slow_output_does_not_block_submit_and_drops_extra_requests(self):
        entered, release = threading.Event(), threading.Event()
        class Service:
            def select(self, target):
                pass
            def send_page(self, direction):
                entered.set()
                release.wait(1)
                return PageResult(True, "changed", 1, 2)
            def close(self):
                pass
        worker = AsyncPageOutput(Service)
        self.assertTrue(worker.submit("target", "next"))
        self.assertTrue(entered.wait(1))
        self.assertTrue(worker.busy)
        self.assertFalse(worker.submit("target", "next"))
        release.set()
        request, result, error = self.await_result(worker)
        self.assertIsNone(error)
        self.assertTrue(result.changed)
        self.assertFalse(worker.busy)
        worker.close()

    def test_temporary_office_busy_retries_without_new_request(self):
        calls = []
        class Service:
            def select(self, target):
                pass
            def send_page(self, direction):
                calls.append(direction)
                if len(calls) < 3:
                    raise PresentationBusy("busy")
                return PageResult(True, "changed", 1, 2)
            def close(self):
                pass
        worker = AsyncPageOutput(Service, retry_seconds=1)
        worker.submit("target", "next")
        _, result, error = self.await_result(worker)
        self.assertIsNone(error)
        self.assertTrue(result.changed)
        self.assertEqual(calls, ["next"] * 3)
        worker.close()

    def test_factory_error_is_reported_instead_of_sticking_busy(self):
        def fail():
            raise RuntimeError("factory failed")
        worker = AsyncPageOutput(fail)
        worker.submit("target", "next")
        _, result, error = self.await_result(worker)
        self.assertIsNone(result)
        self.assertIn("factory failed", str(error))
        self.assertFalse(worker.busy)
        worker.close()

    def test_office_retryable_hresult_detection(self):
        self.assertTrue(is_busy_error(Exception(-2147418111, "rejected")))
        self.assertTrue(is_busy_error(Exception(-2147417846, "retry later")))
        self.assertFalse(is_busy_error(Exception(-1, "other")))


if __name__ == "__main__":
    unittest.main()
