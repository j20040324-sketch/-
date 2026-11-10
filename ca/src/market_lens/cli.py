"""Command-line entry point."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import List

from .analysis import analyze
from .models import Market
from .providers import ProviderError, providers
from .storage import Store


def run(args: argparse.Namespace) -> int:
    captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    store = Store(args.db)
    results, errors = [], []
    try:
        for provider in providers():
            try:
                markets: List[Market] = provider.fetch(args.limit)
                store.save(markets, captured_at)
                for market in markets:
                    results.append(analyze(market, store.history(market), current_snapshot_at=captured_at))
                print("{}: fetched {} markets".format(provider.name, len(markets)), file=sys.stderr)
            except ProviderError as exc:
                errors.append({"provider": provider.name, "error": str(exc)})
                print("{}: {}".format(provider.name, exc), file=sys.stderr)
        results.sort(key=lambda result: (bool(result.anomaly_flags), result.market.volume or 0), reverse=True)
        document = {
            "generated_at": captured_at,
            "disclaimer": "Research output only; not investment advice.",
            "provider_errors": errors,
            "market_count": len(results),
            "markets": [result.to_dict() for result in results[:args.top]],
            "platform_counts": {
                provider.name: sum(1 for result in results if result.market.platform == provider.name)
                for provider in providers()
            },
        }
        rendered = json.dumps(document, ensure_ascii=False, indent=2)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as output:
                output.write(rendered + "\n")
            print("Wrote {}".format(args.output), file=sys.stderr)
        else:
            print(rendered)
        return 0 if results else 1
    finally:
        store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and analyze public prediction markets.")
    parser.add_argument("--limit", type=int, default=100, help="Markets per provider (max depends on provider).")
    parser.add_argument("--top", type=int, default=25, help="Maximum records in the output report.")
    parser.add_argument("--db", default=os.environ.get("MARKET_LENS_DB", "data/markets.sqlite3"))
    parser.add_argument("--output", help="Write JSON report to this path instead of stdout.")
    args = parser.parse_args()
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
