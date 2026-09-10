import json
import os
import tempfile
import unittest

from src import organizer


class HistoryIsolatedTestCase(unittest.TestCase):
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

    def _move(self, name="a", error=None):
        entry = {
            "original": os.path.join("C:", "origin", f"{name}.txt"),
            "destination": os.path.join("C:", "dest", f"{name}.txt"),
            "category": "Doc",
            "timestamp": "2026-01-01T00:00:00+00:00",
        }
        if error:
            entry["error"] = error
        return entry


class LoadSaveHistoryTests(HistoryIsolatedTestCase):
    def test_missing_file_returns_empty(self):
        self.assertEqual(organizer._load_history(), [])

    def test_save_and_load_round_trip(self):
        history = [{"timestamp": "t", "moves": [], "errors": []}]
        organizer._save_history(history)
        self.assertEqual(organizer._load_history(), history)

    def test_corrupt_file_backed_up_and_returns_empty(self):
        path = organizer.history_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{ not json")
        self.assertEqual(organizer._load_history(), [])
        leftovers = os.listdir(os.path.dirname(path))
        self.assertTrue(any("corrupt" in name for name in leftovers))

    def test_non_list_content_backed_up(self):
        path = organizer.history_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"not": "a list"}, handle)
        self.assertEqual(organizer._load_history(), [])

    def test_save_caps_at_max_runs(self):
        runs = [{"timestamp": str(i), "moves": [], "errors": []} for i in range(500)]
        organizer._save_history(runs)
        loaded = organizer._load_history()
        self.assertEqual(len(loaded), organizer.MAX_HISTORY_RUNS)
        self.assertEqual(loaded[-1]["timestamp"], "499")

    def test_no_tmp_leftovers(self):
        organizer._save_history([{"timestamp": "t", "moves": [], "errors": []}])
        leftovers = [name for name in os.listdir(os.path.dirname(organizer.history_path())) if name.endswith(".tmp")]
        self.assertEqual(leftovers, [])


class RecordRunTests(HistoryIsolatedTestCase):
    def test_record_split_moves_and_errors(self):
        organizer._record_run([
            self._move(name="ok"),
            self._move(name="bad", error="boom"),
        ])
        history = organizer._load_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(len(history[0]["moves"]), 1)
        self.assertEqual(history[0]["moves"][0]["destination"].endswith("ok.txt"), True)
        self.assertEqual(history[0]["errors"], ["boom"])

    def test_record_ignores_empty_moves(self):
        organizer._record_run([])
        self.assertEqual(organizer._load_history(), [])

    def test_record_ignores_non_dict_entries(self):
        organizer._record_run([None, "str", 5])
        self.assertEqual(organizer._load_history(), [])

    def test_has_history_flips(self):
        self.assertFalse(organizer.has_history())
        organizer._record_run([self._move(name="x")])
        self.assertTrue(organizer.has_history())


class AppendToLastRunTests(HistoryIsolatedTestCase):
    def test_first_move_creates_run(self):
        organizer._append_to_last_run(self._move(name="first"))
        history = organizer._load_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(len(history[0]["moves"]), 1)

    def test_subsequent_moves_append_to_same_run(self):
        organizer._append_to_last_run(self._move(name="a"))
        organizer._append_to_last_run(self._move(name="b"))
        organizer._append_to_last_run(self._move(name="c", error="oops"))
        history = organizer._load_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(len(history[0]["moves"]), 2)
        self.assertEqual(history[0]["errors"], ["oops"])

    def test_non_dict_move_is_dropped(self):
        organizer._append_to_last_run(self._move(name="a"))
        organizer._append_to_last_run("garbage")
        history = organizer._load_history()
        self.assertEqual(len(history[0]["moves"]), 1)


if __name__ == "__main__":
    unittest.main()