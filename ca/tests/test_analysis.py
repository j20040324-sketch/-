import unittest

from market_lens.analysis import analyze
from market_lens.models import Market, Snapshot


class AnalysisTests(unittest.TestCase):
    def market(self, **kwargs):
        values = dict(market_id="m1", platform="test", title="Will it happen?", status="open",
                      probability=0.6, probability_basis="fixture", volume=40.0, binary=True)
        values.update(kwargs)
        return Market(**values)

    def test_flags_large_probability_move_with_evidence(self):
        old = Snapshot("m1", "test", "2026-01-01T00:00:00+00:00", 0.45, "fixture", 10.0, None, True)
        result = analyze(self.market(), [old], current_snapshot_at="2026-01-02T00:00:00+00:00")
        self.assertAlmostEqual(result.probability_change, 0.15)
        self.assertIn("large_probability_move", result.anomaly_flags)
        self.assertTrue(result.evidence)

    def test_does_not_compare_multoutcome_market(self):
        result = analyze(self.market(binary=False), [])
        self.assertIsNone(result.probability_change)
        self.assertIn("probability_comparison_unsupported", result.anomaly_flags)

    def test_unavailable_kalshi_quote_is_explicit(self):
        result = analyze(self.market(probability=None, probability_basis=None), [])
        self.assertIn("probability_unavailable", result.anomaly_flags)


if __name__ == "__main__":
    unittest.main()
