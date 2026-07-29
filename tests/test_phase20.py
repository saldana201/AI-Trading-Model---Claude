"""Phase 20 tests: component-weight re-fit under CPCV + walk-forward.

The tests that matter here are not "does the arithmetic run" — they are:
  1. on data with a KNOWN good component and a KNOWN inverted one, does the fit
     up-weight the good one and drive the inverted one toward zero?
  2. on pure noise, does the OOS machinery REFUSE to claim an edge (PSR low,
     verdict not trustworthy)? A fitter that finds edges in noise is worse than
     useless.
  3. does purge/embargo actually remove boundary-overlapping training rows?
  4. are weights non-negative and normalized, so the score stays interpretable?
"""

import numpy as np
import pytest

from backtest.weight_fit import (
    COMPONENTS, CURRENT_WEIGHTS, Dataset, scores, selected_mean_r,
    cpcv_splits, fit_weights_on, cpcv_fit, render_fit, _normalize,
)

K = len(COMPONENTS)


def _rows_with_signal(n=480, good_idx=3, bad_idx=0, seed=0):
    """Construct rows where component `good_idx` genuinely predicts positive R,
    component `bad_idx` predicts it INVERTED (high value -> negative R), and the
    rest are noise. This mimics the real finding: sector_strength works,
    vix_alignment is inverted."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        vals = rng.uniform(0, 1, K)
        # realized R driven by good component (+) and bad component (inverted)
        r = 1.5 * (vals[good_idx] - 0.5) - 1.5 * (vals[bad_idx] - 0.5) \
            + rng.normal(0, 0.4)
        rows.append({
            "components": {c: float(vals[j]) for j, c in enumerate(COMPONENTS)},
            "realized_r": float(r), "t": i,
            "symbol": "AAA", "direction": "long", "date": f"d{i}"})
    return rows


def _noise_rows(n=480, seed=1):
    rng = np.random.default_rng(seed)
    return [{"components": {c: float(rng.uniform(0, 1)) for c in COMPONENTS},
             "realized_r": float(rng.normal(0, 1)), "t": i,
             "symbol": "AAA", "direction": "long"} for i in range(n)]


# ---------- Dataset ----------

def test_dataset_drops_rows_without_outcome():
    rows = _noise_rows(20)
    rows[0]["realized_r"] = None
    ds = Dataset.from_rows(rows)
    assert len(ds) == 19
    assert ds.X.shape[1] == K


def test_dataset_sorts_by_time():
    rows = _noise_rows(30)
    rng = np.random.default_rng(5)
    shuffled = list(rng.permutation(rows))
    ds = Dataset.from_rows(shuffled)
    assert list(ds.t) == sorted(ds.t)


def test_dataset_raises_when_empty():
    with pytest.raises(ValueError):
        Dataset.from_rows([{"components": {}, "realized_r": None, "t": 0}])


# ---------- scoring / normalization ----------

def test_weights_are_normalized_and_nonnegative():
    w = _normalize(np.array([-1.0, 2.0, 0.0, 1.0] + [0.0] * (K - 4)))
    assert (w >= 0).all()
    assert w.sum() == pytest.approx(1.0)


def test_score_is_in_expected_range():
    ds = Dataset.from_rows(_noise_rows(50))
    sc = scores(ds.X, np.ones(K))
    assert sc.min() >= 0 and sc.max() <= 10


def test_selected_mean_r_respects_threshold():
    ds = Dataset.from_rows(_noise_rows(200))
    _, all_cnt = selected_mean_r(ds.X, ds.r, np.ones(K), threshold=0.0)
    _, hi_cnt = selected_mean_r(ds.X, ds.r, np.ones(K), threshold=6.0)
    assert all_cnt >= hi_cnt


# ---------- CPCV splits: purge/embargo ----------

def test_cpcv_yields_disjoint_train_test():
    for train, test in cpcv_splits(200, n_blocks=8, test_blocks=2,
                                   horizon=10, embargo=5):
        assert set(train.tolist()).isdisjoint(set(test.tolist()))


def test_cpcv_purges_boundary_overlap():
    # a training row within `horizon` before a test block must be removed
    got_any = False
    for train, test in cpcv_splits(160, n_blocks=8, test_blocks=1,
                                   horizon=10, embargo=0):
        lo = test.min()
        # no training row in [lo-10, lo) should survive
        assert not any(lo - 10 <= i < lo for i in train.tolist())
        got_any = True
    assert got_any


def test_cpcv_number_of_folds_is_combinatorial():
    folds = list(cpcv_splits(240, n_blocks=8, test_blocks=2))
    assert len(folds) == 28          # C(8,2)


# ---------- the core: signal recovery ----------

def test_fit_upweights_good_component_and_zeros_inverted():
    rows = _rows_with_signal(good_idx=3, bad_idx=0, seed=0)
    ds = Dataset.from_rows(rows)
    w = fit_weights_on(ds.X, ds.r, threshold=5.0, passes=5)
    good_w, bad_w = w[3], w[0]
    # the genuinely predictive component gets real weight
    assert good_w > 0.15
    # the inverted component is driven toward zero (never bets on the inverse)
    assert bad_w < good_w
    assert bad_w < 0.08


def test_fit_beats_uniform_on_signal_data_in_sample():
    rows = _rows_with_signal(seed=2)
    ds = Dataset.from_rows(rows)
    fitted = fit_weights_on(ds.X, ds.r, 5.0, passes=5)
    uni = _normalize(np.ones(K))
    mf, _ = selected_mean_r(ds.X, ds.r, fitted, 5.0)
    mu, _ = selected_mean_r(ds.X, ds.r, uni, 5.0)
    assert mf >= mu


def test_fit_is_deterministic():
    ds = Dataset.from_rows(_rows_with_signal(seed=3))
    a = fit_weights_on(ds.X, ds.r, 5.0, passes=4)
    b = fit_weights_on(ds.X, ds.r, 5.0, passes=4)
    assert np.allclose(a, b)


# ---------- the honesty test: noise must not read as edge ----------

def test_cpcv_does_not_manufacture_edge_from_noise():
    ds = Dataset.from_rows(_noise_rows(480, seed=7))
    fr = cpcv_fit(ds, threshold=5.0, n_blocks=8, test_blocks=2, passes=3)
    # on pure noise, out-of-sample PSR must not clear the bar, and the verdict
    # must not call the re-fit trustworthy
    assert fr.psr is None or fr.psr < 0.95
    assert "TRUSTWORTHY" not in fr.verdict


def test_cpcv_recovers_edge_on_signal_data():
    ds = Dataset.from_rows(_rows_with_signal(n=600, seed=11))
    fr = cpcv_fit(ds, threshold=5.0, n_blocks=8, test_blocks=2, passes=3)
    # genuine signal should survive out-of-sample with a positive path Sharpe
    assert fr.path_sharpe is not None and fr.path_sharpe > 0
    assert fr.n_folds > 0
    # and the proposed weights should favor the good component over the bad one
    assert fr.weights["sector_strength"] > fr.weights["vix_alignment"]


def test_fitresult_reports_deflation_and_baseline():
    ds = Dataset.from_rows(_rows_with_signal(n=500, seed=4))
    fr = cpcv_fit(ds, threshold=5.0, passes=3)
    assert fr.n_weight_vectors_tried >= fr.n_folds
    assert "selected_avg_r" in fr.baseline
    assert isinstance(render_fit(fr), str)
    assert "weight re-fit" in render_fit(fr)


def test_walk_forward_runs_and_reports():
    ds = Dataset.from_rows(_rows_with_signal(n=600, seed=6))
    fr = cpcv_fit(ds, threshold=5.0, passes=3)
    assert "available" in fr.walk_forward
    if fr.walk_forward["available"]:
        assert "avg_r" in fr.walk_forward


# ---------- weights stay a valid config ----------

def test_proposed_weights_cover_all_components():
    ds = Dataset.from_rows(_rows_with_signal(seed=8))
    fr = cpcv_fit(ds, threshold=5.0, passes=2)
    assert set(fr.weights.keys()) == set(COMPONENTS)
    assert all(v >= 0 for v in fr.weights.values())
