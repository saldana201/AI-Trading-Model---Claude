# Phase 32 — Azure AI Foundry (claude-fable-5) integration

Built on GitHub `35be6f7` + Phase 31. **380 tests pass.**

## Setup (Windows / MINGW64)

```bash
export CONFLUENCE_LLM_PROVIDER=foundry
export AZURE_FOUNDRY_ENDPOINT="https://joses-m8nko62g-swedencentral.services.ai.azure.com/anthropic/"
export AZURE_FOUNDRY_KEY="<the key from the deployment page>"
export CONFLUENCE_MODEL="claude-fable-5"
```

PowerShell:
```powershell
$env:CONFLUENCE_LLM_PROVIDER="foundry"
$env:AZURE_FOUNDRY_ENDPOINT="https://joses-m8nko62g-swedencentral.services.ai.azure.com/anthropic/"
$env:AZURE_FOUNDRY_KEY="<key>"
$env:CONFLUENCE_MODEL="claude-fable-5"
```

Verify: `curl http://localhost:8000/api/health` → `"chat_mode": "llm"` and an
`llm` block naming the provider. The key is never returned.

## Two gotchas, both handled for you

1. **`CONFLUENCE_MODEL` is the Foundry DEPLOYMENT name**, not an Anthropic model
   id. Yours is `claude-fable-5` because that is what the deployment is called.
2. **The portal's Target URI ends in `/v1/messages`**, but the SDK appends that
   path itself. Passing the full URI gives 404s that look like auth failures.
   `_normalise_base_url` strips `/v1/messages` or `/v1`, so either form works —
   pinned by a parametrised test.

## What changed

| file | change |
|---|---|
| `orchestrator/llm_client.py` | **new** — single provider factory (direct / foundry) |
| `orchestrator/llm.py` | thesis writer builds via the factory |
| `orchestrator/chat.py` | chat loop builds via the factory |
| `apps/api/main.py` | `/api/health` reports the resolved provider |

Both providers expose the same `client.messages.create(...)`, so no call site
changed beyond construction. Direct-API behaviour is untouched: set
`ANTHROPIC_API_KEY` and it works exactly as before.

## Where Fable actually gets used

- **Thesis prose** on composed setups (`make_thesis_writer`)
- **Chat mode** — the tool-use loop over the engines, instead of the
  deterministic intent router

It does **not** touch any engine math, the backtests, or `engine_brief`. The
anti-hallucination validator still rejects any setup citing a level absent from
engine evidence, so a stronger model cannot invent price levels — it only writes
better explanations of numbers the engines produced.

## Security

Never commit the key. Confirm it has not been:

```bash
git log -p --all -S "services.ai.azure.com" | head
```

Keep it in the shell env or an ignored `.env`.
