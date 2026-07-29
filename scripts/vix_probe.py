"""Phase 21 — vix_alignment diagnostic.

Across every real-data run, vix_alignment has been the worst component
(winners score it LOWER than losers). Two possible causes:
  (a) a sign/logic bug in how states map to scores, or
  (b) the signal is genuinely anti-predictive on real data.

Reading engines/vix_mcp/logic.py rules out (a): the state classification is
textbook-correct (price up + VIX up = diverging_warning; price up + VIX falling
below pivot = confirming_bullish). So this probe tests (b) directly: for each
alignment state, what is the DISTRIBUTION of forward index returns? If
'confirming_bullish' is followed by negative forward returns and
'diverging_warning' by positive ones, the signal is inverted on this data and
the honest fix is to down-weight or invert it — not to pretend it works.

This bypasses the composer entirely and measures the raw signal: classify the
VIX/index alignment at each historical day, then look at the index's own return
over the next N days. No setups, no gates — just "does this state predict what
it claims to predict?"

Run:
    CONFLUENCE_DATA=yfinance python -m scripts.vix_probe --symbol QQQ --span 750
"""

from __future__ import annotations

import argparse
from collections import defaultdict

import numpy as np

from engines.shared.providers import BarRequest
from engines.vix_mcp.logic import classify_alignment, compute_vix_levels
from scripts.snapshot import build_provider

VIX_SYMBOL = "^VIX"

# the score each state maps to, from orchestrator/scoring.py ALIGN_VALUE
ALIGN_VALUE = {
    "confirming_bullish": 1.0, "diverging_supportive": 0.7, "neutral_chop": 0.45,
    "diverging_warning": 0.25, "confirming_bearish": 0.0,
}


def probe(symbol="QQQ", span=750, forward=10, lookback=3) -> dict:
    provider, source = build_provider()
    idx = provider.get_bars(BarRequest(symbol, "1d", span + forward + 200))
    vix = provider.get_bars(BarRequest(VIX_SYMBOL, "1d", span + forward + 200))

    # yfinance can return tz-aware / timestamped indices that differ between
    # symbols, so a raw .intersection finds nothing even on identical calendar
    # days. Normalize both to naive dates first.
    def _norm(df):
        df = df.copy()
        try:
            df.index = df.index.tz_localize(None)
        except (TypeError, AttributeError):
            pass
        try:
            df.index = df.index.normalize()      # strip time-of-day
        except (TypeError, AttributeError):
            pass
        df = df[~df.index.duplicated(keep="last")]
        return df

    idx, vix = _norm(idx), _norm(vix)
    common = idx.index.intersection(vix.index)

    if len(common) < 30:
        # fallback: align by position on the overlapping tail. Both are daily
        # bars for the same market, so the last min(len) rows correspond.
        m = min(len(idx), len(vix))
        idx = idx.iloc[-m:].reset_index(drop=True)
        vix = vix.iloc[-m:].reset_index(drop=True)
        idx.index = np.arange(m)
        vix.index = np.arange(m)
        common = idx.index
        aligned_by = "position (timestamp intersection was empty)"
    else:
        idx = idx.loc[common]
        vix = vix.loc[common]
        aligned_by = "date"

    n = len(idx)
    if n < max(60, span // 4):
        return {"available": False,
                "reason": f"only {n} usable bars after alignment ({aligned_by})"}

    by_state = defaultdict(list)     # state -> list of forward returns
    score_ret = []                   # (align_score, forward_return) pairs

    start = max(lookback + 60, n - span)
    for t in range(start, n - forward):
        idx_win = idx.iloc[:t + 1]
        vix_win = vix.iloc[:t + 1]
        try:
            levels = compute_vix_levels(vix_win, 60)
            cls = classify_alignment(idx_win, vix_win, levels, lookback)
        except Exception:
            continue
        state = cls["state"]
        # forward return of the INDEX over the next `forward` days
        p0 = float(idx["close"].iloc[t])
        p1 = float(idx["close"].iloc[t + forward])
        fwd = (p1 / p0 - 1.0)
        by_state[state].append(fwd)
        score_ret.append((ALIGN_VALUE.get(state, 0.45), fwd))

    # summarize each state
    states = {}
    for state, rets in by_state.items():
        arr = np.array(rets)
        states[state] = {
            "n": int(arr.size),
            "mean_fwd_return_pct": round(float(arr.mean()) * 100, 3),
            "win_rate": round(float((arr > 0).mean()), 3),
            "align_score": ALIGN_VALUE.get(state, 0.45),
        }

    # correlation between the alignment SCORE and forward return.
    # positive => signal works as intended; negative => inverted.
    corr = None
    if len(score_ret) > 10:
        s = np.array([x[0] for x in score_ret])
        r = np.array([x[1] for x in score_ret])
        if s.std() > 0 and r.std() > 0:
            corr = float(np.corrcoef(s, r)[0, 1])

    return {"available": True, "symbol": symbol, "source": source,
            "forward_days": forward, "n_observations": len(score_ret),
            "aligned_by": aligned_by,
            "by_state": states, "score_return_correlation": corr}


def render(d: dict) -> str:
    if not d.get("available"):
        return f"vix probe: unavailable ({d.get('reason')})"
    lines = [f"vix_alignment probe — {d['symbol']} ({d['source']}), "
             f"{d['forward_days']}d forward, n={d['n_observations']} "
             f"[aligned by {d.get('aligned_by', '?')}]", ""]
    # order states by the score the system assigns them, best to worst
    order = ["confirming_bullish", "diverging_supportive", "neutral_chop",
             "diverging_warning", "confirming_bearish"]
    lines.append(f"  {'state':<22}{'score':>6}{'n':>5}"
                 f"{'mean fwd %':>12}{'win rate':>10}")
    for st in order:
        if st in d["by_state"]:
            s = d["by_state"][st]
            lines.append(f"  {st:<22}{s['align_score']:>6}{s['n']:>5}"
                         f"{s['mean_fwd_return_pct']:>12}{s['win_rate']:>10}")
    lines.append("")
    corr = d["score_return_correlation"]
    if corr is not None:
        lines.append(f"  score↔forward-return correlation: {corr:+.3f}")
        if corr < -0.05:
            lines.append("  -> INVERTED: higher alignment score predicts LOWER "
                         "forward returns on this data. The signal is backwards "
                         "here. Options: invert it, or down-weight to ~0 and let "
                         "the re-fit decide.")
        elif corr > 0.05:
            lines.append("  -> WORKS: higher score predicts higher forward "
                         "returns, as intended. The negative component-edge was "
                         "likely small-sample noise, not an inverted signal.")
        else:
            lines.append("  -> FLAT: essentially no relationship. The signal "
                         "carries little information on this data; the re-fit "
                         "should down-weight it toward 0.")
    # is the ordering monotonic? (best score should have best forward return)
    scored = [(d["by_state"][s]["align_score"], d["by_state"][s]["mean_fwd_return_pct"])
              for s in d["by_state"]]
    if len(scored) >= 3:
        scored.sort()
        rets = [r for _, r in scored]
        if rets == sorted(rets):
            lines.append("  state ordering is monotonic with forward return "
                         "(signal directionally correct).")
        elif rets == sorted(rets, reverse=True):
            lines.append("  state ordering is EXACTLY REVERSED vs forward return "
                         "(strong evidence the signal is inverted).")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", type=str, default="QQQ")
    ap.add_argument("--span", type=int, default=750)
    ap.add_argument("--forward", type=int, default=10,
                    help="forward return horizon in days")
    ap.add_argument("--lookback", type=int, default=3,
                    help="alignment lookback (must match the engine default)")
    args = ap.parse_args()
    print(render(probe(args.symbol, args.span, args.forward, args.lookback)))


if __name__ == "__main__":
    main()
