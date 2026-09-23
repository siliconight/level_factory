"""The greybox slab takes a pack the building owns, so a hole cut through it
is not lined with greybox.

ROADMAP 168, WALKED. The walker descended a ladder on cold run 9070's package
and reported the floor below reading grey and untextured from above, with the
real texture appearing on the way down -- then the same on a staircase.

Four cheaper explanations were measured and refuted before this pass was
written, and they are kept in `zoo_worldskin.gd` above the rule that replaced
them: not draw distance (every mesh reports `visibility_range 0`, `lod_bias
1.0`, no distance fade), not occlusion culling (two package copies differing
only in the flag drew identical counts at four eye heights), not z-fighting
(the visible faces are 20 mm apart and a 24-bit buffer separates ~0.03 mm at
that range), not a gap in the floor (themed area equals slab area, 3192.0 m2
against 3192.0 m2, and the hole is cut through both to the same rectangle).

What it is: theming skins a slab's TOP as a floor and its BOTTOM as a ceiling
and never touches the faces a hole CREATES. 8 of 344 slabs in that package are
cut, carrying 10.44 m2 of bare `gb_floor` between them -- 1.44 m2 around the
walker's ladder, which is the same area as the opening it rings.

These run the real script through a real Godot import over a generated
package, for the reason `test_worldskin_stairs.py` gives: the GDScript was
correct and the building did not answer it, so a source-shape test could not
have caught the defect this replaces.

Skipped where no Godot is installed. `LF_GODOT` overrides, then `DC_GODOT`,
then `LOT_GODOT`, then the usual Windows install path, then PATH.

Run:  python -m pytest tests/unit/test_worldskin_slabs.py
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

#: The names the base really carries, from cold run 9070's `deli_a03`:
#: `slab_<story>_t<j>_<i>` visual plates tiled to the light budget, and
#: `slab_col_<story>` collision. `slab_-1_*` is a basement plate, spelled here
#: because a negative storey is where a name-prefix test goes wrong.
SLAB = "slab_0_t0_2"
SLAB_BASEMENT = "slab_-1_t0_2"
#: MEASURED, not assumed. The first version of this file wrote `slab_col_0`
#: and the pass skinned it -- because Godot's importer reads `_col` as its own
#: collision convention, renamed the node to `slab_0` and gave it a
#: StaticBody3D, so the test was exercising the importer rather than the pass.
#: Read out of cold run 9070's `lot/deli_a03/site_base.glb`: of 196 slab-named
#: nodes, 192 are plain visual plates and 4 are `slab_col_<story>-colonly`.
#: `-colonly` DELETES the visual mesh, which is why the walker's overlay names
#: `slab_col_-1` as a body and why no collision slab can reach `_assign_slabs`
#: at all. `SLAB_COLLISION_MARK` is therefore a second line of defence over a
#: convention Godot already enforces -- said plainly here rather than left to
#: look like the thing doing the work.
SLAB_COLLISION = "slab_col_0-colonly"

_PROJECT = """\
config_version=5

[application]
config/name="worldskin slab fixture"

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


def _project(tmp_path: Path, *, base_meshes, art=True, art_modules=None,
             textured=True) -> Path:
    """A one-building package: a base beside `art/zoo/`, exactly the layout
    `_skin_slabs` resolves from `get_source_file().get_base_dir()`."""
    proj = tmp_path / "pkg"
    proj.mkdir()
    (proj / "project.godot").write_text(_PROJECT, encoding="utf-8")
    (proj / "zoo_worldskin.gd").write_text(
        WORLDSKIN.read_text(encoding="utf-8"), encoding="utf-8")
    write_glb(proj / "site_base.glb", base_meshes, [("gb_floor", False)])
    if art:
        for name in (art_modules if art_modules is not None
                     else ("floor_delco_1997_05_w1000_d700.glb",)):
            write_glb(proj / "art" / "zoo" / name, [("tile", 0)],
                      [("M_Skin_concrete_delco_1997", textured)])
    return proj


def _import(proj: Path) -> str:
    out = subprocess.run(
        [_godot(), "--headless", "--path", str(proj), "--import"],
        capture_output=True, text=True, timeout=300)
    return out.stdout + out.stderr


def _slab_line(log: str) -> str:
    lines = [ln for ln in log.splitlines()
             if ln.startswith("[worldskin] site_base.glb") and "slabs:" in ln]
    # An unrecognised shape FAILS rather than passing: a missing line means the
    # pass did not run, which is not the same as a pass that skinned nothing.
    assert len(lines) == 1, f"expected one slab line, got {lines!r}\n{log}"
    return lines[0]


# ---------------------------------------------------------------------------
# the rule
# ---------------------------------------------------------------------------
@godot_required
def test_a_slab_takes_the_floor_family(tmp_path):
    """FAILS BEFORE THIS PASS: nothing looked at a slab at all, so every one
    of them shipped in Deli Counter's flat `gb_floor`."""
    proj = _project(tmp_path, base_meshes=[(SLAB, 0), (SLAB_BASEMENT, 0)])
    line = _slab_line(_import(proj))
    assert "2 surface(s) skinned on 2 mesh(es)" in line, line
    assert "0 mesh(es) left flat" in line, line
    assert "reveal from floor_delco_1997_05_w1000_d700.glb" in line, line


@godot_required
def test_a_collision_slab_is_not_skinned(tmp_path):
    """A body is not a surface. Dressing one would cost a material on
    something nobody sees, and would inflate the count this pass reports."""
    proj = _project(tmp_path, base_meshes=[(SLAB, 0), (SLAB_COLLISION, 0)])
    line = _slab_line(_import(proj))
    assert "1 surface(s) skinned on 1 mesh(es)" in line, line


@godot_required
def test_a_base_with_no_slab_is_a_no_op_that_says_which(tmp_path):
    """The no-op and the failure must not print the same sentence -- that is
    how the stair defect stayed invisible for five days (roadmap 144)."""
    proj = _project(tmp_path, base_meshes=[("stair0_0_0", 0)])
    line = _slab_line(_import(proj))
    assert "no visual slab in this base, nothing to skin" in line, line
    assert "0 mesh(es) left flat" in line, line


# ---------------------------------------------------------------------------
# and the loud failure
# ---------------------------------------------------------------------------
@godot_required
def test_no_art_beside_the_base_is_an_error_not_a_note(tmp_path):
    proj = _project(tmp_path, base_meshes=[(SLAB, 0)], art=False)
    log = _import(proj)
    line = _slab_line(log)
    assert "1 mesh(es) left flat" in line, line
    assert "NO art/zoo BESIDE THE BASE" in line, line
    assert "0 surface(s) skinned" in line, line
    assert any("ERROR" in ln and "NO art/zoo BESIDE THE BASE" in ln
               for ln in log.splitlines()), log


@godot_required
def test_an_art_directory_with_no_family_module_is_an_error(tmp_path):
    proj = _project(tmp_path, base_meshes=[(SLAB, 0)],
                    art_modules=("prop_chair_delco_1997_07_w50_d50_h90.glb",))
    log = _import(proj)
    line = _slab_line(log)
    assert "NO MODULE UNDER art/zoo IN FAMILIES" in line, line
    assert "1 mesh(es) left flat" in line, line
    assert any("ERROR" in ln and "NO MODULE UNDER art/zoo" in ln
               for ln in log.splitlines()), log


@godot_required
def test_an_untextured_module_is_not_a_pack(tmp_path):
    """Swapping Deli Counter's grey for somebody else's grey and reporting it
    as a success is the failure mode this whole pass exists to end."""
    proj = _project(tmp_path, base_meshes=[(SLAB, 0)], textured=False)
    line = _slab_line(_import(proj))
    assert "NO MODULE UNDER art/zoo IN FAMILIES" in line, line


# ---------------------------------------------------------------------------
# the shape, for a machine with no Godot
# ---------------------------------------------------------------------------
def test_the_slab_pass_and_its_refutations_are_in_the_source():
    """A retracted finding is cheaper to keep than to rediscover: four wrong
    explanations were measured before this pass and all four are recorded."""
    src = WORLDSKIN.read_text(encoding="utf-8")
    assert 'const SLAB_REVEAL_FAMILY: Array = ["floor_"]' in src
    assert "func _skin_slabs" in src
    assert "NOT occlusion culling" in src
    assert "NOT z-fighting" in src
    assert "NOT draw distance" in src
    assert "NOT a gap in the floor" in src


def test_a_negative_storey_slab_is_still_a_slab():
    """`slab_-1_t0_2` is a basement plate. A prefix test that reached for a
    digit after the underscore would drop every basement in the library."""
    src = WORLDSKIN.read_text(encoding="utf-8")
    assert 'const SLAB_PREFIX: String = "slab_"' in src
    assert 'const SLAB_COLLISION_MARK: String = "col"' in src
