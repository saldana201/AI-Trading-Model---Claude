"""Setup validator (design doc §5.1 — the anti-hallucination contract).

Every price in a setup (entry, stop, targets) must appear in the engine
evidence payload the setup was composed from, within tolerance. Any setup
citing a level absent from evidence is rejected — this is what keeps an
LLM-composed (or buggy) setup from inventing numbers.
"""

from __future__ import annotations

PRICE_FIELDS = ("entry_trigger", "stop", "target_1", "target_2")
REL_TOL = 0.0015  # 0.15%


def collect_numbers(obj) -> set[float]:
    out: set[float] = set()
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.add(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            out |= collect_numbers(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out |= collect_numbers(v)
    return out


def validate_setup(setup: dict, evidence: dict) -> dict:
    """Returns {'valid': bool, 'violations': [...]}. ATR-derived levels are
    allowed only when the setup declares them in derived_levels with their
    formula inputs, and those inputs must themselves trace to evidence."""
    numbers = collect_numbers(evidence)
    derived = setup.get("derived_levels", {})
    violations = []

    def traces(value: float) -> bool:
        return any(
            abs(value - n) <= max(abs(n) * REL_TOL, 0.011) for n in numbers
        )

    for field in PRICE_FIELDS:
        value = setup.get(field)
        if value is None:
            continue
        if traces(value):
            continue
        formula = derived.get(field)
        if formula and all(traces(x) for x in formula.get("inputs", [])):
            continue
        violations.append({
            "field": field, "value": value,
            "reason": "level not present in engine evidence and not a declared derivation",
        })

    return {"valid": not violations, "violations": violations}
