"""Phase 32 — one place that decides which Anthropic client to build.

Two call sites constructed `anthropic.Anthropic()` directly: the thesis writer
(orchestrator/llm.py) and the chat loop (orchestrator/chat.py). Adding a second
provider to both invites drift, so provider selection lives here and both import
it.

Supported providers
-------------------
direct   (default)  ANTHROPIC_API_KEY, api.anthropic.com
foundry             Azure AI Foundry deployment, via anthropic.AnthropicFoundry

Foundry configuration
---------------------
    CONFLUENCE_LLM_PROVIDER=foundry
    AZURE_FOUNDRY_ENDPOINT=https://<resource>.services.ai.azure.com/anthropic/
    AZURE_FOUNDRY_KEY=<key from the deployment page>
    CONFLUENCE_MODEL=claude-fable-5        # your DEPLOYMENT name, not a model id

Two things that catch people out, both handled here:

1. On Foundry, `model` is the *deployment name* you chose in the portal, not an
   Anthropic model string. If you named the deployment `claude-fable-5`, that is
   what goes in CONFLUENCE_MODEL.
2. The portal shows a Target URI ending in `/v1/messages`. The SDK appends the
   version and path itself, so the base_url must stop at `/anthropic/`. Passing
   the full target URI produces 404s that look like auth errors. `_normalise_base_url`
   strips it either way, so both forms work.

Provider selection is inferred when not stated: if AZURE_FOUNDRY_ENDPOINT is set
and ANTHROPIC_API_KEY is not, Foundry is assumed. Explicit setting always wins.
"""

from __future__ import annotations

import os


def _normalise_base_url(url: str) -> str:
    """Accept whatever the portal gave you and return what the SDK wants.

    The deployment page's copy button yields
    `https://x.services.ai.azure.com/anthropic/v1/messages`, but the SDK builds
    the `/v1/messages` path itself.
    """
    u = (url or "").strip().rstrip("/")
    for suffix in ("/v1/messages", "/v1"):
        if u.endswith(suffix):
            u = u[: -len(suffix)]
    return u + "/"


def provider_name() -> str:
    explicit = (os.environ.get("CONFLUENCE_LLM_PROVIDER") or "").strip().lower()
    if explicit in ("direct", "foundry"):
        return explicit
    if os.environ.get("AZURE_FOUNDRY_ENDPOINT") and not os.environ.get("ANTHROPIC_API_KEY"):
        return "foundry"
    return "direct"


def is_configured() -> bool:
    """True when enough is set to build a client. Callers fall back to
    deterministic mode rather than raising when this is False."""
    if provider_name() == "foundry":
        return bool(os.environ.get("AZURE_FOUNDRY_ENDPOINT")
                    and os.environ.get("AZURE_FOUNDRY_KEY"))
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def build_client():
    """Return an Anthropic-compatible client, or None if unconfigured.

    Both providers expose the same `client.messages.create(...)` surface, so
    every existing call site works unchanged.

    A missing `anthropic` package returns None with a clear warning rather than
    raising: the LLM layer is optional, the deterministic chat router and every
    engine work without it, and an optional dependency must never take down the
    whole API server at startup.
    """
    if not is_configured():
        return None
    try:
        import anthropic
    except ImportError:
        import sys
        print(
            "[llm] LLM provider is configured but the 'anthropic' package is "
            "not installed — falling back to deterministic mode.\n"
            "[llm] Install it with:  pip install anthropic",
            file=sys.stderr)
        return None

    if provider_name() == "foundry":
        endpoint = _normalise_base_url(os.environ["AZURE_FOUNDRY_ENDPOINT"])
        try:
            return anthropic.AnthropicFoundry(
                api_key=os.environ["AZURE_FOUNDRY_KEY"],
                base_url=endpoint,
            )
        except AttributeError:
            import sys
            print(
                "[llm] This 'anthropic' version has no AnthropicFoundry client. "
                "Upgrade with:  pip install -U anthropic\n"
                "[llm] Falling back to deterministic mode.",
                file=sys.stderr)
            return None
    return anthropic.Anthropic()


def sdk_available() -> bool:
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


def model_name() -> str | None:
    """On Foundry this is the deployment name; on direct it is a model id."""
    return os.environ.get("CONFLUENCE_MODEL")


def describe() -> dict:
    """Non-secret summary for /api/health and diagnostics. Never returns keys."""
    p = provider_name()
    d = {"provider": p, "configured": is_configured(), "model": model_name(),
         "sdk_installed": sdk_available()}
    if d["configured"] and not d["sdk_installed"]:
        d["status"] = ("configured but inactive — 'anthropic' package missing; "
                       "run: pip install anthropic")
    elif d["configured"] and not d["model"]:
        d["status"] = "configured but inactive — CONFLUENCE_MODEL is not set"
    elif d["configured"]:
        d["status"] = "active"
    else:
        d["status"] = "not configured — deterministic chat router in use"
    if p == "foundry":
        ep = os.environ.get("AZURE_FOUNDRY_ENDPOINT")
        d["endpoint"] = _normalise_base_url(ep) if ep else None
        d["key_present"] = bool(os.environ.get("AZURE_FOUNDRY_KEY"))
        d["note"] = ("CONFLUENCE_MODEL must be the Foundry DEPLOYMENT name "
                     "(e.g. claude-fable-5), not an Anthropic model id.")
    else:
        d["key_present"] = bool(os.environ.get("ANTHROPIC_API_KEY"))
    return d
