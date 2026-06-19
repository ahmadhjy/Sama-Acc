from decimal import Decimal

from django.test import SimpleTestCase

from accounts_core.legacy_import.client_pdf import (
    legacy_client_code,
    parse_trial_balance_text,
)
from accounts_core.legacy_import.client_soa import parse_soa_transactions


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

    def test_parse_soa_transactions(self):
        sample = """
Tel :
1023
10/06/2026
YW8BCZ ticket line
520.000
0.000
520.000
130
17/01/2026
MM-Receipt Voucher-
0.000
840.000
0.000
520.000
0.000
520.000
USD
"""
        txs = parse_soa_transactions(sample)
        self.assertEqual(len(txs), 2)
        self.assertEqual(txs[0].invoice_amount, Decimal("520"))
        self.assertEqual(txs[1].payment_amount, Decimal("840"))
