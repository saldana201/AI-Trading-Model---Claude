"""Phase 12 — layered config loader.

Precedence (lowest to highest):

    DEFAULTS  <  legacy env vars  <  confluence.json  <  runtime updates

The file is authoritative over env vars on purpose: the Settings UI writes
the file, and a stale shell export must not silently defeat a change the
user just made in the dashboard. Runtime updates persist back to the file,
so the effective config survives restarts.

Thread-safe (gateway runs handlers in a threadpool). Every successful
update returns a `config_update` audit event mirroring the `manual_update`
pattern from the trades surface.
"""

from __future__ import annotations

import copy
import datetime as _dt
import json
import os
import threading

from .schema import DEFAULTS, ENV_MAP, deep_merge, validate

_LOCK = threading.RLock()
_STATE: dict = {"cfg": None, "path": None}


def config_path() -> str:
    return os.environ.get("CONFLUENCE_CONFIG", "confluence.json")


def _read_file(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _env_overlay() -> dict:
    out: dict = {}
    for var, (section, key, cast) in ENV_MAP.items():
        raw = os.environ.get(var)
        if raw is None or raw == "":
            continue
        try:
            out.setdefault(section, {})[key] = cast(raw)
        except (TypeError, ValueError):
            continue  # a malformed env var never crashes startup
    return out


def _env_signature() -> tuple:
    """A hashable snapshot of the env vars that feed the config overlay.

    The cache is keyed on this so a late `os.environ[...]=` (or a test's
    monkeypatch.setenv) is honored without an explicit reset — matching the
    pre-Phase-12 behavior where each module read env vars at call time.
    """
    return tuple((v, os.environ.get(v)) for v in sorted(ENV_MAP)) + \
        (("__CONFLUENCE_CONFIG__", os.environ.get("CONFLUENCE_CONFIG")),)


def load(force: bool = False) -> dict:
    """Build (or return cached) effective config."""
    with _LOCK:
        path = config_path()
        sig = _env_signature()
        if (_STATE["cfg"] is not None and _STATE["path"] == path
                and _STATE.get("env_sig") == sig and not force):
            return _STATE["cfg"]
        cfg = deep_merge(DEFAULTS, _env_overlay())
        file_cfg = {}
        try:
            file_cfg = _read_file(path)
        except (ValueError, json.JSONDecodeError, OSError):
            file_cfg = {}  # unreadable file degrades to env+defaults
        if file_cfg and not validate(file_cfg):
            cfg = deep_merge(cfg, file_cfg)
        # in-memory runtime overrides (from update_config persist=False) sit
        # above the file so a rebuild doesn't drop them
        runtime = _STATE.get("runtime") or {}
        if runtime:
            cfg = deep_merge(cfg, runtime)
        _STATE["cfg"] = cfg
        _STATE["path"] = path
        _STATE["env_sig"] = sig
        return cfg


def get_config() -> dict:
    """Effective config (cached). Read-only by convention — copy to mutate."""
    return load()


def get(section: str, key: str):
    """Convenience accessor: get('risk', 'min_score')."""
    return load()[section][key]


def update_config(patch: dict, persist: bool = True,
                  actor: str = "api") -> dict:
    """Validate + apply a partial update; persist to the config file.

    Returns {"config": effective, "event": audit_event}.
    Raises ValueError with the violation list if the patch is invalid.
    """
    with _LOCK:
        current = load()
        candidate = deep_merge(current, patch)
        errors = validate(candidate)
        if errors:
            raise ValueError("; ".join(errors))

        before = copy.deepcopy(current)
        _STATE["cfg"] = candidate
        _STATE["env_sig"] = _env_signature()
        if not persist:
            # accumulate in-memory overrides so a later rebuild preserves them
            _STATE["runtime"] = deep_merge(_STATE.get("runtime") or {}, patch)

        if persist:
            # persist the delta from DEFAULTS, not the whole tree — the file
            # stays a readable statement of *your* choices
            path = config_path()
            try:
                on_disk = _read_file(path)
            except (ValueError, json.JSONDecodeError, OSError):
                on_disk = {}
            merged_file = deep_merge(on_disk, patch)
            tmp = f"{path}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(merged_file, f, indent=2, sort_keys=True)
            os.replace(tmp, path)

        event = {
            "type": "config_update",
            "actor": actor,
            "time": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "patch": patch,
            "changed": _diff(before, candidate),
        }
        return {"config": candidate, "event": event}


def reset_cache() -> None:
    """Drop the cached config (tests, or after editing the file by hand)."""
    with _LOCK:
        _STATE["cfg"] = None
        _STATE["path"] = None
        _STATE["env_sig"] = None
        _STATE["runtime"] = {}


def _diff(before: dict, after: dict, prefix: str = "") -> dict:
    out: dict = {}
    for k in after:
        b, a = before.get(k), after[k]
        if isinstance(a, dict) and isinstance(b, dict):
            out.update(_diff(b, a, f"{prefix}{k}."))
        elif b != a:
            out[f"{prefix}{k}"] = {"from": b, "to": a}
    return out
