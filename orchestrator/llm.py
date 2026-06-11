"""Optional Claude-written thesis (design doc §5.1).

When ANTHROPIC_API_KEY is set, upgrades the template thesis to a Claude-
composed one. The validator in validator.py still applies to every setup —
the LLM writes language, never levels.

SDK + model docs: https://docs.claude.com/en/api/overview and
https://docs.claude.com/en/docs/about-claude/models — set CONFLUENCE_MODEL
to the model you want (e.g. a current Sonnet) rather than relying on a
hardcoded string going stale.
"""
import json
import os

SYSTEM = (
    "You write concise trading theses for a discretionary trader. You are given "
    "a fully-constructed setup and the engine evidence behind it. Write 3-5 "
    "sentences: why the setup exists, what confirms it, what invalidates it. "
    "Use ONLY price levels that appear verbatim in the setup or evidence — never "
    "invent a number. No advice language; this is decision support."
)


def make_thesis_writer():
    """Returns a thesis_writer callable, or None if no API key is configured."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    model = os.environ.get("CONFLUENCE_MODEL")
    if not model:
        raise RuntimeError(
            "Set CONFLUENCE_MODEL (see https://docs.claude.com/en/docs/about-claude/models)")
    import anthropic
    client = anthropic.Anthropic()

    def write(setup: dict, ctx: dict, evidence: dict) -> str:
        msg = client.messages.create(
            model=model, max_tokens=400, system=SYSTEM,
            messages=[{"role": "user", "content": json.dumps(
                {"setup": setup, "context": {k: v for k, v in ctx.items()
                                             if k != "fundamentals"}},
                default=str)}],
        )
        return "".join(b.text for b in msg.content if b.type == "text").strip()

    return write
