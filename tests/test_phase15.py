"""Phase 15 tests: backtest statistical rigor.

Two layers, mirroring Phase 8's split:
  - exact/analytic properties of PSR, MinTRL, DSR, bootstrap, purge — checked by
    construction against known reference values and monotonicity, so a regression
    in the math is caught deterministically;
  - integration: the rigor block appears in report() and degrades gracefully on
    tiny or degenerate samples without breaking the existing report contract.
"""

import math

import numpy as np
import pytest

from backtest.statistics import (
    norm_cdf, norm_ppf, moments, probabilistic_sharpe_ratio,
    min_track_record_length, deflated_sharpe_ratio, profit_factor,
    bootstrap_metric, purge_embargo_split, rigor_block, render_rigor,
)
from backtest.harness import report


# ---------- normal CDF / PPF (reference values) ----------

def test_norm_cdf_reference_points():
    assert norm_cdf(0.0) == pytest.approx(0.5, abs=1e-12)
    assert norm_cdf(1.959963985) == pytest.approx(0.975, abs=1e-6)
    assert norm_cdf(-1.959963985) == pytest.approx(0.025, abs=1e-6)


def test_norm_ppf_is_cdf_inverse():
    for p in (0.01, 0.1, 0.5, 0.9, 0.975, 0.99):
        assert norm_cdf(norm_ppf(p)) == pytest.approx(p, abs=1e-6)


def test_norm_ppf_domain_guard():
    with pytest.raises(ValueError):
        norm_ppf(0.0)
    with pytest.raises(ValueError):
        norm_ppf(1.0)


# ---------- moments ----------

def test_moments_normal_stream_has_near_zero_skew_and_kurt_three():
    rng = np.random.default_rng(1)
    m = moments(rng.normal(0, 1, 5000))
    assert abs(m.skew) < 0.15
    assert m.kurt == pytest.approx(3.0, abs=0.3)   # non-excess


def test_sharpe_matches_hand_calc():
    r = [1.0, -1.0, 2.0, 0.0, -0.5, 1.5]
    m = moments(r)
    expected = np.mean(r) / np.std(r, ddof=1)
    assert m.sharpe == pytest.approx(expected, abs=1e-12)


# ---------- PSR ----------

def test_psr_symmetric_stream_at_benchmark_zero_is_half():
    # exactly-symmetric, zero-mean stream -> Sharpe 0 -> PSR(>0) == 0.5
    r = [1.0, -1.0, 1.0, -1.0, 1.0, -1.0]
    assert probabilistic_sharpe_ratio(r, 0.0) == pytest.approx(0.5, abs=1e-9)


def test_psr_rises_with_sample_size_for_fixed_sharpe():
    # same per-trade Sharpe, more observations -> more confident -> higher PSR
    base = np.array([0.3, -0.2, 0.4, -0.1, 0.5, -0.3, 0.2, 0.1])
    small = probabilistic_sharpe_ratio(base, 0.0)
    large = probabilistic_sharpe_ratio(np.tile(base, 6), 0.0)
    assert large > small


def test_psr_in_unit_interval():
    rng = np.random.default_rng(2)
    for _ in range(20):
        r = rng.normal(rng.uniform(-0.3, 0.3), 1.0, 80)
        p = probabilistic_sharpe_ratio(r, 0.0)
        assert 0.0 <= p <= 1.0


# ---------- MinTRL ----------

def test_min_trl_infinite_when_sharpe_below_benchmark():
    r = [-1.0, -0.5, -2.0, 0.1, -0.3]        # negative Sharpe
    assert min_track_record_length(r, 0.0) == float("inf")


def test_min_trl_finite_and_positive_for_positive_edge():
    rng = np.random.default_rng(3)
    r = rng.normal(0.2, 1.0, 200)
    trl = min_track_record_length(r, 0.0, confidence=0.95)
    assert math.isfinite(trl) and trl > 1


# ---------- DSR (the selection-bias defense) ----------

def test_dsr_deflates_best_of_many_noise_trials():
    # 30 pure-noise strategies; the luckiest looks positive, but DSR should be low
    rng = np.random.default_rng(4)
    trials = [rng.normal(0.0, 1.0, 120) for _ in range(30)]
    d = deflated_sharpe_ratio(None, n_trials=30, all_trial_returns=trials)
    assert d["expected_max_sharpe"] > 0            # luck bar is raised
    assert d["dsr"] < 0.75                          # best noise trial not credible


def test_dsr_single_trial_equals_psr_against_zero_benchmark():
    # with variance 0 across "trials", expected-max is 0 and DSR == PSR(>0)
    rng = np.random.default_rng(5)
    r = rng.normal(0.25, 1.0, 150)
    d = deflated_sharpe_ratio(r, n_trials=2, trial_sharpe_variance=0.0)
    assert d["dsr"] == pytest.approx(probabilistic_sharpe_ratio(r, 0.0), abs=1e-9)


def test_dsr_requires_a_deflation_input():
    with pytest.raises(ValueError):
        deflated_sharpe_ratio([0.1, -0.1, 0.2], n_trials=5)


# ---------- profit factor ----------

def test_profit_factor_hand_calc():
    # gains 3+1=4, losses 2 -> PF 2.0
    assert profit_factor([3.0, -2.0, 1.0]) == pytest.approx(2.0, abs=1e-12)


def test_profit_factor_all_winners_is_inf():
    assert profit_factor([1.0, 2.0, 3.0]) == float("inf")


# ---------- bootstrap ----------

def test_bootstrap_bands_are_ordered_and_bracket_point():
    rng = np.random.default_rng(6)
    r = rng.normal(0.15, 1.0, 300)
    b = bootstrap_metric(r, "avg_r", n_resamples=1000, seed=7)
    assert b.p05 <= b.p50 <= b.p95
    assert b.p05 <= b.point <= b.p95
    assert 0.0 <= b.prob_positive <= 1.0


def test_bootstrap_winrate_probability_positive_for_strong_edge():
    r = [1.0] * 70 + [-1.0] * 30            # 70% win rate, clearly > 0
    b = bootstrap_metric(r, "win_rate", n_resamples=1000, seed=1)
    assert b.prob_positive == pytest.approx(1.0, abs=1e-9)


# ---------- purge + embargo ----------

def test_purge_removes_horizon_overlap_before_test():
    train, test = purge_embargo_split(n_samples=100, test_start=50,
                                       test_end=59, horizon=15, embargo=0)
    assert list(test) == list(range(50, 60))
    # samples 35..49 overlap the test window through the 15-bar horizon -> purged;
    # the block [35, 59] must be absent from train, while earlier (<35) and later
    # (>59, no embargo) samples survive.
    assert not set(range(35, 60)).intersection(train.tolist())
    assert 34 in train.tolist()
    assert 60 in train.tolist()


def test_embargo_drops_samples_after_test():
    train, test = purge_embargo_split(n_samples=100, test_start=40,
                                       test_end=49, horizon=5, embargo=10)
    # nothing in (test_end, test_end+embargo] survives in train
    assert not set(range(50, 60)).intersection(train.tolist())
    assert 60 in train.tolist()


# ---------- integration with report() ----------

def _synthetic_outcomes(rs):
    return [{"realized_r": r, "confidence": 7.0, "final_state": "CLOSED",
             "components": {"vix": 1.0}} for r in rs]


def test_report_includes_rigor_block():
    rng = np.random.default_rng(8)
    rs = list(rng.normal(0.2, 1.0, 60))
    rep = report(_synthetic_outcomes(rs), compose_points=60, n_trials=1)
    assert rep["rigor"]["available"] is True
    assert 0.0 <= rep["rigor"]["psr_vs_zero"] <= 1.0
    assert "interpretation" in rep["rigor"]


def test_report_rigor_carries_dsr_when_trials_gt_one():
    rng = np.random.default_rng(9)
    rs = list(rng.normal(0.3, 1.0, 80))
    rep = report(_synthetic_outcomes(rs), n_trials=25,
                 trial_sharpe_variance=0.05)
    assert "deflated_sharpe" in rep["rigor"]
    assert "dsr" in rep["rigor"]["deflated_sharpe"]


def test_report_rigor_unavailable_on_tiny_sample():
    rep = report(_synthetic_outcomes([0.5, -1.0]))     # only 2 filled
    assert rep["rigor"]["available"] is False
    assert "render" or render_rigor(rep["rigor"])       # render never raises
    assert "unavailable" in render_rigor(rep["rigor"])


def test_report_rigor_unavailable_on_zero_variance():
    rep = report(_synthetic_outcomes([1.0, 1.0, 1.0, 1.0]))
    assert rep["rigor"]["available"] is False


def test_existing_report_keys_unchanged():
    # Phase 15 must be additive: the Phase 8 contract still holds.
    rep = report(_synthetic_outcomes([0.5, -1.0, 2.0, -0.3, 1.1]))
    for key in ("overall", "by_confidence", "final_states",
                "component_signal", "outcomes", "caveats"):
        assert key in rep


# ---------- JSON-safety (regression: /api/journal 500 on inf/nan) ----------

def _assert_json_strict(rep):
    import json
    # Starlette's JSONResponse renders with allow_nan=False; inf/nan must be gone.
    json.dumps(rep, allow_nan=False)


def test_rigor_block_json_safe_with_infinite_min_trl():
    # negative-edge stream -> MinTRL is +inf internally; must serialize as null
    rep = report(_synthetic_outcomes([0.5, -1.0, 0.3, -1.0, 0.4]))
    assert rep["rigor"]["min_track_record_length"] is None
    _assert_json_strict(rep)


def test_rigor_block_json_safe_with_infinite_profit_factor():
    # all winners -> profit_factor is +inf internally; must serialize as null
    rep = report(_synthetic_outcomes([1.0, 2.0, 0.5, 1.5]))
    assert rep["rigor"]["profit_factor"] is None
    _assert_json_strict(rep)


def test_rigor_block_json_safe_normal_case():
    rep = report(_synthetic_outcomes([0.5, -1.0, 2.0, -0.3, 1.1, 0.8, -0.5, 1.2]))
    _assert_json_strict(rep)


def test_render_rigor_tolerates_none_values():
    # renderer must not choke when inf/nan were sanitized to None
    rep = report(_synthetic_outcomes([0.5, -1.0, 0.3, -1.0, 0.4]))
    text = render_rigor(rep["rigor"])
    assert "MinTRL" in text and "n/a" in text
