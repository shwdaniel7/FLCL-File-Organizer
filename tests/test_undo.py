import os
import tempfile
import unittest

from src import organizer


RULES = {
    "Images": [".jpg"],
    "Documents": [".pdf"],
    "Others": [],
}

BASE_FILTERS = {
    "ignored_folders": [],
    "ignore_hidden": True,
    "min_size_kb": 0,
    "ignored_extensions": [],
    "ignored_patterns": [],
}


class UndoIsolatedAppDataTestCase(unittest.TestCase):
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

    def _write_file(self, path, content="x"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        return path


class UndoLastRunTests(UndoIsolatedAppDataTestCase):
    def _run_scan(self, monitored_dir, names):
        logs = []
        for name in names:
            self._write_file(os.path.join(monitored_dir, name))
        move_lists = organizer.build_preview(monitored_dir, RULES, BASE_FILTERS)
        self.assertEqual(len(move_lists), len(names))
        moves = organizer.run_initial_scan(monitored_dir, RULES, logs.append, BASE_FILTERS)
        self.assertEqual(len(moves), len(names))
        organizer._record_run(moves)
        return moves

    def test_full_undo_restores_and_pops_history(self):
        with tempfile.TemporaryDirectory() as monitored:
            moves = self._run_scan(monitored, ["a.jpg", "b.pdf"])
            logs = []
            result = organizer.undo_last_run(logs.append)
            self.assertTrue(result)
            original_first = os.path.join(monitored, "a.jpg")
            self.assertTrue(os.path.exists(original_first))
            self.assertTrue(os.path.exists(os.path.join(monitored, "b.pdf")))
            self.assertFalse(os.path.exists(moves[0]["destination"]))
            self.assertTrue(any("Restored" in line for line in logs))
            self.assertFalse(organizer.has_history())

    def test_undo_restores_in_reverse_order(self):
        with tempfile.TemporaryDirectory() as monitored:
            self._run_scan(monitored, ["a.jpg", "b.jpg", "c.jpg"])
            restored = []
            original = organizer.undo_last_run(lambda msg: restored.append(msg))
            self.assertTrue(original)
            basenames = [line.split("'")[1] for line in restored if "Restored" in line]
            self.assertEqual(basenames, ["c.jpg", "b.jpg", "a.jpg"])

    def test_empty_history_returns_false(self):
        logs = []
        result = organizer.undo_last_run(logs.append)
        self.assertFalse(result)
        self.assertIn("Nothing to undo.", logs)

    def test_missing_destination_is_skipped_and_run_removed(self):
        with tempfile.TemporaryDirectory() as monitored:
            moves = self._run_scan(monitored, ["a.jpg"])
            os.remove(moves[0]["destination"])
            logs = []
            result = organizer.undo_last_run(logs.append)
            self.assertFalse(result)
            self.assertTrue(any("UNDO SKIPPED" in line and "file not found" in line for line in logs))
            self.assertFalse(organizer.has_history())

    def test_occupied_original_keeps_move_in_history(self):
        with tempfile.TemporaryDirectory() as monitored:
            original = os.path.join(monitored, "a.jpg")
            moves = self._run_scan(monitored, ["a.jpg"])
            self._write_file(original, "new occupant")
            logs = []
            result = organizer.undo_last_run(logs.append)
            self.assertFalse(result)
            self.assertTrue(any("UNDO SKIPPED" in line and "already exists" in line for line in logs))
            self.assertTrue(organizer.has_history())
            with open(original, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "new occupant")

    def test_partial_restore_keeps_remaining_moves(self):
        with tempfile.TemporaryDirectory() as monitored:
            moves = self._run_scan(monitored, ["a.jpg", "b.pdf"])
            occupied = next(m for m in moves if m["category"] == "Images")
            self._write_file(occupied["original"], "new occupant")
            logs = []
            result = organizer.undo_last_run(logs.append)
            self.assertTrue(result)
            self.assertTrue(os.path.exists(os.path.join(monitored, "b.pdf")))
            self.assertTrue(organizer.has_history())
            last_run = organizer._load_history()[-1]
            self.assertEqual(len(last_run["moves"]), 1)
            self.assertEqual(last_run["moves"][0]["original"], occupied["original"])

    def test_original_parent_folder_is_recreated(self):
        with tempfile.TemporaryDirectory() as monitored:
            nested = os.path.join(monitored, "deep", "nested")
            self._write_file(os.path.join(nested, "x.jpg"))
            moves = organizer.run_initial_scan(monitored, RULES, lambda m: None, BASE_FILTERS, recursive=True)
            self.assertEqual(len(moves), 1)
            organizer._record_run(moves)
            result = organizer.undo_last_run(lambda m: None)
            self.assertTrue(result)
            restored = os.path.join(monitored, "deep", "nested", "x.jpg")
            self.assertTrue(os.path.exists(restored))


if __name__ == "__main__":
    unittest.main()