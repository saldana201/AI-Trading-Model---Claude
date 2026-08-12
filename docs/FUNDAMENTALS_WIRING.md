# Phase 34 — wiring fundamentals confluence

Base branch: `stabilize/phase-0`. Everything here is additive, and every new
behaviour is behind a config flag that defaults to the pre-Phase-34 path.

## The one invariant this phase was built around

**With default config, scoring output is unchanged.** `orchestrator/scoring.py`
computes `score = raw / total_w * 10`, so adding a twelfth component would have
moved the denominator, shifted every historical score, changed what
`risk.min_score = 6.0` means, and quietly invalidated the calibration bands
(`<6.5` / `6.5-7.5` / `>=7.5`) that `BenchmarkStrip` and `CalibrationPanel`
display. So no component was added. The existing `catalyst_fundamental` slot
gained a mode switch instead — same key, same weight 1.0, same `total_w`.

`tests/test_fundamentals_confluence.py::test_legacy_mode_scoring_is_unchanged`
pins the exact composite (7.9) for a fixed ctx. That number was obtained by
executing the **pre-change** `orchestrator/scoring.py` against that ctx, not by
reading it back off the patched module. If that assertion ever fails, the
composite moved and the calibration bands need re-deriving.

## Files

### New

| File | What |
|---|---|
| `orchestrator/fundamentals_confluence.py` | `assess` / `gate` / `enrich_setup` / `apply` |
| `apps/api/fundamentals.py` | two endpoints, auth'd |
| `tests/test_fundamentals_confluence.py` | 34 tests |
| `scripts/strict_validation_probe.py` | measures the validator change before enabling it |
| `scripts/gen_hints_doc.mjs` | regenerates `docs/reading-confluence.md` from `HINTS` |
| `apps/web/components/FundamentalsBadge.jsx` | badge + drill-down evidence |

### Edited

| File | Diff |
|---|---|
| `config/schema.py` | `fundamentals` section in `DEFAULTS` + validation |
| `orchestrator/composer.py` | 1 import, 1 helper, 3 edits × 2 call sites |
| `orchestrator/scoring.py` | `_score_mode()` + a branch inside the catalyst slot |
| `alerts/engine.py` | one key added to `setup_meta` |
| `apps/api/main.py` | 2 lines appended |
| `apps/web/components/panels.jsx` | `SuppressedSetups`, `ConfluenceScore` swap, badge |
| `apps/web/components/Hints.jsx` | `title` on each entry + a `fundamentals` entry |
| `apps/web/app/globals.css` | appended Phase-34 block only |
| `docs/reading-confluence.md` | **generated** — no longer hand-edited |
| `tests/test_phase14.py` | `GATE_NAMES` gains `"fundamentals"` |

## Exact wiring lines

`apps/api/main.py` (appended, drift-safe):

```python
# ---------- Phase 34: fundamentals confluence ----------

from apps.api.fundamentals import install as install_fundamentals  # noqa: E402
install_fundamentals(app, get_state, _ensure_snapshot)
```

`orchestrator/composer.py` — in **both** `compose()` and `explore()`, directly
after `fund = self.fundamentals.get_snapshot(sym)`:

```python
# compose(): a hard gate
fx = fundamentals_confluence.apply(setup, fund, direction)
if not fx["allowed"]:
    suppressed.append({"symbol": sym, "pinned": sym in self.pinned,
                       "reason": fx["reason"]})
    continue

# explore(): records the gate instead — that path exists to report every gate
fx = fundamentals_confluence.apply(setup, fund, direction)
gate("fundamentals", fx["allowed"], fx["reason"])
```

plus one key in each `ctx` (`"fundamentals_assessment": fx["assessment"]`) and,
in each `setup |= {...}` merge, one added key and one amended:

```python
"fundamentals_assessment": fx["assessment"],
"risks": scored["risks"] + fx["warnings"],
```

`apps/web/components/panels.jsx` — the setup-card head:

```jsx
<FundamentalsBadge symbol={x.symbol} direction={x.direction}
                   assessment={x.fundamentals_assessment} />
<ConfluenceScore value={x.confidence} calibration={x.calibration} compact />
```

and `<SuppressedSetups suppressed={setups.suppressed} />` before `</article>`,
in both the no-trade branch and the normal branch.

`page.jsx` was **not touched.** The Phase 33 three-tier layout is the
information hierarchy; everything this phase adds lives inside the Setups card,
which is already Tier 2.

## Config keys

```jsonc
"fundamentals": {
  "enabled": true,               // false = full bypass
  "earnings_gate": "suppress",   // suppress | flag | ignore
  "earnings_window_days": 7,     // see note below
  "score_mode": "legacy",        // legacy | assessment
  "strict_validation": false,    // see "known defect" below
  "weights": { "growth": 0.40, "profitability": 0.20,
               "valuation": 0.20, "sponsorship": 0.20 }
}
```

**Why the window defaults to 7, not 5.** `engines/fundamentals_mcp/logic.py`
hardcodes `EARNINGS_WINDOW_DAYS = 7` and stamps `in_earnings_window` onto every
snapshot. That flag drives `setup["earnings_flag"]` and the legacy scoring
penalty. Defaulting the gate to 7 means an unconfigured system has exactly one
earnings window. Change it and the gate and the display flag diverge on
purpose — the badge will show an EARNINGS chip on the gate's window while the
card's "earnings window" pill follows the engine's.

The gate **never reads `in_earnings_window`**; it computes from
`days_to_earnings`. `test_gate_ignores_a_contradictory_engine_flag` pins that.

## Known defect this phase documents (and does not yet fix by default)

`orchestrator/validator.py::collect_numbers()` walks the whole evidence payload.
`composer.py` puts the fundamentals snapshot in that payload, so `forward_pe` —
a ratio, commonly 15–55 — sits in the set of numbers a price level may "trace"
to at 0.15% tolerance. For a sub-$60 symbol, a fabricated stop can validate
against a P/E.

`test_KNOWN_DEFECT_forward_pe_widens_the_traceable_number_set` demonstrates it
rather than asserting it away. `fundamentals.strict_validation = true` closes it
by dropping the fundamentals branch from the copy handed to `validate_setup`
(the audit `evidence` record is never filtered). That can only make validation
**stricter**, so it stays off until measured:

```
CONFLUENCE_DATA=synthetic python3 -m scripts.strict_validation_probe
  → symbols 143 · setups checked 210 · changed by strict mode 0
```

Zero on synthetic is **not** proof the hole is closed — it means the synthetic
P/E range did not happen to overlap the synthetic price range. Re-run on live
data before flipping the default.

## Deliberate deviations from the original brief

| Brief said | Why not |
|---|---|
| `assess(snapshot, direction, horizon)` | there is no `horizon` in the composer or any setup dict; inventing one to satisfy a signature would be fiction |
| attach to `setup["setup_meta"]` | `setup_meta` is a field on the `Trade` dataclass (`alerts/lifecycle.py:64`), populated at arm time. On a composer setup it would be a key nothing reads. Attached flat as `fundamentals_assessment`; only the grade string is forwarded into `setup_meta` |
| `setup["warnings"] += [...]` | no `warnings` field exists anywhere. `risks` is the existing vocabulary and already renders |
| one composer call site | there are two (`compose`, `explore`). Both wired |
| `earnings_window_days: 5` | see above |
| add a component if no slot exists | the slot exists, and a new weight moves every score |
| general UX pass | Phase 33 already set the hierarchy; a literal reading would have pulled `RotationTable` and `JournalPanel` out of `.demoted` and undone it |

## What the four components can actually see

The real snapshot carries no margin trend, no guidance, no sponsorship trend and
no history. So:

- **growth** — the only component with two real inputs (`revenue_growth`,
  `eps_growth`). Its curve is anchored on the same bands the engine uses for
  `growth_grade`, so the two surfaces can't tell opposite stories.
- **profitability** — a single `profit_margin` point.
- **valuation** — bare `forward_pe` against absolute bands. There is no peer set
  in the repo, so a cheap utility scores like a cheap semiconductor. Flagged
  `low_confidence`.
- **sponsorship** — `institutional_pct` as a level. Rising and falling ownership
  at the same percentage score identically. Flagged `low_confidence`.

The yfinance provider swallows every exception into `info = {}`, so all-None
snapshots are a common live path. `assess()` returns grade `"unavailable"` —
never `"F"` — and the badge renders a muted dash. Watch how often that happens
on live data before trusting the letter.

## Verification

```
CONFLUENCE_DATA=synthetic python3 -m pytest tests/ -q
  → 410 passed, 4 failed

cd apps/web && npm run build            → ✓ compiled, 5 routes
node scripts/gen_hints_doc.mjs --check  → current (10 sections)
```

The 4 failures are pre-existing and environmental — `mcp` and `anthropic` were
not installable in the verification container, plus one auth env leak. Identical
set before and after this phase (baseline: 380 passed / 4 failed).
