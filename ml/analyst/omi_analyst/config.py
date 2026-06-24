"""Load the Omi Analyst runtime config from the registered HF model repo.

Requirement #3: *load model configuration from ``Andrewexiga/omi-analyst-v1``*. When
the registry + ``huggingface_hub`` + ``HF_TOKEN`` are available, the config is pulled
from the Hub (the source of record for the running Analyst). Otherwise it falls back
to the local published mirror committed at
``ml/analyst/hf_repo/config/analyst_config.json`` — identical content — so the Analyst
runs fully offline. The source actually used is recorded for transparency.

No network is required to run; NO training / fine-tuning happens here. ``HF_TOKEN`` is
read from the environment and never logged.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REPO_ID = "Andrewexiga/omi-analyst-v1"
LOCAL_CONFIG = REPO_ROOT / "ml/analyst/hf_repo/config/analyst_config.json"
CONFIG_PATH_IN_REPO = "config/analyst_config.json"


@dataclass
class AnalystConfig:
    """Resolved Analyst runtime config + provenance of where it was loaded from."""

    repo_id: str
    base_model: str
    model_revision: str
    prompt_version: str
    response_schema_version: int
    decoding: dict[str, Any]
    source: str  # "registry" | "local-mirror"
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def temperature(self) -> float:
        return float(self.decoding.get("temperature", 0.2))

    @property
    def max_new_tokens(self) -> int:
        return int(self.decoding.get("max_new_tokens", 2048))


def _from_dict(data: dict[str, Any], repo_id: str, source: str, revision: str | None) -> AnalystConfig:
    # base_model_revision is the registry's *pinned base*; the model_revision we record
    # on each output is the registry revision actually used (or the local-mirror tag).
    model_revision = revision or (
        "local-mirror" if source == "local-mirror" else data.get("base_model_revision", "main")
    )
    return AnalystConfig(
        repo_id=repo_id,
        base_model=data.get("base_model", "Qwen/Qwen3-4B-Thinking-2507-FP8"),
        model_revision=model_revision,
        prompt_version=data.get("prompt_version", "v1"),
        response_schema_version=int(data.get("response_schema_version", 1)),
        decoding=dict(data.get("decoding", {})),
        source=source,
        raw=data,
    )


def load_analyst_config(
    repo_id: str = DEFAULT_REPO_ID,
    revision: str | None = None,
    prefer_remote: bool = True,
) -> AnalystConfig:
    """Resolve the Analyst config, preferring the HF registry, falling back to local.

    Never raises on a missing token / network / dependency — it degrades to the local
    mirror so the Analyst always has a config to run with.
    """
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
    if prefer_remote and token:
        try:
            from huggingface_hub import hf_hub_download  # type: ignore

            path = hf_hub_download(
                repo_id=repo_id, filename=CONFIG_PATH_IN_REPO,
                repo_type="model", revision=revision, token=token,
            )
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            return _from_dict(data, repo_id, "registry", revision)
        except Exception:  # noqa: BLE001 — any failure → local mirror
            pass

    data = json.loads(LOCAL_CONFIG.read_text(encoding="utf-8"))
    return _from_dict(data, repo_id, "local-mirror", revision)
