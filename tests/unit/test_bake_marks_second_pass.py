"""The light bake's marks go on before the export's second import pass (0.187.0).

The bake asks every model for a lightmap UV (`light_bake.mark_imports`) and used to import the
package again for it -- the third import of every model, 55.0 s of a 277.6 s re-export of cold run
9252 and the pass that lost the shared textures' pins. Written before the second pass, that import
finds nothing to do. Not before the FIRST pass: a model's first import cannot borrow a sibling's
material (cold run 9251's import log: 105 slab meshes greybox in pass one, none in pass two).
"""
import ast
import subprocess
from pathlib import Path

from packages.exporting.occluders import CACHE_DIR

SIDECAR = (
    '[remap]\n\nimporter="scene"\nimporter_version=1\ntype="PackedScene"\n'
    'uid="uid://eigjrtlx25ng"\npath="res://.godot/imported/{name}-{h}.scn"\n\n'
    '[deps]\n\nsource_file="res://{rel}"\n'
    'dest_files=["res://.godot/imported/{name}-{h}.scn"]\n\n'
    '[params]\n\nnodes/root_type=""\nmeshes/light_baking=1\n'
    'gltf/embedded_image_handling=1\n')
H = "195c7f76d71e2b8419448441930805ae"


class _Godot:
    """`subprocess.run` for `--import`. Each pass imports every model; a model with no sidecar
    gets one with Godot's defaults (light baking 1, images extracted), one that has a sidecar
    keeps it, as Godot does. Before each pass it records every model's `meshes/light_baking`."""

    def __init__(self):
        self.seen = []

    def __call__(self, argv, **kw):
        assert "--import" in argv, argv
        pkg = Path(argv[argv.index("--path") + 1])
        state = {}
        for p in sorted(pkg.rglob("*.glb")):
            rel = p.relative_to(pkg).as_posix()
            side = pkg / (rel + ".import")
            if side.exists():
                line = [ln for ln in side.read_text(encoding="utf-8").splitlines()
                        if ln.startswith("meshes/light_baking=")]
                state[rel] = int(line[0].split("=")[1])
            else:
                side.write_text(SIDECAR.format(name=p.name, h=H, rel=rel), encoding="utf-8")
                state[rel] = None
            out = pkg / CACHE_DIR / "imported" / ("%s-%s.scn" % (p.name, H))
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"scn")
        self.seen.append(state)
        return subprocess.CompletedProcess(argv, 0, b"", b"")


def _package(tmp_path, rels=("lot/a/art/zoo/wall.glb", "lot/a/site_base.glb", "cars/cruiser.glb")):
    pkg = tmp_path / "LF_x.portable-godot"
    for rel in rels:
        p = pkg / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"glTF")
    return pkg


def test_the_bakes_marks_are_on_every_model_when_the_second_pass_runs(tmp_path, monkeypatch):
    from packages.exporting import export
    pkg = _package(tmp_path)
    godot = _Godot()
    monkeypatch.setattr(subprocess, "run", godot)
    export._write_import_sidecars(pkg, "godot.exe", bake_spawned=["cars/cruiser.glb"])
    assert len(godot.seen) == 2, godot.seen
    first, second = godot.seen
    assert set(first.values()) == {None}, "the first pass is the models' first import"
    assert second == {"lot/a/art/zoo/wall.glb": 2, "lot/a/site_base.glb": 2,
                      "cars/cruiser.glb": 3}, second


def test_no_bake_no_marks(tmp_path, monkeypatch):
    from packages.exporting import export
    pkg = _package(tmp_path)
    godot = _Godot()
    monkeypatch.setattr(subprocess, "run", godot)
    export._write_import_sidecars(pkg, "godot.exe")
    assert len(godot.seen) == 2
    assert set(godot.seen[1].values()) == {1}, "a package not baked keeps Godot's default"


def test_the_bakes_own_marking_then_finds_nothing_to_change(tmp_path, monkeypatch):
    """What the bake does next: its `mark_imports` writes no sidecar, so its import has
    nothing to import."""
    from packages.exporting import export, light_bake
    pkg = _package(tmp_path)
    monkeypatch.setattr(subprocess, "run", _Godot())
    export._write_import_sidecars(pkg, "godot.exe", bake_spawned=["cars/cruiser.glb"])
    before = {p: p.read_bytes() for p in pkg.rglob("*.glb.import")}
    marks = light_bake.mark_imports(pkg, ["cars/cruiser.glb"])
    assert sorted(marks["baked"]) == ["lot/a/art/zoo/wall.glb", "lot/a/site_base.glb"]
    assert marks["spawned"] == ["cars/cruiser.glb"]
    assert {p: p.read_bytes() for p in pkg.rglob("*.glb.import")} == before


def test_the_export_passes_the_bakes_spawned_models_when_it_bakes():
    """The wiring, read off the source: `export_mission` hands the sidecar step the list the
    bake is handed, and only when it bakes. A keyword nobody passes is a check that cannot fire."""
    from packages.exporting import export
    tree = ast.parse(Path(export.__file__).read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "export_mission")
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
             and getattr(n.func, "id", None) == "_write_import_sidecars"]
    assert len(calls) == 1
    kw = {k.arg: ast.unparse(k.value) for k in calls[0].keywords}
    assert kw.get("bake_spawned") == (
        "responder_vehicle_scenes(themed_site_dir) if profile.bake_lights else None"), kw
