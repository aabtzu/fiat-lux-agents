"""Tests for StatementParser — all Anthropic API calls are mocked."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fiat_lux_agents.statement_parser import StatementParser

_AMEX_CSV = b"""Date,Description,Card Member,Account #,Amount
07/01/2026,DELTA AIR LINES,JOHN DOE,12345,250.00
07/05/2026,PAYMENT THANK YOU,JOHN DOE,12345,-250.00
07/10/2026,SOULCYCLE,JOHN DOE,12345,36.00
"""

_CHASE_CSV = b"""Transaction Date,Description,Category,Type,Amount
07/01/2026,WHOLEFDS #123,Food & Drink,Sale,-85.50
07/03/2026,NETFLIX.COM,Entertainment,Sale,-15.99
07/05/2026,Payment Thank You,Payment,Payment,100.00
"""

_BOFA_CSV = b"""Date,Description,Amount,Running Bal.
07/01/2026,AMAZON.COM,-45.00,1234.56
07/05/2026,ONLINE BANKING PAYMENT,150.00,1384.56
"""


class TestStatementParserCSV(unittest.TestCase):
    def setUp(self):
        with patch("anthropic.Anthropic"):
            self.parser = StatementParser()

    def test_amex_csv_positive_amounts_are_spending(self):
        rows = self.parser.parse_csv(_AMEX_CSV, "activity.csv")
        spending = [r for r in rows if r["amount"] > 0]
        self.assertTrue(len(spending) >= 2)
        delta = next(r for r in rows if "DELTA" in r["description"])
        self.assertEqual(delta["amount"], 250.00)

    def test_amex_csv_payment_is_negative(self):
        rows = self.parser.parse_csv(_AMEX_CSV, "activity.csv")
        payment = next(r for r in rows if "PAYMENT" in r["description"])
        self.assertLess(payment["amount"], 0)

    def test_chase_csv_spending_is_positive(self):
        rows = self.parser.parse_csv(_CHASE_CSV, "chase.csv")
        whole_foods = next(r for r in rows if "WHOLEFDS" in r["description"])
        self.assertGreater(whole_foods["amount"], 0)

    def test_chase_csv_payment_is_negative(self):
        rows = self.parser.parse_csv(_CHASE_CSV, "chase.csv")
        payment = next(r for r in rows if "Payment Thank" in r["description"])
        self.assertLess(payment["amount"], 0)

    def test_bofa_csv_spending_is_positive(self):
        rows = self.parser.parse_csv(_BOFA_CSV, "bofa.csv")
        amazon = next(r for r in rows if "AMAZON" in r["description"])
        self.assertGreater(amazon["amount"], 0)

    def test_canonical_fields_present(self):
        rows = self.parser.parse_csv(_AMEX_CSV, "activity.csv")
        required = {"txn_date", "year", "month", "description", "category", "amount", "account", "source_file"}
        for row in rows:
            self.assertTrue(required.issubset(row.keys()))

    def test_source_file_recorded(self):
        rows = self.parser.parse_csv(_AMEX_CSV, "my_statement.csv")
        self.assertTrue(all(r["source_file"] == "my_statement.csv" for r in rows))


class TestNormalizeCategories(unittest.TestCase):
    def setUp(self):
        with patch("anthropic.Anthropic"):
            self.parser = StatementParser()

    def _mock_haiku(self, categories: list[str]):
        import json
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text=json.dumps(categories))]
        mock_resp.stop_reason = "end_turn"
        self.parser.client.messages.create.return_value = mock_resp

    def test_categories_applied_to_rows(self):
        rows = [
            {"description": "DELTA AIR LINES", "category": "Other"},
            {"description": "NETFLIX.COM", "category": "Other"},
        ]
        self._mock_haiku(["Travel", "Streaming"])
        result = self.parser.normalize_categories(rows)
        self.assertEqual(result[0]["category"], "Travel")
        self.assertEqual(result[1]["category"], "Streaming")

    def test_length_mismatch_uses_zip(self):
        rows = [{"description": "A", "category": "Other"}, {"description": "B", "category": "Other"}]
        self._mock_haiku(["Travel", "Dining", "Extra"])  # 3 for 2 rows
        result = self.parser.normalize_categories(rows)
        self.assertEqual(result[0]["category"], "Travel")
        self.assertEqual(result[1]["category"], "Dining")

    def test_api_failure_leaves_originals(self):
        rows = [{"description": "SOULCYCLE", "category": "Fitness"}]
        self.parser.client.messages.create.side_effect = Exception("API error")
        result = self.parser.normalize_categories(rows)
        self.assertEqual(result[0]["category"], "Fitness")

    def test_empty_rows_returns_empty(self):
        result = self.parser.normalize_categories([])
        self.assertEqual(result, [])


class TestParseAndNormalize(unittest.TestCase):
    def setUp(self):
        with patch("anthropic.Anthropic"):
            self.parser = StatementParser()

    def test_csv_parse_and_normalize(self):
        import json
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text=json.dumps(["Travel", "Payment", "Fitness"]))]
        mock_resp.stop_reason = "end_turn"
        self.parser.client.messages.create.return_value = mock_resp

        rows = self.parser.parse_and_normalize(_AMEX_CSV, "activity.csv")
        self.assertTrue(len(rows) > 0)
        categories = {r["category"] for r in rows}
        self.assertTrue(categories.issubset({"Travel", "Payment", "Fitness", "Other"}))


if __name__ == "__main__":
    unittest.main()
