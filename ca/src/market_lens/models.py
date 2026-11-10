"""Internal data contracts shared by providers, storage, and analysis."""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Market:
    market_id: str
    platform: str
    title: str
    status: str
    url: Optional[str] = None
    end_time: Optional[str] = None
    volume: Optional[float] = None
    liquidity: Optional[float] = None
    probability: Optional[float] = None
    probability_basis: Optional[str] = None
    source_updated_at: Optional[str] = None
    raw_market_type: Optional[str] = None
    binary: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Snapshot:
    market_id: str
    platform: str
    captured_at: str
    probability: Optional[float]
    probability_basis: Optional[str]
    volume: Optional[float]
    liquidity: Optional[float]
    binary: bool = True


@dataclass
class Analysis:
    market: Market
    probability_change: Optional[float]
    volume_change: Optional[float]
    anomaly_flags: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    history_points: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "market": self.market.to_dict(),
            "probability_change": self.probability_change,
            "volume_change": self.volume_change,
            "anomaly_flags": self.anomaly_flags,
            "evidence": self.evidence,
            "history_points": self.history_points,
        }
