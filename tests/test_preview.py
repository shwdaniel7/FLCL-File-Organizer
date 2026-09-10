import os
import tempfile
import unittest

from src.organizer import build_preview, _iter_files


RULES = {
    "Images": [".jpg", ".png"],
    "Documents": [".pdf"],
    "Archives": [".zip", ".tar.gz"],
    "Others": [],
}

BASE_FILTERS = {
    "ignored_folders": [],
    "ignore_hidden": True,
    "min_size_kb": 0,
    "ignored_extensions": [],
    "ignored_patterns": [],
}


class PreviewHelpers(unittest.TestCase):
    def _make_filters(self, **overrides):
        filters = dict(BASE_FILTERS)
        filters.update(overrides)
        return filters

    def _make_files(self, temp_dir, *names, folder=None):
        target = os.path.join(temp_dir, folder) if folder else temp_dir
        os.makedirs(target, exist_ok=True)
        file_names = []
        for name in names:
            if isinstance(name, (list, tuple)):
                file_names.extend(name)
            else:
                file_names.append(name)
        for name in file_names:
            full = os.path.join(target, *name.split("/"))
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as handle:
                handle.write("x")


class BuildPreviewTests(PreviewHelpers):
    def test_files_mapped_to_categories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make_files(temp_dir, ["a.jpg", "b.pdf", "c.zip"])
            plan = build_preview(temp_dir, RULES, BASE_FILTERS)
            moves = [item for item in plan if item["status"] == "move"]
            self.assertEqual(len(moves), 3)
            by_name = {item["filename"]: item for item in moves}
            self.assertEqual(by_name["a.jpg"]["destination_folder"], "Images")
            self.assertEqual(by_name["b.pdf"]["destination_folder"], "Documents")
            self.assertEqual(by_name["c.zip"]["destination_folder"], "Archives")

    def test_unmatched_extension_goes_to_others_with_no_rule_flag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make_files(temp_dir, ["weird.xyz"])
            plan = build_preview(temp_dir, RULES, BASE_FILTERS)
            item = plan[0]
            self.assertEqual(item["status"], "move")
            self.assertEqual(item["destination_folder"], "Others")
            self.assertFalse(item["has_rule"])

    def test_no_extension_is_ignored(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make_files(temp_dir, ["README"])
            plan = build_preview(temp_dir, RULES, BASE_FILTERS)
            self.assertEqual(plan[0]["status"], "ignored")
            self.assertEqual(plan[0]["reason"], "No extension")

    def test_hidden_files_ignored_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make_files(temp_dir, [".hidden.jpg", "visible.jpg"])
            plan = build_preview(temp_dir, RULES, BASE_FILTERS)
            ignored = [item for item in plan if item["status"] == "ignored"]
            self.assertEqual([item["filename"] for item in ignored], [".hidden.jpg"])

    def test_hidden_files_included_when_disabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make_files(temp_dir, [".hidden.jpg"])
            filters = self._make_filters(ignore_hidden=False)
            plan = build_preview(temp_dir, RULES, filters)
            self.assertEqual(plan[0]["status"], "move")

    def test_ignored_extensions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make_files(temp_dir, ["keep.jpg", "skip.tmp"])
            filters = self._make_filters(ignored_extensions=[".tmp"])
            plan = build_preview(temp_dir, RULES, filters)
            ignored = [item for item in plan if item["status"] == "ignored"]
            self.assertEqual([item["filename"] for item in ignored], ["skip.tmp"])

    def test_ignored_patterns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make_files(temp_dir, ["normal.jpg", "cached.jpg"])
            filters = self._make_filters(ignored_patterns=["cached.*"])
            plan = build_preview(temp_dir, RULES, filters)
            ignored = [item for item in plan if item["status"] == "ignored"]
            self.assertEqual([item["filename"] for item in ignored], ["cached.jpg"])

    def test_minimum_size_filter(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make_files(temp_dir, ["small.jpg"])
            with open(os.path.join(temp_dir, "small.jpg"), "w", encoding="utf-8") as handle:
                handle.write("tiny")
            with open(os.path.join(temp_dir, "big.jpg"), "w", encoding="utf-8") as handle:
                handle.write("x" * (20 * 1024))
            filters = self._make_filters(min_size_kb=10)
            plan = build_preview(temp_dir, RULES, filters)
            ignored = [item for item in plan if item["status"] == "ignored"]
            self.assertEqual([item["filename"] for item in ignored], ["small.jpg"])

    def test_temp_prefix_files_skipped_entirely(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make_files(temp_dir, ["~tmpfile.jpg", "real.jpg"])
            plan = build_preview(temp_dir, RULES, BASE_FILTERS)
            self.assertEqual([item["filename"] for item in plan], ["real.jpg"])

    def test_plan_sorted_case_insensitive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make_files(temp_dir, ["Zebra.jpg", "apple.jpg", "Banana.jpg"])
            plan = build_preview(temp_dir, RULES, BASE_FILTERS)
            names = [item["filename"] for item in plan]
            self.assertEqual(names, ["apple.jpg", "Banana.jpg", "Zebra.jpg"])

    def test_destination_does_not_touch_disk(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make_files(temp_dir, ["photo.jpg"])
            build_preview(temp_dir, RULES, BASE_FILTERS)
            self.assertEqual(os.listdir(temp_dir), ["photo.jpg"])

    def test_recursive_only_flattens_other_subfolders(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make_files(temp_dir, "sub1/a.jpg")
            plan = build_preview(temp_dir, RULES, BASE_FILTERS, recursive=False)
            self.assertEqual(plan, [])
            plan = build_preview(temp_dir, RULES, BASE_FILTERS, recursive=True)
            self.assertEqual(len(plan), 1)
            relative = os.path.relpath(plan[0]["destination_path"], temp_dir)
            self.assertEqual(relative, os.path.join("Images", "a.jpg"))

    def test_files_already_in_category_folder_skipped_in_recursive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make_files(temp_dir, "Images/already.jpg")
            self._make_files(temp_dir, "sub/photo.jpg")
            plan = build_preview(temp_dir, RULES, BASE_FILTERS, recursive=True)
            names = [item["filename"] for item in plan]
            self.assertEqual(names, ["photo.jpg"])


class ChainedConflictTests(PreviewHelpers):
    def test_duplicate_names_in_subfolders_flag_second_as_rename(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make_files(temp_dir, "a/x.jpg")
            self._make_files(temp_dir, "b/x.jpg")
            plan = build_preview(temp_dir, RULES, BASE_FILTERS, recursive=True)
            moves = [item for item in plan if item["status"] == "move"]
            self.assertEqual(len(moves), 2)
            self.assertTrue(any(item["conflict"] for item in moves))
            non_conflict = [item for item in moves if not item["conflict"]]
            self.assertEqual(len(non_conflict), 1)
            conflict = [item for item in moves if item["conflict"]][0]
            self.assertTrue("(1)" in os.path.basename(conflict["destination_path"]))


class IterFilesTests(PreviewHelpers):
    def test_non_recursive_only_top_level_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make_files(temp_dir, "top.jpg", "nested/deep.jpg")
            files = list(_iter_files(temp_dir, RULES, BASE_FILTERS, recursive=False))
            self.assertEqual([name for name, _ in files], ["top.jpg"])

    def test_recursive_ignores_folders_by_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make_files(temp_dir, "Temp/temp.jpg", "Keep/ok.jpg")
            filters = self._make_filters(ignored_folders=["Temp"])
            files = list(_iter_files(temp_dir, RULES, filters, recursive=True))
            self.assertEqual([name for name, _ in files], ["ok.jpg"])

    def test_recursive_prunes_root_category_folders(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make_files(temp_dir, "Images/old.jpg", "sub/new.jpg")
            files = list(_iter_files(temp_dir, RULES, BASE_FILTERS, recursive=True))
            self.assertEqual([name for name, _ in files], ["new.jpg"])


if __name__ == "__main__":
    unittest.main()