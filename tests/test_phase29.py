"""Phase 29 tests: calibration disclosure.

The contract: the system must never present a confidence score without the
measured reality beside it, and must never invent reassurance when it has no
calibration data.
"""
import json
import pytest
from orchestrator.calibration import (band_for, disclose, benchmark_context,
                                      annotate_setup, load_calibration, render)


def test_band_boundaries():
    assert band_for(6.4) == "<6.5"
    assert band_for(6.5) == "6.5-7.5"
    assert band_for(7.4) == "6.5-7.5"
    assert band_for(7.5) == ">=7.5"
    assert band_for(None) == "unknown"


def test_disclosure_always_carries_the_caveat():
    d = disclose(8.2)
    assert "CONFLUENCE measure" in d["caveat"]
    assert "not a probability of profit" in d["caveat"]


def test_small_band_is_called_out_as_meaningless():
    cal = {"available": True, "source": "t",
           "by_confidence": {">=7.5": {"n": 8, "avg_r": 0.9, "win_rate": 0.9}}}
    d = disclose(8.0, cal)
    assert "too few" in d["reliability"]
    assert d["historical"]["n"] == 8


def test_losing_band_is_stated_plainly():
    cal = {"available": True, "source": "t",
           "by_confidence": {">=7.5": {"n": 120, "avg_r": -0.15, "win_rate": 0.4}}}
    d = disclose(8.0, cal)
    assert "LOST money" in d["reliability"]


def test_positive_band_reports_the_actual_number():
    cal = {"available": True, "source": "t",
           "by_confidence": {"6.5-7.5": {"n": 117, "avg_r": 0.18, "win_rate": 0.6}}}
    d = disclose(7.0, cal)
    assert "+0.180R" in d["reliability"] or "0.180R" in d["reliability"]


def test_missing_calibration_does_not_invent_reassurance():
    d = disclose(8.0, {"available": False, "source": "fallback"})
    assert "no per-band calibration" in d["reliability"]
    assert d["historical"]["n"] > 0        # falls back to the measured run


def test_benchmark_context_states_the_loss_honestly():
    b = benchmark_context()
    assert b["total_return_pct"] > b["strategy_total_return_pct"]
    assert "outperformed this system" in b["verdict"]
    assert "not as a signal to follow" in b["verdict"]


def test_annotate_does_not_alter_setup_numbers():
    s = {"symbol": "AAA", "confidence": 7.8, "entry_trigger": 100.0,
         "stop": 96.0, "target_1": 108.0}
    out = annotate_setup(s)
    for k in ("entry_trigger", "stop", "target_1", "symbol"):
        assert out[k] == s[k]
    assert "calibration" in out


def test_render_is_a_single_readable_line():
    txt = render(8.2)
    assert "confidence 8.2" in txt and "CONFLUENCE" in txt


def test_load_calibration_handles_missing_file():
    cal = load_calibration("/nonexistent/path.json")
    assert cal["available"] is False
    assert "fallback" in cal
