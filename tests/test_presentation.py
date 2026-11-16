"""Page-number confirmation and target selection, without launching Office."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from airpresent.presentation import PresentationOutput, PresentationTarget


class Collection:
    def __init__(self, items):
        self.items = items

    @property
    def Count(self):
        return len(self.items)

    def Item(self, index):
        return self.items[index - 1]


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.slide = SimpleNamespace(SlideIndex=1)
        self.view = SimpleNamespace(Slide=self.slide, GotoSlide=lambda value: setattr(self.slide, "SlideIndex", value))
        self.doc = SimpleNamespace(Name="fixture.pptx", FullName="C:/fixture.pptx", Slides=Collection([1, 2, 3]))
        self.doc.SlideShowWindow = SimpleNamespace(View=self.view, Presentation=self.doc)
        self.app = SimpleNamespace(Presentations=Collection([self.doc]))
        self.output = PresentationOutput()

        @contextmanager
        def fake_com():
            yield SimpleNamespace(GetActiveObject=lambda progid: self.app,
                                  gencache=SimpleNamespace(EnsureDispatch=lambda value: value))
        self.output._com = fake_com
        self.target = PresentationTarget("PowerPoint.Application", self.doc.FullName, self.doc.Name)

    def test_aliases_do_not_duplicate_a_target(self):
        targets = self.output.list_targets()
        self.assertEqual(targets, [self.target])

    def test_confirmed_page_change_and_boundary(self):
        self.output.select(self.target)
        result = self.output.send_page("next")
        self.assertTrue(result.changed)
        self.assertEqual((result.before, result.after), (1, 2))
        self.output.send_page("previous")
        self.assertFalse(self.output.send_page("previous").changed)

    def test_unchanged_page_is_not_reported_as_success(self):
        self.output.select(self.target)
        self.view.GotoSlide = lambda value: None
        with patch("airpresent.presentation.time.monotonic", side_effect=[1, 2]):
            result = self.output.send_page("next")
        self.assertFalse(result.changed)
        self.assertEqual(result.after, 1)
        self.assertIn("未确认", result.message)

    def test_no_target_is_an_explicit_error(self):
        with self.assertRaisesRegex(RuntimeError, "尚未连接"):
            self.output.send_page("next")

    def test_closed_target_is_an_explicit_error(self):
        self.output.select(self.target)
        self.app.Presentations.items.clear()
        with self.assertRaisesRegex(RuntimeError, "已经关闭"):
            self.output.send_page("next")


if __name__ == "__main__":
    unittest.main()
