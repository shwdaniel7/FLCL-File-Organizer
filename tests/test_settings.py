import json
import os
import tempfile
import unittest
from unittest import mock

from src import organizer


class IsolateAppDataMixin(unittest.TestCase):
    """Point LOCALAPPDATA at a fresh temp dir per test."""

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


class NormalizeSettingsTests(unittest.TestCase):
    def test_legacy_flat_rules_normalized(self):
        settings = organizer._normalize_settings({"Images": [".jpg"], "Docs": [".pdf"]})
        self.assertEqual(settings["rules"], {"Images": [".jpg"], "Docs": [".pdf"]})
        self.assertEqual(settings["filters"]["ignore_hidden"], True)
        self.assertEqual(settings["preferences"]["notify"], True)

    def test_structured_settings_preserved(self):
        raw = {
            "rules": {"A": [".a"]},
            "filters": {"min_size_kb": 5, "ignored_extensions": [".tmp"]},
            "preferences": {"recursive": True, "custom_key": 42},
        }
        settings = organizer._normalize_settings(raw)
        self.assertEqual(settings["rules"], {"A": [".a"]})
        self.assertEqual(settings["filters"]["min_size_kb"], 5)
        self.assertEqual(settings["filters"]["ignore_hidden"], True)
        self.assertEqual(settings["preferences"]["recursive"], True)
        self.assertEqual(settings["preferences"]["custom_key"], 42)

    def test_non_dict_input_returns_defaults(self):
        for bad in (None, [1, 2], "nope", 7):
            settings = organizer._normalize_settings(bad)
            self.assertEqual(settings["rules"], {})
            self.assertEqual(settings["filters"]["ignore_hidden"], True)

    def test_list_rules_do_not_crash(self):
        settings = organizer._normalize_settings({"rules": [1, 2]})
        self.assertEqual(settings["rules"], {})


class LoadSettingsFromFileTests(unittest.TestCase):
    def test_valid_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "config.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"Media": [".mp3"]}, handle)
            settings = organizer.load_settings_from_file(path)
            self.assertEqual(settings["rules"]["Media"], [".mp3"])

    def test_invalid_json_raises_value_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "config.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{ not json !")
            with self.assertRaises(ValueError):
                organizer.load_settings_from_file(path)

    def test_non_object_json_raises_value_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "config.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump([1, 2, 3], handle)
            with self.assertRaises(ValueError):
                organizer.load_settings_from_file(path)


class LoadSettingsTests(IsolateAppDataMixin):
    def _write_user_config(self, content):
        path = organizer.user_config_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        return path

    def _bundled_config(self, temp_dir):
        bundled = os.path.join(temp_dir, "bundled_config.json")
        with open(bundled, "w", encoding="utf-8") as handle:
            json.dump({"Bundled": [".bin"]}, handle)
        return bundled

    def test_missing_user_config_uses_bundled(self):
        with tempfile.TemporaryDirectory() as bundled_dir:
            bundled = self._bundled_config(bundled_dir)
            with mock.patch.object(organizer, "resource_path", return_value=bundled):
                settings = organizer.load_settings()
            self.assertEqual(settings["rules"], {"Bundled": [".bin"]})

    def test_corrupt_user_config_falls_back_and_is_backed_up(self):
        with tempfile.TemporaryDirectory() as bundled_dir:
            bundled = self._bundled_config(bundled_dir)
            path = self._write_user_config("{ nope !")
            with mock.patch.object(organizer, "resource_path", return_value=bundled):
                settings = organizer.load_settings()
            self.assertEqual(settings["rules"], {"Bundled": [".bin"]})
            leftovers = os.listdir(os.path.dirname(path))
            self.assertTrue(any("corrupt" in name for name in leftovers))

    def test_valid_user_config_wins_over_bundled(self):
        with tempfile.TemporaryDirectory() as bundled_dir:
            bundled = self._bundled_config(bundled_dir)
            self._write_user_config(json.dumps({"User": [".u"]}))
            with mock.patch.object(organizer, "resource_path", return_value=bundled):
                settings = organizer.load_settings()
            self.assertEqual(settings["rules"], {"User": [".u"]})

    def test_corrupt_bundled_config_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as bundled_dir:
            bundled = os.path.join(bundled_dir, "bundled_config.json")
            with open(bundled, "w", encoding="utf-8") as handle:
                handle.write("[corrupt")
            with mock.patch.object(organizer, "resource_path", return_value=bundled):
                settings = organizer.load_settings()
            self.assertEqual(settings["rules"], {})
            self.assertEqual(settings["filters"]["ignore_hidden"], True)

    def test_user_config_does_not_exist_and_bundled_uses_real_resource(self):
        settings = organizer.load_settings()
        self.assertIn("rules", settings)
        self.assertIn("Images", settings["rules"])


class SaveSettingsTests(IsolateAppDataMixin):
    def test_round_trip(self):
        settings = {
            "rules": {"Docs": [".pdf"]},
            "filters": {"ignore_hidden": False},
            "preferences": {"recursive": True},
        }
        organizer.save_settings(settings)
        loaded = organizer.load_settings_from_file(organizer.user_config_path())
        self.assertEqual(loaded["rules"], {"Docs": [".pdf"]})
        self.assertEqual(loaded["filters"]["ignore_hidden"], False)
        self.assertEqual(loaded["preferences"]["recursive"], True)

    def test_save_to_custom_destination(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "out.json")
            organizer.save_settings({"rules": {"A": [".a"]}}, destination=path)
            self.assertTrue(os.path.exists(path))
            with open(path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            self.assertEqual(raw["rules"], {"A": [".a"]})


class LoadRulesTests(IsolateAppDataMixin):
    def test_load_rules_returns_dict(self):
        rules = organizer.load_rules()
        self.assertIsInstance(rules, dict)


if __name__ == "__main__":
    unittest.main()