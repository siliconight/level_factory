"""Every model is imported once, with its final settings, in three passes over three sets (0.189.0).

The export's sidecar step imported the package twice -- a first pass with Godot's defaults, then
everything again with the sidecars rewritten and the cache wiped: 86 s of a 238 s re-export of
cold run 9254. A model's first import carries its final settings now, and a first import has two
hazards, both measured (the factory's docs/findings/grader_speed/sidecar_once_probe.py): a model
imported before the shared textures it names embeds a copy of each (1,463 surfaces in 461
models), so the textures go first; and a worldskin base skins its slabs from a sibling floor module
it `load()`s, which a first import cannot promise is there (105 slab meshes greybox), so the bases
go last. A model imported twice, its textures already imported, is the race 0.182.0 backstops, so
a model whose light baking is its own is held with the bases and imported from a whole sidecar.
"""
import json
import re
import struct
import subprocess
from pathlib import Path

import pytest

from packages.exporting.occluders import CACHE_DIR

H = "195c7f76d71e2b8419448441930805ae"
TEX_SIDECAR = ('[remap]\n\nimporter="texture"\ntype="CompressedTexture2D"\n\n[params]\n\n'
               'compress/mode=0\ncompress/normal_map=0\nmipmaps/generate=false\nroughness/mode=0\n'
               'roughness/src_normal=""\nprocess/fix_alpha_border=true\ndetect_3d/compress_to=1\n')
WORLDSKIN = '[importer_defaults]\n\nscene={\n"import_script/path": "res://zoo_worldskin.gd"\n}\n'


def _glb(path, *, uv2=False, tex=None, normal=False):
    """A GLB whose JSON chunk says what `glb_has_uv2` and `_normal_map_shared_textures` read."""
    doc = {"meshes": [{"primitives": [{"attributes": dict({"POSITION": 0},
                                                          **({"TEXCOORD_1": 1} if uv2 else {}))}]}]}
    if tex:
        use = {"normalTexture": {"index": 0}} if normal else {
            "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}
        doc.update({"images": [{"uri": tex}], "textures": [{"source": 0}], "materials": [use]})
    body = json.dumps(doc).encode("utf-8")
    body += b" " * (-len(body) % 4)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"glTF" + struct.pack("<II", 2, 20 + len(body))
                     + struct.pack("<I", len(body)) + b"JSON" + body)


def _scene_defaults(project):
    text = project.read_text(encoding="utf-8") if project.is_file() else ""
    if "[importer_defaults]" not in text or "scene={" not in text:
        return {}
    block = text[text.index("scene={", text.index("[importer_defaults]")):]
    block = block[:block.index("}")]
    return {k: v for k, v in re.findall(r'"([^"]+)": ("[^"]*"|[0-9]+)', block)}


class _Godot:
    """`subprocess.run` for `--import`, behaving as Godot does where it matters here: a model with
    no sidecar imports with `project.godot`'s `[importer_defaults] scene` over the importer's own
    (light baking 1, images extracted, texture map mode 1, as a new import); a sidecar lacking
    `gltf/texture_map_mode` is an old one and takes 0; a model whose sidecar changed since its
    last import imports again. It records each model's imports with the settings they ran with,
    and which models each pass could see."""

    def __init__(self, models_never=False):
        self.imports, self.visible, self.calls = {}, [], 0
        self._last = {}
        self.models_never = models_never

    def __call__(self, argv, **kw):
        assert "--import" in argv, argv
        self.calls += 1
        pkg = Path(argv[argv.index("--path") + 1])
        (pkg / CACHE_DIR).mkdir(parents=True, exist_ok=True)
        defaults = _scene_defaults(pkg / "project.godot")
        for png in pkg.rglob("*.png"):
            side = Path(str(png) + ".import")
            if not side.exists():
                side.write_text(TEX_SIDECAR, encoding="utf-8")
        seen = set()
        for p in sorted(pkg.rglob("*.glb")):
            rel = p.relative_to(pkg).as_posix()
            seen.add(rel)
            if self.models_never:
                continue
            side = pkg / (rel + ".import")
            if not side.exists():
                params = {"meshes/light_baking": "1", "gltf/embedded_image_handling": "1",
                          "gltf/texture_map_mode": "1"}
                params.update(defaults)
                side.write_text(
                    '[remap]\n\nimporter="scene"\ndest_files=["res://.godot/imported/%s-%s.scn"]\n\n'
                    "[params]\n\n%s\n" % (p.name, H, "\n".join("%s=%s" % kv for kv in params.items())),
                    encoding="utf-8")
            text = side.read_text(encoding="utf-8")
            if "gltf/texture_map_mode=" not in text:
                text = text.rstrip("\n") + "\ngltf/texture_map_mode=0\n"
            if 'dest_files=' not in text:
                text = text.replace('importer="scene"\n', 'importer="scene"\n'
                                    'dest_files=["res://.godot/imported/%s-%s.scn"]\n' % (p.name, H), 1)
            side.write_text(text, encoding="utf-8")
            if self._last.get(rel) != text:
                got = dict(re.findall(r"^([a-z_/0-9]+)=(.*)$", text, re.M))
                self.imports.setdefault(rel, []).append(
                    (self.calls, got.get("meshes/light_baking"), got.get("gltf/embedded_image_handling"),
                     got.get("gltf/texture_map_mode"), got.get("import_script/path")))
                self._last[rel] = text
            out = pkg / CACHE_DIR / "imported" / ("%s-%s.scn" % (p.name, H))
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"scn")
        self.visible.append(seen)
        return subprocess.CompletedProcess(argv, 0, b"", b"")


def _package(tmp_path):
    pkg = tmp_path / "LF_x.portable-godot"
    _glb(pkg / "lot" / "a" / "art" / "zoo" / "floor_x.glb", tex="_tex/smooth.png", normal=True)
    _glb(pkg / "lot" / "a" / "art" / "zoo" / "wall_x.glb", tex="_tex/plain.png")
    _glb(pkg / "lot" / "a" / "site_base.glb")
    _glb(pkg / "cover" / "prop_tree.glb", uv2=True)
    _glb(pkg / "cars" / "cruiser.glb")
    for t in ("smooth.png", "plain.png"):
        (pkg / "lot" / "a" / "art" / "zoo" / "_tex").mkdir(parents=True, exist_ok=True)
        (pkg / "lot" / "a" / "art" / "zoo" / "_tex" / t).write_bytes(b"png")
    (pkg / "project.godot").write_text("config_version=5\n\n" + WORLDSKIN, encoding="utf-8")
    return pkg


def _step(tmp_path, monkeypatch, bake=True, godot=None):
    from packages.exporting import export
    pkg = _package(tmp_path)
    godot = godot or _Godot()
    monkeypatch.setattr(subprocess, "run", godot)
    export._write_import_sidecars(pkg, "godot.exe", bake_spawned=["cars/cruiser.glb"] if bake else None)
    return pkg, godot


def test_no_model_is_seen_by_the_first_pass_and_the_late_ones_by_the_last_alone(tmp_path, monkeypatch):
    """FAILS ON 0.188.0, whose first pass imported every model with Godot's defaults."""
    _, godot = _step(tmp_path, monkeypatch)
    assert godot.calls == 3, godot.visible
    assert godot.visible[0] == set(), "the textures go first, every model held"
    assert godot.visible[1] == {"lot/a/art/zoo/floor_x.glb", "lot/a/art/zoo/wall_x.glb"}
    assert {"lot/a/site_base.glb", "cover/prop_tree.glb", "cars/cruiser.glb"} <= godot.visible[2]


def test_every_model_is_imported_once_with_its_final_settings(tmp_path, monkeypatch):
    """FAILS ON 0.188.0, which imported each model twice, the first time with Godot's defaults."""
    _, godot = _step(tmp_path, monkeypatch)
    want = {"lot/a/art/zoo/floor_x.glb": "2", "lot/a/art/zoo/wall_x.glb": "2",
            "lot/a/site_base.glb": "2", "cover/prop_tree.glb": "1", "cars/cruiser.glb": "3"}
    for rel, baking in want.items():
        runs = godot.imports[rel]
        assert len(runs) == 1, (rel, runs)
        _, light, embedded, map_mode, script = runs[0]
        assert (light, embedded, map_mode) == (baking, "3", "1"), (rel, runs[0])
        assert script == '"res://zoo_worldskin.gd"', (rel, runs[0])


def test_without_a_bake_every_model_keeps_the_importers_light_baking(tmp_path, monkeypatch):
    _, godot = _step(tmp_path, monkeypatch, bake=False)
    for rel, runs in godot.imports.items():
        assert len(runs) == 1 and runs[0][1:3] == ("1", "3"), (rel, runs)


def test_the_bakes_own_marking_then_finds_nothing_to_change(tmp_path, monkeypatch):
    """What the bake does next: its `mark_imports` writes no sidecar, so its import has nothing
    to import (0.187.0's contract, kept)."""
    from packages.exporting import light_bake
    pkg, _ = _step(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for p in pkg.rglob("*.glb.import")}
    light_bake.mark_imports(pkg, ["cars/cruiser.glb"])
    assert {p: p.read_bytes() for p in pkg.rglob("*.glb.import")} == before


def test_a_normal_map_is_pinned_as_one_though_the_models_were_held(tmp_path, monkeypatch):
    """The normal maps are read off the models' glTF (0.190.0), and so must be read before the
    models are held: the filtered set read while they were held found none, and 26 textures went
    lossless until the read-back after the last import (sidecar_once_probe, arms C and E)."""
    pkg, _ = _step(tmp_path, monkeypatch)
    tex = pkg / "lot" / "a" / "art" / "zoo" / "_tex"
    smooth = (tex / "smooth.png.import").read_text(encoding="utf-8")
    plain = (tex / "plain.png.import").read_text(encoding="utf-8")
    assert "compress/normal_map=1" in smooth
    assert 'roughness/src_normal="res://lot/a/art/zoo/_tex/smooth.png"' in smooth
    assert "compress/normal_map=0" in plain
    assert "compress/mode=2" in smooth and "compress/mode=2" in plain   # compressed everywhere


def test_project_godot_and_every_model_are_put_back(tmp_path, monkeypatch):
    pkg, _ = _step(tmp_path, monkeypatch)
    assert (pkg / "project.godot").read_text(encoding="utf-8") == "config_version=5\n\n" + WORLDSKIN
    assert not list(pkg.rglob("*.held"))
    assert len(list(pkg.rglob("*.glb"))) == 5


def test_a_failed_import_puts_back_every_model_and_the_project(tmp_path, monkeypatch):
    from packages.exporting import export
    with pytest.raises(export.ExportImportError):
        _step(tmp_path, monkeypatch, godot=_Godot(models_never=True))
    pkg = tmp_path / "LF_x.portable-godot"
    assert not list(pkg.rglob("*.held")), "a held model left behind is a model the package lost"
    assert len(list(pkg.rglob("*.glb"))) == 5
    assert (pkg / "project.godot").read_text(encoding="utf-8") == "config_version=5\n\n" + WORLDSKIN
