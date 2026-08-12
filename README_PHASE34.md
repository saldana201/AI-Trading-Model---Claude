# Phase 34 — fundamentals confluence + suppressed-setup visibility

Extract at the repo root. Paths mirror the repo, so files land in place.

**Base: `stabilize/phase-0`.** Built and verified against that branch, not
`master` — `master` does not have the Phase 33 UI, and extracting there would
revert `page.jsx`, `panels.jsx` and `globals.css`.

## Files

### New — safe to extract over anything

| Path | |
|---|---|
| `orchestrator/fundamentals_confluence.py` | the deterministic module |
| `apps/api/fundamentals.py` | API installer |
| `apps/web/components/FundamentalsBadge.jsx` | badge + drill-down |
| `tests/test_fundamentals_confluence.py` | 34 tests |
| `scripts/strict_validation_probe.py` | validator-scope probe |
| `scripts/gen_hints_doc.mjs` | doc generator |
| `docs/FUNDAMENTALS_WIRING.md` | full wiring notes |

### Edited — **DIFF BEFORE OVERWRITE** if you have local changes

| Path | Change |
|---|---|
| `apps/web/app/globals.css` | FULL FILE = phase-0 content + an appended Phase-34 block. If you've touched CSS since the Phase 33 zip, diff — the appended block starts at `/* ---- fundamentals badge + suppressed section (Phase 34) ---- */` and is the only addition |
| `apps/web/components/panels.jsx` | FULL FILE. Adds `SuppressedSetups`, swaps the bare confidence number for `ConfluenceScore`, adds the badge. Phase 33 already rewrote this file — diff if you've edited it since |
| `apps/web/components/Hints.jsx` | FULL FILE. Adds a `title` to each of the 9 existing entries + a new `fundamentals` entry. No existing text changed |
| `docs/reading-confluence.md` | **GENERATED.** Do not hand-edit any more — edit `HINTS` and run the generator |

### Edited — small surgical diffs

| Path | Change |
|---|---|
| `config/schema.py` | `fundamentals` section + validation |
| `orchestrator/composer.py` | 1 import, 1 helper, 3 edits × 2 call sites |
| `orchestrator/scoring.py` | `_score_mode()` + branch in the catalyst slot |
| `alerts/engine.py` | one key in `setup_meta` |
| `apps/api/main.py` | 2 lines appended at EOF |
| `tests/test_phase14.py` | `GATE_NAMES` gains `"fundamentals"` |

`apps/web/app/page.jsx` is **not** in this zip. The Phase 33 three-tier layout
is untouched.

## Run

```bash
CONFLUENCE_DATA=synthetic python3 -m pytest tests/ -q
cd apps/web && npm run build && cd ../..
node scripts/gen_hints_doc.mjs --check

CONFLUENCE_DATA=synthetic uvicorn apps.api.main:app --port 8000
cd apps/web && npm run dev
```

## Defaults are deliberately inert

Nothing about your current output changes until you turn something on:

- `score_mode: "legacy"` — the composite is byte-identical. Pinned by
  `test_legacy_mode_scoring_is_unchanged` (7.9, derived from the pre-change
  scorer).
- `strict_validation: false` — the validator sees the same evidence as before.
- `earnings_window_days: 7` — matches the engine's own constant.

The one thing that **does** change by default: setups with earnings inside 7
days are now suppressed (`earnings_gate: "suppress"`) instead of merely
score-penalized. Verified end to end on synthetic — CEG, earnings in 1 day,
appears in the suppressed list with its reason. Set `earnings_gate` to `"flag"`
to warn instead, or `"ignore"` for the old behaviour.

## Two things to eyeball

1. **The suppressed list was invisible.** It only rendered when *zero* setups
   cleared the gates, while the header always counted it — so the gate vanished
   exactly when it was working. It's now a collapsible section that always shows
   when non-empty. Open a snapshot with setups present and confirm you can see
   the 12 suppressed candidates.

2. **`fund —` is not `fund F`.** A muted dash means no component could be
   scored; a red F means it was measured and it's bad. On live data the
   yfinance path swallows errors into an empty dict fairly often, so watch how
   many dashes you get before trusting the letters.

## Next

Run the probe on live data before enabling `strict_validation`:

```bash
python3 -m scripts.strict_validation_probe          # synthetic: 0 of 210 changed
CONFLUENCE_DATA=yfinance python3 -m scripts.strict_validation_probe
```

And A/B `score_mode` with the existing backtest scripts before trusting
`"assessment"`. Per the standing rule, a raw backtest improvement isn't enough —
it needs to clear Deflated Sharpe out-of-sample inside the CPCV splits.
