# Phase 33 — UI hierarchy + explainer layer

Extract this at the repo root. Paths mirror the repo, so files land in place.

## Files

- `apps/web/app/page.jsx`         — REWRITE. Three-tier layout (answer / output / demoted evidence).
                                     Old version saved locally as page.jsx.bak before swap.
- `apps/web/app/globals.css`      — FULL FILE with appended Phase-33 blocks (hint layer, tier
                                     dividers, demote rule, level-list). If you've edited globals.css
                                     since your last pull, DIFF before overwriting.
- `apps/web/components/Hints.jsx` — NEW. Clickable ⓘ per panel + one HINTS source of truth.
- `apps/web/components/panels.jsx`— EDIT. ⓘ + captions wired into 9 headers; sparse SVG ladder
                                     replaced by clean LevelList in VIX/index panels.
- `docs/reading-confluence.md`    — NEW. Reference guide, generated from the same HINTS object.

## Run

    CONFLUENCE_DATA=synthetic uvicorn apps.api.main:app --port 8000
    cd apps/web && npm run dev

## One knob to eyeball

Demote opacity is `.demoted .card{opacity:.5}` in globals.css — nudge to .4 or .6 to taste.
