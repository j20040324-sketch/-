"""Public API adapters. They normalize platform-specific responses at the edge."""

import json
import time
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import Market


class ProviderError(RuntimeError):
    pass


def _get_json(url: str, timeout: int = 20, attempts: int = 3) -> Any:
    last_error = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": "prediction-market-lens/0.1"})
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if isinstance(exc, HTTPError) and exc.code < 500 and exc.code != 429:
                break
            if attempt + 1 < attempts:
                time.sleep(0.5 * (2 ** attempt))
    raise ProviderError("GET failed for {}: {}".format(url, last_error))


def _number(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


class PolymarketProvider:
    name = "polymarket"
    base_url = "https://gamma-api.polymarket.com/markets"

    def fetch(self, limit: int = 100) -> List[Market]:
        query = urlencode({"limit": min(max(limit, 1), 500), "active": "true", "closed": "false"})
        payload = _get_json("{}?{}".format(self.base_url, query))
        if not isinstance(payload, list):
            raise ProviderError("Unexpected Polymarket response: expected a list")
        markets = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            prices = row.get("outcomePrices")
            probability = None
            try:
                parsed = json.loads(prices) if isinstance(prices, str) else prices
                if isinstance(parsed, list) and parsed:
                    probability = _number(parsed[0])
            except (TypeError, json.JSONDecodeError):
                pass
            market_id = row.get("id") or row.get("conditionId")
            if not market_id:
                continue
            outcomes = row.get("outcomes")
            try:
                parsed_outcomes = json.loads(outcomes) if isinstance(outcomes, str) else outcomes
                binary = isinstance(parsed_outcomes, list) and len(parsed_outcomes) == 2
            except (TypeError, json.JSONDecodeError):
                binary = False
            markets.append(Market(
                market_id=str(market_id), platform=self.name,
                title=str(row.get("question") or row.get("title") or "Untitled market"),
                status="open" if row.get("active") and not row.get("closed") else "closed",
                url="https://polymarket.com/event/{}".format(row.get("slug")) if row.get("slug") else None,
                end_time=row.get("endDate") or row.get("endDateIso"),
                volume=_number(row.get("volume24hr")) or _number(row.get("volumeNum")) or _number(row.get("volume")),
                liquidity=_number(row.get("liquidityNum")) or _number(row.get("liquidity")),
                probability=probability,
                probability_basis="top_outcome_price",
                source_updated_at=row.get("updatedAt"),
                raw_market_type="binary" if binary else "multi_outcome_or_unknown",
                binary=binary,
            ))
        return markets


class KalshiProvider:
    name = "kalshi"
    base_url = "https://api.elections.kalshi.com/trade-api/v2/markets"

    def fetch(self, limit: int = 100) -> List[Market]:
        page_size = min(max(limit, 1), 1000)
        cursor = None
        rows = []
        # The first page is often dominated by combo markets. Walk cursors until
        # enough ordinary binary markets are collected or the API is exhausted.
        for _ in range(10):
            params = {"limit": page_size, "status": "open", "mve_filter": "exclude"}
            if cursor:
                params["cursor"] = cursor
            payload = _get_json("{}?{}".format(self.base_url, urlencode(params)))
            page = payload.get("markets") if isinstance(payload, dict) else None
            if not isinstance(page, list):
                raise ProviderError("Unexpected Kalshi response: expected markets list")
            rows.extend(page)
            cursor = payload.get("cursor")
            if not cursor or len(rows) >= page_size * 10:
                break
        markets = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            ticker = row.get("ticker")
            if not ticker:
                continue
            if str(ticker).startswith("KXMV") or row.get("market_type") != "binary":
                continue
            title = str(row.get("title") or ticker)
            if title.lower().count("yes ") > 1 or title.lower().count("no ") > 1:
                continue
            bid, ask = _number(row.get("yes_bid_dollars")), _number(row.get("yes_ask_dollars"))
            last = _number(row.get("last_price_dollars"))
            # Kalshi quote fields are dollar values in current API responses.
            # Require an actual two-sided quote; never interpret 0/0 as 0% probability.
            if bid is not None and ask is not None and 0 <= bid <= ask <= 1 and (bid > 0 or ask > 0):
                probability, basis = (bid + ask) / 2, "yes_quote_midpoint"
            elif last is not None and 0 < last < 1:
                probability, basis = last, "last_trade_price"
            else:
                probability, basis = None, None
            markets.append(Market(
                market_id=str(ticker), platform=self.name,
                title=title, status=str(row.get("status") or "open"),
                url="https://kalshi.com/markets/{}".format(ticker),
                end_time=row.get("expected_expiration_time") or row.get("expiration_time"),
                volume=_number(row.get("volume_24h")) or _number(row.get("volume")),
                liquidity=_number(row.get("liquidity_dollars")),
                probability=probability, probability_basis=basis,
                source_updated_at=row.get("updated_time") or row.get("updated_ts"),
                raw_market_type=row.get("market_type"),
                binary=row.get("market_type") == "binary",
            ))
            if len(markets) >= limit:
                break
        return markets


def providers() -> List[Any]:
    return [PolymarketProvider(), KalshiProvider()]
