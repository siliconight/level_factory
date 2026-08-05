"""One compose per archetype: a varied themed lot dresses each building as itself.

`_write_site_spec` activates its varied-library path only when `themed_scene`
is a MAPPING of archetype -> scene. Until then, `--art` produced one composed
scene and the site placed it N times, so a "four-building lot" was one
building four times -- item 37 wearing a different hat. The comment in Lot's
site-spec builder is explicit that dressing varied greyboxes as one themed
scene "would be a worse lie than the one it replaces", which is why the
varied path stayed greybox-only.

This is the compose half: the adapter emits one command per archetype, each
with that archetype's OWN slots, gameplay and greybox.

The mission's own shell is still composed to `presentation/site.tscn`. It
satisfies the job's output contract and keeps the single-shell path
byte-for-byte for every mission that does not set `lot_library` -- a level
already evaluated must not quietly become a different one.

Run:  python -m pytest test_presentation_lot.py
"""
from pathlib import Path

import pytest

from adapters.presentation import (
    PresentationAdapter, _lot_archetypes, _SCENE_REL, _LOT_SUBDIR,
)


@pytest.fixture()
def tree(tmp_path):
    """A DC repo with a composer, a Zoo kit, and three library archetypes."""
    repo = tmp_path / "deli"
    repo.mkdir()
    (repo / "portable_building.py").write_text("x")
    mods = tmp_path / "kit"
    mods.mkdir()
    (mods / "wall.glb").write_text("x")
    build = tmp_path / "build"
    build.mkdir()
    lot = []
    for aid in ("bank_branch_a02", "deli_a01", "pawn_shop_a01"):
        for suf in (".glb", ".slots.json", ".gameplay.json"):
            (build / (aid + suf)).write_text("x")
        lot.append({"id": aid, "family": aid.rsplit("_a", 1)[0],
                    "glb": str(build / (aid + ".glb")),
                    "slots": str(build / (aid + ".slots.json")),
                    "gameplay": str(build / (aid + ".gameplay.json"))})
    shell = tmp_path / "shell"
    shell.mkdir()
    for nm in ("shell.glb", "shell.slots.json", "shell.gameplay.json"):
        (shell / nm).write_text("x")
    spec = {
        "deli_repo": str(repo),
        "slots_path": str(shell / "shell.slots.json"),
        "gameplay_path": str(shell / "shell.gameplay.json"),
        "greybox_glb": str(shell / "shell.glb"),
        "modules_dir": str(mods),
        "theme": "rockay", "style": 1,
    }
    ctx = {"work_dir": str(tmp_path / "work"), "python_executable": "python"}
    (tmp_path / "work").mkdir()
    return spec, ctx, lot


def _args(cmd):
    return list(cmd.arguments)


def _flag(cmd, name):
    a = _args(cmd)
    return a[a.index(name) + 1] if name in a else None


# --- the single-shell path must not move ---------------------------------

def test_no_lot_is_exactly_one_compose(tree):
    spec, ctx, _ = tree
    cmds = PresentationAdapter().plan_commands(spec, ctx)
    assert len(cmds) == 1
    assert cmds[0].expected_outputs == (_SCENE_REL,)


def test_the_mission_shell_is_still_composed_when_a_lot_is_present(tree):
    """The output contract is `presentation/site.tscn`; the scheduler enforces
    it. A varied lot adds scenes, it does not replace that one."""
    spec, ctx, lot = tree
    spec["lot_archetypes"] = lot
    cmds = PresentationAdapter().plan_commands(spec, ctx)
    assert cmds[0].expected_outputs == (_SCENE_REL,)
    assert _flag(cmds[0], "--greybox") == spec["greybox_glb"]


# --- one compose per archetype -------------------------------------------

def test_each_archetype_gets_its_own_compose(tree):
    spec, ctx, lot = tree
    spec["lot_archetypes"] = lot
    cmds = PresentationAdapter().plan_commands(spec, ctx)
    assert len(cmds) == 1 + len(lot)


def test_each_archetype_is_dressed_as_itself(tree):
    """Its OWN slots, gameplay and greybox -- not the mission shell's. This is
    the whole point: five buildings pointed at one scene would place five
    greyboxes and dress them identically."""
    spec, ctx, lot = tree
    spec["lot_archetypes"] = lot
    cmds = PresentationAdapter().plan_commands(spec, ctx)[1:]
    for cmd, a in zip(cmds, lot):
        assert _flag(cmd, "--greybox") == a["glb"]
        assert _flag(cmd, "--slots") == a["slots"]
        assert _flag(cmd, "--gameplay") == a["gameplay"]


def test_archetype_scenes_land_in_their_own_directories(tree):
    spec, ctx, lot = tree
    spec["lot_archetypes"] = lot
    cmds = PresentationAdapter().plan_commands(spec, ctx)[1:]
    rels = [c.expected_outputs[0] for c in cmds]
    assert rels == [f"{_LOT_SUBDIR}/{a['id']}/site.tscn" for a in lot]
    assert len(set(rels)) == len(lot)          # no two share a path


def test_every_archetype_gets_the_same_theme_and_kit(tree):
    """A lot is one street. Buildings differ; the theme does not."""
    spec, ctx, lot = tree
    spec["lot_archetypes"] = lot
    for cmd in PresentationAdapter().plan_commands(spec, ctx):
        assert _flag(cmd, "--theme") == "rockay"
        assert _flag(cmd, "--modules") == spec["modules_dir"]


# --- selection travels with the spec -------------------------------------

def test_an_archetype_missing_a_part_is_not_composed(tree):
    """`building_library.index` already drops incomplete archetypes; this is
    the belt to that braces. A GLB with no slots.json cannot be themed."""
    spec, ctx, lot = tree
    lot[1] = dict(lot[1]); lot[1].pop("slots")
    spec["lot_archetypes"] = lot
    assert len(_lot_archetypes(spec)) == 2


def test_validate_names_an_archetype_whose_file_vanished(tree):
    """Fail here, not three stages downstream."""
    spec, ctx, lot = tree
    Path(lot[2]["glb"]).unlink()
    spec["lot_archetypes"] = lot
    problems = _real_problems(spec, ctx)
    assert any(lot[2]["id"] in p and "glb missing" in p for p in problems)


def _real_problems(spec, ctx):
    """Everything except the compose driver's own path, which is resolved
    relative to the installed repo and is not what these tests are about."""
    return [p for p in PresentationAdapter().validate_configuration(spec, ctx)
            if "LF compose driver missing" not in p]


def test_no_lot_validates_exactly_as_before(tree):
    spec, ctx, _ = tree
    assert _real_problems(spec, ctx) == []


def test_a_complete_lot_adds_no_problems(tree):
    spec, ctx, lot = tree
    spec["lot_archetypes"] = lot
    assert _real_problems(spec, ctx) == []


# --- the cache must see every building ------------------------------------

def test_the_fingerprint_covers_every_archetype(tree):
    """Swapping one building for another must invalidate the compose. The
    composer fingerprint had exactly this hole for its own sources and it
    took a walk to find."""
    spec, ctx, lot = tree
    spec["lot_archetypes"] = lot
    fp = PresentationAdapter().fingerprint_inputs(spec, ctx)
    assert set(fp["lot"]) == {a["id"] for a in lot}
    for aid in fp["lot"]:
        assert set(fp["lot"][aid]) == {"glb", "slots", "gameplay"}


def test_changing_one_archetype_changes_the_fingerprint(tree):
    spec, ctx, lot = tree
    spec["lot_archetypes"] = lot
    before = PresentationAdapter().fingerprint_inputs(spec, ctx)
    Path(lot[0]["glb"]).write_text("DIFFERENT")
    after = PresentationAdapter().fingerprint_inputs(spec, ctx)
    assert before["lot"] != after["lot"]


def test_no_lot_leaves_the_fingerprint_shape_alone(tree):
    """No `lot` key at all on the single-shell path, so existing missions
    keep their cache rather than all recomposing once."""
    spec, ctx, _ = tree
    assert "lot" not in PresentationAdapter().fingerprint_inputs(spec, ctx)
