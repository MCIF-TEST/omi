"""The "no model, no network" guarantee, pinned at the import level.

This was an explicit product requirement, and a requirement that is only true by inspection stops
being true the first time someone adds a convenient import. Checking the module graph rather than
mocking a client is what makes it hold: you cannot call what you cannot import.

The detector is also the reason ``app/campaigns/detector/cohort.py`` reads the analyst's cache key
out of the payload dict by name instead of importing ``app.reasoning.analyst``. That looks like an
odd choice until you see this test.
"""

from __future__ import annotations

import ast
import pathlib

PACKAGE = pathlib.Path(__file__).resolve().parents[1] / "app" / "campaigns" / "detector"

#: Nothing in the detector may reach these. The first three are the model and provider stacks; the
#: rest are the transport libraries that would let it make a call directly.
FORBIDDEN_PREFIXES = (
    "app.reasoning",
    "app.governor",
    "app.integrations",
    "httpx",
    "requests",
    "urllib.request",
    "openai",
    "anthropic",
    "transformers",
    "sentence_transformers",
)

#: scipy is installed here only as a transitive dependency of scikit-learn and is NOT declared in
#: apps/api/pyproject.toml. Importing it would put the statistical core of a detector that names
#: real people at the mercy of somebody else's dependency change.
FORBIDDEN_EXACT = ("scipy",)


def _module_names(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import, stays inside the package
                continue
            if node.module:
                names.add(node.module)
    return names


def _detector_files() -> list[pathlib.Path]:
    files = sorted(PACKAGE.glob("*.py"))
    assert files, "the detector package should not be empty"
    return files


def test_the_detector_cannot_reach_a_model_or_the_network():
    offenders: list[str] = []
    for path in _detector_files():
        for name in _module_names(path):
            if name in FORBIDDEN_EXACT or any(
                name == p or name.startswith(p + ".") for p in FORBIDDEN_PREFIXES
            ):
                offenders.append(f"{path.name} imports {name}")
    assert offenders == [], (
        "The coordination detector must stay deterministic and offline. Offending imports:\n  "
        + "\n  ".join(offenders)
    )


def test_the_detector_does_not_import_scipy():
    """Called out separately from the network check because the reason is different: scipy is
    present in this environment, so this would pass silently at runtime and fail only on a
    production build where scikit-learn's dependency set had moved."""
    for path in _detector_files():
        assert "scipy" not in _module_names(path), path.name


def test_the_signals_registry_matches_the_family_map():
    """A signal with no family is silently dropped by ``fuse_pairs``: ``METHOD_FAMILY.get`` returns
    None and the edge is skipped, so the signal would run on every scan, cost time, and contribute
    nothing, with nothing anywhere reporting a problem. Same shape of failure as the signal-name
    contract between the analyst and the frontend."""
    from app.campaigns.detector import signals
    from app.campaigns.detector.types import METHOD_FAMILY

    registered = {fn.__name__ for fn in signals.SIGNALS}
    mapped = set(METHOD_FAMILY)
    assert registered == mapped, (
        f"registered but unmapped: {sorted(registered - mapped)}; "
        f"mapped but unregistered: {sorted(mapped - registered)}"
    )


def test_every_family_has_a_reliability_and_a_frontend_label():
    """The Python family list and ``COORDINATION_FAMILY_LABEL`` in apps/web/lib/api.ts are declared
    twice in two languages with nothing at runtime reconciling them. Rename one side and the UI
    silently renders a raw key. Same drift ``test_signal_names_contract.py`` guards for the eight
    per-account signals."""
    import re

    from app.campaigns.detector.types import FAMILY_RELIABILITY, METHOD_FAMILY

    families = set(METHOD_FAMILY.values())
    assert families == set(FAMILY_RELIABILITY), "every family needs a reliability prior"

    api_ts = (
        pathlib.Path(__file__).resolve().parents[3]
        / "apps" / "web" / "lib" / "api.ts"
    )
    if not api_ts.exists():  # pragma: no cover - the web app is not always checked out
        return
    block = re.search(
        r"COORDINATION_FAMILY_LABEL:\s*Record<string, string>\s*=\s*\{(.*?)\}",
        api_ts.read_text(), re.S,
    )
    assert block, "COORDINATION_FAMILY_LABEL not found in apps/web/lib/api.ts"
    declared = set(re.findall(r"^\s*(\w+):", block.group(1), re.M))
    assert families == declared, (
        f"family drift between Python and the frontend: "
        f"python-only {sorted(families - declared)}, ts-only {sorted(declared - families)}"
    )
