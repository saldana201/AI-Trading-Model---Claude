"""Measure what fundamentals.strict_validation would actually change.

WHY THIS EXISTS
---------------
orchestrator/validator.py::collect_numbers() walks the entire evidence
payload. composer.py passes the fundamentals snapshot in that payload, so
`forward_pe` — a ratio, commonly 15-55 — sits in the set of numbers a price
level is allowed to "trace" to at 0.15% tolerance. For any symbol trading in
that range, a fabricated level can validate against a P/E.

Dropping the fundamentals branch from the payload handed to validate_setup
loses nothing legitimate (fundamentals carry no price levels) but can only
make validation STRICTER. Stricter means some setups that pass today would
stop passing, and that is a behaviour change nobody should ship on a hunch.

This script reports the number. Run it before flipping the default.

    CONFLUENCE_DATA=synthetic python3 -m scripts.strict_validation_probe
    python3 -m scripts.strict_validation_probe --symbols NVDA,AMD,MSFT

Reading the output:
  collisions  a price field that traces ONLY through the fundamentals branch.
              Every one of these is a level the validator is currently
              accepting for the wrong reason.
  A zero collision count is not proof of safety — it means the current
  watchlist and the current synthetic P/E distribution did not happen to
  overlap the price range. Re-run on live data before drawing conclusions.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from orchestrator.validator import PRICE_FIELDS, collect_numbers, validate_setup


def _drop_fundamentals(evidence: dict) -> dict:
    return {k: v for k, v in evidence.items() if k != "fundamentals"}


def _traces(value: float, numbers: set[float]) -> bool:
    from orchestrator.validator import REL_TOL
    return any(abs(value - n) <= max(abs(n) * REL_TOL, 0.011) for n in numbers)


def probe_setup(setup: dict, evidence: dict) -> list[dict]:
    """Fields that validate only because of the fundamentals branch."""
    full = collect_numbers(evidence)
    lean = collect_numbers(_drop_fundamentals(evidence))
    out = []
    for field in PRICE_FIELDS:
        value = setup.get(field)
        if value is None:
            continue
        if _traces(value, full) and not _traces(value, lean):
            out.append({"field": field, "value": value,
                        "matched_in_fundamentals": sorted(
                            n for n in full - lean
                            if abs(value - n) <= max(abs(n) * 0.0015, 0.011))})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", default="",
                    help="comma-separated override for the watchlist")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    os.environ.setdefault("CONFLUENCE_DATA", "synthetic")

    from scripts.snapshot import build_provider
    from orchestrator.composer import SetupComposer, load_pinned, load_watchlist
    from engines.levels_mcp.logic import LevelsEngine
    from engines.fundamentals_mcp.logic import (
        FundamentalsEngine, SyntheticFundamentals, YFinanceFundamentals)

    provider, _source = build_provider()          # returns (provider, source)
    levels = LevelsEngine(provider)
    fundamentals = FundamentalsEngine(
        SyntheticFundamentals()
        if os.environ.get("CONFLUENCE_DATA") == "synthetic"
        else YFinanceFundamentals())

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        watchlist = load_watchlist()
        symbols = sorted({s for names in watchlist.values() for s in names})

    composer = SetupComposer.__new__(SetupComposer)   # geometry only
    composer.levels = levels
    composer.pinned = load_pinned()

    rows, checked, collisions = [], 0, 0
    for sym in symbols:
        try:
            level_payload = levels.get_levels(sym)
            fund = fundamentals.get_snapshot(sym)
        except Exception as exc:                       # noqa: BLE001
            rows.append({"symbol": sym, "error": str(exc)[:120]})
            continue
        for direction in ("long", "short"):
            try:
                setup = SetupComposer._construct(composer, sym, direction,
                                                 level_payload)
            except Exception:                          # noqa: BLE001
                continue
            if setup is None:
                continue
            evidence = {"levels": level_payload, "fundamentals": fund}
            checked += 1
            hits = probe_setup(setup, evidence)
            strict_ok = validate_setup(setup, _drop_fundamentals(evidence))["valid"]
            loose_ok = validate_setup(setup, evidence)["valid"]
            if hits or loose_ok != strict_ok:
                collisions += 1
                rows.append({"symbol": sym, "direction": direction,
                             "loose_valid": loose_ok, "strict_valid": strict_ok,
                             "forward_pe": fund.get("forward_pe"),
                             "fields": hits})

    summary = {
        "data_source": os.environ.get("CONFLUENCE_DATA", "live"),
        "symbols": len(symbols),
        "setups_checked": checked,
        "setups_changed_by_strict_mode": collisions,
        "detail": rows,
    }

    if args.json:
        print(json.dumps(summary, indent=2, default=str))
        return 0

    print(f"data source           : {summary['data_source']}")
    print(f"symbols               : {summary['symbols']}")
    print(f"setups checked        : {checked}")
    print(f"changed by strict mode: {collisions}")
    if not rows:
        print("\nNo setup changed outcome. This is NOT proof the hole is closed —")
        print("it means the current price range did not overlap the P/E range.")
        print("Re-run on live data (CONFLUENCE_DATA=live) before concluding.")
    else:
        print("\nsymbol  dir    loose  strict  fwd_pe  fields")
        for r in rows:
            if "error" in r:
                print(f"{r['symbol']:<7} ERROR  {r['error']}")
                continue
            fields = ", ".join(f"{h['field']}={h['value']}" for h in r["fields"])
            print(f"{r['symbol']:<7} {r['direction']:<6} "
                  f"{str(r['loose_valid']):<6} {str(r['strict_valid']):<7} "
                  f"{str(r['forward_pe']):<7} {fields}")
        print("\nEach row is a price level the validator currently accepts for")
        print("the wrong reason. Set fundamentals.strict_validation=true to close it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
