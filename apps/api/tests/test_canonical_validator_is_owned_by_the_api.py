"""The canonical validator must be importable from the API's OWN package, on a real deploy.

**The bug this exists to prevent, which shipped and floored every investigation.**

``app/governor/comprehensive.py`` imported ``omi_analyst.schema_validate``. That package lives under
``ml/analyst/`` and ``apps/api/pyproject.toml`` packages only ``app*``, so it is not installed with the
API. On a real deploy:

1. the import raised ``ModuleNotFoundError``;
2. ``validate_comprehensive_model_output`` appended ``"canonical validator unavailable: ..."``;
3. a non-empty error list IS a validation failure, so ``runtime.py::_canonical_candidate`` returned
   ``None`` for EVERY model response, whatever the model actually said;
4. the deterministic Floor was persisted instead, on every investigation;
5. nothing raised, so the background pool reported nothing and the error tracker never heard about it.

The product looked like it was running an AI analyst and had not produced a written analysis for any
scan. Failing closed when the validator is unreachable is correct and is unchanged. The defect was that
a packaging boundary, not a validation problem, made it unreachable.

**Why the old suite could not catch it.** These same tests ran green with the validator unavailable,
because nothing asserted that validation was actually happening. A test that passes whether or not the
validator loads cannot protect the validator. That is the specific gap closed here.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.governor import validate_comprehensive_model_output
from app.governor.canonical_validate import validate_analyst_response
from app.reasoning.prompts.comprehensive_investigation_template import (
    COMPREHENSIVE_SECTION_KEYS,
    comprehensive_investigation_canonical_schema,
)
from app.reasoning.prompts.master_protocol import compile_master_analyst_protocol

_UNAVAILABLE = "canonical validator unavailable"


@pytest.fixture(scope="module")
def worked_example() -> dict:
    """The example object the shipped protocol tells the model to copy."""
    text = compile_master_analyst_protocol()["text"]
    seg = text[text.index("EXAMPLE of a valid output object"):]
    return json.loads(seg[seg.index("{"):].rstrip())


def test_the_canonical_validator_imports_from_the_api_package():
    """The load-bearing assertion. If this import needs anything outside ``app/``, a packaged deploy
    cannot run it and every investigation floors."""
    assert callable(validate_analyst_response)
    assert validate_analyst_response.__module__.startswith("app.")


def test_the_api_does_not_import_the_ml_validator_anywhere():
    """A source-level guard, in the spirit of the signal-gate one: re-adding the cross-boundary import
    would restore the outage and no behavioural test would necessarily notice, because the failure is
    an import that only fails once the app is packaged."""
    # Scoped to the VALIDATOR import, and matching an import rather than a mention (this fix's own
    # comments name the old import, and a substring check would flag the explanation as the offence).
    #
    # `analyst.py` separately does `import omi_analyst` to load the legacy HF implementation, after
    # appending ml/analyst to sys.path inside `_impl()`. That is deliberately left alone here, but it is
    # also how this outage hid for so long: the validator import only ever succeeded when `_impl()` had
    # already run and patched sys.path as a side effect. Canonical validation of every investigation was
    # riding on an unrelated legacy function having been called first.
    import re

    pattern = re.compile(
        r"^\s*(?:from\s+omi_analyst\.schema_validate\s+import|"
        r"from\s+omi_analyst\s+import\s+schema_validate)", re.M)
    app_dir = Path(__file__).resolve().parents[1] / "app"
    offenders = [
        p.relative_to(app_dir).as_posix()
        for p in app_dir.rglob("*.py")
        if pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == [], (
        f"{offenders} import the validator from ml/, which apps/api does not package. "
        "Use app.governor.canonical_validate."
    )


def test_validation_actually_runs_rather_than_reporting_itself_unavailable(worked_example):
    """The exact production symptom, asserted directly: a good object must come back with NO errors,
    and specifically not the 'unavailable' one. Before the fix this returned exactly that string."""
    errs = validate_comprehensive_model_output(
        worked_example,
        schema=comprehensive_investigation_canonical_schema(),
        section_keys=COMPREHENSIVE_SECTION_KEYS,
    )
    assert not any(_UNAVAILABLE in str(e) for e in errs), errs
    assert errs == [], errs


def test_the_shipped_worked_example_validates(worked_example):
    """Models copy the example over the rules, so an example that cannot pass our own validator would
    teach every response to fail it. This is cheap and it closes the loop between the prompt we ship
    and the validator that judges the reply."""
    # A5 is the elevated worked account added in v14. Before it, the only non-low example in the
    # whole protocol was an 82 resting on leaked machine boilerplate, so the 50-74 band had no
    # picture at all and the model had never been shown what an ordinary elevated account is.
    assert [a["ref"] for a in worked_example["commenter_assessments"]] == [
        "A1", "A2", "A3", "A4", "A5"]
    errs = validate_comprehensive_model_output(
        worked_example,
        schema=comprehensive_investigation_canonical_schema(),
        section_keys=COMPREHENSIVE_SECTION_KEYS,
    )
    assert errs == [], errs


def test_a_genuinely_invalid_object_is_still_rejected():
    """The fix must not have turned validation into a rubber stamp: the whole point is that real
    schema violations still floor the response."""
    errs = validate_comprehensive_model_output(
        {"not": "a valid assessment"},
        schema=comprehensive_investigation_canonical_schema(),
        section_keys=COMPREHENSIVE_SECTION_KEYS,
    )
    assert errs
    assert not any(_UNAVAILABLE in str(e) for e in errs)


def test_a_missing_schema_fails_closed_rather_than_passing():
    """The vendored copy dropped ml/'s repo-relative schema default, which could not resolve in a
    packaged deploy anyway. Absent a schema it must return an error, never an empty (valid) list."""
    assert validate_analyst_response({"anything": 1}, schema=None)


def test_the_api_copy_and_the_ml_copy_agree(worked_example):
    """``ml/analyst/omi_analyst/schema_validate.py`` stays where it is for the offline pipeline. The two
    must not drift, or the API and the training tooling would disagree about what a valid response is.
    Skipped when the ml/ tree is absent, the same way the corpus-backed tests skip themselves."""
    ml_mod = (Path(__file__).resolve().parents[3]
              / "ml" / "analyst" / "omi_analyst" / "schema_validate.py")
    if not ml_mod.exists():
        pytest.skip("ml/ tree not present")

    import importlib.util

    spec = importlib.util.spec_from_file_location("_ml_schema_validate", ml_mod)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    schema = comprehensive_investigation_canonical_schema()
    for obj in (worked_example, {"not": "valid"}):
        assert mod.validate_analyst_response(obj, schema=schema) == \
            validate_analyst_response(obj, schema=schema)
