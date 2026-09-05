import os
import tempfile
import unittest

from src.organizer import generate_report


class GenerateReportTests(unittest.TestCase):
    def test_generate_report_includes_summary_and_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            for folder_name in ("Images", "Documents"):
                os.makedirs(os.path.join(temp_dir, folder_name), exist_ok=True)

            history = [
                {
                    "timestamp": "2024-01-01T00:00:00+00:00",
                    "moves": [
                        {"destination": os.path.join(temp_dir, "Images", "a.jpg"), "category": "Images"},
                        {"destination": os.path.join(temp_dir, "Images", "b.jpg"), "category": "Images"},
                        {"destination": os.path.join(temp_dir, "Documents", "c.pdf"), "category": "Documents"},
                    ],
                    "errors": ["Error moving file"],
                }
            ]

            report = generate_report(temp_dir, history=history)

            self.assertEqual(report["organized_files"], 3)
            self.assertIn("Images", {item["name"] for item in report["popular_categories"]})
            self.assertEqual(report["errors"], ["Error moving file"])
            self.assertTrue(report["recent_history"])
            self.assertIn("Images", {item["name"] for item in report["space_by_category"]})


if __name__ == "__main__":
    unittest.main()
