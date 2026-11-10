"""Application service shared by the web API and CLI."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .analysis import analyze
from .models import Analysis, Market
from .providers import ProviderError, providers
from .storage import Store


def refresh(store: Store, limit: int = 100) -> Dict[str, Any]:
    captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    counts, errors = {}, []
    for provider in providers():
        try:
            markets: List[Market] = provider.fetch(limit)
            store.save(markets, captured_at)
            counts[provider.name] = len(markets)
        except ProviderError as exc:
            counts[provider.name] = 0
            errors.append({"provider": provider.name, "error": str(exc)})
    return {"captured_at": captured_at, "provider_counts": counts, "provider_errors": errors}


def analyze_market(store: Store, market: Market) -> Analysis:
    return analyze(market, store.history(market), current_snapshot_at=store.latest_capture(market))


def market_results(store: Store, limit: int = 500) -> List[Analysis]:
    results = [analyze_market(store, market) for market in store.list_markets(limit)]
    results.sort(key=lambda result: (bool(result.anomaly_flags), result.market.volume or 0), reverse=True)
    return results
