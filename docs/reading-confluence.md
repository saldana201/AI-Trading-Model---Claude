# How to read Confluence

A plain-language guide to every panel on the dashboard. Each section below is the
same explanation that appears in the panel's ℹ tooltip, plus the context that
does not fit in a tooltip. In-panel hints and this document are generated from one
source (`components/Hints.jsx`), so they cannot disagree.

## Read the board in this order

The dashboard has a natural top-to-bottom logic. Read it as a funnel:

1. **Market regime** — is today favorable, hostile, or directionless? If it is chop, the honest answer is often *do nothing*, and the rest is context.
2. **VIX + index levels** — the risk backdrop and the specific price rungs that matter.
3. **Tape + options + rotation** — the character of the move, dealer positioning, and where money is rotating. These narrow *where* to look.
4. **Setups** — what the engines composed from all of the above, or the explicit reason there is nothing.
5. **Alerts + journal** — what is live right now, and what the system's ideas have actually done.

## The one thing to keep in mind

Every number on this board traces to a deterministic engine — fractal clusters,
pivot math, GARCH volatility, GEX from option chains. That makes them auditable
facts. It does **not** make them predictions. In definitive backtesting the
composed-setup product underperformed buy-and-hold on every risk-adjusted metric.
So treat this board as *decision support* — a fast, honest read of the tape you
interpret yourself — not as a signal to follow. The confidence score measures how
many engines agree, never a probability of profit.

---

## Market regime

*The one-glance verdict: is the tape favorable, hostile, or directionless right now?*

**How to read it**

- Verdict (risk-on / risk-off / chop) is a rules-first composite over VIX, index levels, the MA stack, breadth, index RVOL, and gamma sign — not an LLM opinion. It is reproducible bar-by-bar.
- The gauge is a −10…+10 risk-on score. The white pin is where today sits; +3 or higher colors green (constructive), −3 or lower red (defensive), the middle band is chop.
- Component bars show what drove the score — each input's signed contribution. A green bar pushed risk-on, red pushed risk-off; bar length is the size of that push.

**Caveat** — chop isn't a failure state — it's the system telling you to stand aside. Most no-trade days come from here.

## VIX framework

*Where fear sits relative to its own recent structure — the market's risk backdrop.*

**How to read it**

- Spot is current VIX. The gold pivot is the fractal cluster nearest spot; VIX below pivot is the constructive backdrop for longs, above pivot is the warning.
- Dashed rungs are upside targets (higher fear, bearish for stocks) and downside targets (falling fear, supportive). They are the next fractal clusters above and below, not forecasts.
- Alignment state reads VIX against price: confirming_bullish and diverging_supportive are tailwinds; diverging_warning (fear rising with price) and confirming_bearish are headwinds.

**Caveat** — your own backtest found VIX alignment carried little predictive signal — treat it as context, not a trigger.

## Index levels (QQQ / SPY)

*The level map for QQQ / SPY: the rungs price has to clear or lose to change character.*

**How to read it**

- Gold rungs are the bullish/bearish triggers — the alert-arming levels. A break-and-hold above the bull trigger is what arms long setups.
- Dashed rungs are the weekly pivot / ceiling / floor (classic pivot math). Above weekly pivot = constructive structure; the badge states which side you're on.
- Colored rungs are fractal support (green) and resistance (red) clusters; rung width is cluster strength — recency-weighted and touch-weighted, so a wide rung has been tested more and more recently.
- RVOL badge turns amber at ≥1.3× — a level break on high relative volume is worth more than one on thin volume.

**Caveat** — levels are structured pattern detection, not price predictions — they mark where behavior tends to change, nothing more.

## Tape character

*The character of the move: who's in control and whether momentum agrees with price.*

**How to read it**

- Phase is a Wyckoff-style read: mark_up / accumulation / failed_breakdown are constructive; distribution / mark_down are not; exhaustion and failed_breakout are caution flags.
- Trend slope, up/down volume ratio, and 60-day range position are the evidence behind the phase label — the numbers it was derived from.
- The RSI stack runs monthly → 30m. Cells turn red (overbought) or green (oversold). Divergence between price and RSI across timeframes is where reversals often start.

**Caveat** — phase labels describe the recent past; they tell you the current regime of the move, not its next bar.

## Options positioning

*Where dealer hedging is likely to dampen or accelerate moves — the invisible hand on intraday price.*

**How to read it**

- Net GEX is dollar gamma per 1% move. Positive gamma (green header) = dealers dampen moves, walls act as magnets/pins. Negative gamma (amber) = dealers amplify, breaks accelerate.
- Bars are GEX by strike: green above the line is positive, red is negative. The gold dashed line is the zero-gamma flip — the level where the regime switches.
- Call wall (largest positive GEX) tends to cap; put wall tends to support. The white dashed line is spot.

**Caveat** — this is a documented approximation (dealers long calls / short puts) — a positioning estimate, never dealer ground truth.

## Sector rotation

*Which sectors money is moving into and out of — where to hunt, and where to avoid.*

**How to read it**

- Relative performance is each ETF vs SPY over 1 / 4 / 12 weeks. Green outperformed, red lagged. The multi-window view catches early rotation, not just what already ran.
- Status: leading (top quartile 4w+12w) is where setups are strongest; improving is early rotation — the name reclaiming strength on volume; deteriorating and lagging are to avoid.
- RVOL flags where the move has participation behind it.

**Caveat** — sector strength is a where-to-look filter, not a setup on its own — a leading sector still needs a stock that passes every quality gate.

## Trade setups

*The composed trade ideas — or the explicit reason there aren't any.*

**How to read it**

- Each card: entry trigger (a condition to wait for, not a prediction), stop, target 1/2, and R:R. A setup only exists if R:R clears the gate (T1 ≥ 1.0, T2 ≥ 2.0).
- Confidence is out of 10 and colors green ≥7.5, gold ≥6.5, grey below. It measures how many engines agree — NOT a probability of profit.
- 'No-trade conditions' or 'no setups cleared the gates' is a real output: the funnel line tells you exactly which gate stopped each candidate.

**Caveat** — confidence is a confluence measure. The composed-setup product underperformed buy-and-hold in backtest — treat every card as one input to your own decision.

## Alert feed

*The live lifecycle: what each armed setup is doing right now.*

**How to read it**

- Each row is a state transition with the price and reason that caused it. Gold badges (TRIGGERED, TRIMMED_T1) are progress; green (ACTIVE, TRAILING, CLOSED) is a working trade; red (STOPPED, DETERIORATED, INVALIDATED) is an exit.
- DETERIORATED is the key one: the trade's stop hasn't hit, but the thesis broke (e.g. VIX reclaimed pivot while the index lost its weekly pivot) — an early warning the stop alone wouldn't give.

**Caveat** — the bar feed is daily unless you've wired intraday ingest — so transitions evaluate on daily closes, not tick by tick.

## Outcome journal

*The honest scorecard: what the system's ideas actually did, in R-multiples.*

**How to read it**

- R is the outcome in units of initial risk: +2R means twice what you risked, −1R is a full stop. Win rate and average R at the top are the resolved-trade summary.
- Live and backtest use one definition of 'win' (half off at T1, breakeven stop, trail), so this table and the backtest calibration can't contradict each other.

**Caveat** — small samples lie — a high win rate over few trades isn't edge. Read it next to the calibration bands before trusting any confidence level.

---

*Decision-support tooling, not investment advice. Levels are heuristic pattern
detection; validate with backtests before trading against them.*
