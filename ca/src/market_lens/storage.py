"""SQLite persistence for normalized market snapshots."""

import json
import os
import sqlite3
from typing import List, Optional

from .models import Market, Snapshot


class Store:
    def __init__(self, path: str):
        self.path = path
        parent = os.path.dirname(os.path.abspath(path))
        if parent and parent != ".":
            os.makedirs(parent, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS markets (
            platform TEXT NOT NULL, market_id TEXT NOT NULL, market_json TEXT NOT NULL,
            PRIMARY KEY(platform, market_id)
        );
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT NOT NULL, market_id TEXT NOT NULL,
            captured_at TEXT NOT NULL, probability REAL, probability_basis TEXT,
            volume REAL, liquidity REAL, binary INTEGER NOT NULL DEFAULT 1,
            UNIQUE(platform, market_id, captured_at)
        );
        CREATE INDEX IF NOT EXISTS idx_snapshots_market_time
            ON snapshots(platform, market_id, captured_at DESC);
        """)
        self.connection.commit()

    def save(self, markets: List[Market], captured_at: str) -> None:
        with self.connection:
            for market in markets:
                self.connection.execute(
                    "INSERT INTO markets(platform, market_id, market_json) VALUES(?,?,?) "
                    "ON CONFLICT(platform, market_id) DO UPDATE SET market_json=excluded.market_json",
                    (market.platform, market.market_id, json.dumps(market.to_dict(), ensure_ascii=False)),
                )
                self.connection.execute(
                    "INSERT OR IGNORE INTO snapshots(platform, market_id, captured_at, probability, probability_basis, volume, liquidity, binary) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (market.platform, market.market_id, captured_at, market.probability,
                     market.probability_basis, market.volume, market.liquidity, int(market.binary)),
                )

    def history(self, market: Market, limit: int = 25) -> List[Snapshot]:
        rows = self.connection.execute(
            "SELECT * FROM snapshots WHERE platform=? AND market_id=? ORDER BY captured_at DESC, id DESC LIMIT ?",
            (market.platform, market.market_id, limit),
        ).fetchall()
        return [Snapshot(row["market_id"], row["platform"], row["captured_at"], row["probability"],
                         row["probability_basis"], row["volume"], row["liquidity"], bool(row["binary"])) for row in rows]

    def list_markets(self, limit: int = 2000) -> List[Market]:
        rows = self.connection.execute(
            "SELECT DISTINCT m.market_json FROM markets m "
            "JOIN snapshots s ON s.platform=m.platform AND s.market_id=m.market_id "
            "JOIN (SELECT platform, MAX(captured_at) AS captured_at FROM snapshots GROUP BY platform) latest "
            "ON latest.platform=s.platform AND latest.captured_at=s.captured_at "
            "ORDER BY m.platform, m.market_id LIMIT ?", (limit,)
        ).fetchall()
        return [Market(**json.loads(row["market_json"])) for row in rows]

    def latest_capture(self, market: Optional[Market] = None) -> Optional[str]:
        if market is None:
            row = self.connection.execute("SELECT MAX(captured_at) AS captured_at FROM snapshots").fetchone()
        else:
            row = self.connection.execute(
                "SELECT MAX(captured_at) AS captured_at FROM snapshots WHERE platform=? AND market_id=?",
                (market.platform, market.market_id),
            ).fetchone()
        return row["captured_at"] if row else None

    def close(self) -> None:
        self.connection.close()
