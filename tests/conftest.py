"""Test-wide environment: set BEFORE any gateway import, regardless of which
test module loads first."""
import os

os.environ.setdefault("CONFLUENCE_DATA", "synthetic")
os.environ["CONFLUENCE_SSE_KEEPALIVE"] = "0.2"
os.environ.setdefault("CONFLUENCE_ALERT_DB", ":memory:")
