"""Phase 32 tests: provider selection for direct API vs Azure AI Foundry.

The two things that actually break a Foundry setup are pinned here: the base_url
suffix (the portal hands you `/v1/messages`, the SDK appends that itself) and the
model field (a Foundry DEPLOYMENT name, not an Anthropic model id).
"""
import os
import pytest
from orchestrator import llm_client as lc


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("CONFLUENCE_LLM_PROVIDER", "ANTHROPIC_API_KEY",
              "AZURE_FOUNDRY_ENDPOINT", "AZURE_FOUNDRY_KEY", "CONFLUENCE_MODEL"):
        monkeypatch.delenv(k, raising=False)


# ---------- base_url normalisation (the #1 Foundry gotcha) ----------

@pytest.mark.parametrize("given", [
    "https://x.services.ai.azure.com/anthropic/v1/messages",
    "https://x.services.ai.azure.com/anthropic/v1",
    "https://x.services.ai.azure.com/anthropic/",
    "https://x.services.ai.azure.com/anthropic",
])
def test_base_url_always_normalises_to_the_sdk_form(given):
    assert lc._normalise_base_url(given) == "https://x.services.ai.azure.com/anthropic/"


def test_base_url_tolerates_whitespace():
    assert lc._normalise_base_url("  https://x/anthropic/v1/messages  ").endswith("/anthropic/")


# ---------- provider selection ----------

def test_defaults_to_direct(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert lc.provider_name() == "direct"
    assert lc.is_configured() is True


def test_foundry_inferred_when_only_azure_is_set(monkeypatch):
    monkeypatch.setenv("AZURE_FOUNDRY_ENDPOINT", "https://x/anthropic/")
    monkeypatch.setenv("AZURE_FOUNDRY_KEY", "k")
    assert lc.provider_name() == "foundry"
    assert lc.is_configured() is True


def test_explicit_provider_beats_inference(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("AZURE_FOUNDRY_ENDPOINT", "https://x/anthropic/")
    monkeypatch.setenv("AZURE_FOUNDRY_KEY", "k")
    monkeypatch.setenv("CONFLUENCE_LLM_PROVIDER", "foundry")
    assert lc.provider_name() == "foundry"


def test_unconfigured_returns_none_rather_than_raising():
    assert lc.is_configured() is False
    assert lc.build_client() is None


def test_foundry_without_key_is_not_configured(monkeypatch):
    monkeypatch.setenv("AZURE_FOUNDRY_ENDPOINT", "https://x/anthropic/")
    assert lc.is_configured() is False


# ---------- the client itself ----------

def test_builds_a_foundry_client_with_normalised_url(monkeypatch):
    monkeypatch.setenv("CONFLUENCE_LLM_PROVIDER", "foundry")
    monkeypatch.setenv("AZURE_FOUNDRY_ENDPOINT",
                       "https://joses.services.ai.azure.com/anthropic/v1/messages")
    monkeypatch.setenv("AZURE_FOUNDRY_KEY", "k")
    c = lc.build_client()
    import anthropic
    assert isinstance(c, anthropic.AnthropicFoundry)
    assert "v1/messages" not in str(c.base_url)


def test_foundry_client_exposes_the_same_messages_surface(monkeypatch):
    monkeypatch.setenv("CONFLUENCE_LLM_PROVIDER", "foundry")
    monkeypatch.setenv("AZURE_FOUNDRY_ENDPOINT", "https://x/anthropic/")
    monkeypatch.setenv("AZURE_FOUNDRY_KEY", "k")
    c = lc.build_client()
    assert hasattr(c.messages, "create")     # call sites need no changes


# ---------- describe() must never leak secrets ----------

def test_describe_reports_without_exposing_the_key(monkeypatch):
    monkeypatch.setenv("CONFLUENCE_LLM_PROVIDER", "foundry")
    monkeypatch.setenv("AZURE_FOUNDRY_ENDPOINT", "https://x/anthropic/")
    monkeypatch.setenv("AZURE_FOUNDRY_KEY", "super-secret-value")
    monkeypatch.setenv("CONFLUENCE_MODEL", "claude-fable-5")
    d = lc.describe()
    assert d["provider"] == "foundry" and d["key_present"] is True
    assert "super-secret-value" not in str(d)
    assert d["model"] == "claude-fable-5"
    assert "DEPLOYMENT name" in d["note"]


def test_describe_direct_provider(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    d = lc.describe()
    assert d["provider"] == "direct" and d["key_present"] is True
    assert "sk-secret" not in str(d)


# ---------- missing SDK must not take down the server ----------

def test_missing_anthropic_package_returns_none_not_crash(monkeypatch, capsys):
    """An optional dependency must never break app startup. The deterministic
    router and every engine work without the LLM layer."""
    monkeypatch.setenv("CONFLUENCE_LLM_PROVIDER", "foundry")
    monkeypatch.setenv("AZURE_FOUNDRY_ENDPOINT", "https://x/anthropic/")
    monkeypatch.setenv("AZURE_FOUNDRY_KEY", "k")
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "anthropic":
            raise ImportError("No module named 'anthropic'")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert lc.build_client() is None
    err = capsys.readouterr().err
    assert "pip install anthropic" in err


def test_thesis_writer_returns_none_when_sdk_missing(monkeypatch):
    """make_thesis_writer is called during app startup — it must not raise."""
    monkeypatch.setenv("CONFLUENCE_LLM_PROVIDER", "foundry")
    monkeypatch.setenv("AZURE_FOUNDRY_ENDPOINT", "https://x/anthropic/")
    monkeypatch.setenv("AZURE_FOUNDRY_KEY", "k")
    monkeypatch.setenv("CONFLUENCE_MODEL", "claude-fable-5")
    monkeypatch.setattr(lc, "build_client", lambda: None)
    from orchestrator.llm import make_thesis_writer
    assert make_thesis_writer() is None


def test_describe_explains_why_llm_is_inactive(monkeypatch):
    monkeypatch.setenv("CONFLUENCE_LLM_PROVIDER", "foundry")
    monkeypatch.setenv("AZURE_FOUNDRY_ENDPOINT", "https://x/anthropic/")
    monkeypatch.setenv("AZURE_FOUNDRY_KEY", "k")
    monkeypatch.setattr(lc, "sdk_available", lambda: False)
    d = lc.describe()
    assert "pip install anthropic" in d["status"]


def test_describe_reports_active_when_all_set(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    monkeypatch.setenv("CONFLUENCE_MODEL", "claude-sonnet-4-5")
    monkeypatch.setattr(lc, "sdk_available", lambda: True)
    assert lc.describe()["status"] == "active"
