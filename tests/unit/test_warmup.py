"""A package pays its shader compile bill at load, not in the first lap.

WHAT THESE PIN, and what each one cost to learn. Measured on cold run 9066's
package, 2026-09-21, Godot 4.7.stable, gl_compatibility, RTX 2060, a camera
following one six-leg route twice at 3 m/s with BOTH shader caches cleared
before the run:

    lap 1   mean 15.64 ms   2.43% over 16.7 ms   worst 8,564 ms
    lap 2   mean  7.16 ms   0.22% over 16.7 ms   worst    24 ms

* IT IS COMPILATION, AND THE INSTRUMENT THAT SETTLES IT IS OUTSIDE THE
  PROJECT. The renderer's three memory monitors and its resource count are
  flat across every multi-second frame; draw calls and object counts are the
  same on both laps. What moved the number was moving the DRIVER's program
  cache aside -- 172 ms with both caches warm, 376 ms with Godot's wiped,
  8,641 ms with the driver's wiped too. `PIPELINE_COMPILATIONS_*` read 0 on
  every frame of every one of those runs, which is what they do under GL
  Compatibility; they cannot settle this and were not asked to.

* DRAWING EVERY MATERIAL ONCE IS NOT ENOUGH, and this is the one that looks
  obviously sufficient. Every unique material on a quad at spawn took the
  worst frame from 8,564 ms to 5,151 ms; every unique mesh SURFACE, same.
  A GL Compatibility program is specialized on the lighting context of the
  draw, and the renderable-light set is chosen by distance to the camera --
  so the warm-up has to stand where the player will stand. Six headings at
  every light cluster reached 2,730 ms; adding a grid over the level's own
  extent reached 155 ms.

* THE GUARDS ARE THE SHIPPED ARTEFACT'S, NOT THE REPO'S. A warm-up that runs
  headless costs the QA walkers 252 frames for nothing, and one that runs in
  the editor sweeps the camera while somebody is using it. `audit` reads the
  script out of the PACKAGE, because the gap between what a step believes it
  wrote and what shipped is where 9065's occluders lived.

* WIRING IS IDEMPOTENT AND HONEST ABOUT load_steps. The export is
  re-runnable; two `Warmup` nodes is two sweeps for one level. And
  `mission.tscn` carries its entry script as a sub_resource with NO
  ext_resource block at all, so the branch that inserts the first one is the
  branch every real package takes.

* A PACKAGE THAT NAMES A SCRIPT IT DOES NOT SHIP MUST FAIL. That entry scene
  does not load, and a level that does not load is worse than one that
  stalls.

Run:  python -m pytest tests/unit/test_warmup.py
"""
import json
from pathlib import Path

import pytest

from packages.exporting.warmup import (HOLDER_NODE, REPORT_NAME,
                                       REQUIRED_GUARDS, SCHEMA, SCRIPT_NAME,
                                       WARMUP_SCRIPT, WarmupError, audit,
                                       emit, script_text, wire_into_scene)

#: `mission.tscn` as `localize.write_entry_scene` writes it: a sub_resource
#: script, no ext_resource block, load_steps=2. Copied from cold run 9066's
#: shipped package rather than invented, so a change to the real template
#: shows up here as a failure instead of passing against a fiction.
ENTRY = '''[gd_scene load_steps=2 format=3]

[sub_resource type="GDScript" id="mission_entry"]
script/source = "extends Node3D

func _ready() -> void:
\tprint('scene instantiated ok')
"

[node name="Mission" type="Node3D"]
script = SubResource("mission_entry")
'''


def _pkg(tmp_path: Path) -> Path:
    (tmp_path / "mission.tscn").write_text(ENTRY, encoding="utf-8")
    return tmp_path


def test_the_repo_ships_a_script_and_it_carries_every_guard():
    """The source of truth exists and is not a stub.

    `script_text` refuses rather than shipping one without its guards,
    because a warm-up with no way off is one a recipient cannot A/B against
    the stall it is there to remove.
    """
    assert WARMUP_SCRIPT.is_file(), WARMUP_SCRIPT
    body = script_text()
    for guard in REQUIRED_GUARDS:
        assert guard in body, guard


def test_wiring_adds_one_node_and_one_ext_resource(tmp_path):
    pkg = _pkg(tmp_path)
    assert wire_into_scene(pkg / "mission.tscn") is True
    text = (pkg / "mission.tscn").read_text(encoding="utf-8")
    assert text.count(f'[node name="{HOLDER_NODE}" type="Node3D"') == 1
    assert text.count(f'path="res://{SCRIPT_NAME}"') == 1
    # The header has to stay first, or Godot does not read the file as a
    # scene at all.
    assert text.splitlines()[0].startswith("[gd_scene ")


def test_wiring_bumps_load_steps_for_the_resource_it_added(tmp_path):
    """A scene that lies about its own size is a defect somebody has to read.

    `mission.tscn` goes out at load_steps=2 for its one sub_resource; the
    ext_resource the warm-up adds is a second.
    """
    pkg = _pkg(tmp_path)
    assert "load_steps=2" in (pkg / "mission.tscn").read_text(encoding="utf-8")
    wire_into_scene(pkg / "mission.tscn")
    assert "load_steps=3" in (pkg / "mission.tscn").read_text(encoding="utf-8")


def test_wiring_is_idempotent(tmp_path):
    pkg = _pkg(tmp_path)
    assert wire_into_scene(pkg / "mission.tscn") is True
    first = (pkg / "mission.tscn").read_text(encoding="utf-8")
    assert wire_into_scene(pkg / "mission.tscn") is False
    assert (pkg / "mission.tscn").read_text(encoding="utf-8") == first


def test_wiring_refuses_a_file_that_is_not_a_scene(tmp_path):
    (tmp_path / "mission.tscn").write_text("not a scene\n", encoding="utf-8")
    with pytest.raises(WarmupError):
        wire_into_scene(tmp_path / "mission.tscn")


def test_emit_ships_the_script_the_scene_names(tmp_path):
    pkg = _pkg(tmp_path)
    report = emit(pkg)
    assert report["schema"] == SCHEMA
    assert (pkg / SCRIPT_NAME).is_file()
    assert (pkg / SCRIPT_NAME).read_bytes() == WARMUP_SCRIPT.read_bytes()
    assert report["warmup_nodes"] == 1
    assert report["script_shipped"] is True
    assert sorted(report["guards_present"]) == sorted(REQUIRED_GUARDS)
    written = json.loads((pkg / REPORT_NAME).read_text(encoding="utf-8"))
    assert written["schema"] == SCHEMA


def test_emit_twice_leaves_one_node(tmp_path):
    pkg = _pkg(tmp_path)
    emit(pkg)
    second = emit(pkg)
    assert second["wired"] is False
    assert second["warmup_nodes"] == 1


def test_audit_fails_when_the_scene_names_a_script_that_did_not_ship(tmp_path):
    pkg = _pkg(tmp_path)
    emit(pkg)
    (pkg / SCRIPT_NAME).unlink()
    with pytest.raises(WarmupError) as exc:
        audit(pkg)
    assert SCRIPT_NAME in str(exc.value)


def test_audit_fails_when_the_shipped_script_lost_a_guard(tmp_path):
    """The PACKAGE's script, not the repo's.

    An export that copied a stale or edited script ships a warm-up that runs
    headless in every QA walk, and nothing in the scene would show it.
    """
    pkg = _pkg(tmp_path)
    emit(pkg)
    body = (pkg / SCRIPT_NAME).read_text(encoding="utf-8")
    body = body.replace('DisplayServer.get_name() == "headless"', "false")
    (pkg / SCRIPT_NAME).write_text(body, encoding="utf-8")
    with pytest.raises(WarmupError) as exc:
        audit(pkg)
    assert "headless" in str(exc.value)


def test_audit_fails_on_two_warmups(tmp_path):
    pkg = _pkg(tmp_path)
    emit(pkg)
    text = (pkg / "mission.tscn").read_text(encoding="utf-8")
    (pkg / "mission.tscn").write_text(
        text + f'\n[node name="{HOLDER_NODE}" type="Node3D" parent="."]\n',
        encoding="utf-8")
    with pytest.raises(WarmupError):
        audit(pkg)


def test_audit_is_quiet_about_a_package_with_no_warmup_at_all(tmp_path):
    """Every package before 0.99.0. Consistent, and reported rather than
    raised -- the export decides what to do about it, not the auditor."""
    pkg = _pkg(tmp_path)
    verdict = audit(pkg)
    assert verdict["warmup_nodes"] == 0
    assert verdict["script_shipped"] is False


def test_the_export_ships_a_warmup(tmp_path):
    """THE ONE THAT FAILS ON 0.98.0 FOR THE REASON THAT MATTERS.

    Every test above can be satisfied by a module nothing calls. This asserts
    the export path itself names the step, so a warm-up that exists and is
    never wired -- which is precisely the shape of 0.98.0's occluder defect --
    fails here rather than in somebody's first lap.
    """
    import packages.exporting.export as export_mod
    source = Path(export_mod.__file__).read_text(encoding="utf-8")
    assert "warmup_emit" in source
    assert "warmup_audit" in source
    assert hasattr(export_mod, "ExportWarmupError")
