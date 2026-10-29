import unittest

from src import organizer
from src.ui.pages.activity import log_kind


class NormalizeExtensionTests(unittest.TestCase):
    def test_adds_dot_and_lowercases(self):
        self.assertEqual(organizer.normalize_extension("PNG"), ".png")
        self.assertEqual(organizer.normalize_extension("  .Tar.GZ "), ".tar.gz")

    def test_rejects_invalid_input(self):
        for bad in ("", "   ", ".", "..", ".my ext", ".a/b", "*.png", None):
            with self.subTest(value=bad):
                self.assertIsNone(organizer.normalize_extension(bad))


class CategoryNameTests(unittest.TestCase):
    def test_valid_name(self):
        self.assertIsNone(organizer.category_name_error("Images", ["Docs"]))

    def test_rejects_names_windows_cannot_create(self):
        for bad in ("", "  ", "a/b", "a\\b", "what?", "..", "trailing.", "CON", "com1", "nul.txt"):
            with self.subTest(name=bad):
                self.assertIsNotNone(organizer.category_name_error(bad))

    def test_rejects_case_insensitive_duplicates(self):
        self.assertIsNotNone(organizer.category_name_error("images", ["Images"]))


class DefaultPreferencesTests(unittest.TestCase):
    def test_new_preferences_have_defaults(self):
        preferences = organizer._normalize_settings({"rules": {}})["preferences"]
        self.assertEqual(preferences["theme"], "FLCL")
        self.assertFalse(preferences["reduce_motion"])
        self.assertFalse(preferences["sidebar_collapsed"])


class LogKindTests(unittest.TestCase):
    def test_classifies_organizer_messages(self):
        self.assertEqual(log_kind("File moved: 'a.pdf' -> 'a.pdf' in 'Docs'"), "moved")
        self.assertEqual(log_kind("Restored: 'a.pdf'"), "moved")
        self.assertEqual(log_kind("ERROR organizing a.pdf: denied"), "error")
        self.assertEqual(log_kind("SKIPPED: 'a.iso' is still changing; waiting timed out."), "warn")
        self.assertEqual(log_kind("Real-time monitoring started. Waiting for new files..."), "accent")
        self.assertEqual(log_kind("New file detected: a.pdf"), "info")


if __name__ == "__main__":
    unittest.main()
