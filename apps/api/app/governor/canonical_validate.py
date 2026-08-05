"""The canonical analyst-response validator, owned by the API.

This is a VERBATIM port of ``ml/analyst/omi_analyst/schema_validate.py`` and must stay behaviourally
identical to it (``tests/test_canonical_validator_is_owned_by_the_api.py`` asserts they agree).

**Why it lives here.** ``app/governor/comprehensive.py`` and ``app/reasoning/runtime.py`` imported
``omi_analyst.schema_validate`` directly. That package lives under ``ml/analyst/`` and
``apps/api/pyproject.toml`` packages only ``app*``, so it is NOT installed with the API. On a real
deploy the import raised ModuleNotFoundError, ``validate_comprehensive_model_output`` returned
``["canonical validator unavailable: ..."]``, and because a non-empty error list IS a validation
failure, ``runtime.py`` discarded EVERY model response and served the deterministic Floor. The result
was an analyst that appeared to run and never produced a written analysis, on every investigation,
with no exception raised anywhere to say so.

Failing closed when the validator is unreachable is the right call and is unchanged. The bug was that
a packaging boundary, not a validation problem, made it unreachable in production. The API's own
canonical validation must not depend on a directory the API does not ship.

The ``ml/`` copy stays where it is: the offline pipeline uses it and must not import from the API.
"""

from __future__ import annotations

from typing import Any

# No repo-relative schema default here on purpose: every API caller passes the canonical schema
# explicitly, and a path into ml/ would not resolve inside a packaged deploy anyway.

# Absolute phrasings the analyst must never use (spec 15.3 / prompt rule 2).
BANNED_PHRASES = (
    "is a bot", "is fake", "is a coordinated campaign", "definitely",
    "certainly", "proven", "without a doubt", "is a manipulation network",
)
# Phrases that legitimately explain an empty evidence_against (failure mode F5).
_NO_EXCULPATION_HINTS = (
    "no exculpatory", "no counter-evidence", "no counter evidence", "no exculpation",
    "none were present", "no signal lowered", "no exculpating", "no mitigating",
)


def _check_enum(errors: list[str], where: str, value: Any, enum: list[Any]) -> None:
    if value not in enum:
        errors.append(f"{where}: {value!r} not in allowed {enum}")


def _check_evidence_item(errors: list[str], where: str, item: Any) -> None:
    if not isinstance(item, dict):
        errors.append(f"{where}: evidence item must be an object")
        return
    for req in ("signal", "claim", "evidence_refs"):
        if req not in item:
            errors.append(f"{where}: missing required '{req}'")
    if not str(item.get("signal", "")).strip():
        errors.append(f"{where}: 'signal' is empty")
    if not str(item.get("claim", "")).strip():
        errors.append(f"{where}: 'claim' is empty")
    refs = item.get("evidence_refs")
    if not isinstance(refs, list) or len([r for r in refs if str(r).strip()]) < 1:
        errors.append(f"{where}: 'evidence_refs' must have >=1 non-empty ref (F1)")
    direction = item.get("direction")
    if direction is not None:
        _check_enum(errors, f"{where}.direction", direction, ["raises", "lowers", "neutral"])
    impact = item.get("impact")
    if impact is not None and not (isinstance(impact, (int, float)) and 0.0 <= impact <= 1.0):
        errors.append(f"{where}.impact: must be a number in [0,1]")


def validate_analyst_response(obj: Any, schema: dict[str, Any] | None = None) -> list[str]:
    """Return a list of validation errors; empty means the object is valid."""
    errors: list[str] = []
    if not isinstance(obj, dict):
        return ["response is not a JSON object"]
    if schema is None:
        return ["canonical schema was not supplied to the validator"]
    props: dict[str, Any] = schema.get("properties", {})

    # 1) required top-level keys + no unexpected keys (additionalProperties: false).
    for req in schema.get("required", []):
        if req not in obj:
            errors.append(f"missing required field: {req}")
    if schema.get("additionalProperties") is False:
        for key in obj:
            if key not in props:
                errors.append(f"unexpected top-level field: {key}")

    # 2) generic scalar/enum/const checks driven by the schema itself.
    for key, spec in props.items():
        if key not in obj:
            continue
        val = obj[key]
        if "const" in spec and val != spec["const"]:
            errors.append(f"{key}: must equal {spec['const']!r}")
        if "enum" in spec and not isinstance(val, list):
            _check_enum(errors, key, val, spec["enum"])
        if "pattern" in spec and isinstance(val, str):
            import re
            if not re.match(spec["pattern"], val):
                errors.append(f"{key}: {val!r} does not match {spec['pattern']}")
        if spec.get("type") == "number" and isinstance(val, (int, float)):
            if "minimum" in spec and val < spec["minimum"]:
                errors.append(f"{key}: {val} < minimum {spec['minimum']}")
            if "maximum" in spec and val > spec["maximum"]:
                errors.append(f"{key}: {val} > maximum {spec['maximum']}")
        if spec.get("minLength") and isinstance(val, str) and len(val) < spec["minLength"]:
            errors.append(f"{key}: shorter than minLength {spec['minLength']}")

    # 3) subject sub-object.
    subject = obj.get("subject")
    if isinstance(subject, dict):
        for req in ("grain", "ref", "platform"):
            if req not in subject:
                errors.append(f"subject: missing '{req}'")
        if "grain" in subject:
            _check_enum(errors, "subject.grain", subject["grain"],
                        ["account", "campaign", "narrative", "comment_section", "commenter"])
        if "platform" in subject:
            _check_enum(errors, "subject.platform", subject["platform"],
                        ["youtube", "twitter", "unknown"])
    elif subject is not None:
        errors.append("subject: must be an object")

    # 4) evidence arrays + items.
    for arr_key in ("evidence_for", "evidence_against"):
        arr = obj.get(arr_key)
        if arr is None:
            continue
        if not isinstance(arr, list):
            errors.append(f"{arr_key}: must be an array")
            continue
        for i, item in enumerate(arr):
            _check_evidence_item(errors, f"{arr_key}[{i}]", item)

    # 5) mandatory-counter-evidence rule (F5).
    ev_against = obj.get("evidence_against")
    if isinstance(ev_against, list) and len(ev_against) == 0:
        rationale = str(obj.get("confidence_rationale", "")).lower()
        if not any(h in rationale for h in _NO_EXCULPATION_HINTS):
            errors.append(
                "evidence_against is empty but confidence_rationale does not state that "
                "no exculpatory signal was present (failure mode F5)"
            )

    # 6) mandatory non-empty list fields.
    for arr_key in ("uncertainty", "what_would_change_this"):
        arr = obj.get(arr_key)
        if isinstance(arr, list) and len([x for x in arr if str(x).strip()]) == 0:
            errors.append(f"{arr_key}: must contain >=1 non-empty entry")

    # 7) corroboration sub-object.
    corr = obj.get("corroboration")
    if isinstance(corr, dict):
        for req in ("discriminative_methods", "single_axis_capped", "convergence"):
            if req not in corr:
                errors.append(f"corroboration: missing '{req}'")
    elif corr is not None:
        errors.append("corroboration: must be an object")

    # 8) banned-absolute-phrase lint over the free-text fields.
    text = " ".join(str(obj.get(k, "")) for k in ("headline", "assessment", "limits_statement"))
    low = text.lower()
    for phrase in BANNED_PHRASES:
        if phrase in low:
            errors.append(f"banned absolute phrasing in prose: {phrase!r} (spec 15.3)")

    # 9) optional cross-check with jsonschema if it happens to be installed.
    try:
        import jsonschema  # type: ignore

        v = jsonschema.Draft202012Validator(schema)
        for e in v.iter_errors(obj):
            errors.append(f"jsonschema: {e.message}")
    except Exception:  # noqa: BLE001 — not installed / any issue: rely on built-in checks
        pass

    # de-dupe while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for e in errors:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out
