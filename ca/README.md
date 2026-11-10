# Prediction Market Lens

A small, auditable research pipeline for public prediction-market data from Polymarket and Kalshi. It normalizes provider responses, saves snapshots in SQLite, and reports explainable changes. It does not place trades and is not investment advice.

## Requirements

- Python 3.9+
- Network access to the public provider APIs for live runs
- No API key is required for the current public endpoints

## Run

From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
market-lens --limit 100 --top 25 --output sample-report.json
```

Or without installing the entry point:

```sh
PYTHONPATH=src python -m market_lens.cli --limit 100 --top 25
```

## Web app

Start the local dashboard and API from the repository root:

```sh
PYTHONPATH=src python -m market_lens.web --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765/`. In VS Code, choose **Run Market Lens Web** from Run and Debug. The dashboard can trigger API collection, search by title or ID, filter by provider or signal, sort markets, and inspect a market's stored snapshots. The Python standard library serves both the JSON API and static frontend; Node.js is not required.

The API endpoints are `GET /api/health`, `GET /api/markets`, `GET /api/markets/{platform}/{market_id}`, `POST /api/refresh`, and `GET /api/refresh/status?job={id}`. Refresh runs in a background thread so the request does not block while public APIs respond.

Snapshots are stored in `data/markets.sqlite3` by default. Set `MARKET_LENS_DB` or use `--db` to change the location. Run repeatedly to build history. `--limit` is per provider; `--top` limits only the output report, not stored snapshots.

## Pipeline

```text
Polymarket Gamma API ─┐
                      ├─> provider adapters ─> normalized Market ─> SQLite snapshots
Kalshi Trade API ─────┘                                      │
                                                             v
                                             deterministic signal analysis ─> JSON
```

Each provider adapter owns its response mapping. Analysis and persistence consume the shared internal model, so provider-specific fields do not leak into the signal code. The first implementation deliberately uses deterministic analysis only; a constrained LLM explanation stage can be added after snapshot semantics have been validated.

## Signals and data semantics

- Polymarket probability is the first listed outcome price. It is compared only when the API confirms exactly two outcomes; multi-outcome markets are retained but marked as unsupported for probability movement analysis.
- Kalshi probability uses the midpoint of a valid two-sided YES quote. When no valid quote exists, a non-zero last trade price is used. A 0/0 quote is treated as unavailable, not as a zero probability.
- A probability move of at least 8 percentage points between the two most recent snapshots is flagged. This is a simple configurable-in-code screening threshold, not a calibrated alert.
- Volume is stored as reported by each provider. Polymarket prefers its 24-hour volume field; Kalshi prefers its 24-hour field when present. Because these are often rolling-window values, current output does not claim to calculate true interval volume changes.
- Snapshot timestamps are capture times in UTC. Provider update timestamps are retained separately on the market record.

The public endpoints verified for this prototype are:

- `https://gamma-api.polymarket.com/markets`
- `https://api.elections.kalshi.com/trade-api/v2/markets`

Provider schemas and availability can change. Current Kalshi endpoint fields include dollar-denominated YES bid/ask prices and `market_type`; composite/non-binary markets should not be interpreted as ordinary binary probabilities.

## Tests

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```

Tests use mocked API payloads and do not require network access. A live run will include a provider error in the report if one source is unavailable; records from the other source can still be returned.

## Next extensions

1. Persist provider volume-window metadata and compute stable interval deltas from cumulative counters where available.
2. Add an optional LLM adapter with schema-validated output, evidence-only prompts, and graceful fallback to deterministic results.
3. Add a scheduled polling command, retention policy, and a small historical report view.

The first Kalshi result pages can be dominated by multi-event combo markets. The adapter uses the API's `mve_filter=exclude`, follows cursors, and applies a conservative ticker/title filter. This has been checked against live responses but should be monitored as the provider schema and market naming evolve. API field absence (for example, volume/liquidity on some rows) is preserved as `null`.
