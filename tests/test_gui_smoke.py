import os
import tempfile
import tkinter as tk
import unittest
from unittest import mock

import customtkinter

from src.gui import AppGUI
from src.ui import theme
from src.ui.pages import PAGES


class GuiSmokeTests(unittest.TestCase):
    """Builds the real window offscreen-ish and drives every page once."""

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self._localappdata = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self._tempdir.name
        try:
            self.root = customtkinter.CTk()
        except tk.TclError as error:
            self.skipTest(f"No display available: {error}")
        self.patches = [mock.patch("src.gui.set_autostart"), mock.patch("src.gui.anim.system_reduce_motion", return_value=True)]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in self.patches:
            patch.stop()
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        if self._localappdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._localappdata
        self._tempdir.cleanup()

    def pump(self):
        for _ in range(5):
            self.root.update()

    def test_every_page_builds_and_theme_switch_preserves_state(self):
        folder = os.path.join(self._tempdir.name, "inbox")
        os.makedirs(folder)
        for name in ("report.pdf", "photo.jpg", "mystery.xyz"):
            with open(os.path.join(folder, name), "w", encoding="utf-8") as handle:
                handle.write("data")

        app = AppGUI(self.root)
        app._load_folder(folder, cascade=True)
        self.pump()
        for key, *_rest in PAGES:
            app.show_page(key)
            self.pump()

        organize = app.pages["organize"]
        rows = organize.tree.get_children()
        self.assertEqual(len(rows), 3)
        organize._toggle([rows[0]])
        self.assertEqual(len(app.selected_move_items()), 2)

        app.search_text = "photo"
        organize.render()
        self.assertEqual(len(organize.tree.get_children()), 1)

        app.set_theme("Neutral")
        self.pump()
        self.assertIs(theme.current, theme.PALETTES["Neutral"])
        self.assertEqual(len(app.selected_move_items()), 2, "exclusions survive the UI rebuild")
        app.show_page("organize")
        self.assertEqual(len(app.pages["organize"].tree.get_children()), 1, "search survives the UI rebuild")

        app.toasts.show("Smoke test toast", "success")
        app.toggle_sidebar()
        self.pump()
        app._shutdown()


if __name__ == "__main__":
    unittest.main()
