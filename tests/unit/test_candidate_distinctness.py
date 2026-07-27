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
    """A gap between origins is not a gap between buildings.

    This test used to assert ``min(gaps) >= 30`` at a spacing of 45, which reads
    as generous and is not: the shells are 44 m wide, so a 30 m gap between
    origins is 14 m of one building standing inside the other. It measured the
    thing that was easy to measure rather than the thing that had to be true, and
    the pipeline shipped interpenetrating shells underneath it.
    """
    from packages.pipeline.site_variation import STREET, overlapping, row_spacing

    footprint = (44.0, 44.0)
    spacing = row_spacing(footprint)
    for seed in REAL_SEEDS:
        placed = site_placements(seed, 6, spacing=spacing)["buildings"]
        spec = {"buildings": [{"id": f"b{i}", "at": b["at"]}
                              for i, b in enumerate(placed)]}
        assert overlapping(spec, footprint) == [], f"seed {seed}"
        xs = [b["at"][0] for b in placed]
        gaps = [b - a for a, b in zip(xs, xs[1:])]
        assert min(gaps) >= max(footprint) + STREET, (
            f"seed {seed}: {min(gaps)} m between origins of {max(footprint)} m "
            "shells leaves no street")


def test_the_spacing_is_derived_from_the_shell_not_assumed():
    from packages.pipeline.site_variation import DEFAULT_FOOTPRINT, row_spacing

    assert row_spacing((44.0, 44.0)) > 44.0
    assert row_spacing((80.0, 20.0)) > row_spacing((44.0, 44.0))
    # a quarter turn presents the longer axis to the street, so the longer axis
    # is what the spacing has to clear
    assert row_spacing((20.0, 80.0)) == row_spacing((80.0, 20.0))
    # unmeasurable is the documented default, never zero
    assert row_spacing(None) == row_spacing(DEFAULT_FOOTPRINT)


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
    """The plate has to contain the buildings' FOOTPRINTS, not their origins.

    This test used to read ``assert abs(b["at"][0]) <= span_x / 2 + 90``. The
    ``+ 90`` is the shape of the bug: a real coverage failure was made to pass by
    widening the assertion until it did, and the check that remained looked at
    origins only, so a 44 m shell whose origin was 1 m inside the rim counted as
    covered while 21 m of it hung over open air. That is what shipped -- the last
    building of ``category5_baie_dore_001`` stood 44 m off the plate, its ground
    hole was clipped away, and the crew spawned on it as an island.
    """
    from packages.pipeline.site_variation import row_spacing

    footprint = (44.0, 44.0)               # a real Deli Counter shell
    reach = max(footprint) / 2.0
    spacing = row_spacing(footprint)
    for seed in REAL_SEEDS:
        span_x, span_y = ground_size(4, spacing=spacing, footprint=footprint)
        for b in site_placements(seed, 4, spacing=spacing)["buildings"]:
            x, y = b["at"]
            assert abs(x) + reach <= span_x / 2, (
                f"seed {seed}: {b} hangs off the east/west rim of a "
                f"{span_x} x {span_y} m plate")
            assert abs(y) + reach <= span_y / 2, (
                f"seed {seed}: {b} hangs off the north/south rim of a "
                f"{span_x} x {span_y} m plate")


def test_the_plate_leaves_a_street_outside_the_outermost_shell():
    """Flush with the wall is not covered: Godot erodes the navmesh by the agent
    radius at the plate rim, so ground that ends at the geometry leaves nothing
    walkable along it."""
    from packages.pipeline.site_variation import CLEARANCE, row_spacing
    footprint = (44.0, 44.0)
    spacing = row_spacing(footprint)
    span_x, span_y = ground_size(4, spacing=spacing, footprint=footprint)
    outermost = max(abs(b["at"][0]) for seed in REAL_SEEDS
                    for b in site_placements(seed, 4, spacing=spacing)["buildings"])
    assert span_x / 2 - (outermost + max(footprint) / 2) >= CLEARANCE


def test_the_row_is_centred_because_the_plate_is():
    """Lot draws ``size_x``/``size_y`` centred on the origin. A row that marches
    out from the origin under a plate centred on it is the original defect, and
    it is invisible unless something compares the two centres."""
    from packages.pipeline.site_variation import row_spacing

    spacing = row_spacing((44.0, 44.0))
    for seed in REAL_SEEDS:
        xs = [b["at"][0]
              for b in site_placements(seed, 4, spacing=spacing)["buildings"]]
        centre = (min(xs) + max(xs)) / 2.0
        # Half a spacing of asymmetry is the even-count stagger, not a drift.
        assert abs(centre) <= spacing / 2 + 6, (
            f"seed {seed}: the row is centred on x={centre:g}, the plate on x=0")


def test_the_written_spec_is_checked_against_its_own_plate():
    """``uncovered`` is the producer's self-check; it has to be able to fail."""
    from packages.pipeline.site_variation import row_spacing, uncovered
    footprint = (44.0, 44.0)
    spacing = row_spacing(footprint)
    span_x, span_y = ground_size(4, spacing=spacing, footprint=footprint)
    placed = site_placements(5219, 4, spacing=spacing)["buildings"]
    good = {"ground": {"size_x": span_x, "size_y": span_y},
            "buildings": [{"id": f"b{i}", "at": b["at"], "rot": b["rot"]}
                          for i, b in enumerate(placed)]}
    assert uncovered(good, footprint) == []

    # the spec as it was actually written before the fix: the same shells, but
    # marching out from the origin under a plate sized from the building count
    marched = {"ground": {"size_x": 232, "size_y": 100},
               "buildings": [{"id": "b0", "at": [-6, 10]}, {"id": "b1", "at": [39, 5]},
                             {"id": "b2", "at": [93, 0]}, {"id": "b3", "at": [138, -10]}]}
    off = uncovered(marched, footprint)
    assert len(off) == 1 and off[0].startswith("b3"), off
    assert "outside the declared 232 x 100 m plate" in off[0]

    # and a spec with no readable ground is not a spec that passes
    assert uncovered({"buildings": [{"id": "b0", "at": [0, 0]}]}, footprint)


# ---------------------------------------------------------------------------
# the plate is sized from the shell, so the shell has to be measured
# ---------------------------------------------------------------------------
def test_the_shell_is_measured_from_its_own_collision(tmp_path):
    from packages.pipeline.site_variation import shell_footprint
    from tests.unit.glb_fixture import slab, write_glb

    path = write_glb(tmp_path / "shell.glb", [slab("floor-col")])
    # the fixture slab is 44 x 32 in glTF x/z, centred on its origin
    assert shell_footprint(path) == (44.0, 32.0)


def test_a_shell_modelled_off_its_origin_is_measured_from_the_origin(tmp_path):
    """Lot places a building by its origin, so what matters is how far the
    geometry reaches from there -- not how wide the bounding box is. A 20 m slab
    sitting 30 m off the origin needs 80 m of plate, not 20."""
    from packages.pipeline.site_variation import shell_footprint
    from tests.unit.glb_fixture import write_glb

    path = write_glb(tmp_path / "shell.glb",
                     [("floor-col", (30.0, -0.15, 0.0), (20.0, 0.3, 20.0))])
    assert shell_footprint(path) == (80.0, 20.0)


def test_a_shell_that_cannot_be_measured_is_not_a_shell_of_size_zero(tmp_path):
    """The whole bug family: "I could not read it" must not return the same
    answer as "it is not there". None sends the caller to the documented default
    instead of to a plate sized for nothing."""
    from packages.pipeline.site_variation import (
        DEFAULT_FOOTPRINT, ground_size, shell_footprint)

    missing = tmp_path / "nope.glb"
    assert shell_footprint(missing) is None
    garbage = tmp_path / "garbage.glb"
    garbage.write_bytes(b"not a glb at all")
    assert shell_footprint(garbage) is None
    # a plate sized from None is a plate sized from the default, not from zero
    assert ground_size(4, footprint=None) == ground_size(4, footprint=DEFAULT_FOOTPRINT)
    assert ground_size(4, footprint=None) > ground_size(4, footprint=(1.0, 1.0))


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
