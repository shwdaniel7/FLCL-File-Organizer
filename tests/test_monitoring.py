import os
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

from src import organizer
from src.organizer import OrganizerEventHandler


RULES = {"Images": [".jpg"], "Others": []}
BASE_FILTERS = {
    "ignored_folders": [],
    "ignore_hidden": True,
    "min_size_kb": 0,
    "ignored_extensions": [],
    "ignored_patterns": [],
}


class OrganizerEventHandlerIsolatedTestCase(unittest.TestCase):
    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self._localappdata = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self._tempdir.name

    def tearDown(self):
        if self._localappdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._localappdata
        self._tempdir.cleanup()


class OnCreatedTests(OrganizerEventHandlerIsolatedTestCase):
    def _event(self, src_path, is_directory=False):
        return SimpleNamespace(src_path=src_path, is_directory=is_directory)

    def _build(self, monitored_dir, filters=None):
        logs = []
        handler = OrganizerEventHandler(monitored_dir, RULES, logs.append, filters or BASE_FILTERS, pause_event=None)
        return handler, logs

    def test_ignores_directory_events(self):
        with tempfile.TemporaryDirectory() as monitored:
            handler, logs = self._build(monitored)
            event = self._event(os.path.join(monitored, "Images"), is_directory=True)
            with mock.patch.object(organizer, "_wait_for_stable_file", return_value=True) as stable:
                handler.on_created(event)
            stable.assert_not_called()
            self.assertEqual(logs, [])

    def test_file_created_gets_moved(self):
        with tempfile.TemporaryDirectory() as monitored:
            src = os.path.join(monitored, "photo.jpg")
            with open(src, "w", encoding="utf-8") as handle:
                handle.write("x")
            handler, logs = self._build(monitored)
            event = self._event(src)
            with mock.patch("src.organizer._wait_for_stable_file", return_value=True):
                handler.on_created(event)
            self.assertTrue(os.path.exists(os.path.join(monitored, "Images", "photo.jpg")))
            self.assertFalse(os.path.exists(src))
            self.assertTrue(any("File moved" in line for line in logs))

    def test_unstable_file_logs_error_and_records(self):
        with tempfile.TemporaryDirectory() as monitored:
            src = os.path.join(monitored, "photo.jpg")
            with open(src, "w", encoding="utf-8") as handle:
                handle.write("x")
            handler, logs = self._build(monitored)
            event = self._event(src)
            with mock.patch("src.organizer._wait_for_stable_file", return_value=False):
                handler.on_created(event)
            self.assertTrue(any("Timed out waiting" in line for line in logs))
            self.assertTrue(any("ERROR" in line for line in logs))
            history = organizer._load_history()
            self.assertEqual(len(history[0]["errors"]), 1)

    def test_pause_event_blocks_then_continues(self):
        import threading
        with tempfile.TemporaryDirectory() as monitored:
            src = os.path.join(monitored, "photo.jpg")
            with open(src, "w", encoding="utf-8") as handle:
                handle.write("x")
            pause_event = threading.Event()
            pause_event.set()
            handler, logs = self._build(monitored)
            event = self._event(src)

            def _clear_after(frame):
                threading.Timer(0.3, pause_event.clear).start()
                return True

            with mock.patch("src.organizer._wait_for_stable_file", side_effect=_clear_after):
                handler.on_created(event)
            self.assertTrue(os.path.exists(os.path.join(monitored, "Images", "photo.jpg")))


if __name__ == "__main__":
    unittest.main()