"""The scene a tool grades came from this run, or it is not there at all.

`stage_godot_project` writes into a directory that is reused every run, and the
scene it puts at ``res://`` is the single input every Godot-side grade is a
statement about. Two guards used to decide whether that file was current: the
copy ran only if the source existed, and the post-process ran only if the
destination existed. Neither is wrong on its own, and together they let a
staging dir keep the previous run's scene, rewrite it in place, and hand Godot a
map from a build nobody was asking about -- with a modification time from this
one, so nothing on disk read as stale.

These are the tests for the thing that guarantee cannot be recovered from the
timestamps: what the staged scene is, and where it came from.
"""
from __future__ import annotations

import json
from pathlib import Path

from packages.staging.godot_project import stage_godot_project

SCENE = '[gd_scene format=3]\n\n[node name="Root" type="Node3D"]\n'
OLDER = '[gd_scene format=3]\n\n[node name="Stale" type="Node3D"]\n'


def _stage(dest: Path, scene_src: Path, **kw):
    return stage_godot_project(dest, addon_dirs=[], scene_src=scene_src,
                               plugins=[], **kw)


def test_the_staged_scene_is_the_one_the_source_holds(tmp_path):
    src = tmp_path / "job" / "site_walk.tscn"
    src.parent.mkdir(parents=True)
    src.write_text(SCENE, encoding="utf-8")
    dest = tmp_path / "staging"

    _stage(dest, src)

    assert (dest / "level.tscn").read_text(encoding="utf-8") == SCENE


def test_a_previous_run_s_scene_does_not_survive_a_missing_source(tmp_path):
    """The defect, stated as the thing it produced.

    Seed 5320 of ``category5_baie_dore_001`` was graded on a scene whose two
    nearest enemies stood 23 m and 25 m from the crew spawn, because an older
    placement rule had put them there; the ``site_walk.tscn`` the same run had
    just written held them at 48 m and 54 m. Laser Tag reported INSTANT_CONTACT,
    a team wipe in under ten seconds and 0% route completion -- all true of the
    file it loaded, none of it true of the level that had been built.
    """
    dest = tmp_path / "staging"
    dest.mkdir()
    (dest / "level.tscn").write_text(OLDER, encoding="utf-8")
    missing = tmp_path / "job" / "site_walk.tscn"

    _stage(dest, missing)

    assert not (dest / "level.tscn").exists(), (
        "a staging dir kept a scene this run cannot account for; a grade "
        "against it describes a level that was not built")


def test_the_post_process_cannot_resurrect_a_scene_that_was_not_staged(tmp_path):
    """Freshening is not staging.

    The rewrite pass exists to bake hook nodes and resolve absolute refs, and it
    ran on whatever sat at the destination. Given a stale file it did its job
    perfectly and produced a scene that was internally consistent, correctly
    named, loadable, current by every timestamp, and wrong.
    """
    dest = tmp_path / "staging"
    dest.mkdir()
    (dest / "level.tscn").write_text(OLDER, encoding="utf-8")
    seen = []

    def _post(text: str):
        seen.append(text)
        return text + "\n[node name=\"Baked\" type=\"Node3D\"]\n", "baked"

    _stage(dest, tmp_path / "gone.tscn", scene_post_process=_post)

    assert seen == [], "the rewrite pass read a scene this run never staged"
    assert not (dest / "level.tscn").exists()


def test_the_staged_scene_says_where_it_came_from(tmp_path):
    """Provenance next to the artifact, not inferred from mtimes.

    A reader holding a bad grade needs to answer "which file was this?" without
    trusting the clock, because the clock is exactly what the rewrite pass
    changes.
    """
    import hashlib

    src = tmp_path / "job" / "site_walk.tscn"
    src.parent.mkdir(parents=True)
    src.write_text(SCENE, encoding="utf-8")
    dest = tmp_path / "staging"

    _stage(dest, src)

    notes = json.loads((dest / "staging.notes.json").read_text(encoding="utf-8"))
    assert notes["scene_source"] == str(src)
    assert notes["scene_source_sha256"] == hashlib.sha256(
        src.read_bytes()).hexdigest()
    assert notes["scene_staged"] is True


def test_a_missing_source_is_recorded_rather_than_left_blank(tmp_path):
    dest = tmp_path / "staging"

    _stage(dest, tmp_path / "gone.tscn")

    notes = json.loads((dest / "staging.notes.json").read_text(encoding="utf-8"))
    assert notes["scene_source_sha256"] is None
    assert notes["scene_staged"] is False


def test_a_staged_asset_subtree_is_refreshed_not_kept(tmp_path):
    """The same defect as the scene, one branch over.

    Sibling SUBDIRECTORIES were copied under `if not dst.exists()`, so the
    first run to stage an asset subtree made it immortal: every later run found
    it present and left it alone, no matter what the source became. A staging
    dir is reused, so "already there" means "left by a run nobody is looking
    at" -- the addons a few lines up are replaced wholesale for exactly this
    reason, and this branch was the one that got missed."""
    job = tmp_path / "job"
    (job / "art").mkdir(parents=True)
    src = job / "site_walk.tscn"
    src.write_text(SCENE, encoding="utf-8")
    (job / "art" / "module.txt").write_text("first build", encoding="utf-8")
    dest = tmp_path / "staging"

    _stage(dest, src)
    assert (dest / "art" / "module.txt").read_text(encoding="utf-8") == "first build"

    # The source subtree changes: a file rewritten, and one that no longer exists.
    (job / "art" / "module.txt").write_text("second build", encoding="utf-8")
    (job / "art" / "added.txt").write_text("new", encoding="utf-8")

    _stage(dest, src)
    assert (dest / "art" / "module.txt").read_text(encoding="utf-8") == "second build"
    assert (dest / "art" / "added.txt").exists()


def test_a_staged_asset_removed_from_the_source_does_not_linger(tmp_path):
    """Refresh has to mean replace, not merge. A module deleted upstream that
    survives in the staging dir is the stale-scene defect with a different file
    name: Godot resolves it, the grade is a statement about it, and nothing on
    disk says it belongs to a build that no longer exists."""
    job = tmp_path / "job"
    (job / "art").mkdir(parents=True)
    src = job / "site_walk.tscn"
    src.write_text(SCENE, encoding="utf-8")
    (job / "art" / "dropped.txt").write_text("here", encoding="utf-8")
    dest = tmp_path / "staging"

    _stage(dest, src)
    assert (dest / "art" / "dropped.txt").exists()

    (job / "art" / "dropped.txt").unlink()
    (job / "art" / "kept.txt").write_text("here", encoding="utf-8")

    _stage(dest, src)
    assert not (dest / "art" / "dropped.txt").exists()
    assert (dest / "art" / "kept.txt").exists()
