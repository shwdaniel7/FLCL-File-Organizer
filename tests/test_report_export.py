import csv
import os
import tempfile
import unittest

from src.report_export import render_report_html, write_report_csv
from src.ui.theme import PALETTES

REPORT = {
    "organized_files": 3,
    "popular_categories": [{"name": "<script>alert(1)</script>", "count": 2}, {"name": "Docs", "count": 1}],
    "errors": ["ERROR organizing <b>bad</b>.txt: denied"],
    "space_by_category": [{"name": "Docs", "size_bytes": 2048, "size_human": "2.0 KB"}],
    "recent_history": [{"timestamp": "2026-10-28T10:00:00", "files": ["a&b.pdf"], "count": 1}],
}


class HtmlExportTests(unittest.TestCase):
    def test_report_values_are_escaped(self):
        html = render_report_html(REPORT, PALETTES["FLCL"])
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertIn("&lt;b&gt;bad&lt;/b&gt;", html)
        self.assertIn("a&amp;b.pdf", html)

    def test_uses_palette_colors(self):
        html = render_report_html(REPORT, PALETTES["Neutral"])
        self.assertIn(PALETTES["Neutral"]["accent"], html)

    def test_empty_report(self):
        empty = {"organized_files": 0, "popular_categories": [], "errors": [], "space_by_category": [], "recent_history": []}
        html = render_report_html(empty, PALETTES["FLCL"])
        self.assertIn("No recorded errors", html)
        self.assertIn("No recorded operations", html)


class CsvExportTests(unittest.TestCase):
    def test_writes_categories_and_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "report.csv")
            write_report_csv(path, REPORT)
            with open(path, encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.reader(handle))
        self.assertIn(["Files organized", "3"], rows)
        self.assertIn(["Docs", "1", "2048", "2.0 KB"], rows)
        self.assertIn(["2026-10-28T10:00:00", "1", "a&b.pdf"], rows)


if __name__ == "__main__":
    unittest.main()
