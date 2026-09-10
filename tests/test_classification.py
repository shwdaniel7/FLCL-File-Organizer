import os
import tempfile
import unittest

from src.organizer import _get_file_extension, _classify_file


RULES = {
    "Images": [".jpg", ".jpeg", ".png"],
    "Documents": [".pdf", ".txt"],
    "Archives": [".zip", ".rar", ".tar.gz"],
}


class GetFileExtensionTests(unittest.TestCase):
    def test_simple_extension(self):
        self.assertEqual(_get_file_extension("photo.jpg", RULES), ".jpg")

    def test_unknown_extension_falls_back_to_splitext(self):
        self.assertEqual(_get_file_extension("weird.xyz", RULES), ".xyz")

    def test_compound_extension_wins_over_single(self):
        self.assertEqual(_get_file_extension("archive.tar.gz", RULES), ".tar.gz")

    def test_longest_matching_extension_selected(self):
        rules = {"A": [".g"], "B": [".gz", ".tar.gz"]}
        self.assertEqual(_get_file_extension("bundle.tar.gz", rules), ".tar.gz")

    def test_case_insensitive(self):
        self.assertEqual(_get_file_extension("REPORT.PDF", RULES), ".pdf")
        self.assertEqual(_get_file_extension("Photo.JPG", RULES), ".jpg")

    def test_no_extension(self):
        self.assertEqual(_get_file_extension("README", RULES), "")

    def test_compound_suffix_case_insensitive(self):
        self.assertEqual(_get_file_extension("Bundle.TAR.GZ", RULES), ".tar.gz")

    def test_dotfile_without_extension(self):
        self.assertEqual(_get_file_extension(".env", RULES), "")


class ClassifyFileTests(unittest.TestCase):
    def test_matching_rule_returns_folder_and_flag(self):
        folder, extension, has_rule = _classify_file("photo.jpg", RULES)
        self.assertEqual(folder, "Images")
        self.assertEqual(extension, ".jpg")
        self.assertTrue(has_rule)

    def test_compound_rule_match(self):
        folder, extension, has_rule = _classify_file("bundle.tar.gz", RULES)
        self.assertEqual(folder, "Archives")
        self.assertEqual(extension, ".tar.gz")
        self.assertTrue(has_rule)

    def test_unmatched_extension_goes_to_others(self):
        folder, extension, has_rule = _classify_file("file.xyz", RULES)
        self.assertEqual(folder, "Others")
        self.assertEqual(extension, ".xyz")
        self.assertFalse(has_rule)

    def test_no_extension(self):
        folder, extension, has_rule = _classify_file("README", RULES)
        self.assertIsNone(folder)
        self.assertEqual(extension, "")
        self.assertFalse(has_rule)

    def test_empty_rules_goes_to_others(self):
        folder, extension, has_rule = _classify_file("file.txt", {})
        self.assertEqual(folder, "Others")
        self.assertFalse(has_rule)

    def test_multi_extension_rule(self):
        folder, _, _ = _classify_file("notes.txt", RULES)
        self.assertEqual(folder, "Documents")


if __name__ == "__main__":
    unittest.main()