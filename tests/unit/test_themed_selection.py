"""A themed lot draws only from shells that can carry a theme.

WHAT WAS MEASURED, 2026-08-08, over the 135-shell library.

Coverage, from `<id>.slots.json` -- `pharmacy_a02` fills 118 wall slots and
stands solid; `final_stand` has `coverage: {}` and holes where its walls
should be. Keyed on EMPTY and never on a count: 0 is measured-bad, 128 is
measured-good, nothing between has been measured.

Reachability, from `<id>.navgate.json` -- and this half shipped WRONG once and
was reverted. The rule read `markers.reachable == markers.checked`, which kept
6 of 134 shells, because 99 of them have an extraction point standing on a
street Lot has not laid yet. Not one of the six was kept for being a better
building: two had no extraction marker or one placed indoors, four had theirs
close enough to the wall that the snap landed on connected navmesh.

So the reachability question is now ASKED AND ANSWERED IN DELI COUNTER, which
owns the marker positions and the footprint, and Level Factory reads
`navigable` off the manifest. This file pins that Level Factory does not
re-derive it, and that every way of NOT having an answer keeps a shell out.

`test_an_exterior_extraction_does_not_disqualify_a_shell` is the falsifier,
and it asserts the old predicate on the same fixture first -- so if the shape
that was wrong ever stops being reproduced here, the test says so instead of
passing for free.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from packages.pipeline import building_library as bl   # noqa: E402
from test_fanout import ARCHETYPES, _library           # noqa: E402


def _entry(root: Path, aid: str) -> dict:
    """The index row for one shell of a library built by `_library`."""
    complete, _i, _n = bl.index(root)
    hit = [e for e in complete if e["id"] == aid]
    assert hit, f"{aid} is not in the index"
    return hit[0]


def _rewrite_navgate(root: Path, aid: str, payload) -> None:
    (root / f"{aid}.navgate.json").write_text(json.dumps(payload),
                                              encoding="utf-8")


# ---------------------------------------------------------------------------
# the falsifier
# ---------------------------------------------------------------------------

def test_an_exterior_extraction_does_not_disqualify_a_shell(tmp_path):
    """99 shells look like this, and the reverted rule refused all of them."""
    root = _library(tmp_path / "build")
    entry = _entry(root, "depot_a01")
    markers = json.loads(Path(entry["navgate"]).read_text())["markers"]

    # The predicate that shipped and was reverted. Asserted here so this test
    # cannot quietly stop reproducing the shape it exists to rule out.
    assert markers["reachable"] != markers["checked"], (
        "the fixture no longer has a deferred exterior marker, so this test "
        "is no longer exercising the defect it was written for")

    assert bl.themed_fitness(entry)["fit"], bl.themed_fitness(entry)["reasons"]


def test_a_shell_whose_own_interior_is_broken_is_still_refused(tmp_path):
    """final_stand: the correction must not launder a real defect."""
    root = _library(tmp_path / "build", themeable=False)
    verdict = bl.themed_fitness(_entry(root, "depot_a01"))
    assert not verdict["fit"]
    assert any("broken" in r for r in verdict["reasons"])


# ---------------------------------------------------------------------------
# Deli Counter owns the classification; this module reads a field
# ---------------------------------------------------------------------------

def test_the_published_verdict_wins_over_the_counts_beside_it(tmp_path):
    """`nav_gate` owns inside/outside. If Level Factory re-derived fitness
    from `interior_reachable` it would be a second definition of "exterior" in
    a second repo, which is how the coverage and layer keys drifted twice.

    The manifest here is deliberately self-contradictory -- `navigable: true`
    over counts that say 0 of 1 -- which the real gate cannot emit. It is the
    only way to see WHICH field is being read.
    """
    root = _library(tmp_path / "build")
    _rewrite_navgate(root, "depot_a01", {
        "navigable": True, "navigable_reason": "r",
        "markers": {"checked": 1, "reachable": 0, "unreachable": ["x"],
                    "interior_checked": 1, "interior_reachable": 0,
                    "interior_unreachable": ["objective_A (snap 0.4m)"],
                    "exterior_deferred": []}})
    assert bl.themed_fitness(_entry(root, "depot_a01"))["fit"]


def test_a_pre_scope_manifest_is_unscoped_not_trusted(tmp_path):
    """135 manifests were written before the split and carry a `navigable`
    computed over ALL markers -- `false` on 99 shells purely because of an
    extraction point. Reading that field would re-import the defect the split
    removed, so its MISSING `interior_checked` is what makes it unreadable."""
    root = _library(tmp_path / "build")
    _rewrite_navgate(root, "depot_a01", {
        "ok": True, "navigable": False,
        "navigable_reason": "1 of 2 marker(s) unreachable from spawn",
        "markers": {"checked": 2, "reachable": 1,
                    "unreachable": ["extraction_STREET (snap 2.6m)"]}})
    verdict = bl.themed_fitness(_entry(root, "depot_a01"))
    assert not verdict["fit"]
    assert any("unscoped" in r for r in verdict["reasons"])
    assert any("re-run nav_gate" in r for r in verdict["reasons"])


# ---------------------------------------------------------------------------
# every way of having no answer keeps a shell out
# ---------------------------------------------------------------------------

def test_no_navgate_manifest_is_unfit(tmp_path):
    root = _library(tmp_path / "build")
    (root / "depot_a01.navgate.json").unlink()
    verdict = bl.themed_fitness(_entry(root, "depot_a01"))
    assert not verdict["fit"]
    assert any("absent" in r for r in verdict["reasons"])


def test_unjudged_is_not_fit(tmp_path):
    """17 shells check no interior marker at all. A predicate reading "not
    broken" passes every one of them, and a check that cannot fail is
    indistinguishable from one that passed."""
    root = _library(tmp_path / "build")
    _rewrite_navgate(root, "depot_a01", {
        "navigable": None,
        "navigable_reason": "UNJUDGED: no marker was checked at all",
        "markers": {"checked": 0, "reachable": 0, "unreachable": [],
                    "interior_checked": 0, "interior_reachable": 0,
                    "interior_unreachable": [], "exterior_deferred": []}})
    verdict = bl.themed_fitness(_entry(root, "depot_a01"))
    assert not verdict["fit"]
    assert any("unjudged" in r for r in verdict["reasons"])


def test_an_unreadable_manifest_is_unfit(tmp_path):
    root = _library(tmp_path / "build")
    (root / "depot_a01.navgate.json").write_text("{ truncated", encoding="utf-8")
    assert not bl.themed_fitness(_entry(root, "depot_a01"))["fit"]


def test_empty_coverage_is_unfit_however_walkable(tmp_path):
    """`final_stand` walks fine and has holes in its walls. Both conditions."""
    root = _library(tmp_path / "build")
    (root / "depot_a01.slots.json").write_text(json.dumps({"coverage": {}}),
                                               encoding="utf-8")
    verdict = bl.themed_fitness(_entry(root, "depot_a01"))
    assert not verdict["fit"]
    assert any("coverage" in r for r in verdict["reasons"])


# ---------------------------------------------------------------------------
# refusing, and refusing by FAMILY
# ---------------------------------------------------------------------------

def test_a_hollow_library_is_refused_rather_than_shortened(tmp_path):
    """A five-building brief over a library that cannot theme is a DIFFERENT
    brief. Dropping the unfit ones silently is the failure recorded in
    docs/WALKABLE_SITE.md."""
    root = _library(tmp_path / "build", themeable=False)
    complete, _i, _n = bl.index(root)
    with pytest.raises(bl.ThemedShellsUnavailable) as excinfo:
        bl.require_themed_shells(complete, 5)
    msg = str(excinfo.value)
    assert "needs 5 fit families" in msg
    assert "8 of 8" in msg
    assert "without --art" in msg


def test_the_shortfall_is_counted_in_families_not_shells(tmp_path):
    """`pick_lot` draws one shell per family, so six fit shells across three
    families cannot fill a five-building lot. A shell count would look
    sufficient and fail at selection -- item 37 wearing a different hat."""
    root = _library(tmp_path / "build",
                    ids=("deli_a01", "deli_a02", "deli_a03",
                         "depot_a01", "depot_a02", "bank_job"))
    complete, _i, _n = bl.index(root)
    assert len(complete) == 6
    with pytest.raises(bl.ThemedShellsUnavailable) as excinfo:
        bl.require_themed_shells(complete, 5)
    assert "offers 3" in str(excinfo.value)
    # and the same six fill a three-building lot without complaint
    assert len(bl.require_themed_shells(complete, 3)) == 6


def test_a_themeable_library_passes_through_unchanged(tmp_path):
    root = _library(tmp_path / "build")
    complete, _i, _n = bl.index(root)
    assert len(bl.require_themed_shells(complete, 5)) == len(complete)


# ---------------------------------------------------------------------------
# the constraint that governs all of it
# ---------------------------------------------------------------------------

def test_the_greybox_draw_is_not_narrowed(tmp_path):
    """THE constraint. `pick_lot` draws from whatever it is handed, so a
    narrower pool re-selects lots that have already been built and graded --
    "a different level wearing the same grade", in `_write_site_spec`'s own
    words. `themed` is opt-in for exactly this reason."""
    root = _library(tmp_path / "build", themeable=False)
    lot, _ = bl.lot_for(str(root), 5, "m.candidate.seed_5118")
    assert len(lot) == 5                     # no refusal on the greybox path
    themed_root = _library(tmp_path / "themed")
    a, _ = bl.lot_for(str(themed_root), 5, "m.candidate.seed_5118")
    b, _ = bl.lot_for(str(themed_root), 5, "m.candidate.seed_5118", themed=True)
    assert [e["id"] for e in a] == [e["id"] for e in b], (
        "with every shell fit, the themed pool IS the complete pool and the "
        "draw must be identical -- otherwise `themed` reshuffles by itself")


def test_a_themed_lot_refuses_where_the_greybox_one_would_have_drawn(tmp_path):
    root = _library(tmp_path / "build", themeable=False)
    assert bl.lot_for(str(root), 5, "m.candidate.seed_5118")[0]
    with pytest.raises(bl.ThemedShellsUnavailable):
        bl.lot_for(str(root), 5, "m.candidate.seed_5118", themed=True)


def test_index_reports_the_navgate_path_without_requiring_it(tmp_path):
    """Reported, never used to EXCLUDE -- the same rule as `lights`. Adding it
    to REQUIRED would drop shells from the pool and reshuffle every draw."""
    root = _library(tmp_path / "build")
    (root / "depot_a01.navgate.json").unlink()
    complete, incomplete, _non_source = bl.index(root)
    assert not incomplete
    by_id = {e["id"]: e for e in complete}
    assert by_id["depot_a01"]["navgate"] == ""
    assert by_id["deli_a01" if "deli_a01" in by_id else ARCHETYPES[0]]["navgate"]


# ---------------------------------------------------------------------------
# every caller of the rule, not the ones you happen to be looking at
# ---------------------------------------------------------------------------

def test_the_planner_fans_out_over_the_themed_pool(tmp_path, monkeypatch):
    """The third caller, and the one that was missed.

    `lot_for` has three call sites: the compose spec, the themed site spec and
    the ART FAN-OUT in `planner.py`. Themed selection landed on the first two,
    and the planner kept drawing from the full pool -- so it planned a Zoo bake
    for an archetype the narrower pool does not contain and `_art_entry` raised
    "the planner and the spec builder disagree about which buildings this
    mission places". Its own guard, firing exactly as written.

    The rest of this suite could not see it: `_library` builds a library where
    every shell is themeable, so the two pools are identical and the two
    derivations agree by accident. This test uses a MIXED library, which is the
    only shape where the disagreement is observable.

    `grep lot_for` over the package names all three call sites in one command.
    """
    from test_fanout import _brief, _plan, _specs

    build = tmp_path / "build"
    _library(build)
    _library(build, ids=("hollow_a01", "hollow_a02", "hollow_a03"),
             themeable=False)

    brief = _brief(build)
    plan = _plan(brief)
    fanned = sorted({j.archetype_id for j in plan.graph.jobs()
                     if getattr(j, "archetype_id", None)})
    assert fanned, "no art jobs were fanned out at all"
    assert not [a for a in fanned if a.startswith("hollow")], (
        f"the planner fanned art jobs out over unthemeable shells: {fanned}")

    # and the spec builder agrees -- this raised before the planner narrowed
    _specs(tmp_path, plan, brief, monkeypatch, publish=False)


def test_a_mixed_library_still_fills_the_lot(tmp_path):
    """The guard above must not pass by planning nothing. Eight themeable
    shells over eight families fill a five-building lot with room to spare."""
    build = tmp_path / "build"
    _library(build)
    _library(build, ids=("hollow_a01",), themeable=False)
    complete, _i, _n = bl.index(build)
    assert len(complete) == 9
    assert len(bl.require_themed_shells(complete, 5)) == 8
