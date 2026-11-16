import io
import json
from pathlib import Path
import threading
import time
import unittest
from urllib.error import HTTPError, URLError

from airpresent.summary import SummaryConfig, SummaryWorker, VisionClient, model_id
from airpresent.presentation import PresentationTarget


class SummaryTests(unittest.TestCase):
    def test_known_xingtu_display_names_use_catalog_ids(self):
        self.assertEqual(model_id("星图 按量付费", " Kimi-K3 "), "kimi-k3")
        self.assertEqual(model_id("星图 Token Plan", "Kimi-K2.6"), "kimi-k2.6")
        self.assertEqual(model_id("自定义兼容服务", "Other-Model"), "Other-Model")

    def test_structured_errors_are_shown_with_secrets_removed(self):
        body = {"error": {"message": "unsupported image: secret-key-value sk-abcdef Bearer token123 data:image/png;base64,YWJj"}}
        def fail(*args, **kwargs):
            raise HTTPError("https://example", 400, "bad", {}, io.BytesIO(json.dumps(body).encode()))
        with self.assertRaises(RuntimeError) as caught:
            VisionClient(fail).summarize(SummaryConfig(), "secret-key-value", b"png")
        text = str(caught.exception)
        self.assertIn("unsupported image", text)
        for secret in ("secret-key-value", "sk-abcdef", "token123", "YWJj"):
            self.assertNotIn(secret, text)

    def test_unstructured_http_body_is_not_displayed(self):
        def fail(*args, **kwargs):
            raise HTTPError("https://example", 400, "bad", {}, io.BytesIO(b'<html>private</html>'))
        with self.assertRaises(RuntimeError) as caught:
            VisionClient(fail).summarize(SummaryConfig(), "test", b"png")
        self.assertNotIn("private", str(caught.exception))

    def test_xingtu_routes_by_billing_plan(self):
        for provider, path in (("星图 Token Plan", "token/v1"), ("星图 按量付费", "v1")):
            captured = []
            def open_fake(req, timeout):
                captured.append(req)
                return io.BytesIO(b'{"choices":[{"message":{"content":"ok"}}]}')
            VisionClient(open_fake).summarize(SummaryConfig(provider, "test-vision-id"), "test-only", b"png")
            self.assertEqual(captured[0].full_url, f"https://ai.csdn.net/api/model/{path}/chat/completions")
            self.assertNotIn("thinking", json.loads(captured[0].data))

    def test_custom_base_and_full_url_are_equivalent(self):
        for url in ("https://example.com/v1", "https://example.com/v1/", "https://example.com/v1/chat/completions"):
            config = SummaryConfig("自定义兼容服务", "vision", url)
            config.validate()
            self.assertEqual(config.endpoint, "https://example.com/v1/chat/completions")

    def test_custom_transport_has_no_vendor_options(self):
        captured = []
        def open_fake(req, timeout):
            captured.append(req)
            return io.BytesIO(b'{"choices":[{"message":{"content":"ok"}}]}')
        VisionClient(open_fake).summarize(SummaryConfig("自定义兼容服务", "vision", "https://example.com/v1"), "test", b"png")
        self.assertNotIn("thinking", json.loads(captured[0].data))
        self.assertNotIn("reasoning_effort", json.loads(captured[0].data))

    def test_custom_url_rejects_credentials_and_insecure_urls(self):
        for url in ("", "http://example.com/v1", "https://key@example.com/v1", "https://example.com/v1?key=x", "https://example.com/#key", "https://example.com/bad path"):
            with self.assertRaises(ValueError):
                SummaryConfig("自定义兼容服务", "vision", url).validate()

    def test_cache_config_includes_endpoint(self):
        self.assertNotEqual(SummaryConfig("自定义兼容服务", "vision", "https://a.com/v1"),
                            SummaryConfig("自定义兼容服务", "vision", "https://b.com/v1"))

    def test_invalid_config_types_are_reported(self):
        for config in (SummaryConfig([], "x"), SummaryConfig("智谱", 12), SummaryConfig("other", "x")):
            with self.assertRaises(ValueError):
                config.validate()

    def test_visual_payload_for_each_provider(self):
        for provider, model in (("智谱", "glm-4.6v-flash"), ("Kimi", "kimi-k3.1-pro")):
            captured = []
            def open_fake(req, timeout):
                captured.append((req, timeout))
                return io.BytesIO(json.dumps({"choices": [{"message": {"content": "主题与要点"}}]}).encode())
            text = VisionClient(open_fake).summarize(SummaryConfig(provider, model), "test-only-key", b"png")
            self.assertEqual(text, "主题与要点")
            req, timeout = captured[0]
            payload = json.loads(req.data)
            self.assertTrue(req.full_url.startswith("https://"))
            self.assertEqual(timeout, 60)
            self.assertEqual(payload["messages"][0]["content"][1]["image_url"]["url"], "data:image/png;base64,cG5n")
            self.assertNotIn("test-only-key", req.data.decode())

    def test_errors_are_safe_and_not_retried(self):
        for failure in (HTTPError("https://example", 401, "secret", {}, None), URLError("secret")):
            calls = []
            def fail(*args, **kwargs):
                calls.append(1)
                raise failure
            with self.assertRaises(RuntimeError) as raised:
                VisionClient(fail).summarize(SummaryConfig(), "secret", b"png")
            self.assertNotIn("secret", str(raised.exception))
            self.assertEqual(len(calls), 1)

    def test_invalid_response_and_missing_key(self):
        for raw in (b"{}", b"broken", b'{"choices":[]}'):
            with self.assertRaises(RuntimeError):
                VisionClient(lambda *a, **k: io.BytesIO(raw)).summarize(SummaryConfig(), "test", b"png")
        with self.assertRaises(ValueError):
            VisionClient().summarize(SummaryConfig(), "", b"png")

    def make_worker(self):
        self.images = [b"image1"]
        self.exported = []
        images, exported = self.images, self.exported
        class Service:
            def select(self, target):
                self.target = target
            def export_current_slide(self, path):
                path.write_bytes(images[0])
                exported.append(path)
                return {"presentation": self.target.name, "slide": 2, "path": str(path)}
            def close(self):
                pass
        self.calls = []
        calls = self.calls
        class Client:
            def summarize(self, config, key, png):
                calls.append(png)
                return "摘要"
        return SummaryWorker(Service, Client())

    def drain(self, worker):
        events = []
        deadline = time.monotonic() + 3
        while worker.busy and time.monotonic() < deadline:
            item = worker.poll()
            if item:
                events.append(item)
            time.sleep(.005)
        self.assertFalse(worker.busy)
        return events

    def test_cache_tracks_image_model_and_source_and_deletes_png(self):
        worker = self.make_worker()
        target = PresentationTarget("ppt", "fixture", "fixture.pptx")
        for config in (SummaryConfig(), SummaryConfig(), SummaryConfig("智谱", "other")):
            self.assertTrue(worker.submit(target, config, "test"))
            self.drain(worker)
        self.assertEqual(len(self.calls), 2)
        self.images[0] = b"changed"
        worker.submit(target, SummaryConfig(), "test")
        self.drain(worker)
        self.assertEqual(len(self.calls), 3)
        self.assertTrue(all(not p.exists() for p in self.exported))

    def test_preview_never_calls_model_and_busy_does_not_queue(self):
        worker = self.make_worker()
        target = PresentationTarget("ppt", "fixture", "fixture.pptx")
        worker.submit(target, SummaryConfig(), "", preview=True)
        self.assertFalse(worker.submit(target, SummaryConfig(), "", preview=True))
        events = self.drain(worker)
        self.assertEqual(self.calls, [])
        self.assertIn("preview", [e[0] for e in events])

    def test_cancel_before_export_finishes_never_sends(self):
        worker = self.make_worker()
        original = worker.factory
        gate = threading.Event()
        def factory():
            gate.wait(2)
            return original()
        worker.factory = factory
        worker.submit(PresentationTarget("ppt", "fixture", "fixture.pptx"), SummaryConfig(), "test")
        worker.cancel()
        gate.set()
        self.drain(worker)
        self.assertEqual(self.calls, [])
