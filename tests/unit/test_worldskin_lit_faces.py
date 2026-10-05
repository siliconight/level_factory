"""A lit face keeps its own UVs on a kit module (0.140.0).

`_apply` world-projects every material on a kit module (`uv1_triplanar`,
`uv1_world_triplanar`), which is right for a tiling skin -- brick, siding,
drywall -- and was right for every kit material until Zoo 1.64.0 painted the
Empties' window panes into ONE ATLAS whose cell is chosen by the pane's UVs.
Cold run 9152, headless on its walk copy: the street side of every pane
carried its cell (`pane_face_probe.gd`), and the material imported with
`uv1_triplanar true, uv1_world_triplanar true, uv1_scale 0.1856` -- so the
mesh's UVs were ignored, the atlas was sampled by world position, and from the
street every pane read as flat frame-paint beige with no glow.

A material named with one of Lux's lit-face suffixes (`_Face`, `_Lens`,
`_Diffuser` -- `lux_emissive_binder.gd` SUFFIXES) is artwork mapped by its
UVs: it is never world-projected, and the report counts it.

These run the real script through a real Godot import over a generated
module, as `test_worldskin_slabs.py` does. Skipped where no Godot is
installed.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from glb_import_fixture import write_glb  # noqa: E402
from tests.siblings import sibling_repo  # noqa: E402

WORLDSKIN = ROOT / "assets" / "godot" / "zoo_worldskin.gd"

_PROJECT = """\
config_version=5

[application]
config/name="worldskin lit-face fixture"

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
    _godot() is None, reason="no Godot binary; this test imports a real module")

MODULE = "window_delco_1997_01_w95_mbrick_plit_o173e47.glb"


def _import(tmp_path: Path, meshes, materials) -> str:
    proj = tmp_path / "pkg"
    proj.mkdir()
    (proj / "project.godot").write_text(_PROJECT, encoding="utf-8")
    (proj / "zoo_worldskin.gd").write_text(WORLDSKIN.read_text(encoding="utf-8"), encoding="utf-8")
    write_glb(proj / MODULE, meshes, materials, spread_uv=True)
    out = subprocess.run([_godot(), "--headless", "--path", str(proj), "--import"],
                         capture_output=True, text=True, timeout=300)
    log = out.stdout + out.stderr
    lines = [ln for ln in log.splitlines()
             if ln.startswith(f"[worldskin] {MODULE}") and "world-projected" in ln]
    # an unrecognised shape FAILS: a missing line means the pass did not run
    assert len(lines) == 1, f"expected one report line, got {lines!r}\n{log}"
    return lines[0]


def _counts(line: str) -> tuple:
    projected = int(re.search(r"(\d+) material\(s\) world-projected", line).group(1))
    m = re.search(r"(\d+) lit face\(s\) left on their own UVs", line)
    assert m, f"no lit-face count in the report: {line}"
    return projected, int(m.group(1))


@godot_required
def test_a_painted_pane_keeps_its_uvs_and_the_brick_is_still_projected(tmp_path):
    """FAILS ON 0.139.0: both world-projected, and no lit-face count."""
    line = _import(tmp_path, [("Window_brick", 0), ("Window_Glass", 1)],
                   [("M_Skin_brick_delco_1997", True), ("M_Window_pane_Face", True)])
    assert _counts(line) == (1, 1), line


@godot_required
def test_a_module_with_no_lit_face_is_projected_as_before(tmp_path):
    """The control: a plain skin is world-projected exactly as it was."""
    line = _import(tmp_path, [("Window_brick", 0)], [("M_Skin_brick_delco_1997", True)])
    assert _counts(line) == (1, 0), line


def test_the_suffixes_are_lux_s_binder_s():
    """One contract, two readers: what Lux binds as a lit face is what this
    leaves on its UVs. A suffix added on one side and not the other is a lit
    face that glows in the wrong place or a skin that tiles at the wrong
    density."""
    src = WORLDSKIN.read_text(encoding="utf-8")
    assert 'const LIT_FACE_SUFFIXES: Array = ["_Lens", "_Diffuser", "_Face"]' in src
    # found by searching, not by counting parents (`tests/siblings.py`)
    binder = "addons/lux/runtime/lux_emissive_binder.gd"
    lux = sibling_repo("lux", marker=binder)
    if lux is not None:
        assert 'const SUFFIXES: Array[String] = ["_Lens", "_Diffuser", "_Face"]' in (lux / binder).read_text(encoding="utf-8")
