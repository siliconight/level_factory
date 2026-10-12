"""A site's overhead wires stay out of the lightmap (0.194.0, factory roadmap 240).

Lot 0.119.0 ships a site's wires as `site_wires_*.obj` beside the scene, unshaded, on nodes that take
no GI. `mark_imports` asks every other OBJ -- the road paint (0.177.1) -- for a lightmap UV so it
bakes like a model; a wire's it leaves as the engine wrote it and lists under `unlit`.
"""
from pathlib import Path

from packages.exporting import light_bake

#: the shape Godot 4.7 writes beside an OBJ (cold run 9262's package, its paint's
#: sidecar, as the engine leaves it before the bake asks for a lightmap UV)
SIDECAR = """[remap]

importer="wavefront_obj"
importer_version=1
type="Mesh"
uid="uid://bt3k47vyophcn"
path="res://.godot/imported/x.obj-550f5b6e3f6de89066dd96074e4a748b.mesh"

[deps]

files=["res://.godot/imported/x.obj-550f5b6e3f6de89066dd96074e4a748b.mesh"]

source_file="res://x.obj"
dest_files=["res://.godot/imported/x.obj-550f5b6e3f6de89066dd96074e4a748b.mesh"]

[params]

generate_tangents=true
generate_lods=true
generate_shadow_mesh=true
generate_lightmap_uv2=false
generate_lightmap_uv2_texel_size=0.2
scale_mesh=Vector3(1, 1, 1)
offset_mesh=Vector3(0, 0, 0)
force_disable_mesh_compression=false
"""


def _package(tmp_path: Path) -> Path:
    for name in ("site_marks_090_075_020_c500_500.obj", "site_wires_c500_500.obj",
                 "site_wires_c501_499.obj"):
        (tmp_path / name).write_text("o x\n", encoding="utf-8")
        (tmp_path / (name + ".import")).write_text(SIDECAR, encoding="utf-8")
    return tmp_path


def test_the_paint_is_asked_for_a_lightmap_uv_and_a_wire_is_not(tmp_path):
    pkg = _package(tmp_path)
    out = light_bake.mark_imports(pkg)
    paint = (pkg / "site_marks_090_075_020_c500_500.obj.import").read_text(encoding="utf-8")
    assert "generate_lightmap_uv2=true" in paint
    for name in ("site_wires_c500_500.obj", "site_wires_c501_499.obj"):
        assert (pkg / (name + ".import")).read_text(encoding="utf-8") == SIDECAR
    assert out["baked"] == ["site_marks_090_075_020_c500_500.obj"]
    assert sorted(out["unlit"]) == ["site_wires_c500_500.obj", "site_wires_c501_499.obj"]


def test_the_prefix_is_the_name_lot_writes():
    """Lot 0.119.0's `site_poles.wire_meshes` names each cell's mesh
    `site_wires_c<x>_<y>`; this is the prefix that keeps them unlit."""
    assert light_bake.UNLIT_PREFIXES == ("site_wires_",)
