"""Phase 2 — the IO-coordination harness (real campaigns through existing detectors).

Pins the reuse contract: a coordinated clone-set scores higher and flags members,
while a diverse set scores lower — using the SAME detectors the synthetic
coordination benchmark runs, with real timestamps preserved.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.evaluation.io_coordination import build_scenario, evaluate_scenario
from app.ml.public_import import PublicRecord

_T0 = datetime(2020, 1, 1, tzinfo=timezone.utc)

# Two ~30-word posts → over the style detector's word floor.
_CLONE = [
    "Citizens must rise up today and reject the corrupt establishment agenda before our great nation is lost forever to the globalist elite forces",
    "Share this everywhere now: the corrupt establishment agenda threatens our great nation and only united patriots can stop the globalist elite today",
]


def _rec(eid: str, texts: list[str], *, role_bot: bool, age: int = 200) -> PublicRecord:
    return PublicRecord(
        external_id=eid, texts=texts, is_bot=role_bot, handle=eid,
        account_age_days=age,
        post_times=[_T0 + timedelta(hours=i) for i in range(len(texts))],
    )


def test_harness_separates_coordinated_from_diverse():
    # Coordinated: five accounts posting the SAME cloned text (shared style +
    # near-identical fingerprints) and created in the same window.
    coord = [_rec(f"c{i}", list(_CLONE), role_bot=True, age=200) for i in range(5)]
    coord_scn = build_scenario("clones", coord, role="bot", expected="high")
    cr = evaluate_scenario(coord_scn)

    # Diverse: five accounts with distinct content, varied ages.
    diverse_texts = [
        ["just tried the new ramen place downtown and honestly the broth was incredible, ten out of ten would slurp again"],
        ["spent the weekend debugging a gnarly race condition in the scheduler, turns out it was a missing memory barrier the whole time"],
        ["my garden tomatoes finally came in this year after three failed attempts, the trick was way more compost than i expected"],
        ["watched a documentary about deep sea anglerfish last night and now i cannot stop thinking about bioluminescence honestly"],
        ["the city council meeting ran four hours over the zoning variance, democracy is slow but i guess that is the point"],
    ]
    diverse = [_rec(f"d{i}", diverse_texts[i], role_bot=False, age=300 + i * 137) for i in range(5)]
    div_scn = build_scenario("diverse", diverse, role="organic", expected="none")
    dr = evaluate_scenario(div_scn)

    # Shape of the result (the per-detector contribution breakdown is the deliverable).
    assert {"score", "recall", "fpr", "contributions", "clusters_by_method"} <= cr.keys()
    methods = {c["method"] for c in cr["contributions"]}
    assert "fingerprint_cluster" in methods and "style_match" in methods

    # The cloned campaign scores higher and flags its members; the diverse set
    # is not pulled up to the same level.
    assert cr["score"] > dr["score"]
    assert cr["flagged_fraction"] > 0.0
    assert cr["recall"] is not None and dr["fpr"] is not None


def test_evaluate_scenario_is_deterministic():
    recs = [_rec(f"c{i}", list(_CLONE), role_bot=True) for i in range(4)]
    scn = build_scenario("x", recs, role="bot", expected="high")
    a = evaluate_scenario(scn)
    b = evaluate_scenario(build_scenario("x", recs, role="bot", expected="high"))
    assert a["score"] == b["score"] and a["flagged_fraction"] == b["flagged_fraction"]
