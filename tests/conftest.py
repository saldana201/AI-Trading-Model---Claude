"""Test-wide environment: set BEFORE any gateway import, regardless of which
test module loads first."""
import os

os.environ.setdefault("CONFLUENCE_DATA", "synthetic")
os.environ["CONFLUENCE_SSE_KEEPALIVE"] = "0.2"
os.environ.setdefault("CONFLUENCE_ALERT_DB", ":memory:")

# ---------------------------------------------------------------------------
# Phase 14.1 — hermetic config.
#
# Your live trading settings persist in confluence.json BY DESIGN (a preset
# click in the Settings panel writes it). But the test suite asserts engine
# behavior at DEFAULTS, so tests must never read that file: with the
# aggressive preset applied, three older tests fail on trail distance and
# confidence floors — correctly reflecting your config, wrongly failing
# the suite.
#
# Every test gets CONFLUENCE_CONFIG pointed at a nonexistent per-test path
# (defaults + env vars only). test_phase12 layers its own config fixture on
# top of this one, which still works: its monkeypatch.setenv runs after and
# wins for those tests.
# ---------------------------------------------------------------------------
import pytest


@pytest.fixture(autouse=True)
def _hermetic_config(monkeypatch, tmp_path):
    monkeypatch.setenv("CONFLUENCE_CONFIG",
                       str(tmp_path / "hermetic-confluence.json"))
    try:
        from config import reset_cache
        reset_cache()
    except ImportError:      # config package absent in very old checkouts
        yield
        return
    yield
    reset_cache()
