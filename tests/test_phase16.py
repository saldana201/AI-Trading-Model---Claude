"""Phase 16 tests: the Book (setups grouped by direction, with instrument lenses).

The contract being defended:
  - direction is a *partition* — every setup lands in exactly one of long/short;
  - options is a *lens* — it re-shows setups already counted in a direction,
    so long + short == total, while options + shares also == total;
  - empty groups always explain themselves (the chop-gate transparency lesson);
  - the book never invents numbers: contract fields are copied from the engine.
"""

import pytest

from orchestrator.book import (
    build_book, render_book, instrument_label, is_options,
    contract_summary, stock_only_reason,
)


def mk(symbol="AAA", direction="long", instrument="stock",
       suggestion=None, **over):
    s = {"symbol": symbol, "direction": direction, "instrument": instrument,
         "instrument_suggestion": suggestion, "confidence": 7.2,
         "entry_trigger": 100.0, "stop": 96.0, "target_1": 106.0,
         "target_2": 112.0, "risk_reward_t1": 1.5, "sector_etf": "SMH",
         "classification": "canslim_leader", "pinned": False,
         "thesis": "t", "risks": []}
    s.update(over)
    return s


SPREAD = {"expiry": "2026-08-24", "dte": 30, "iv": 0.30, "iv_rank": 0.62,
          "oi": 793, "spread_pct": 0.0211, "expected_move": 16.68,
          "t1_within_expected_move": True, "notes": [],
          "instrument": "call_debit_spread", "long_strike": 100.0,
          "short_strike": 112.0, "reason": "IV rank 62% ≥ 55%"}


# ---------- labels & predicates ----------

def test_instrument_labels():
    assert instrument_label("call_debit_spread") == "CALL SPREAD"
    assert instrument_label("put") == "PUT"
    assert instrument_label(None) == "STOCK"
    assert instrument_label("weird_thing") == "WEIRD THING"


def test_is_options_predicate():
    assert is_options(mk(instrument="call"))
    assert is_options(mk(instrument="put_debit_spread"))
    assert not is_options(mk(instrument="stock"))
    assert not is_options({"symbol": "X"})          # missing -> stock


# ---------- contract summary copies, never derives ----------

def test_contract_summary_copies_engine_fields():
    c = contract_summary(mk(instrument="call_debit_spread", suggestion=SPREAD))
    assert c["expiry"] == "2026-08-24" and c["dte"] == 30
    assert c["long_strike"] == 100.0 and c["short_strike"] == 112.0
    assert c["iv_rank"] == 0.62 and c["open_interest"] == 793
    assert c["label"] == "CALL SPREAD"


def test_contract_summary_single_leg_carries_strike_not_legs():
    single = {"expiry": "2026-08-24", "dte": 30, "strike": 105.0,
              "instrument": "call", "reason": "IV not elevated"}
    c = contract_summary(mk(instrument="call", suggestion=single))
    assert c["strike"] == 105.0
    assert "long_strike" not in c


def test_contract_summary_none_for_shares():
    assert contract_summary(mk(instrument="stock")) is None


def test_stock_only_reason_surfaces_engine_explanation():
    fallback = {"instrument": "stock",
                "reason": "no liquid strike near entry (OI < 200)"}
    assert "no liquid strike" in stock_only_reason(
        mk(instrument="stock", suggestion=fallback))


def test_stock_only_reason_when_engine_absent():
    assert "not attached" in stock_only_reason(mk(instrument="stock"))


# ---------- direction is a partition ----------

def test_long_short_partition_is_complete_and_disjoint():
    plan = {"direction": "long", "setups": [
        mk("AAA", "long"), mk("BBB", "long"), mk("CCC", "short")]}
    b = build_book(plan)
    assert b["counts"]["long"] == 2 and b["counts"]["short"] == 1
    assert b["counts"]["long"] + b["counts"]["short"] == b["counts"]["total"]
    longs = {c["symbol"] for c in b["long"]["setups"]}
    shorts = {c["symbol"] for c in b["short"]["setups"]}
    assert longs.isdisjoint(shorts)


# ---------- options is a lens, not a bucket ----------

def test_options_lens_overlaps_direction_by_design():
    # one long call spread: it is BOTH a long setup and an options setup
    plan = {"direction": "long",
            "setups": [mk("AVGO", "long", "call_debit_spread", SPREAD)]}
    b = build_book(plan)
    assert b["counts"]["total"] == 1
    assert b["counts"]["long"] == 1
    assert b["counts"]["options"] == 1          # same trade, second view
    assert b["options"]["view"] == "cross-cutting"


def test_options_plus_shares_equals_total():
    plan = {"direction": "long", "setups": [
        mk("AVGO", "long", "call_debit_spread", SPREAD),
        mk("MSFT", "long", "stock"),
        mk("NVDA", "long", "call", {"instrument": "call", "strike": 90.0}),
    ]}
    b = build_book(plan)
    c = b["counts"]
    assert c["options"] + c["shares"] == c["total"] == 3
    assert c["by_instrument"] == {"call_debit_spread": 1, "stock": 1, "call": 1}


# ---------- empty groups explain themselves ----------

def test_empty_short_side_explains_the_regime_choice():
    plan = {"direction": "long", "regime": {"regime": "risk_on"},
            "setups": [mk("AAA", "long")]}
    b = build_book(plan)
    assert b["short"]["count"] == 0
    reason = b["short"]["reason"]
    assert "risk_on" in reason and "long" in reason
    assert "not scanned" in reason


def test_forced_direction_is_named_in_the_empty_reason():
    plan = {"direction": "long", "forced": True,
            "regime": {"regime": "chop"}, "setups": [mk("AAA", "long")]}
    assert "forced by config" in build_book(plan)["short"]["reason"]


def test_no_trade_plan_explains_both_sides():
    plan = {"no_trade": True, "regime": {"regime": "chop"}, "setups": []}
    b = build_book(plan)
    assert "no-trade" in b["long"]["reason"]
    assert "no-trade" in b["short"]["reason"]


def test_options_empty_reason_quotes_the_engine():
    plan = {"direction": "long", "setups": [
        mk("AAA", "long", "stock",
           {"instrument": "stock", "reason": "no liquid strike near entry"}),
    ]}
    b = build_book(plan)
    assert b["options"]["count"] == 0
    assert "no liquid strike near entry" in b["options"]["reason"]


def test_empty_plan_has_no_options_reason_key():
    # nothing composed at all -> the direction reasons carry the explanation
    b = build_book({"no_trade": True, "setups": []})
    assert "reason" not in b["options"]


# ---------- rendering ----------

def test_render_book_is_readable_and_names_empty_sides():
    plan = {"direction": "long", "regime": {"regime": "risk_on"}, "setups": [
        mk("AVGO", "long", "call_debit_spread", SPREAD)]}
    text = render_book(build_book(plan))
    assert "LONG (1)" in text and "SHORT (0)" in text
    assert "CALL SPREAD" in text
    assert "100.0/112.0" in text              # both legs shown
    assert "not scanned" in text              # empty short explained


def test_render_book_handles_shares_section():
    plan = {"direction": "long", "setups": [
        mk("MSFT", "long", "stock",
           {"instrument": "stock", "reason": "no usable expiry"})]}
    text = render_book(build_book(plan))
    assert "SHARES VIEW (1)" in text and "no usable expiry" in text


# ---------- generated_from provenance ----------

def test_book_records_what_it_was_built_from():
    plan = {"direction": "short", "regime": {"regime": "risk_off"},
            "forced": False, "setups": [mk("AAA", "short")]}
    g = build_book(plan)["generated_from"]
    assert g["direction"] == "short" and g["regime"] == "risk_off"
    assert g["no_trade"] is False


def test_book_tolerates_missing_keys():
    # shape drift must degrade, not raise
    b = build_book({})
    assert b["counts"]["total"] == 0
    assert b["long"]["count"] == 0 and b["short"]["count"] == 0


# ---------- both-directions honesty ----------

def test_both_directions_says_scanned_not_skipped():
    # when the second pass actually ran, an empty side must not claim it was
    # never scanned — that would be a quiet lie in a glass-box system
    plan = {"direction": "long", "both_directions": True,
            "regime": {"regime": "risk_on"},
            "suppressed": [{"symbol": "X"}, {"symbol": "Y"}],
            "setups": [mk("AAA", "long")]}
    reason = build_book(plan)["short"]["reason"]
    assert "were scanned" in reason
    assert "not scanned" not in reason
    assert "2 candidates suppressed" in reason


def test_both_directions_singular_suppressed_grammar():
    plan = {"direction": "long", "both_directions": True,
            "suppressed": [{"symbol": "X"}], "setups": []}
    assert "1 candidate suppressed" in build_book(plan)["short"]["reason"]


def test_both_directions_with_no_suppressed_omits_the_tail():
    plan = {"direction": "long", "both_directions": True,
            "suppressed": [], "setups": []}
    r = build_book(plan)["short"]["reason"]
    assert "were scanned" in r and "suppressed" not in r


def test_no_trade_still_wins_over_both_directions():
    plan = {"no_trade": True, "both_directions": True, "setups": []}
    assert "no-trade" in build_book(plan)["short"]["reason"]
