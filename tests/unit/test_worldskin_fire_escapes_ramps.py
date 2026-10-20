"""A legacy fire escape and a vehicle ramp are skinned (0.220.0): the fire escape the darkest metal the building owns,
the ramp its floor.

Level Factory 0.218.0 made the export's greybox census refuse any greybox surface in a themed package, on the claim
that every kind of base geometry it had met had an owner. Two kinds had none. The factory's cold run 9342
(precinct_yard_001) was refused on apartment_walkup_a01's legacy fire escape -- Deli Counter's `_fire_escapes`,
`FIREESCAPE_<id>_<story>` and its `_RAIL`, two surfaces on `gb_floor` -- and cold runs 9168, 9174 and 9177 had shipped a
garage's vehicle ramp (`_ramps`, `ramp<n>`, on `gb_ramp`), reported and not refused. The factory's
`docs/findings/base_greybox_owners/census.py` read every base in Deli Counter's library against the passes' name tests
and found exactly those two kinds in the shells a themed lot can draw.

WHAT EACH WEARS IS A CALL, made 2026-10-20 and meant to be changed: the walk-ups' fire escapes are Zoo's
`fire_escape`, black painted steel, so this one takes the darkest tinted metal in the building's `prop_` modules (the
ladder rail's pick), and the theme's rust only when no tinted metal is there; a ramp is a floor, as a tread is, so it
takes the floor family the slabs' reveal takes, roof as the fallback.

These run the real script through a real Godot import, as `test_worldskin_vault_ledges.py` does, and are skipped
where no Godot is installed. `LF_GODOT` overrides, then `DC_GODOT`, then `LOT_GODOT`, then the usual Windows install
path, then PATH.

Run:  python -m pytest tests/unit/test_worldskin_fire_escapes_ramps.py
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

#: The names Deli Counter emits (`deli_counter.py` `_fire_escapes`, `_ramps`): the fire escape's deck, its outer
#: guard, the stub down to the platform below, and the deck's convex collider, whose visual Godot's `-convcolonly`
#: convention deletes on import; a ramp, a second one, and its collider.
DECK = "FIREESCAPE_REAR_FIRE_ESCAPE_1"
GUARD = "FIREESCAPE_REAR_FIRE_ESCAPE_1_RAIL"
STUB = "FIREESCAPE_REAR_FIRE_ESCAPE_2_STAIR"
DECK_COLLIDER = "FIREESCAPE_REAR_FIRE_ESCAPE_1-convcolonly"
RAMP = "ramp0"
RAMP_2 = "ramp1"
RAMP_COLLIDER = "ramp0_col-convcolonly"
#: Three real metals off the factory's cold run 9070's package, with their measured baseColorFactors (as
#: `test_worldskin_ladders.py` carries them); the rusted skin's colour lives in its texture, so its factor is 1.
DARK = ("M_Skin_metal_painted_delco_1997_040404", True, [0.015, 0.015, 0.016])
LIGHT = ("M_Skin_metal_bare_delco_1997_c7c9cc", True, [0.78, 0.79, 0.80])
RUST = ("M_Skin_metal_delco_1997", True, [1.0, 1.0, 1.0])
#: The luminance the pass prints is of `albedo_color` as Godot's glTF importer reports it, sRGB: the dark metal
#: reads 0.129 (`test_worldskin_ladders.py` records how that was found).
DARK_LUM = "0.129"
FLOOR = ("floor_delco_1997_05_w1000_d700.glb", "M_Skin_concrete_delco_1997")
ROOF = ("roof_delco_1997_01_w1000_d700.glb", "M_Skin_tar_delco_1997")
WALL = ("wall_delco_1997_01_w200_mbrick.glb", "M_Skin_brick_delco_1997")

_PROJECT = """\
config_version=5

[application]
config/name="worldskin fire escape and ramp fixture"

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


def _project(tmp_path: Path, *, base_meshes, modules=(FLOOR,), metals=(DARK, LIGHT, RUST), art=True) -> Path:
    proj = tmp_path / "pkg"
    proj.mkdir()
    (proj / "project.godot").write_text(_PROJECT, encoding="utf-8")
    (proj / "zoo_worldskin.gd").write_text(WORLDSKIN.read_text(encoding="utf-8"), encoding="utf-8")
    write_glb(proj / "site_base.glb", base_meshes, [("gb_floor", False)])
    if art:
        for fname, mat in modules:
            write_glb(proj / "art" / "zoo" / fname, [("part", 0)], [(mat, True)])
        if metals:
            write_glb(proj / "art" / "zoo" / "prop_bench_delco_1997_01_w180.glb",
                      [("part_%d" % i, i) for i in range(len(metals))], list(metals))
    return proj


def _import(proj: Path) -> str:
    out = subprocess.run([_godot(), "--headless", "--path", str(proj), "--import"],
                         capture_output=True, text=True, timeout=300)
    return out.stdout + out.stderr


def _line(log: str, what: str) -> str:
    lines = [ln for ln in log.splitlines()
             if ln.startswith("[worldskin] site_base.glb") and ("  %s:" % what) in ln]
    # An unrecognised shape FAILS rather than passing.
    assert len(lines) == 1, f"expected one {what} line, got {lines!r}\n{log}"
    return lines[0]


# ---------------------------------------------------------------------------
# a fire escape
# ---------------------------------------------------------------------------
@godot_required
def test_a_fire_escape_takes_the_darkest_metal(tmp_path):
    """FAILS BEFORE THIS PASS: nothing looked at a fire escape, so it shipped in gb_floor and, since 0.218.0, the
    export refused the package. The deck, its guard and the stub between platforms take one metal."""
    proj = _project(tmp_path, base_meshes=[(DECK, 0), (GUARD, 0), (STUB, 0)])
    line = _line(_import(proj), "fire escapes")
    assert "3 surface(s) skinned on 3 mesh(es)" in line, line
    assert "0 mesh(es) left flat" in line, line
    assert "darkest tinted metal %s (%s)" % (DARK[0], DARK_LUM) in line, line


@godot_required
def test_no_tinted_metal_takes_the_rust(tmp_path):
    proj = _project(tmp_path, base_meshes=[(DECK, 0)], metals=(RUST,))
    line = _line(_import(proj), "fire escapes")
    assert "1 surface(s) skinned on 1 mesh(es)" in line, line
    assert "no tinted metal, the theme's rust %s" % RUST[0] in line, line


@godot_required
def test_the_fire_escapes_collider_is_not_skinned(tmp_path):
    proj = _project(tmp_path, base_meshes=[(DECK, 0), (DECK_COLLIDER, 0)])
    line = _line(_import(proj), "fire escapes")
    assert "1 surface(s) skinned on 1 mesh(es)" in line, line


@godot_required
def test_a_base_with_no_fire_escape_is_a_no_op_that_says_which(tmp_path):
    proj = _project(tmp_path, base_meshes=[("slab_0_t0_0", 0)])
    line = _line(_import(proj), "fire escapes")
    assert "no fire escape in this base, nothing to skin" in line, line
    assert "0 mesh(es) left flat" in line, line


@godot_required
def test_no_art_beside_the_base_is_an_error_not_a_note(tmp_path):
    proj = _project(tmp_path, base_meshes=[(DECK, 0), (RAMP, 0)], art=False)
    log = _import(proj)
    for what, kind in (("fire escapes", "fire escape"), ("ramps", "ramp")):
        line = _line(log, what)
        assert "NO art/zoo BESIDE THE BASE" in line, line
        assert "1 mesh(es) left flat" in line, line
        assert any("ERROR" in ln and kind in ln and "NO art/zoo BESIDE THE BASE" in ln
                   for ln in log.splitlines()), log


@godot_required
def test_no_metal_is_an_error_not_a_note(tmp_path):
    proj = _project(tmp_path, base_meshes=[(DECK, 0), (GUARD, 0)], metals=())
    log = _import(proj)
    line = _line(log, "fire escapes")
    assert "NO METAL MATERIAL UNDER art/zoo" in line, line
    assert "2 mesh(es) left flat" in line, line
    assert any("ERROR" in ln and "fire escape" in ln for ln in log.splitlines()), log


# ---------------------------------------------------------------------------
# a vehicle ramp
# ---------------------------------------------------------------------------
@godot_required
def test_a_ramp_takes_the_floor_family(tmp_path):
    """FAILS BEFORE THIS PASS: nothing looked at a ramp, so it shipped in gb_ramp (cold runs 9168, 9174, 9177)."""
    proj = _project(tmp_path, base_meshes=[(RAMP, 0), (RAMP_2, 0)], modules=(WALL, FLOOR, ROOF))
    line = _line(_import(proj), "ramps")
    assert "2 surface(s) skinned on 2 mesh(es)" in line, line
    assert "0 mesh(es) left flat" in line, line
    assert "from %s" % FLOOR[0] in line, line


@godot_required
def test_no_floor_takes_the_roof_family(tmp_path):
    proj = _project(tmp_path, base_meshes=[(RAMP, 0)], modules=(WALL, ROOF))
    line = _line(_import(proj), "ramps")
    assert "1 surface(s) skinned on 1 mesh(es)" in line, line
    assert "from %s" % ROOF[0] in line, line


@godot_required
def test_only_ramp_and_an_index_is_a_ramp(tmp_path):
    """The name test is exact: the collider is not drawn, and a name that merely begins `ramp` is not claimed."""
    proj = _project(tmp_path, base_meshes=[(RAMP, 0), (RAMP_COLLIDER, 0), ("ramp_kerb_0", 0), ("rampart", 0)])
    line = _line(_import(proj), "ramps")
    assert "1 surface(s) skinned on 1 mesh(es)" in line, line


@godot_required
def test_a_base_with_no_ramp_is_a_no_op_that_says_which(tmp_path):
    proj = _project(tmp_path, base_meshes=[("slab_0_t0_0", 0)])
    line = _line(_import(proj), "ramps")
    assert "no vehicle ramp in this base, nothing to skin" in line, line
    assert "0 mesh(es) left flat" in line, line


@godot_required
def test_no_floor_or_roof_is_an_error_not_a_note(tmp_path):
    proj = _project(tmp_path, base_meshes=[(RAMP, 0)], modules=(WALL,))
    log = _import(proj)
    line = _line(log, "ramps")
    assert "NO MODULE UNDER art/zoo IN FAMILIES" in line, line
    assert "1 mesh(es) left flat" in line, line
    assert any("ERROR" in ln and "ramp" in ln for ln in log.splitlines()), log


def test_the_calls_are_recorded_as_ones_that_can_change():
    """Both choices are calls, not measurements. The source says so, so a reader moves the dial rather than 'fixing'
    a choice whose reason they cannot find."""
    src = WORLDSKIN.read_text(encoding="utf-8")
    assert 'const FIRE_ESCAPE_PREFIX: String = "FIREESCAPE_"' in src
    assert 'const RAMP_PREFIX: String = "ramp"' in src
    assert 'const RAMP_FAMILY: Array = ["floor_", "roof_"]' in src
    assert src.count("made 2026-10-20 and meant to be changed") == 2
