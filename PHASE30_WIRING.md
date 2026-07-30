# Phase 30 — wiring the honest-mode UI

Two files: `Honest.jsx` (new) and `Book.jsx` (one line changed to use it).
Both verified to parse as valid JSX with @babel/parser.

## Add to `apps/web/app/page.jsx`

```jsx
import { BenchmarkStrip, CalibrationPanel } from "../components/Honest";
```

Place `<BenchmarkStrip />` high — directly under `<RegimeStrip .../>` — so a
trade idea is never seen without the benchmark comparison beside it:

```jsx
<RegimeStrip regime={d.regime} />
<BenchmarkStrip />
```

Place `<CalibrationPanel />` near `<Explorer />` / `<Assistant />`:

```jsx
<CalibrationPanel />
```

## What each does

- **BenchmarkStrip** — persistent, dismissible. States the measured result
  (+37.4% vs QQQ +111.7%, -33.0% vs -22.8% drawdown, Sharpe 0.55 vs 1.00) and
  that the index outperformed. Reads `/api/benchmark-context`.
- **ConfluenceScore** — replaces every bare `conf 8.2`. Shows "confluence 8.2"
  plus the historical avg-R for that band. Border turns amber when the band has
  <30 trades and red when the band's historical average is negative. Tooltip:
  "how many engines agree. NOT a probability of profit."
- **CalibrationPanel** — the full per-band table with the plain-language reading
  of each band.

## Naming decision (deliberate)

The internal field stays `confidence`. It is threaded through `scoring.py`,
`composer.py`, the harness, the SQLite journal schema, and the REST resources;
renaming it is a multi-file refactor with real drift risk — the same pattern that
destroyed the Phase 10/11 features previously. The relabel is display-layer only:
the UI says "confluence", the wire format is unchanged. Same benefit, no risk.

## Remaining Phase 30 item

`Assistant.jsx` and `Chat.jsx` still surface raw confidence in prose. Swap those
call sites to `<ConfluenceScore />` when convenient — the component is reusable
and self-fetches its calibration if not passed any.

## Do this first

Your fingerprint showed `force_direction=long` persisted in `confluence.json`.
Delete that key (or the file) — it silently constrains every run.
