"""Phase 31 tests: the engine brief.

The contract under test is restraint. The brief exists because the composed-setup
product lost to buy-and-hold while the engines themselves held up. So it must
report engine facts and must NOT drift back into advice — that guard is the
feature, and these tests defend it.
"""
import pytest
from orchestrator.engine_brief import (build_brief, assert_no_recommendation,
                                       render_brief, _safe)


class FakeLevels:
    def get_levels(self, s):
        return {"symbol": s, "levels": [
            {"level": 100.0, "kind": "weekly_pivot", "method": "pivot_math",
             "computed_at": "2026-07-30"}]}


class FakeRegime:
    def get_regime(self):
        return {"regime": "risk_on", "risk_score": 6.3}


class Exploding:
    def get_levels(self, s):
        raise RuntimeError("engine down")


def test_brief_collects_available_engines():
    b = build_brief("nvda", {"levels": FakeLevels(), "regime": FakeRegime()})
    assert b["symbol"] == "NVDA"
    assert set(b["available_engines"]) == {"levels", "regime"}
    assert b["engines"]["regime"]["regime"] == "risk_on"


def test_missing_engines_are_simply_absent():
    b = build_brief("AAA", {"regime": FakeRegime()})
    assert "levels" not in b["engines"]


def test_engine_failure_degrades_and_is_reported():
    b = build_brief("AAA", {"levels": Exploding()})
    assert b["engines"]["levels"]["available"] is False
    assert "engine down" in b["engines"]["levels"]["error"]
    assert "levels" in b["unavailable"]


def test_safe_wraps_exceptions():
    out = _safe(lambda: (_ for _ in ()).throw(ValueError("boom")))
    assert out["available"] is False and "boom" in out["error"]


def test_brief_declares_it_holds_no_recommendation():
    b = build_brief("AAA", {"regime": FakeRegime()})
    assert b["contains_recommendation"] is False
    assert "no score" in b["note"].lower()


# ---------- the guard is the point ----------

def test_guard_passes_on_clean_facts():
    b = build_brief("AAA", {"levels": FakeLevels(), "regime": FakeRegime()})
    assert_no_recommendation(b)          # must not raise


def test_guard_catches_advisory_language_in_values():
    b = build_brief("AAA", {"regime": FakeRegime()})
    b["engines"]["regime"]["commentary"] = "You should buy this dip"
    with pytest.raises(AssertionError) as ei:
        assert_no_recommendation(b)
    assert "advisory language" in str(ei.value)


def test_guard_catches_nested_advisory_language():
    b = build_brief("AAA", {"regime": FakeRegime()})
    b["engines"]["regime"]["nested"] = {"deep": [{"x": "we recommend entering"}]}
    with pytest.raises(AssertionError):
        assert_no_recommendation(b)


def test_guard_ignores_metadata_key_names():
    """`contains_recommendation` is metadata about the guard, not content —
    scanning key names made it false-positive on every brief."""
    b = build_brief("AAA", {"regime": FakeRegime()})
    assert_no_recommendation(b)          # key contains 'recommend'; must pass


def test_guard_allows_its_own_disclaimer():
    b = build_brief("AAA", {"regime": FakeRegime()})
    assert "suggested trade" in b["note"]
    assert_no_recommendation(b)


# ---------- rendering ----------

def test_render_includes_symbol_and_disclaimer():
    txt = render_brief(build_brief("AAA", {"levels": FakeLevels(),
                                           "regime": FakeRegime()}))
    assert "AAA" in txt
    assert "facts only" in txt
    assert "interpretation is yours" in txt


def test_render_lists_unavailable_engines():
    txt = render_brief(build_brief("AAA", {"levels": Exploding()}))
    assert "unavailable" in txt
