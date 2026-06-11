"""Fractal detection and level clustering.

Methodology (design doc §4.1–4.2):

1. Williams fractals: a bar is a fractal high if its high exceeds the highs of
   the `wing` bars on each side (default 2). Mirror for fractal lows.
2. Clustering: fractal prices within a tolerance band (percent or ATR-scaled)
   are merged into a single level. Each cluster is weighted by recency
   (exponential decay) and touch count, producing a normalized strength score.

Everything here is deterministic and unit-tested; the LLM layer only ever
*reads* these outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd


@dataclass
class Fractal:
    price: float
    timestamp: pd.Timestamp
    kind: str  # "high" | "low"
    bar_index: int


@dataclass
class LevelCluster:
    price: float                 # touch-weighted mean of member prices
    kind: str                    # "resistance" | "support" | "mixed"
    touches: int
    strength: float              # 0..1, normalized within the result set
    first_seen: str
    last_seen: str
    members: list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["price"] = round(self.price, 2)
        d["strength"] = round(self.strength, 3)
        d["members"] = [round(m, 2) for m in self.members]
        return d


def find_fractals(bars: pd.DataFrame, wing: int = 2) -> list[Fractal]:
    """Detect Williams fractal highs/lows. Requires len(bars) > 2*wing."""
    highs = bars["high"].to_numpy()
    lows = bars["low"].to_numpy()
    idx = bars.index
    out: list[Fractal] = []
    for i in range(wing, len(bars) - wing):
        window_h = highs[i - wing: i + wing + 1]
        window_l = lows[i - wing: i + wing + 1]
        if highs[i] == window_h.max() and (window_h == highs[i]).sum() == 1:
            out.append(Fractal(float(highs[i]), idx[i], "high", i))
        if lows[i] == window_l.min() and (window_l == lows[i]).sum() == 1:
            out.append(Fractal(float(lows[i]), idx[i], "low", i))
    return out


def atr(bars: pd.DataFrame, period: int = 14) -> float:
    h, l, c = bars["high"], bars["low"], bars["close"]
    prev_c = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    val = tr.rolling(period).mean().iloc[-1]
    return float(val) if pd.notna(val) else float(tr.mean())


def cluster_levels(
    fractals: list[Fractal],
    n_bars: int,
    tolerance_pct: float = 0.0035,
    recency_half_life: int = 30,
) -> list[LevelCluster]:
    """Merge fractal prices into weighted level clusters.

    tolerance_pct: prices within this fraction of each other join one cluster.
    recency_half_life: bars after which a touch's weight halves.
    """
    if not fractals:
        return []
    fr = sorted(fractals, key=lambda f: f.price)
    groups: list[list[Fractal]] = [[fr[0]]]
    for f in fr[1:]:
        anchor = np.mean([g.price for g in groups[-1]])
        if abs(f.price - anchor) / anchor <= tolerance_pct:
            groups[-1].append(f)
        else:
            groups.append([f])

    decay = np.log(2) / max(recency_half_life, 1)
    raw: list[tuple[LevelCluster, float]] = []
    for g in groups:
        weights = [np.exp(-decay * (n_bars - 1 - m.bar_index)) for m in g]
        price = float(np.average([m.price for m in g], weights=weights))
        kinds = {m.kind for m in g}
        kind = "mixed" if len(kinds) == 2 else ("resistance" if "high" in kinds else "support")
        ts = sorted(m.timestamp for m in g)
        cluster = LevelCluster(
            price=price,
            kind=kind,
            touches=len(g),
            strength=0.0,
            first_seen=str(ts[0]),
            last_seen=str(ts[-1]),
            members=[m.price for m in g],
        )
        raw.append((cluster, float(sum(weights)) * len(g) ** 0.5))

    max_w = max(w for _, w in raw)
    out = []
    for cluster, w in raw:
        cluster.strength = w / max_w
        out.append(cluster)
    return sorted(out, key=lambda c: c.price)


def nearest_cluster(clusters: list[LevelCluster], price: float) -> LevelCluster | None:
    if not clusters:
        return None
    return min(clusters, key=lambda c: abs(c.price - price))


def clusters_above(clusters: list[LevelCluster], price: float, n: int = 2) -> list[LevelCluster]:
    return [c for c in clusters if c.price > price][:n]


def clusters_below(clusters: list[LevelCluster], price: float, n: int = 2) -> list[LevelCluster]:
    below = [c for c in clusters if c.price < price]
    return list(reversed(below[-n:]))
