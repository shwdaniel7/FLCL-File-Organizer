import unittest

from src.ui import theme

REQUIRED_KEYS = {
    "window", "panel", "surface", "raised", "border", "text", "muted", "accent", "accent_soft",
    "accent_alt", "highlight", "on_accent", "success", "warning", "error", "series",
}


class PaletteTests(unittest.TestCase):
    def test_every_palette_defines_every_token(self):
        for name, palette in theme.PALETTES.items():
            with self.subTest(theme=name):
                self.assertEqual(set(palette), REQUIRED_KEYS)

    def test_text_meets_wcag_aa_contrast(self):
        for name, p in theme.PALETTES.items():
            for fg, bg in [("text", "window"), ("text", "panel"), ("text", "surface"), ("text", "raised"),
                           ("muted", "window"), ("muted", "panel"), ("muted", "surface"), ("on_accent", "accent")]:
                with self.subTest(theme=name, pair=(fg, bg)):
                    self.assertGreaterEqual(theme.contrast_ratio(p[fg], p[bg]), 4.5)

    def test_contrast_ratio_reference_values(self):
        self.assertAlmostEqual(theme.contrast_ratio("#000000", "#FFFFFF"), 21.0, places=1)
        self.assertAlmostEqual(theme.contrast_ratio("#777777", "#777777"), 1.0)

    def test_unknown_palette_falls_back_to_default(self):
        self.assertIs(theme.palette("nope"), theme.PALETTES[theme.DEFAULT_THEME])

    def test_ctk_theme_uses_palette_and_keeps_base_keys(self):
        base = {"CTkButton": {"corner_radius": 6, "fg_color": ["a", "b"], "border_width": 0}, "CTkExtra": {"x": 1}}
        built = theme.build_ctk_theme(base, theme.PALETTES["FLCL"])
        self.assertEqual(built["CTkButton"]["fg_color"], "#FF3399")
        self.assertEqual(built["CTkButton"]["border_width"], 0)
        self.assertEqual(built["CTkExtra"], {"x": 1})
        self.assertEqual(base["CTkButton"]["fg_color"], ["a", "b"])  # base is not mutated


if __name__ == "__main__":
    unittest.main()
