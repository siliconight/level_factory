"""The resource manifest accounts for every file the package ships.

`portable_resource_manifest.json` carries a sha256 and a size per file and is
what an integrating team checks a received package against. Measured
2026-09-22 on cold run 9067's shipped
`workspaces/cold-9067-ws/.level_factory/exports/LF_club_block_006.portable-godot`
-- the package that went out:

    listed in portable_resource_manifest.json : 562
    files on disk                             : 567
    listed but absent                         :   0

    shipped and unlisted: LF_MANIFEST.json, LICENSES.json,
                          export_profile.json, output_layers.json,
                          portable_resource_manifest.json

Four of those five had no reason recorded anywhere. Three -- `LICENSES.json`,
`export_profile.json`, `output_layers.json` -- were an ordering accident:
`build_resource_manifest(export_dir)` ran at `export.py:1442` and their
writers sat at 1446, 1448 and 1451, four lines too low. Nothing about a
licence block makes it unlistable. `LF_MANIFEST.json` is written after the
walk on purpose and said so in a comment; the manifest itself cannot carry
the hash of its own finished bytes.

Four files arriving unannounced read as tampering or a truncated download,
and were neither.

WHAT THIS ASSERTS is the equation, because a set of exceptions nobody counts
is the same silence with more words in it:

    listed + declared_unlisted == files in the package

FAILS ON 0.103.0, and it has to: the manifest there has no `unlisted` key and
four files are outside every list it does have.

Run:  python -m pytest tests/unit/test_manifest_lists_what_ships.py
"""
import inspect
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.exporting import export as E
from packages.exporting.export import ExportProfile, export_mission

# `ExportManifestError` is resolved through the module AT CALL TIME, not
# imported at the top. Against 0.103.0 a top-level import of a name that
# version does not have turns this whole file into a COLLECTION ERROR, and a
# collection error says nothing about the manifest -- the counting tests
# below never run, so the measured gap never gets reported. Bound late, the
# arithmetic tests fail on the numbers, which is the finding.

#: What cold 9067 shipped, kept as the number this change is answering. Not
#: read by any assertion below -- the tests measure a package they build
#: themselves, because a figure from a folder that may not be on the next
#: machine is a check that cannot fail.
COLD_9067 = {"listed": 562, "on_disk": 567, "unaccounted": 4}

#: The three whose writers moved above the walk, and the two that stayed
#: below it and are declared instead.
MOVED_ABOVE_THE_WALK = ("LICENSES.json", "export_profile.json",
                        "output_layers.json")
DECLARED_UNLISTED = ("portable_resource_manifest.json", "LF_MANIFEST.json")


def _export(tmp_path):
    """A package built end to end by the exporter, not a hand-made fixture.

    The ordering under test is a property of `export_mission`'s line order, so
    a fixture assembled by the test would be asserting the test's own ordering
    back at itself.
    """
    handoff = tmp_path / "handoff"
    handoff.mkdir()
    (handoff / "mission.tscn").write_text("[gd_scene]\n")
    # The entry stub replaces mission.tscn, so without a second scene the
    # package instances nothing and 0.37.0's guard refuses it.
    (handoff / "site.tscn").write_text("[gd_scene]\n")
    (handoff / "gameplay_anchors.json").write_text("{}")
    return export_mission(
        mission_id="m1", handoff_dir=handoff, presentation_dir=None,
        source_dir=None, profile=ExportProfile(),
        tool_versions={"dispatch": "0.1.0"}, out_root=tmp_path / "exports",
    )


def _read(export_dir):
    path = export_dir / "portable_resource_manifest.json"
    man = json.loads(path.read_text(encoding="utf-8"))
    listed = {r["path"] for r in man["resources"]}
    # `or []` ON A MISSING KEY, which is the shape this repo has a warning
    # about -- and it is the right call in THIS one place, for the opposite
    # reason to the usual. In a checker the absence turns a real problem into
    # an empty problem list and prints "clean". Here the absence turns into
    # an empty `declared` set, so the arithmetic below reports the four
    # unaccounted files BY NAME instead of dying on a KeyError that says
    # nothing about the package. A failure has to be legible against the
    # version it is failing on, which is 0.103.0. That the key must EXIST is
    # asserted separately, in `test_the_manifest_states_the_equation_itself`,
    # and the production guard refuses a manifest without it outright.
    declared = {u["path"] for u in (man.get("unlisted") or [])}
    on_disk = {p.relative_to(export_dir).as_posix()
               for p in export_dir.rglob("*") if p.is_file()}
    return man, listed, declared, on_disk


def test_the_equation_closes_on_a_package_the_exporter_built(tmp_path):
    """listed + declared_unlisted == files on disk, on a real export."""
    result = _export(tmp_path)
    man, listed, declared, on_disk = _read(result.export_dir)
    assert len(listed) + len(declared) == len(on_disk), (
        "unaccounted: %s" % sorted(on_disk - listed - declared))
    # And the sets, not only the sizes -- two errors of equal size cancel.
    assert listed | declared == on_disk
    assert not (listed & declared), "a file cannot be both"


def test_nothing_ships_outside_every_list(tmp_path):
    """The shape of the 9067 finding, asked of a package built here.

    On 0.103.0 this set is the four files that had no reason recorded:
    LF_MANIFEST.json, LICENSES.json, export_profile.json, output_layers.json.
    """
    result = _export(tmp_path)
    _man, listed, declared, on_disk = _read(result.export_dir)
    assert sorted(on_disk - listed - declared) == []
    assert sorted(listed - on_disk) == [], "the manifest names a file nobody shipped"


def test_the_three_that_were_an_ordering_accident_are_now_listed(tmp_path):
    """They are listed, with a hash and a size, like any other shipped file."""
    result = _export(tmp_path)
    man, listed, _declared, _on_disk = _read(result.export_dir)
    by_path = {r["path"]: r for r in man["resources"]}
    for name in MOVED_ABOVE_THE_WALK:
        assert name in listed, "%s ships unlisted; its writer is below the walk" % name
        row = by_path[name]
        # `hash_file` returns "sha256:<64 hex>", not a bare digest. Checked
        # against a real row rather than assumed -- the first draft of this
        # line asserted len == 64 and failed on the prefix.
        assert row["size"] > 0, row
        algo, _, digest = row["hash"].partition(":")
        assert algo == "sha256" and len(digest) == 64, row


def test_the_two_that_cannot_be_listed_are_declared_with_a_reason(tmp_path):
    result = _export(tmp_path)
    man, _listed, declared, _on_disk = _read(result.export_dir)
    assert declared == set(DECLARED_UNLISTED)
    reasons = {u["path"]: u["reason"] for u in man["unlisted"]}
    # The two reasons are not the same KIND of reason, and the rows say so:
    # one is impossible under any ordering, the other is a deliberate choice.
    assert "STRUCTURAL" in reasons["portable_resource_manifest.json"]
    assert "DELIBERATE" in reasons["LF_MANIFEST.json"]
    # `LF_MANIFEST.json`'s reason is the one the export.py comment has always
    # given; losing it would turn a documented decision back into an omission.
    assert "does not list a file that describes it" in reasons["LF_MANIFEST.json"]


def test_the_manifest_states_the_equation_itself(tmp_path):
    """An integrator reads the claim off the file, not off this repo."""
    result = _export(tmp_path)
    man, listed, declared, on_disk = _read(result.export_dir)
    assert man["schema"] == "level_factory.portable_manifest.v0.2"
    acc = man["accounting"]
    assert acc["listed"] == len(listed)
    assert acc["declared_unlisted"] == len(declared)
    assert acc["files_in_package"] == len(on_disk)
    assert acc["files_in_package"] == acc["listed"] + acc["declared_unlisted"]
    assert "listed + declared_unlisted" in acc["check"]


def test_the_guard_fires_on_a_file_written_after_the_walk(tmp_path):
    """PROOF THE INSTRUMENT CAN MOVE. A guard that has never failed is
    indistinguishable from one that cannot."""
    result = _export(tmp_path)
    E._guard_manifest_accounts_for_the_package(result.export_dir)  # clean
    (result.export_dir / "a_late_writer.json").write_text("{}", encoding="utf-8")
    with pytest.raises(E.ExportManifestError) as exc:
        E._guard_manifest_accounts_for_the_package(result.export_dir)
    assert "a_late_writer.json" in str(exc.value)
    assert "neither listed nor declared" in str(exc.value)


def test_the_guard_fires_when_a_listed_file_is_gone(tmp_path):
    result = _export(tmp_path)
    (result.export_dir / "HANDOFF.md").unlink()
    with pytest.raises(E.ExportManifestError) as exc:
        E._guard_manifest_accounts_for_the_package(result.export_dir)
    assert "not in the package" in str(exc.value)


def test_an_unrecognised_manifest_shape_fails_rather_than_passes(tmp_path):
    """A 0.103.0-shaped manifest must be REFUSED, not read as having nothing
    unlisted. `or []` here would turn a renamed key into a clean verdict --
    the defect that once printed "closure verdict clean" three lines under
    EXPORT_CLOSURE_BROKEN."""
    result = _export(tmp_path)
    old_shape = {"schema": "level_factory.portable_manifest.v0.1",
                 "created_at": "x", "resources": []}
    (result.export_dir / "portable_resource_manifest.json").write_text(
        json.dumps(old_shape), encoding="utf-8")
    with pytest.raises(E.ExportManifestError) as exc:
        E._guard_manifest_accounts_for_the_package(result.export_dir)
    msg = str(exc.value)
    assert "`unlisted`" in msg and "`accounting`" in msg
    assert "v0.1" in msg, "the message names the shape it found"


def test_the_declared_set_cannot_drift_from_the_post_verdict_list():
    """A file the manifest declines to list is one written after the walk, and
    the walk is after the closure verdict -- so it must already be allowed to
    land there, and be closure metadata. Same anti-drift tie as
    `_WRITTEN_AFTER_VERDICT` against `closure._METADATA_FILES`."""
    from packages.exporting.closure import _METADATA_FILES
    declared = {name for name, _why in E._UNLISTED_BY_CONSTRUCTION}
    assert declared == set(DECLARED_UNLISTED)
    assert declared <= E._WRITTEN_AFTER_VERDICT
    assert declared <= _METADATA_FILES


def test_the_three_writers_sit_above_the_manifest_walk():
    """The mechanism, not only the outcome: source order in `export_mission`.

    This is what 0.103.0 got wrong by four lines, and the outcome tests above
    would still pass if a future edit listed these files some other way while
    leaving the writers below the walk -- which would be a second answer to
    one question."""
    src = inspect.getsource(E.export_mission)
    walk = src.index("build_resource_manifest(export_dir)")
    head = src[:walk]
    for name in MOVED_ABOVE_THE_WALK:
        assert '"%s"' % name in head, (
            "%s is still written below the manifest walk" % name)
    # And LF_MANIFEST.json is still written below it, deliberately.
    assert "EXPORT_MANIFEST_NAME).write_text" in src[walk:]


def test_the_guards_both_run_before_the_package_is_returned():
    src = inspect.getsource(E.export_mission)
    assert "_guard_verdict_is_about_the_package(export_dir, scan)" in src
    assert "_guard_manifest_accounts_for_the_package(export_dir)" in src
    tail = src[src.index("_guard_manifest_accounts_for_the_package(export_dir)"):]
    assert ".write_text(" not in tail, (
        "something writes into the package after the manifest guard, which "
        "is the defect the guard exists to catch")
