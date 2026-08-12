"""Phase 34 — fundamentals confluence.

The load-bearing test in this file is test_legacy_mode_scoring_is_unchanged:
it pins the exact composite float so that adding this feature provably does
not move any existing score under default config.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from engines.fundamentals_mcp.logic import SyntheticFundamentals, enrich
from orchestrator import fundamentals_confluence as fc
from orchestrator.scoring import score_setup
from orchestrator.validator import validate_setup

TODAY = date(2026, 6, 15)


def snap(**over) -> dict:
    base = {
        "symbol": "TEST",
        "revenue_growth": 0.32,
        "eps_growth": 0.40,
        "profit_margin": 0.24,
        "forward_pe": 18.0,
        "institutional_pct": 0.72,
        "sector": "Technology",
        "industry": "Semiconductors",
        "earnings_date": None,
        "source": "synthetic",
    }
    base.update(over)
    return enrich(base, TODAY)


# ------------------------------------------------------------ assess()
def test_strong_snapshot_grades_high_with_full_component_coverage():
    a = fc.assess(snap(), "long", today=TODAY)
    assert a["grade"] in ("A", "B")
    assert a["quality_score"] > 0.65
    assert a["unavailable"] == []
    assert a["evidence"]["renormalized"] is False
    assert set(a["components"]) == {
        "growth", "profitability", "valuation", "sponsorship"}
    for comp in a["components"].values():
        assert comp["rule"] and comp["inputs"]


def test_weak_snapshot_grades_low():
    a = fc.assess(snap(revenue_growth=0.01, eps_growth=0.0,
                       profit_margin=0.01, forward_pe=70.0,
                       institutional_pct=0.15), "long", today=TODAY)
    assert a["grade"] in ("D", "F")
    assert a["quality_score"] < 0.35


def test_growth_component_agrees_with_engine_grade():
    """The growth curve is anchored on the same bands the engine uses for
    growth_grade, so the two surfaces can never tell opposite stories."""
    strong = snap(revenue_growth=0.20, eps_growth=0.25)
    assert strong["growth_grade"] == "strong"
    assert fc.assess(strong, "long", today=TODAY)["components"]["growth"]["score"] >= 0.75

    moderate = snap(revenue_growth=0.08, eps_growth=0.10)
    assert moderate["growth_grade"] == "moderate"
    g = fc.assess(moderate, "long", today=TODAY)["components"]["growth"]["score"]
    assert 0.35 <= g < 0.75


def test_direction_awareness_inverts_alignment():
    weak = snap(revenue_growth=0.0, eps_growth=0.0, profit_margin=0.0,
                forward_pe=75.0, institutional_pct=0.10)
    lng = fc.assess(weak, "long", today=TODAY)
    sht = fc.assess(weak, "short", today=TODAY)
    assert lng["quality_score"] == sht["quality_score"]      # same quality
    assert lng["alignment_score"] < 0.35                     # bad for longs
    assert sht["alignment_score"] > 0.65                     # good for shorts
    assert lng["grade"] == sht["grade"]                      # grade is absolute
    assert "weaker inference" in sht["evidence"]["direction_caveat"]


# -------------------------------------------------- missing data handling
def test_missing_component_is_unavailable_and_weights_renormalize():
    a = fc.assess(snap(profit_margin=None), "long", today=TODAY)
    assert [u["component"] for u in a["unavailable"]] == ["profitability"]
    assert a["unavailable"][0]["reason"]
    assert a["components"]["profitability"]["score"] is None
    ev = a["evidence"]
    assert ev["renormalized"] is True
    assert "profitability" not in ev["weights_applied"]
    assert pytest.approx(sum(ev["weights_applied"].values()), abs=1e-6) == 1.0
    # declared weights are still reported, so the drop is visible
    assert ev["weights_declared"]["profitability"] == 0.40 / 2


def test_all_missing_is_unavailable_not_f():
    """The common live path: yfinance swallows the error and returns {}.
    'Not measured' must never render as 'measured and bad'."""
    a = fc.assess(snap(revenue_growth=None, eps_growth=None, profit_margin=None,
                       forward_pe=None, institutional_pct=None),
                  "long", today=TODAY)
    assert a["grade"] == "unavailable"
    assert a["grade"] != "F"
    assert a["quality_score"] is None and a["alignment_score"] is None
    assert len(a["unavailable"]) == 4
    assert a["evidence"]["weights_applied"] == {}


def test_non_positive_pe_is_unavailable_not_expensive():
    a = fc.assess(snap(forward_pe=-12.0), "long", today=TODAY)
    assert a["components"]["valuation"]["score"] is None
    assert "non-positive" in a["unavailable"][0]["reason"]


def test_empty_snapshot_does_not_raise():
    a = fc.assess({}, "long", today=TODAY)
    assert a["grade"] == "unavailable"
    assert a["earnings"]["days_until"] is None


# ------------------------------------------------------------- gate()
def _cfg(**over) -> dict:
    return {**fc.DEFAULT_CFG, **over}


def earnings_in(days: int) -> dict:
    return snap(earnings_date=str(TODAY + timedelta(days=days)))


def test_gate_suppresses_inside_the_window():
    cfg = _cfg(earnings_gate="suppress", earnings_window_days=5)
    a = fc.assess(earnings_in(3), "long", cfg, today=TODAY)
    v = fc.gate({}, a, cfg)
    assert v["allowed"] is False
    assert v["action"] == "suppress"
    assert "earnings in 3d" in v["reason"]


def test_gate_flag_allows_with_a_warning():
    cfg = _cfg(earnings_gate="flag", earnings_window_days=5)
    a = fc.assess(earnings_in(3), "long", cfg, today=TODAY)
    v = fc.gate({}, a, cfg)
    assert v["allowed"] is True and v["action"] == "flag"
    assert "binary-event risk" in v["warning"]


def test_gate_ignore_is_a_noop():
    cfg = _cfg(earnings_gate="ignore", earnings_window_days=5)
    v = fc.gate({}, fc.assess(earnings_in(3), "long", cfg, today=TODAY), cfg)
    assert v["allowed"] is True and v["warning"] is None


def test_gate_window_boundary_is_inclusive():
    cfg = _cfg(earnings_window_days=5)
    inside = fc.assess(earnings_in(5), "long", cfg, today=TODAY)
    outside = fc.assess(earnings_in(6), "long", cfg, today=TODAY)
    assert inside["earnings"]["in_gate_window"] is True
    assert outside["earnings"]["in_gate_window"] is False
    assert fc.gate({}, inside, cfg)["allowed"] is False
    assert fc.gate({}, outside, cfg)["allowed"] is True


def test_gate_ignores_a_contradictory_engine_flag():
    """The engine's in_earnings_window is fixed at 7 days and drives the
    display flag. The gate must compute its own window regardless."""
    cfg = _cfg(earnings_window_days=2)
    s = earnings_in(6)
    assert s["in_earnings_window"] is True          # engine says yes at 7d
    a = fc.assess(s, "long", cfg, today=TODAY)
    assert a["earnings"]["in_gate_window"] is False  # gate says no at 2d
    assert fc.gate({}, a, cfg)["allowed"] is True


def test_gate_passes_when_no_earnings_date():
    a = fc.assess(snap(earnings_date=None), "long", today=TODAY)
    assert fc.gate({}, a)["allowed"] is True


def test_disabled_config_is_a_full_bypass():
    cfg = _cfg(enabled=False, earnings_window_days=30)
    a = fc.assess(earnings_in(1), "long", cfg, today=TODAY)
    v = fc.gate({}, a, cfg)
    assert v["allowed"] is True and v["action"] == "disabled"


# ------------------------------------------------- enrich / apply / validator
def _setup_and_evidence():
    setup = {"symbol": "TEST", "direction": "long", "entry_trigger": 142.50,
             "stop": 139.80, "target_1": 147.0, "target_2": 151.0}
    evidence = {"levels": {"clusters": [142.50, 139.80, 147.0, 151.0]}}
    return setup, evidence


def test_enrichment_does_not_break_validation():
    setup, evidence = _setup_and_evidence()
    assert validate_setup(setup, evidence)["valid"] is True
    fc.enrich_setup(setup, fc.assess(snap(), "long", today=TODAY))
    assert "fundamentals_assessment" in setup
    assert validate_setup(setup, evidence)["valid"] is True


def test_enrichment_is_flat_not_setup_meta():
    """setup_meta belongs to the Trade dataclass; writing it on a composer
    setup would create a key nothing reads."""
    setup, _ = _setup_and_evidence()
    fc.enrich_setup(setup, fc.assess(snap(), "long", today=TODAY))
    assert "setup_meta" not in setup


def test_apply_is_one_call_and_returns_warnings_as_a_list():
    cfg = _cfg(earnings_gate="flag", earnings_window_days=5)
    setup, _ = _setup_and_evidence()
    fx = fc.apply(setup, earnings_in(2), "long", cfg, today=TODAY)
    assert fx["allowed"] is True
    assert isinstance(fx["warnings"], list) and len(fx["warnings"]) == 1
    assert setup["fundamentals_assessment"]["grade"]
    # suppress mode returns no warning, because the setup is gone
    cfg2 = _cfg(earnings_gate="suppress", earnings_window_days=5)
    fx2 = fc.apply(setup, earnings_in(2), "long", cfg2, today=TODAY)
    assert fx2["allowed"] is False and fx2["warnings"] == []


# ------------------------------------------- KNOWN DEFECT characterization
def test_KNOWN_DEFECT_forward_pe_widens_the_traceable_number_set():
    """PINS A DEFECT, DOES NOT ENDORSE IT.

    validator.collect_numbers() walks the whole evidence payload, so a P/E
    ratio in the fundamentals branch can launder a fabricated price level.
    fundamentals.strict_validation (default False) closes this; the default
    remains open only until scripts/strict_validation_probe.py has measured
    what closing it changes.
    """
    fake_stop = 42.0
    setup = {"symbol": "TEST", "entry_trigger": 45.0, "stop": fake_stop,
             "target_1": 48.0, "target_2": 50.0}
    evidence = {
        "levels": {"clusters": [45.0, 48.0, 50.0]},          # no 42.0 here
        "fundamentals": snap(forward_pe=fake_stop),           # but a P/E of 42
    }
    assert validate_setup(setup, evidence)["valid"] is True   # the hole

    filtered = {k: v for k, v in evidence.items() if k != "fundamentals"}
    check = validate_setup(setup, filtered)
    assert check["valid"] is False
    assert check["violations"][0]["field"] == "stop"


# --------------------------------------------------- scoring mode contract
def _ctx(assessment=None, **over) -> dict:
    ctx = {
        "regime": "risk_on", "regime_risk_score": 4,
        "vix_alignment_state": "confirming_bullish",
        "sector_etf": "SMH", "sector_status": "leading", "sector_rank_4w": 1,
        "screen": {"passes": 7, "total_checks": 8,
                   "classification": "canslim_leader",
                   "extension_vs_21d_pct": 3.0},
        "phase": "mark_up", "rvol_20d": 1.8, "daily_rsi": 61.0,
        "bearish_divergence": False, "bullish_divergence": False,
        "mas_above": 6, "risk_reward_t1": 1.4, "risk_reward_t2": 2.6,
        "avg_dollar_volume_m": 320.0,
        "fundamentals": snap(),
    }
    if assessment is not None:
        ctx["fundamentals_assessment"] = assessment
    ctx.update(over)
    return ctx


def test_legacy_mode_scoring_is_unchanged(monkeypatch):
    """R4 regression guard. With default config the composite must be
    byte-identical to its pre-Phase-34 value. The expected float below was
    captured on stabilize/phase-0 BEFORE this feature existed."""
    monkeypatch.delenv("CONFLUENCE_FUNDAMENTALS_MODE", raising=False)
    scored = score_setup("long", _ctx())
    # 7.9 was computed by executing the ORIGINAL orchestrator/scoring.py from
    # the pre-Phase-34 tree against this exact ctx, not read back off the
    # patched module. If this line ever needs changing, the composite moved.
    assert scored["score"] == 7.9
    cat = scored["components"]["catalyst_fundamental"]
    assert cat["evidence"]["mode"] == "legacy"
    assert cat["weight"] == 1.0


def test_assessment_mode_changes_only_the_catalyst_slot(monkeypatch):
    from config import get_config
    a = fc.assess(snap(), "long", today=TODAY)
    legacy = score_setup("long", _ctx(a))

    monkeypatch.setattr("orchestrator.scoring._score_mode", lambda: "assessment")
    new = score_setup("long", _ctx(a))

    assert set(legacy["components"]) == set(new["components"])
    changed = [k for k in legacy["components"]
               if legacy["components"][k]["value"] != new["components"][k]["value"]]
    assert changed == ["catalyst_fundamental"]
    # total weight — and therefore the meaning of min_score — is untouched
    assert (sum(c["weight"] for c in legacy["components"].values())
            == sum(c["weight"] for c in new["components"].values()))
    assert new["components"]["catalyst_fundamental"]["evidence"]["mode"] == "assessment"
    assert get_config()["fundamentals"]["score_mode"] == "legacy"   # default intact


def test_assessment_mode_falls_back_when_nothing_is_scoreable(monkeypatch):
    monkeypatch.setattr("orchestrator.scoring._score_mode", lambda: "assessment")
    blank = fc.assess({}, "long", today=TODAY)
    scored = score_setup("long", _ctx(blank))
    ev = scored["components"]["catalyst_fundamental"]["evidence"]
    assert ev["mode"] == "legacy"
    assert "fell back" in ev["fallback"]


def test_assessment_mode_does_not_double_count_earnings(monkeypatch):
    monkeypatch.setattr("orchestrator.scoring._score_mode", lambda: "assessment")
    s = earnings_in(2)
    a = fc.assess(s, "long", today=TODAY)
    scored = score_setup("long", _ctx(a, fundamentals=s))
    ev = scored["components"]["catalyst_fundamental"]["evidence"]
    assert scored["components"]["catalyst_fundamental"]["value"] == round(
        a["alignment_score"], 2)
    assert "double-counted" in ev["note"]


# ------------------------------------------------------------- config
def test_config_defaults_are_conservative():
    from config import get_config
    f = get_config()["fundamentals"]
    assert f["score_mode"] == "legacy"
    assert f["strict_validation"] is False
    assert f["earnings_gate"] == "suppress"


def test_config_rejects_bad_fundamentals_values():
    from config.schema import validate
    errs = validate({"fundamentals": {"earnings_gate": "nope"}})
    assert any("earnings_gate" in e for e in errs)
    errs = validate({"fundamentals": {"score_mode": "magic"}})
    assert any("score_mode" in e for e in errs)
    errs = validate({"fundamentals": {"earnings_window_days": -1}})
    assert any("earnings_window_days" in e for e in errs)
    errs = validate({"fundamentals": {"weights": {"growth": -1}}})
    assert any("growth" in e for e in errs)
    errs = validate({"fundamentals": {"weights": {"nonsense": 1}}})
    assert any("nonsense" in e for e in errs)
    assert validate({"fundamentals": {"earnings_gate": "flag"}}) == []


def test_synthetic_provider_snapshots_are_assessable():
    """Every synthetic symbol must produce a usable assessment, or the
    offline test path is not exercising the real code path."""
    provider = SyntheticFundamentals(today=TODAY)
    for sym in ("NVDA", "AAPL", "MSFT", "AMD", "TSLA"):
        a = fc.assess(provider.get_snapshot(sym), "long", today=TODAY)
        assert a["grade"] != "unavailable"
        assert 0.0 <= a["quality_score"] <= 1.0


# ------------------------------------------------------------- API surface
@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("CONFLUENCE_DATA", "synthetic")
    monkeypatch.delenv("CONFLUENCE_API_KEY", raising=False)
    from fastapi.testclient import TestClient
    from apps.api.main import app
    return TestClient(app)


def test_fundamentals_endpoint_returns_a_full_assessment(client):
    r = client.get("/api/fundamentals/NVDA")
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "NVDA" and body["direction"] == "long"
    assert body["assessment"]["grade"]
    assert set(body["assessment"]["components"]) == {
        "growth", "profitability", "valuation", "sponsorship"}
    assert "gate" in body and "allowed" in body["gate"]


def test_fundamentals_endpoint_honours_direction(client):
    lng = client.get("/api/fundamentals/NVDA?direction=long").json()
    sht = client.get("/api/fundamentals/NVDA?direction=short").json()
    assert (lng["assessment"]["quality_score"]
            == sht["assessment"]["quality_score"])
    assert (lng["assessment"]["alignment_score"]
            != sht["assessment"]["alignment_score"])
    assert client.get("/api/fundamentals/NVDA?direction=sideways").status_code == 400


def test_suppressed_endpoint_shape(client):
    r = client.get("/api/setups/suppressed")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["suppressed"], list)
    assert body["count"] == len(body["suppressed"])


def test_fundamentals_routes_enforce_the_api_key(monkeypatch):
    monkeypatch.setenv("CONFLUENCE_DATA", "synthetic")
    monkeypatch.setenv("CONFLUENCE_API_KEY", "s3cret")
    from fastapi.testclient import TestClient
    from apps.api.main import app
    c = TestClient(app)
    assert c.get("/api/fundamentals/NVDA").status_code == 401
    assert c.get("/api/setups/suppressed").status_code == 401
    ok = c.get("/api/fundamentals/NVDA", headers={"X-API-Key": "s3cret"})
    assert ok.status_code == 200
