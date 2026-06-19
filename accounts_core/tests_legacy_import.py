from decimal import Decimal

from django.test import SimpleTestCase

from accounts_core.legacy_import.client_pdf import (
    legacy_client_code,
    parse_trial_balance_text,
)


SAMPLE_TRIAL = """
MAHMOUD BAKRI BOS
USD
5,516.00
10,416.00
4,900.00
0.00
4110000009
ALI MERASHLI (1)
USD
520.00
520.00
0.00
0.00
4110000505
"""


class LegacyClientPdfTests(SimpleTestCase):
    def test_parse_trial_balance(self):
        rows = parse_trial_balance_text(SAMPLE_TRIAL)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].legacy_account, "4110000009")
        self.assertEqual(rows[0].name_en, "Mahmoud Bakri Bos")
        self.assertEqual(rows[1].legacy_account, "4110000505")
        self.assertEqual(rows[1].name_en, "Ali Merashli")

    def test_legacy_client_code(self):
        self.assertEqual(legacy_client_code("4110000505"), "C-0505")

    def test_closing_balance(self):
        rows = parse_trial_balance_text(SAMPLE_TRIAL)
        ali = rows[1]
        self.assertEqual(ali.closing_balance, Decimal("0"))
