"""A mission that reports five candidates must have built five levels.

For the whole life of the pipeline it did not. The site spec was written to one
path per mission instead of one per candidate, so every Lot job read whichever
spec was written last and every candidate came out byte-identical. It passed
validation five times, because per-candidate validation running N times looks
exactly the same whether the N are real or copies.

These tests cover both halves of the fix: the variation that makes candidates
diverge, and the comparison that notices when they don't. The comparison matters
more -- variation can regress quietly, a gate cannot.
"""
from __future__ import annotations

from packages.pipeline.site_variation import (
    ground_size, site_placements,
)
from packages.validation.candidate_diversity import (
    CODE_NO_CANDIDATES, CODE_NOT_DISTINCT, check_candidate_diversity,
    distinct_count, summarize,
)

# The real seeds from the user's rockay_category5 batch -- the set that shipped
# five identical levels. If any pair of these ever collides again, the pipeline
# is back where it started, so they are the fixture rather than tidy 1..5.
REAL_SEEDS = (5017, 5118, 5219, 5320, 5421)


# ---------------------------------------------------------------------------
# site_variation: candidates have to actually differ
# ---------------------------------------------------------------------------
def test_the_real_seed_set_produces_five_different_sites():
    placements = [site_placements(s, 4) for s in REAL_SEEDS]
    signatures = {repr(p) for p in placements}
    assert len(signatures) == len(REAL_SEEDS), (
        "two seeds produced the same site -- this is the exact failure that "
        "shipped five identical candidates")


def test_the_same_seed_always_produces_the_same_site():
    # The cache fingerprint and the diversity gate both re-derive what the
    # builder derived; if this drifts, a cached build and a fresh one disagree.
    assert site_placements(5017, 4) == site_placements(5017, 4)


def test_variation_is_structural_not_cosmetic():
    # A metre of jitter would make the hashes differ while leaving the level
    # identical to play. Yaw is the thing that changes which facade fronts the
    # street, so across a seed set the yaws must not all be the same.
    yaws = {b["rot"] for s in REAL_SEEDS for b in site_placements(s, 4)["buildings"]}
    assert len(yaws) > 1
    assert yaws <= {0, 90, 180, 270}, "off-cardinal yaw reads as damage, not design"


def test_buildings_never_overlap_their_neighbours():
    spacing = 45
    for seed in REAL_SEEDS:
        xs = [b["at"][0] for b in site_placements(seed, 6, spacing=spacing)["buildings"]]
        gaps = [b - a for a, b in zip(xs, xs[1:])]
        assert min(gaps) >= 30, f"seed {seed} pushed two buildings into each other"


def test_every_candidate_names_a_spawn_objective_and_extraction():
    # These were never set, so Lot fell back to its origin default and every
    # candidate started the player in the same place regardless of the site.
    for seed in REAL_SEEDS:
        p = site_placements(seed, 4)
        ids = {f"b{i}" for i in range(4)}
        assert p["spawn"] in ids
        assert p["objective"] in ids
        assert p["extraction"] in ids
        assert p["extraction"] != p["spawn"], "the route should cross the site"


def test_a_single_building_site_is_valid_not_degenerate():
    p = site_placements(5017, 1)
    assert len(p["buildings"]) == 1
    assert p["spawn"] == p["objective"] == p["extraction"] == "b0"


def test_the_ground_plate_covers_the_placed_row():
    for seed in REAL_SEEDS:
        span_x, span_y = ground_size(4)
        for b in site_placements(seed, 4)["buildings"]:
            assert abs(b["at"][0]) <= span_x / 2 + 90
            assert abs(b["at"][1]) <= span_y / 2


# ---------------------------------------------------------------------------
# candidate_diversity: the gate that makes the regression impossible to hide
# ---------------------------------------------------------------------------
def _hashes(*per_candidate):
    return {f"m.candidate.seed_{s}": h
            for s, h in zip(REAL_SEEDS, per_candidate)}


def test_identical_candidates_are_a_blocking_finding():
    same = {"site.tscn": "sha256:aaa", "shell.glb": "sha256:bbb"}
    findings = check_candidate_diversity(_hashes(same, same, same, same, same))
    assert len(findings) == 1
    f = findings[0]
    assert f["code"] == CODE_NOT_DISTINCT
    assert f["blocking"] is True
    assert f["severity"] == "blocker"
    # The message has to name the candidates; "some candidates matched" sends
    # someone back to the job dirs to work out which.
    for seed in REAL_SEEDS:
        assert f"seed_{seed}" in f["message"]


def test_distinct_candidates_produce_no_findings():
    findings = check_candidate_diversity(_hashes(
        {"site.tscn": "sha256:1"}, {"site.tscn": "sha256:2"},
        {"site.tscn": "sha256:3"}, {"site.tscn": "sha256:4"},
        {"site.tscn": "sha256:5"}))
    assert findings == []


def test_only_the_duplicated_group_is_reported():
    findings = check_candidate_diversity(_hashes(
        {"site.tscn": "sha256:dup"}, {"site.tscn": "sha256:dup"},
        {"site.tscn": "sha256:3"}, {"site.tscn": "sha256:4"},
        {"site.tscn": "sha256:5"}))
    assert len(findings) == 1
    assert "seed_5017" in findings[0]["message"]
    assert "seed_5118" in findings[0]["message"]
    assert "seed_5219" not in findings[0]["message"]


def test_a_single_candidate_mission_is_exempt():
    # One candidate cannot fail to differ from itself, and a finding here would
    # train people to ignore the code.
    assert check_candidate_diversity({"m.candidate.seed_1": {"site.tscn": "x"}}) == []


def test_a_candidate_that_never_built_is_a_different_finding():
    by_candidate = {"m.candidate.seed_1": {"site.tscn": "sha256:1"},
                    "m.candidate.seed_2": {"site.tscn": "sha256:2"},
                    "m.candidate.seed_3": {}}
    findings = check_candidate_diversity(by_candidate)
    codes = [f["code"] for f in findings]
    assert codes == [CODE_NO_CANDIDATES]
    # Absent output and duplicated output are separate problems; collapsing them
    # would hide whichever is rarer.
    assert findings[0]["blocking"] is False
    assert "seed_3" in findings[0]["message"]


def test_artifact_order_does_not_change_the_verdict():
    a = {"m.candidate.seed_1": {"site.tscn": "x", "shell.glb": "y"},
         "m.candidate.seed_2": {"shell.glb": "y", "site.tscn": "x"}}
    assert check_candidate_diversity(a)[0]["code"] == CODE_NOT_DISTINCT


def test_summarize_says_how_many_levels_there_really_are():
    same = {"site.tscn": "sha256:aaa"}
    assert summarize(_hashes(same, same, same, same, same)) == (
        "candidates: 5 built but only 1 distinct -- 4 are copies")
    assert summarize(_hashes(
        {"site.tscn": "1"}, {"site.tscn": "2"}, {"site.tscn": "3"},
        {"site.tscn": "4"}, {"site.tscn": "5"})) == (
        "candidates: 5 built, all distinct")
    assert summarize({}) == "candidates: none built"


def test_distinct_count_ignores_candidates_with_no_output():
    assert distinct_count({"a": {"x": "1"}, "b": {"x": "1"}, "c": {}}) == 1
