"""The eight scored dimensions are declared twice, in two languages, and nothing at runtime
reconciles them.

``COMPREHENSIVE_SIGNAL_NAMES`` (Python) is what the model is told to return and what
``analyst._normalise_signals`` normalises against. ``ACCOUNT_SIGNAL_KEYS`` (TypeScript, in
``apps/web/lib/api.ts``) is what the UI renders, and ``ACCOUNT_SIGNAL_META`` is the reader-facing
name and explanation for each.

The failure this guards is silent and one-directional. Rename or reorder a dimension on the backend
and the model happily returns the new name; the frontend's ``ACCOUNT_SIGNAL_META`` lookup misses,
``SignalBreakdown`` filters the row out, and the account renders with seven dimensions (or none) with
no error anywhere. Customers see a gap in the product's primary output and nothing logs it.

So the lists must stay identical, in the same order, and every key must carry a label and a
description. Change one side, change the other in the same commit.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app.reasoning.prompts.comprehensive_investigation_template import (
    COMPREHENSIVE_SIGNAL_NAMES,
)

_WEB_API_TS = Path(__file__).resolve().parents[3] / "apps" / "web" / "lib" / "api.ts"

pytestmark = pytest.mark.skipif(
    not _WEB_API_TS.is_file(),
    reason="apps/web is not checked out beside apps/api",
)


def _source() -> str:
    return _WEB_API_TS.read_text(encoding="utf-8")


def _ts_signal_keys() -> list[str]:
    """The string literals of ``export const ACCOUNT_SIGNAL_KEYS = [...] as const``, in order."""
    m = re.search(r"export const ACCOUNT_SIGNAL_KEYS = \[(.*?)\] as const;", _source(), re.S)
    assert m, "ACCOUNT_SIGNAL_KEYS is missing from apps/web/lib/api.ts"
    return re.findall(r"'([^']+)'", m.group(1))


def _ts_meta_keys() -> list[str]:
    """The keys of the ``ACCOUNT_SIGNAL_META`` record, in declaration order."""
    m = re.search(
        r"export const ACCOUNT_SIGNAL_META: Record<[^>]+> = \{(.*?)\n\};", _source(), re.S
    )
    assert m, "ACCOUNT_SIGNAL_META is missing from apps/web/lib/api.ts"
    # Top-level keys only: each entry is `  name: {` at exactly two spaces of indent.
    return re.findall(r"^  (\w+): \{", m.group(1), re.M)


def test_the_web_signal_keys_match_the_backend_exactly():
    """Same names, same order. Order matters: the UI renders the grid in list order, so a reordered
    backend tuple would silently reshuffle every account's breakdown."""
    assert _ts_signal_keys() == list(COMPREHENSIVE_SIGNAL_NAMES)


def test_every_signal_has_a_reader_facing_label_and_description():
    """A key with no metadata entry is filtered out of the rendered grid, so a missing one costs the
    customer a whole dimension rather than raising."""
    meta_keys = _ts_meta_keys()
    assert sorted(meta_keys) == sorted(COMPREHENSIVE_SIGNAL_NAMES)

    body = re.search(
        r"export const ACCOUNT_SIGNAL_META: Record<[^>]+> = \{(.*?)\n\};", _source(), re.S
    ).group(1)
    for name in COMPREHENSIVE_SIGNAL_NAMES:
        entry = re.search(rf"^  {name}: \{{(.*?)^  \}},", body, re.S | re.M)
        assert entry, f"{name} has no ACCOUNT_SIGNAL_META entry"
        assert "label:" in entry.group(1), f"{name} is missing a label"
        assert "description:" in entry.group(1), f"{name} is missing a description"


def test_the_signal_names_are_stable_identifiers():
    """These strings cross a JSON boundary, a schema enum and a TS union. Anything that is not a
    plain snake_case identifier would need escaping somewhere and break quietly."""
    for name in COMPREHENSIVE_SIGNAL_NAMES:
        assert re.fullmatch(r"[a-z][a-z0-9_]*", name), name
    assert len(set(COMPREHENSIVE_SIGNAL_NAMES)) == len(COMPREHENSIVE_SIGNAL_NAMES) == 8


def test_the_web_signal_type_is_derived_from_the_key_list():
    """``AccountSignalKey`` must be derived from ACCOUNT_SIGNAL_KEYS rather than re-typed by hand,
    or the union and the runtime list can disagree without TypeScript noticing."""
    assert (
        "export type AccountSignalKey = (typeof ACCOUNT_SIGNAL_KEYS)[number];" in _source()
    )


def test_no_em_or_en_dashes_in_the_signal_metadata():
    """House rule: no em or en dashes anywhere in apps/web. This copy renders directly on the site,
    once per dimension per account, so it is the highest-frequency prose in the product."""
    body = re.search(
        r"export const ACCOUNT_SIGNAL_META: Record<[^>]+> = \{(.*?)\n\};", _source(), re.S
    ).group(1)
    assert "—" not in body and "–" not in body


def test_the_backend_normaliser_returns_every_dimension_in_order():
    """The UI renders eight rows unconditionally and never branches per account, which is only safe
    because the backend materialises the ones the model omitted."""
    from app.reasoning.analyst import _normalise_signals

    partial = [{"name": "voice", "score": 91, "reason": "reads as interchangeable filler"}]
    out = _normalise_signals(partial)

    assert [s["name"] for s in out] == list(COMPREHENSIVE_SIGNAL_NAMES)
    assert out[COMPREHENSIVE_SIGNAL_NAMES.index("voice")]["score"] == 91
    # Everything the model did not send comes back explicitly unscored, never zero.
    assert all(
        s["score"] is None for s in out if s["name"] != "voice"
    ), "an omitted dimension must be None, not 0"


def test_ast_parse_of_the_signal_tuple_matches_the_module_constant():
    """Belt and braces: read the tuple out of the source too, so a dynamically rebuilt
    COMPREHENSIVE_SIGNAL_NAMES could not quietly diverge from what a reader sees in the file."""
    src = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "reasoning"
        / "prompts"
        / "comprehensive_investigation_template.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(src)
    literal = None
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "COMPREHENSIVE_SIGNAL_NAMES":
            literal = ast.literal_eval(node.value)
            break
    assert literal is not None, "COMPREHENSIVE_SIGNAL_NAMES is no longer a module-level literal"
    assert list(literal) == list(COMPREHENSIVE_SIGNAL_NAMES)
