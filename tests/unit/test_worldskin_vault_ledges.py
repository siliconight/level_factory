"""A vault ledge is skinned: the building's drywall, then any wall, then its floor (0.217.0).

Deli Counter builds a waist-height ledge inside a floor (`_vault_ledges`, `VAULTLEDGE_<n>`) as a box in the
FLOOR role, so it shipped in `gb_floor`: on the factory's cold run 9321 the only greybox left in the themed
package was three of them, 49.7 m2. No kit module stands in for one, so -- like a slab, a flight and a
ladder -- the base's own pass has to dress it.

WHAT IT WEARS IS A CALL, made 2026-10-19 and meant to be changed (`VAULT_LEDGE_FAMILIES`): a ledge inside a
floor reads as a short partition, so the building's interior drywall wall first, then any wall, then the floor
family the slabs take.

These run the real script through a real Godot import, as `test_worldskin_ladders.py` does, and are skipped
where no Godot is installed. `LF_GODOT` overrides, then `DC_GODOT`, then `LOT_GODOT`, then the usual Windows
install path, then PATH.

Run:  python -m pytest tests/unit/test_worldskin_vault_ledges.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from glb_import_fixture import write_glb  # noqa: E402

WORLDSKIN = ROOT / "assets" / "godot" / "zoo_worldskin.gd"

#: The names Deli Counter emits (`deli_counter.py` `_vault_ledges`): the visual box, and its convex collider,
#: whose visual Godot's `-convcolonly` convention deletes on import.
LEDGE = "VAULTLEDGE_0"
LEDGE_2 = "VAULTLEDGE_1"
COLLIDER = "VAULTLEDGE_0-convcolonly"
#: The modules a mission building ships beside its base (on cold run 9321, deli_a01, office and pharmacy_a01
#: each carry `wall_delco_1997_02_w200_mdrywall.glb`).
DRYWALL = ("wall_delco_1997_02_w200_mdrywall.glb", "M_Skin_drywall_delco_1997")
BRICK = ("wall_delco_1997_01_w200_mbrick.glb", "M_Skin_brick_delco_1997")
FLOOR = ("floor_delco_1997_05_w1000_d700.glb", "M_Skin_concrete_delco_1997")
PROP = ("prop_bench_delco_1997_01_w180.glb", "M_Skin_wood_delco_1997")

_PROJECT = """\
config_version=5

[application]
config/name="worldskin vault ledge fixture"

[rendering]
renderer/rendering_method="gl_compatibility"

[importer_defaults]

scene={
"import_script/path": "res://zoo_worldskin.gd"
}
"""


def _godot() -> str | None:
    for env in ("LF_GODOT", "DC_GODOT", "LOT_GODOT"):
        p = os.environ.get(env)
        if p and Path(p).is_file():
            return p
    usual = Path("C:/Godot/4.7/Godot_v4.7-stable_win64_console.exe")
    if usual.is_file():
        return str(usual)
    return shutil.which("godot")


godot_required = pytest.mark.skipif(
    _godot() is None, reason="no Godot binary; this test imports a real package")


def _project(tmp_path: Path, *, base_meshes, modules=(DRYWALL, BRICK, FLOOR), art=True) -> Path:
    proj = tmp_path / "pkg"
    proj.mkdir()
    (proj / "project.godot").write_text(_PROJECT, encoding="utf-8")
    (proj / "zoo_worldskin.gd").write_text(WORLDSKIN.read_text(encoding="utf-8"), encoding="utf-8")
    write_glb(proj / "site_base.glb", base_meshes, [("gb_floor", False)])
    if art:
        for fname, mat in modules:
            write_glb(proj / "art" / "zoo" / fname, [("part", 0)], [(mat, True)])
    return proj


def _import(proj: Path) -> str:
    out = subprocess.run([_godot(), "--headless", "--path", str(proj), "--import"],
                         capture_output=True, text=True, timeout=300)
    return out.stdout + out.stderr


def _ledge_line(log: str) -> str:
    lines = [ln for ln in log.splitlines()
             if ln.startswith("[worldskin] site_base.glb") and "vault ledges:" in ln]
    # An unrecognised shape FAILS rather than passing.
    assert len(lines) == 1, f"expected one vault ledge line, got {lines!r}\n{log}"
    return lines[0]


@godot_required
def test_a_ledge_takes_the_buildings_drywall(tmp_path):
    """FAILS BEFORE THIS PASS: nothing looked at a vault ledge, so it shipped in gb_floor."""
    proj = _project(tmp_path, base_meshes=[(LEDGE, 0), (LEDGE_2, 0)])
    line = _ledge_line(_import(proj))
    assert "2 surface(s) skinned on 2 mesh(es)" in line, line
    assert "0 mesh(es) left flat" in line, line
    assert "from %s" % DRYWALL[0] in line, line


@godot_required
def test_no_drywall_takes_any_wall(tmp_path):
    proj = _project(tmp_path, base_meshes=[(LEDGE, 0)], modules=(BRICK, FLOOR))
    line = _ledge_line(_import(proj))
    assert "1 surface(s) skinned on 1 mesh(es)" in line, line
    assert "from %s" % BRICK[0] in line, line


@godot_required
def test_no_wall_takes_the_floor_family(tmp_path):
    proj = _project(tmp_path, base_meshes=[(LEDGE, 0)], modules=(FLOOR,))
    line = _ledge_line(_import(proj))
    assert "1 surface(s) skinned on 1 mesh(es)" in line, line
    assert "from %s" % FLOOR[0] in line, line


@godot_required
def test_the_collider_is_not_skinned(tmp_path):
    proj = _project(tmp_path, base_meshes=[(LEDGE, 0), (COLLIDER, 0)])
    line = _ledge_line(_import(proj))
    assert "1 surface(s) skinned on 1 mesh(es)" in line, line


@godot_required
def test_a_base_with_no_ledge_is_a_no_op_that_says_which(tmp_path):
    proj = _project(tmp_path, base_meshes=[("slab_0_t0_0", 0)])
    line = _ledge_line(_import(proj))
    assert "no vault ledge in this base, nothing to skin" in line, line
    assert "0 mesh(es) left flat" in line, line


@godot_required
def test_no_art_beside_the_base_is_an_error_not_a_note(tmp_path):
    proj = _project(tmp_path, base_meshes=[(LEDGE, 0)], art=False)
    log = _import(proj)
    line = _ledge_line(log)
    assert "NO art/zoo BESIDE THE BASE" in line, line
    assert "1 mesh(es) left flat" in line, line
    assert any("ERROR" in ln and "vault ledge" in ln and "NO art/zoo BESIDE THE BASE" in ln
               for ln in log.splitlines()), log


@godot_required
def test_no_module_in_any_family_is_an_error_not_a_note(tmp_path):
    proj = _project(tmp_path, base_meshes=[(LEDGE, 0)], modules=(PROP,))
    log = _import(proj)
    line = _ledge_line(log)
    assert "NO MODULE UNDER art/zoo IN FAMILIES" in line, line
    assert "1 mesh(es) left flat" in line, line
    assert any("ERROR" in ln and "vault ledge" in ln for ln in log.splitlines()), log


def test_the_call_is_recorded_as_one_that_can_change():
    """Drywall first is a call, not a measurement. The source says so, so a reader moves the dial rather than
    'fixing' a choice whose reason they cannot find."""
    src = WORLDSKIN.read_text(encoding="utf-8")
    assert 'const VAULT_LEDGE_FAMILIES: Array = [["wall_", "_mdrywall"], ["wall_", ""], ["floor_", ""]]' in src
    assert "meant to be changed" in src
