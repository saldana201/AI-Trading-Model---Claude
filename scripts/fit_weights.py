"""Phase 20 Stage 2 — fit and validate scorer weights from the cached dataset.

Fast, no data access, reproducible. Reads the dataset built by
scripts.build_dataset, runs the CPCV + walk-forward re-fit, prints the verdict,
and (only with --write, and only if the re-fit cleared the out-of-sample bar)
writes the proposed weights into confluence.json under scoring.weights.

    python -m scripts.fit_weights --dataset backtest/weight_dataset.json
    python -m scripts.fit_weights --dataset backtest/weight_dataset.json --write

The --write guard is deliberate: deploying weights that did not survive OOS
validation is the exact mistake this whole phase exists to prevent, so it
refuses unless the verdict is trustworthy (override with --force at your own
risk).
"""

from __future__ import annotations

import argparse
import json
import os

from backtest.weight_fit import Dataset, cpcv_fit, render_fit


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", type=str, default="backtest/weight_dataset.json")
    ap.add_argument("--threshold", type=float, default=6.0,
                    help="score gate the composer uses to admit a setup")
    ap.add_argument("--blocks", type=int, default=8)
    ap.add_argument("--test-blocks", type=int, default=2)
    ap.add_argument("--horizon", type=int, default=15)
    ap.add_argument("--embargo", type=int, default=5)
    ap.add_argument("--write", action="store_true",
                    help="write proposed weights to confluence.json if trustworthy")
    ap.add_argument("--force", action="store_true",
                    help="write even if the re-fit did not clear the OOS bar")
    ap.add_argument("--config", type=str, default="confluence.json")
    args = ap.parse_args()

    with open(args.dataset) as fh:
        data = json.load(fh)
    rows = data["rows"] if isinstance(data, dict) else data
    ds = Dataset.from_rows(rows)
    print(f"[fit] {len(ds)} rows from {args.dataset}")

    if len(ds) < args.blocks * 2:
        print(f"\n[fit] STOP: only {len(ds)} rows — far too few to fit weights "
              f"(need dozens, ideally 100+).\n"
              f"      This almost always means Stage 1 ran on the wrong data.\n"
              f"      Rebuild with real data and enough history:\n\n"
              f"        CONFLUENCE_DATA=yfinance python -m scripts.build_dataset "
              f"--span 500 --out {args.dataset}\n\n"
              f"      Then check the line it prints — it reports how many filled "
              f"setups it captured and the split by direction.")
        return

    try:
        fr = cpcv_fit(ds, threshold=args.threshold, n_blocks=args.blocks,
                      test_blocks=args.test_blocks, horizon=args.horizon,
                      embargo=args.embargo)
    except ValueError as exc:
        print(f"\n[fit] cannot run CPCV: {exc}")
        return
    print()
    print(render_fit(fr))

    if not args.write:
        print("\n[fit] dry run. Re-run with --write to apply (guarded by the verdict).")
        return

    trustworthy = "TRUSTWORTHY" in fr.verdict
    if not trustworthy and not args.force:
        print("\n[fit] REFUSING to write: the re-fit did not clear the "
              "out-of-sample bar. This is the safeguard working. Use --force "
              "only if you understand the risk.")
        return

    _write_weights(args.config, fr.weights)
    tag = "" if trustworthy else " (FORCED — did NOT clear OOS bar)"
    print(f"\n[fit] wrote scoring.weights to {args.config}{tag}")


def _write_weights(path: str, weights: dict) -> None:
    cfg = {}
    if os.path.exists(path):
        with open(path) as fh:
            cfg = json.load(fh)
    cfg.setdefault("scoring", {})["weights"] = weights
    with open(path, "w") as fh:
        json.dump(cfg, fh, indent=2)


if __name__ == "__main__":
    main()
