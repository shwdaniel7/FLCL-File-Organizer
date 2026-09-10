import os
import tempfile
import unittest
from unittest import mock

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


def _write_file(path, content="content"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


class UniqueDestinationPathTests(unittest.TestCase):
    def test_available_path_unchanged(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = organizer._unique_destination_path(os.path.join(temp_dir, "a.jpg"))
            self.assertEqual(result, os.path.join(temp_dir, "a.jpg"))

    def test_existing_file_gets_suffix(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _write_file(os.path.join(temp_dir, "a.jpg"))
            result = organizer._unique_destination_path(os.path.join(temp_dir, "a.jpg"))
            self.assertEqual(os.path.basename(result), "a (1).jpg")

    def test_multiple_existing_conflicts_increment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _write_file(os.path.join(temp_dir, "a.jpg"))
            _write_file(os.path.join(temp_dir, "a (1).jpg"))
            result = organizer._unique_destination_path(os.path.join(temp_dir, "a.jpg"))
            self.assertEqual(os.path.basename(result), "a (2).jpg")

    def test_compound_extension_suffix_inserted_before_last_dot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _write_file(os.path.join(temp_dir, "b.tar.gz"))
            result = organizer._unique_destination_path(os.path.join(temp_dir, "b.tar.gz"))
            self.assertEqual(os.path.basename(result), "b.tar (1).gz")

    def test_reserved_sets_avoid_plan_collisions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            planned = os.path.join(temp_dir, "x.jpg")
            reserved = {planned}
            result = organizer._unique_destination_path(planned, reserved=reserved)
            self.assertEqual(os.path.basename(result), "x (1).jpg")

    def test_reserved_and_occupied_skip_to_next(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = os.path.join(temp_dir, "x.jpg")
            _write_file(base)
            reserved = {base, os.path.join(temp_dir, "x (1).jpg")}
            result = organizer._unique_destination_path(base, reserved=reserved)
            self.assertEqual(os.path.basename(result), "x (2).jpg")


class SafeMoveTests(unittest.TestCase):
    def test_same_directory_is_rename(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            src = _write_file(os.path.join(temp_dir, "a.txt"), "hello")
            dst = os.path.join(temp_dir, "b.txt")
            organizer._safe_move(src, dst)
            self.assertFalse(os.path.exists(src))
            self.assertTrue(os.path.exists(dst))
            with open(dst, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "hello")

    def test_cross_directory_move_preserves_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            src = _write_file(os.path.join(temp_dir, "a.txt"), "payload")
            dst = os.path.join(temp_dir, "sub", "nested", "a.txt")
            organizer._safe_move(src, dst)
            self.assertFalse(os.path.exists(src))
            self.assertTrue(os.path.exists(dst))
            with open(dst, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "payload")

    def test_no_partial_files_left_behind(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            src = _write_file(os.path.join(temp_dir, "a.txt"))
            dst_dir = os.path.join(temp_dir, "sub")
            organizer._safe_move(src, os.path.join(dst_dir, "a.txt"))
            leftovers = [name for name in os.listdir(dst_dir) if ".partial" in name]
            self.assertEqual(leftovers, [])


class ProcessAndMoveFileTests(unittest.TestCase):
    def test_moves_file_to_category_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            src = _write_file(os.path.join(temp_dir, "photo.jpg"))
            logs = []
            move = organizer._process_and_move_file(src, temp_dir, RULES, logs.append, BASE_FILTERS)
            self.assertIsNotNone(move)
            self.assertEqual(move["category"], "Images")
            expected = os.path.join(temp_dir, "Images", "photo.jpg")
            self.assertEqual(move["destination"], expected)
            self.assertTrue(os.path.exists(expected))
            self.assertFalse(os.path.exists(src))
            self.assertTrue(any("Folder created" in line for line in logs))
            self.assertTrue(any("File moved" in line for line in logs))

    def test_unmatched_extension_uses_others(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            src = _write_file(os.path.join(temp_dir, "file.xyz"))
            move = organizer._process_and_move_file(src, temp_dir, RULES, lambda m: None, BASE_FILTERS)
            self.assertEqual(move["category"], "Others")

    def test_ignored_file_returns_none(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            src = _write_file(os.path.join(temp_dir, "skip.tmp"))
            filters = dict(BASE_FILTERS, ignored_extensions=[".tmp"])
            result = organizer._process_and_move_file(src, temp_dir, RULES, lambda m: None, filters)
            self.assertIsNone(result)
            self.assertTrue(os.path.exists(src))

    def test_missing_source_returns_none(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = os.path.join(temp_dir, "ghost.jpg")
            result = organizer._process_and_move_file(missing, temp_dir, RULES, lambda m: None)
            self.assertIsNone(result)

    def test_no_extension_returns_none(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            src = _write_file(os.path.join(temp_dir, "README"))
            result = organizer._process_and_move_file(src, temp_dir, RULES, lambda m: None)
            self.assertIsNone(result)

    def test_file_already_in_destination_folder_is_noop(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            images = os.path.join(temp_dir, "Images")
            src = _write_file(os.path.join(images, "photo.jpg"))
            result = organizer._process_and_move_file(src, temp_dir, RULES, lambda m: None)
            self.assertIsNone(result)
            self.assertTrue(os.path.exists(src))

    def test_conflicting_destination_gets_unique_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _write_file(os.path.join(temp_dir, "Images", "photo.jpg"))
            src = _write_file(os.path.join(temp_dir, "photo.jpg"))
            move = organizer._process_and_move_file(src, temp_dir, RULES, lambda m: None, BASE_FILTERS)
            self.assertEqual(os.path.basename(move["destination"]), "photo (1).jpg")

    def test_error_path_records_error_object(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            src = os.path.join(temp_dir, "locked.jpg")
            _write_file(src)
            with mock.patch.object(organizer, "_safe_move", side_effect=OSError("disk full")):
                move = organizer._process_and_move_file(src, temp_dir, RULES, lambda m: None, BASE_FILTERS)
            self.assertIn("error", move)
            self.assertIn("disk full", move["error"])


class RunInitialScanTests(unittest.TestCase):
    def test_organizes_existing_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _write_file(os.path.join(temp_dir, "a.jpg"))
            _write_file(os.path.join(temp_dir, "b.pdf"))
            _write_file(os.path.join(temp_dir, "c.jpg"))
            with mock.patch.object(organizer, "_wait_for_stable_file", return_value=True):
                moves = organizer.run_initial_scan(temp_dir, RULES, lambda m: None, BASE_FILTERS)
            self.assertEqual(len(moves), 3)
            self.assertTrue(os.path.exists(os.path.join(temp_dir, "Images", "a.jpg")))
            self.assertTrue(os.path.exists(os.path.join(temp_dir, "Images", "c.jpg")))
            self.assertTrue(os.path.exists(os.path.join(temp_dir, "Documents", "b.pdf")))

    def test_unstable_files_are_skipped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _write_file(os.path.join(temp_dir, "a.jpg"))
            logs = []
            with mock.patch.object(organizer, "_wait_for_stable_file", return_value=False):
                moves = organizer.run_initial_scan(temp_dir, RULES, logs.append, BASE_FILTERS)
            self.assertEqual(moves, [])
            self.assertTrue(os.path.exists(os.path.join(temp_dir, "a.jpg")))
            self.assertTrue(any("SKIPPED" in line and "still changing" in line for line in logs))


if __name__ == "__main__":
    unittest.main()