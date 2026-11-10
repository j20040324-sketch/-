"""Small deterministic signals. All deltas are fractions (0.10 = 10 percentage points)."""

from typing import List, Optional

from .models import Analysis, Market, Snapshot


def analyze(market: Market, history: List[Snapshot], probability_threshold: float = 0.08,
            volume_multiple: float = 3.0, current_snapshot_at: Optional[str] = None) -> Analysis:
    flags, evidence = [], []
    prior = next((point for point in history if point.probability is not None and point.binary
                  and point.captured_at != current_snapshot_at), None)
    probability_change: Optional[float] = None
    if not market.binary:
        flags.append("probability_comparison_unsupported")
        evidence.append("Market is not confirmed binary; probability movement is not compared.")
    elif market.probability is not None and prior is not None:
        probability_change = market.probability - prior.probability
        evidence.append("{} probability moved from {:.1f}% to {:.1f}% since {} ({} basis).".format(
            market.platform, prior.probability * 100, market.probability * 100,
            prior.captured_at, market.probability_basis or "unspecified"))
        if abs(probability_change) >= probability_threshold:
            flags.append("large_probability_move")
    elif market.probability is None:
        flags.append("probability_unavailable")
        evidence.append("No valid probability quote or trade price was available.")
    if market.volume is not None:
        prior_volume = next((point.volume for point in history if point.captured_at != current_snapshot_at
                             and point.volume is not None and point.volume > 0), None)
        if prior_volume is not None and market.volume >= prior_volume * volume_multiple:
            flags.append("volume_spike")
            evidence.append("Reported volume increased from {:.2f} to {:.2f} ({}x); provider volume window/definition may differ.".format(
                prior_volume, market.volume, round(market.volume / prior_volume, 2)))
    if market.status.lower() not in ("open", "active"):
        flags.append("market_not_open")
    if market.source_updated_at:
        evidence.append("Provider update timestamp: {}.".format(market.source_updated_at))
    return Analysis(market, probability_change, None, flags, evidence, len(history))
