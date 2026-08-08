"use client";
import { useState, useId } from "react";

/*
  Phase-33 explainer layer. One <InfoHint> per panel header + a one-line
  caption under it. Content lives in HINTS below so the in-panel text and
  the reference doc (docs/reading-confluence.md) share one source of truth —
  edit here, regenerate the doc, they can never disagree.

  Drift-safe: this file is additive. Each panel imports { InfoHint, PanelCaption }
  and adds two lines; no existing panel logic changes.
*/

export const HINTS = {
  regime: {
    caption: "The one-glance verdict: is the tape favorable, hostile, or directionless right now?",
    read: [
      "Verdict (risk-on / risk-off / chop) is a rules-first composite over VIX, index levels, the MA stack, breadth, index RVOL, and gamma sign — not an LLM opinion. It is reproducible bar-by-bar.",
      "The gauge is a −10…+10 risk-on score. The white pin is where today sits; +3 or higher colors green (constructive), −3 or lower red (defensive), the middle band is chop.",
      "Component bars show what drove the score — each input's signed contribution. A green bar pushed risk-on, red pushed risk-off; bar length is the size of that push.",
    ],
    caveat: "chop isn't a failure state — it's the system telling you to stand aside. Most no-trade days come from here.",
  },
  vix: {
    caption: "Where fear sits relative to its own recent structure — the market's risk backdrop.",
    read: [
      "Spot is current VIX. The gold pivot is the fractal cluster nearest spot; VIX below pivot is the constructive backdrop for longs, above pivot is the warning.",
      "Dashed rungs are upside targets (higher fear, bearish for stocks) and downside targets (falling fear, supportive). They are the next fractal clusters above and below, not forecasts.",
      "Alignment state reads VIX against price: confirming_bullish and diverging_supportive are tailwinds; diverging_warning (fear rising with price) and confirming_bearish are headwinds.",
    ],
    caveat: "your own backtest found VIX alignment carried little predictive signal — treat it as context, not a trigger.",
  },
  index: {
    caption: "The level map for QQQ / SPY: the rungs price has to clear or lose to change character.",
    read: [
      "Gold rungs are the bullish/bearish triggers — the alert-arming levels. A break-and-hold above the bull trigger is what arms long setups.",
      "Dashed rungs are the weekly pivot / ceiling / floor (classic pivot math). Above weekly pivot = constructive structure; the badge states which side you're on.",
      "Colored rungs are fractal support (green) and resistance (red) clusters; rung width is cluster strength — recency-weighted and touch-weighted, so a wide rung has been tested more and more recently.",
      "RVOL badge turns amber at ≥1.3× — a level break on high relative volume is worth more than one on thin volume.",
    ],
    caveat: "levels are structured pattern detection, not price predictions — they mark where behavior tends to change, nothing more.",
  },
  tape: {
    caption: "The character of the move: who's in control and whether momentum agrees with price.",
    read: [
      "Phase is a Wyckoff-style read: mark_up / accumulation / failed_breakdown are constructive; distribution / mark_down are not; exhaustion and failed_breakout are caution flags.",
      "Trend slope, up/down volume ratio, and 60-day range position are the evidence behind the phase label — the numbers it was derived from.",
      "The RSI stack runs monthly → 30m. Cells turn red (overbought) or green (oversold). Divergence between price and RSI across timeframes is where reversals often start.",
    ],
    caveat: "phase labels describe the recent past; they tell you the current regime of the move, not its next bar.",
  },
  options: {
    caption: "Where dealer hedging is likely to dampen or accelerate moves — the invisible hand on intraday price.",
    read: [
      "Net GEX is dollar gamma per 1% move. Positive gamma (green header) = dealers dampen moves, walls act as magnets/pins. Negative gamma (amber) = dealers amplify, breaks accelerate.",
      "Bars are GEX by strike: green above the line is positive, red is negative. The gold dashed line is the zero-gamma flip — the level where the regime switches.",
      "Call wall (largest positive GEX) tends to cap; put wall tends to support. The white dashed line is spot.",
    ],
    caveat: "this is a documented approximation (dealers long calls / short puts) — a positioning estimate, never dealer ground truth.",
  },
  rotation: {
    caption: "Which sectors money is moving into and out of — where to hunt, and where to avoid.",
    read: [
      "Relative performance is each ETF vs SPY over 1 / 4 / 12 weeks. Green outperformed, red lagged. The multi-window view catches early rotation, not just what already ran.",
      "Status: leading (top quartile 4w+12w) is where setups are strongest; improving is early rotation — the name reclaiming strength on volume; deteriorating and lagging are to avoid.",
      "RVOL flags where the move has participation behind it.",
    ],
    caveat: "sector strength is a where-to-look filter, not a setup on its own — a leading sector still needs a stock that passes every quality gate.",
  },
  setups: {
    caption: "The composed trade ideas — or the explicit reason there aren't any.",
    read: [
      "Each card: entry trigger (a condition to wait for, not a prediction), stop, target 1/2, and R:R. A setup only exists if R:R clears the gate (T1 ≥ 1.0, T2 ≥ 2.0).",
      "Confidence is out of 10 and colors green ≥7.5, gold ≥6.5, grey below. It measures how many engines agree — NOT a probability of profit.",
      "'No-trade conditions' or 'no setups cleared the gates' is a real output: the funnel line tells you exactly which gate stopped each candidate.",
    ],
    caveat: "confidence is a confluence measure. The composed-setup product underperformed buy-and-hold in backtest — treat every card as one input to your own decision.",
  },
  alerts: {
    caption: "The live lifecycle: what each armed setup is doing right now.",
    read: [
      "Each row is a state transition with the price and reason that caused it. Gold badges (TRIGGERED, TRIMMED_T1) are progress; green (ACTIVE, TRAILING, CLOSED) is a working trade; red (STOPPED, DETERIORATED, INVALIDATED) is an exit.",
      "DETERIORATED is the key one: the trade's stop hasn't hit, but the thesis broke (e.g. VIX reclaimed pivot while the index lost its weekly pivot) — an early warning the stop alone wouldn't give.",
    ],
    caveat: "the bar feed is daily unless you've wired intraday ingest — so transitions evaluate on daily closes, not tick by tick.",
  },
  journal: {
    caption: "The honest scorecard: what the system's ideas actually did, in R-multiples.",
    read: [
      "R is the outcome in units of initial risk: +2R means twice what you risked, −1R is a full stop. Win rate and average R at the top are the resolved-trade summary.",
      "Live and backtest use one definition of 'win' (half off at T1, breakeven stop, trail), so this table and the backtest calibration can't contradict each other.",
    ],
    caveat: "small samples lie — a high win rate over few trades isn't edge. Read it next to the calibration bands before trusting any confidence level.",
  },
};

export function InfoHint({ k }) {
  const h = HINTS[k];
  const [open, setOpen] = useState(false);
  const id = useId();
  if (!h) return null;
  return (
    <span className="hint" style={{ position: "relative", display: "inline-flex" }}>
      <button
        type="button"
        className="hintbtn"
        aria-label="How to read this panel"
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onClick={() => setOpen((v) => !v)}
        onBlur={() => setOpen(false)}
      >i</button>
      {open && (
        <span className="hintpop" id={id} role="tooltip">
          <b>How to read this</b>
          <ul>{h.read.map((line, i) => <li key={i}>{line}</li>)}</ul>
          <span className="hintcaveat">⚠ {h.caveat}</span>
        </span>
      )}
    </span>
  );
}

export function PanelCaption({ k }) {
  const h = HINTS[k];
  if (!h) return null;
  return <p className="panelcap">{h.caption}</p>;
}
