# Phase 12 Hotfix — restores Phase 10/11 features

## What went wrong

The Phase 12 upgrade shipped `composer.py` and `main.py` as **whole-file
replacements**, built against a snapshot of `master` that predated your
Phase 10 and 11 work. Applying it (commit `a216b28`, "removed version 2")
silently deleted:

| Lost | Where | Impact |
|---|---|---|
| `load_pinned()` + pinned-ticker pipeline | `composer.py` | **Pinned tickers stopped working entirely.** `tests/test_phase10.py` couldn't even import. |
| `funnel` diagnostic block | `composer.py` | The Phase 11 transparency work — why candidates were dropped — vanished from every snapshot. |
| `pinned` flag on setups/suppressed rows | `composer.py` | No way to tell pinned outcomes from ordinary ones. |
| `/api/journal` endpoint | `main.py` | Outcome journal / R-multiple reporting unreachable over HTTP. |
| `pinned` + `watchlist_sectors` + `autoarm_et` in `/api/health` | `main.py` | Startup diagnostics degraded. |

Test collection was broken, so the suite couldn't run at all:
`ImportError: cannot import name 'load_pinned'`.

**This was my error** — I retrofitted against a stale clone and replaced
files instead of layering onto them.

## What this hotfix does

Takes the **Phase 11 versions** of both files (recovered from commit
`2303b6a`) and applies the Phase 12 config retrofit *onto* them, so
nothing is lost in either direction. Only two files change.

Everything Phase 12 added still works: config layering, presets, the
tunable chop gate, and the trade assistant (`assistant/`, `config/`,
`apps/api/phase12.py`, and the JSX panels were all additive and were never
affected).

## Applying

From the repo root:

```bash
cp hotfix/orchestrator/composer.py orchestrator/composer.py
cp hotfix/apps/api/main.py         apps/api/main.py

python3 -m pytest tests/ -q        # 160 passed
```

## Verified after the fix

- **160 tests pass** — every phase green simultaneously (was: collection error)
- `/api/health` reports your real pinned list (`OUST`, `AAOI`, `TMC`) and all 16 watchlist sectors
- `/api/journal` returns 200
- `/api/config` and the assistant endpoints unchanged
- Snapshots carry the `funnel` block again

## The bonus: pinned tickers are now actually reachable

Your long-standing diagnostic finding was that pinned features worked but
were never *reached*, because the chop gate short-circuits `compose()`
before the watchlist is processed. Phase 12 turned that gate into a dial,
and now the two features compose correctly:

```
regime: chop
--- hard gate (default, unchanged behavior) ---
  no_trade: True    | funnel present: False     <- gate fires first, as before
--- soft gate ---
  no_trade: False   | chop_gate: soft
  pinned_candidates: ['NVDA']
  pinned_outcomes: {'NVDA': 'screen classified it canslim_leader
                             (need no_setup or overextended)'}
```

Under `chop_mode: "soft"` a pinned name reaches the funnel and reports
exactly why it produced no setup, instead of being invisible. Set it in
`confluence.json`, from the Settings panel, or with the `aggressive`
preset.

## Recommended follow-up

The repo tracks ~61,000 files — `.next/`, `node_modules/`, and `*.db` are
still in git history. That's what made the stale-snapshot mistake easy to
make and hard to see. Worth a `.gitignore` pass and a history prune.
