"""AI Activation — runtime path, prompt single-source-of-truth, GitHub↔HF coherence (Sprint 016).

Sprint 016 activates Omi's real intelligence by making the AI runtime path verifiable end to end
and removing the last embedded prompt. These tests lock in the new guarantees:

  * the **runtime dependency graph** (`runtime_path`) reports every link verified / operator_action /
    blocked, so "what prevents live Qwen" is a single checkable answer;
  * the **Prompt Registry is the single source of truth** — the production analyst resolves its
    system prompt from the registry and records its content-addressed version in the governance
    block (no longer an embedded file read);
  * **GitHub ↔ Hugging Face cannot drift** — the registry's ``omi_analyst`` prompt and the ml/ spec
    doc (the HF model-card source) are byte-identical, enforced here;
  * the **Governor stays mandatory** and the **deterministic fallback is unchanged**.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.reasoning import analyst
from app.reasoning.prompts import default_registry
from app.storage.db import reset_db_for_tests

_MD = Path(__file__).resolve().parents[3] / "ml" / "analyst" / "analyst_system_prompt_v1.md"


@pytest.fixture(autouse=True)
def _fresh():
    reset_db_for_tests("sqlite:///:memory:")
    yield


def _payload() -> dict:
    return {
        "overall_probability": 0.72, "overall_tier": "elevated", "confidence": 0.6,
        "summary": "Elevated suspicion across multiple signals.",
        "contributions": [
            {"name": "temporal", "impact": 0.5, "direction": "raises"},
            {"name": "community", "impact": 0.2, "direction": "lowers"},
        ],
        "video": {"clusters": [{"method": "co_engagement", "members": ["@a", "@b", "@c"]}]},
    }


def _md_system_prompt() -> str:
    text = _MD.read_text(encoding="utf-8")
    m = re.search(r"## SYSTEM_PROMPT.*?```text\n(.*?)\n```", text, re.DOTALL)
    return (m.group(1) if m else "").strip()


# --------------------------------------------------------------------------- #
# Prompt Registry = single source of truth (priority 6)
# --------------------------------------------------------------------------- #
def test_omi_analyst_prompt_is_registered_and_active():
    reg = default_registry()
    spec = reg.resolve("omi_analyst")
    assert spec.prompt_version == "v1" and reg.active_version("omi_analyst") == "v1"
    assert spec.prompt_hash.startswith("ph:")
    assert "OMI ANALYST" in spec.template and len(spec.template) > 2000
    # behavior_analyst (the council prompt) is untouched and still has its own active default.
    assert reg.active_version("behavior_analyst") == "v1"


def test_registry_prompt_matches_ml_doc_no_github_hf_drift():
    """The registry is canonical; the ml/ spec doc (HF model-card source) must mirror it exactly."""
    assert default_registry().resolve("omi_analyst").template == _md_system_prompt()


def test_assess_payload_records_registry_prompt_provenance(monkeypatch):
    """Every governed assessment is attributable to a content-addressed registry prompt version —
    proof the runtime prompt comes from the registry, not an embedded file."""
    monkeypatch.setattr(analyst, "analyst_enabled", lambda settings=None: True)
    out = analyst.assess_payload(_payload(), ref="sub_x", platform="youtube")
    assert out is not None
    prompt = out["governance"]["prompt"]
    assert prompt["analyst"] == "omi_analyst" and prompt["source"] == "registry"
    assert prompt["version"] == "v1"
    assert prompt["hash"] == default_registry().resolve("omi_analyst").prompt_hash
    # Governor still mandatory; engine number still echoed (unchanged by the prompt rewiring).
    assert out["governance"]["verdict"] in ("permit", "reject")
    assert out["suspicion_probability"] == 0.72


def test_injected_prompt_reaches_the_qwen_provider(monkeypatch):
    """The provider sends the *injected* registry prompt to the model, not the embedded fallback."""
    impl = analyst._impl()
    assert impl is not None
    captured = {}

    def _fake_call(self, system, user, config):
        captured["system"] = system
        return None  # force graceful fallback; we only care about what was sent

    monkeypatch.setattr(impl.providers.QwenAnalystProvider, "_call_model", _fake_call)
    sentinel = "SENTINEL REGISTRY PROMPT v1"
    provider = impl.QwenAnalystProvider(endpoint_url="https://x.invalid", system_prompt=sentinel)
    provider.generate({"headline_scores": {"overall_probability": 0.5, "tier": "moderate"}},
                      impl.load_analyst_config())
    assert captured["system"] == sentinel


# --------------------------------------------------------------------------- #
# Runtime dependency graph (deliverable: verified AI runtime path)
# --------------------------------------------------------------------------- #
def test_runtime_path_graph_marks_operator_gates_and_verified_code():
    rp = analyst.runtime_path()
    steps = {n["step"]: n["status"] for n in rp["nodes"]}
    # code-side links are VERIFIED out of the box…
    assert steps["evidence_bundle"] == "verified"
    assert steps["prompt_registry"] == "verified"
    assert steps["governor"] == "verified"
    assert steps["deterministic_floor"] == "verified"
    # …the blockers are exactly the operator-side config/secrets (off by default).
    assert steps["feature_flag"] == "operator_action"
    assert steps["hf_endpoint"] == "operator_action"
    assert steps["hf_token"] == "operator_action"
    assert rp["ready_for_live_qwen"] is False
    assert rp["active_provider"] == "deterministic-floor"
    assert set(rp["blockers"]) >= {"feature_flag", "hf_endpoint", "hf_token"}


def test_runtime_path_prompt_registry_is_verified_even_when_disabled():
    """The prompt registry link is a code dependency — verified regardless of the feature flag."""
    rp = analyst.runtime_path()
    prompt = next(n for n in rp["nodes"] if n["step"] == "prompt_registry")
    assert prompt["status"] == "verified" and "omi_analyst v1" in prompt["detail"]


def test_analyst_status_endpoint_includes_runtime_path():
    with TestClient(app) as tc:
        body = tc.get("/v1/investigations/analyst/status").json()
    assert "runtime_path" in body
    assert body["runtime_path"]["governor"] == "mandatory"
    assert any(n["step"] == "prompt_registry" for n in body["runtime_path"]["nodes"])


# --------------------------------------------------------------------------- #
# Deterministic fallback unchanged (priority 3) + Governor mandatory (priority 5)
# --------------------------------------------------------------------------- #
def test_disabled_by_default_no_assessment():
    assert analyst.runtime_path()["ready_for_live_qwen"] is False
    assert analyst.assess_payload(_payload(), ref="sub_x") is None   # off by default → no AI, no error
