from datetime import date

from django.test import TestCase

from accounts_core.export_names import export_filename, export_period_suffix, slugify_filename_part


class ExportFilenameTests(TestCase):
    def test_slugify_strips_unsafe_chars(self):
        self.assertEqual(slugify_filename_part("Acme Corp. (UK)"), "Acme_Corp_UK")

    def test_export_filename_joins_parts(self):
        name = export_filename("Statement", "Client A", "C0001", "2025")
        self.assertEqual(name, "Statement_Client_A_C0001_2025.pdf")

    def test_export_period_suffix_full_year(self):
        self.assertEqual(
            export_period_suffix(date(2025, 1, 1), date(2025, 12, 31)),
            "2025",
        )

    def test_export_period_suffix_range(self):
        self.assertEqual(
            export_period_suffix(date(2025, 3, 1), date(2025, 3, 31)),
            "2025-03-01_to_2025-03-31",
        )
