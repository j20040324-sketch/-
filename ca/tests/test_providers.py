import unittest
from unittest.mock import patch

from market_lens.providers import KalshiProvider, PolymarketProvider


class ProviderTests(unittest.TestCase):
    @patch("market_lens.providers._get_json")
    def test_polymarket_maps_binary_and_multi_outcome(self, get_json):
        get_json.return_value = [
            {"id": "1", "question": "Binary?", "outcomes": '["Yes", "No"]',
             "outcomePrices": '["0.61", "0.39"]', "volume24hr": "12", "active": True},
            {"id": "2", "question": "Many?", "outcomes": '["A", "B", "C"]',
             "outcomePrices": '["0.3", "0.4", "0.3"]', "active": True},
        ]
        rows = PolymarketProvider().fetch()
        self.assertTrue(rows[0].binary)
        self.assertEqual(rows[0].probability, 0.61)
        self.assertFalse(rows[1].binary)

    @patch("market_lens.providers._get_json")
    def test_kalshi_uses_quote_midpoint_and_ignores_zero_quote(self, get_json):
        get_json.return_value = {"markets": [
            {"ticker": "KX1", "title": "Quoted", "market_type": "binary",
             "yes_bid_dollars": "0.40", "yes_ask_dollars": "0.50"},
            {"ticker": "KX2", "title": "No quote", "market_type": "binary",
             "yes_bid_dollars": "0.0000", "yes_ask_dollars": "0.0000", "last_price_dollars": "0.0000"},
        ]}
        rows = KalshiProvider().fetch()
        self.assertEqual(rows[0].probability, 0.45)
        self.assertEqual(rows[0].probability_basis, "yes_quote_midpoint")
        self.assertIsNone(rows[1].probability)


if __name__ == "__main__":
    unittest.main()

