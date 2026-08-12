"""Art inputs are indexed, reported, and refused -- never quietly filtered.

Step 2 of docs/PER_BUILDING_ART.md. Pure: a temp directory and arithmetic.

The load-bearing test here is `test_selection_is_unchanged_by_this_change`.
Everything else describes new behaviour; that one says the change is safe to
apply to a workspace whose lots have already been built and evaluated.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.pipeline import building_library as bl  # noqa: E402


def _lib(root: Path, spec: dict[str, bool]) -> Path:
    """A build dir. `spec` maps archetype id -> does it ship a .lights.json."""
    root.mkdir(parents=True, exist_ok=True)
    for aid, has_lights in spec.items():
        for suf in bl.REQUIRED:
            (root / f"{aid}{suf}").write_text("{}", encoding="utf-8")
        if has_lights:
            (root / f"{aid}.lights.json").write_text(
                '{"building_id": "%s"}' % aid, encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# the constraint that made this a two-constant change
# ---------------------------------------------------------------------------
def test_lights_is_not_in_required():
    """`pick_lot` draws from `complete`, so REQUIRED decides selection.

    Adding a fourth suffix would remove archetypes from the pool and reshuffle
    every draw -- an already-evaluated seed would select different buildings.
    """
    assert ".lights.json" not in bl.REQUIRED
    assert ".lights.json" in bl.ART_REQUIRED


def test_selection_is_unchanged_by_this_change(tmp_path):
    """The same seed picks the same buildings whether or not lights exist.

    This is the safety claim of the whole patch, so it is checked across a
    spread of seeds rather than one lucky one.
    """
    with_lights = _lib(tmp_path / "a", {f"fam{i}_a01": True for i in range(8)})
    without = _lib(tmp_path / "b", {f"fam{i}_a01": False for i in range(8)})
    a, _i, _n = bl.index(with_lights)
    b, _i, _n = bl.index(without)
    for seed in (1, 5017, 5118, 5219, 99991):
        assert ([e["id"] for e in bl.pick_lot(a, seed, 5)]
                == [e["id"] for e in bl.pick_lot(b, seed, 5)]), seed


# ---------------------------------------------------------------------------
# indexing
# ---------------------------------------------------------------------------
def test_the_light_manifest_is_carried_when_present(tmp_path):
    complete, _i, _n = bl.index(_lib(tmp_path, {"deli_a01": True}))
    assert len(complete) == 1
    assert complete[0]["lights"].endswith("deli_a01.lights.json")


def test_a_building_without_lights_is_still_complete_and_placeable(tmp_path):
    complete, incomplete, _non_source = bl.index(_lib(tmp_path, {"deli_a01": False}))
    assert incomplete == []
    assert len(complete) == 1
    assert complete[0]["lights"] == ""


def test_a_building_missing_a_required_part_still_drops_out(tmp_path):
    root = _lib(tmp_path, {"deli_a01": True})
    (root / "deli_a01.slots.json").unlink()
    complete, incomplete, _non_source = bl.index(root)
    assert complete == []
    assert incomplete[0]["id"] == "deli_a01"
    assert ".slots.json" in incomplete[0]["missing"]


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------
def test_art_incomplete_names_who_and_what(tmp_path):
    complete, _i, _n = bl.index(_lib(tmp_path, {
        "alpha_a01": True, "bravo_a01": False, "charlie_a01": False}))
    gaps = bl.art_incomplete(complete)
    assert [g["id"] for g in gaps] == ["bravo_a01", "charlie_a01"]
    assert gaps[0]["missing"] == [".lights.json"]


def test_art_incomplete_is_empty_for_a_dressable_lot(tmp_path):
    complete, _i, _n = bl.index(_lib(tmp_path, {"a_a01": True, "b_a01": True}))
    assert bl.art_incomplete(complete) == []


@pytest.mark.parametrize("lot", [None, []])
def test_art_incomplete_tolerates_nothing_to_check(lot):
    assert bl.art_incomplete(lot) == []


# ---------------------------------------------------------------------------
# refusing
# ---------------------------------------------------------------------------
def test_require_art_inputs_raises_rather_than_shortening_the_lot(tmp_path):
    complete, _i, _n = bl.index(_lib(tmp_path, {
        "alpha_a01": True, "bravo_a01": False}))
    with pytest.raises(bl.ArtInputsMissing) as exc:
        bl.require_art_inputs(complete)
    msg = str(exc.value)
    assert "bravo_a01" in msg
    assert ".lights.json" in msg
    # the operator has to be able to act on it without reading the source
    assert "--art" in msg


def test_require_art_inputs_passes_a_dressable_lot(tmp_path):
    complete, _i, _n = bl.index(_lib(tmp_path, {"a_a01": True, "b_a01": True}))
    bl.require_art_inputs(complete)  # must not raise


def test_the_refusal_counts_both_sides(tmp_path):
    """'2 of 5' tells you whether this is a gap or a broken library."""
    complete, _i, _n = bl.index(_lib(tmp_path, {
        "a_a01": True, "b_a01": True, "c_a01": True,
        "d_a01": False, "e_a01": False}))
    with pytest.raises(bl.ArtInputsMissing, match=r"2 of 5"):
        bl.require_art_inputs(complete)


# ---------------------------------------------------------------------------
# step 3a: one selection rule, three callers
# ---------------------------------------------------------------------------
def test_lot_for_is_the_same_answer_as_the_parts_it_replaces(tmp_path):
    """The planner, the compose spec and the site spec must not be three
    derivations that happen to agree."""
    root = _lib(tmp_path, {f"fam{i}_a01": True for i in range(8)})
    lot, incomplete = bl.lot_for(str(root), 5, "m1.candidate.seed_5118")
    expected = bl.pick_lot(bl.index(root)[0], 5118, 5)
    assert [e["id"] for e in lot] == [e["id"] for e in expected]
    assert incomplete == []


def test_lot_for_is_empty_for_the_single_shell_path(tmp_path):
    root = _lib(tmp_path, {"deli_a01": True})
    assert bl.lot_for(str(root), 1, "m1.candidate.seed_5118") == ([], [])
    assert bl.lot_for("", 5, "m1.candidate.seed_5118") == ([], [])
    assert bl.lot_for(None, 5, "m1.candidate.seed_5118") == ([], [])


def test_lot_for_reports_incomplete_rather_than_printing_it(tmp_path):
    root = _lib(tmp_path, {f"fam{i}_a01": True for i in range(6)})
    (root / "fam3_a01.slots.json").unlink()
    lot, incomplete = bl.lot_for(str(root), 5, "m1.candidate.seed_5118")
    assert [g["id"] for g in incomplete] == ["fam3_a01"]
    assert "fam3_a01" not in {e["id"] for e in lot}


def test_lot_for_keys_on_the_candidate_seed(tmp_path):
    root = _lib(tmp_path, {f"fam{i}_a01": True for i in range(10)})
    a, _ = bl.lot_for(str(root), 5, "m1.candidate.seed_5017")
    b, _ = bl.lot_for(str(root), 5, "m1.candidate.seed_5118")
    assert [e["id"] for e in a] != [e["id"] for e in b], \
        "two candidates must get two different lots"
