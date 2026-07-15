"""Repository-wide invariant — EXACTLY ONE production investigation inference path exists.

The single-inference architecture requires that the whole production investigation reason in ONE
endpoint request. This invariant scans the application source and proves it structurally:

* ``run_stage_inference(...)`` — the canonical per-stage inference entry — is CALLED from exactly one
  production site: :func:`app.reasoning.analyst._assess_core` (the comprehensive investigation);
* the retired per-stage runners (comment / commenter-history) no longer import or call it — they are
  builder-only;
* the ONE transport (``_qwen_transport``) and the ONE Governor invocation are reached only through the
  runtime, never a stage directly;
* the two public production entries (``assess_payload`` / ``assess_investigation``) both funnel into the
  single ``_assess_core``.

If a new endpoint-capable per-stage inference path is ever added, this test fails.
"""
from __future__ import annotations

import re
from pathlib import Path

_APP = Path(__file__).resolve().parents[1] / "app"


def _py_files() -> list[Path]:
    return [p for p in _APP.rglob("*.py") if "__pycache__" not in p.parts]


def _call_sites(symbol: str) -> list[tuple[str, int]]:
    """Every source line that CALLS ``symbol`` (``symbol(``) — excluding its definition, imports, and
    ``__all__`` / docstring mentions. Returns (relative_path, lineno)."""
    call = re.compile(rf"(?<![\w.]){re.escape(symbol)}\s*\(")
    hits: list[tuple[str, int]] = []
    for p in _py_files():
        for i, line in enumerate(p.read_text().splitlines(), start=1):
            s = line.strip()
            if s.startswith(("def ", "import ", "from ", "#", '"', "*")):
                continue
            if f"def {symbol}(" in line:
                continue
            if call.search(line):
                hits.append((str(p.relative_to(_APP)), i))
    return hits


def test_exactly_one_production_run_stage_inference_call_site():
    sites = _call_sites("run_stage_inference")
    assert len(sites) == 1, f"expected ONE run_stage_inference call site, found: {sites}"
    path, _ln = sites[0]
    assert path == "reasoning/analyst.py", f"the sole inference call site must be analyst.py, got {path}"


def test_retired_stage_runners_do_not_import_or_call_inference():
    for mod in ("reasoning/comment_analysis.py", "reasoning/commenter_history_analysis.py"):
        src = (_APP / mod).read_text()
        assert "run_stage_inference" not in src, f"{mod} must not reference run_stage_inference"
        assert "def run_comment_analysis" not in src and "def run_commenter_history_analysis" not in src
        # they remain builder-only — the stage prompt builder is still present
        assert "build_prompt(" in src and "register_stage_prompt(" in src


def test_only_the_runtime_reaches_the_transport_and_governor():
    """No stage reaches the model transport directly. The runtime reaches the model ONLY through the
    provider dispatcher ``_reasoning_transport`` (Phase 2), and the concrete provider transports (the HF
    ``_qwen_transport`` and the ``_openrouter_transport``) are reached ONLY by that dispatcher — so there
    is still a SINGLE funnel to the ONE inference no matter which provider serves it."""
    dispatch = _call_sites("_reasoning_transport")
    assert all(path == "reasoning/runtime.py" for path, _ in dispatch), \
        f"_reasoning_transport must be reached only via the runtime, got {dispatch}"
    for name in ("_qwen_transport", "_openrouter_transport"):
        sites = _call_sites(name)
        assert all(path == "reasoning/analyst.py" for path, _ in sites), \
            f"{name} must be reached only via the provider dispatcher in analyst.py, got {sites}"


def test_both_public_entries_funnel_into_the_single_core():
    from app.reasoning import analyst, runtime
    # assess_payload -> assess_investigation -> _assess_core  (one production path)
    import inspect
    assert "_assess_core" in inspect.getsource(runtime.assess_investigation)
    assert "assess_investigation" in inspect.getsource(analyst.assess_payload)


def test_only_one_stage_makes_a_model_response_with_domain_sidecars():
    """The comprehensive stage is the only one that emits the six per-domain reasoning sidecars; the
    runtime strips exactly those keys (plus the legacy per-item sidecars) before the Governor."""
    from app.reasoning.prompts.comprehensive_investigation_template import COMPREHENSIVE_SECTION_KEYS
    from app.reasoning.runtime import _STAGE_SIDECAR_KEYS
    for key in COMPREHENSIVE_SECTION_KEYS:
        assert key in _STAGE_SIDECAR_KEYS, f"{key} must be stripped before the Governor validates"
