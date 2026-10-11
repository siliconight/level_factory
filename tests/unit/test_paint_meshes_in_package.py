"""The export carries the paint meshes beside the assembly scene (0.177.3).

Cold run 9235: the Lot adapter published Lot 0.114.0's `site_marks_<colour>.obj`
(0.177.2) and every stage up to the export found them beside the scene; the
export's step 2.5 copied the assembly's `site.tscn` and its `skins/`, `cover/`
and `signs/` and nothing else, so the package's scene named two meshes
"from ./" that were not there, Lux's applied scene named them as
`res://site_marks_*.obj`, the closure gate refused the package and the
bake's scene would not open. The themed dir here is the assembly as Lot
leaves it: the scene naming its meshes, and the meshes beside it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from packages.exporting.export import ExportProfile, export_mission  # noqa: E402

OBJ = "site_marks_090_090_088.obj"
SCENE = ('[gd_scene load_steps=2 format=3]\n\n'
         f'[ext_resource type="Mesh" path="{OBJ}" id="site_marks_090_090_088"]\n\n'
         '[node name="Site" type="Node3D"]\n\n'
         '[node name="site_marks_090_090_088" type="MeshInstance3D" parent="."]\n'
         'mesh = ExtResource("site_marks_090_090_088")\n')


def test_the_assemblys_paint_meshes_land_beside_the_scene(tmp_path):
    themed = tmp_path / "themed"
    themed.mkdir()
    (themed / "site.tscn").write_text(SCENE, encoding="utf-8")
    (themed / OBJ).write_text("o site_marks_090_090_088\nv 0 0 0\nv 1 0 0\nv 1 0 1\n"
                              "vt 0 0\nvt 1 0\nvt 1 1\nvn 0 1 0\nf 1/1/1 2/2/1 3/3/1\n",
                              encoding="utf-8")
    (themed / "site.markings.json").write_text("{}", encoding="utf-8")
    handoff = tmp_path / "handoff"
    handoff.mkdir()
    (handoff / "mission.tscn").write_text("[gd_scene]\n", encoding="utf-8")
    (handoff / "site.tscn").write_text("[gd_scene]\n", encoding="utf-8")
    result = export_mission(mission_id="m1", handoff_dir=handoff, presentation_dir=None,
                            source_dir=None, profile=ExportProfile(), tool_versions={},
                            out_root=tmp_path / "exports", themed_site_dir=themed)
    out = Path(result.export_dir)
    assert (out / OBJ).read_text(encoding="utf-8").startswith("o site_marks_090_090_088\n")
    assert (out / "site.tscn").read_text(encoding="utf-8") == SCENE
    # the manifest is not a sibling the scene names, and is not carried
    assert not (out / "site.markings.json").exists()
    scan = out / "export_closure_scan.json"
    if scan.exists():
        doc = json.loads(scan.read_text(encoding="utf-8"))
        assert doc.get("unresolved_relative_count", 0) == 0, doc.get("issues")
