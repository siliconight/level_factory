"""The import pass checks its own work (0.163.1).

COLD RUN 9214 IS WHY. Its export's first `--import` left sidecars on 140 of
the package's 975 importable files -- SkyMint's, which arrive with Lux's
runtime -- and on none of its 425 models. Nothing looked: the pass's exit code
and output were thrown away, `ensure_imported` took the `.godot` folder's
existence for an import, the occluder bake loaded a scene whose every module
was missing and reported `ok` with 0 modules, and the Empties' merge was the
first step to refuse. The same package imported 425 of 425 in seven fresh
reruns (`docs/cold_runs/cold_9214/import_reruns.txt` at the factory root).

A model is imported when its sidecar names the files Godot made of it and
those files are there. The shape below is copied from a real one: cold run
9214's `doorway_delco_1997_01_w100_mbrick_orange_enavy_o3e3b2d.glb.import`,
imported by Godot 4.7 -- `[deps]` carries `dest_files`, one `.scn` under
`.godot/imported/`.
"""
import subprocess
from pathlib import Path

import pytest

from packages.exporting.occluders import (CACHE_DIR, OccluderError,
                                          ensure_imported)


def unimported_models(pkg):
    """Imported here, not at the top, so on 0.163.0 -- which has no such
    function -- each test fails on its own behaviour rather than the file
    failing to collect."""
    from packages.exporting.occluders import unimported_models as f
    return f(pkg)

SIDECAR = (
    '[remap]\n\nimporter="scene"\nimporter_version=1\ntype="PackedScene"\n'
    'uid="uid://eigjrtlx25ng"\npath="res://.godot/imported/{name}-{h}.scn"\n\n'
    '[deps]\n\nsource_file="res://{rel}"\n'
    'dest_files=["res://.godot/imported/{name}-{h}.scn"]\n\n'
    '[params]\n\nnodes/root_type=""\n')


def _import_one(pkg: Path, rel: str, *, with_dest=True, dest_files=True):
    """What Godot leaves for one model it imported."""
    name = Path(rel).name
    h = "195c7f76d71e2b8419448441930805ae"
    text = SIDECAR.format(name=name, h=h, rel=rel)
    if not dest_files:
        text = "\n".join(ln for ln in text.splitlines()
                         if not ln.startswith("dest_files")) + "\n"
    (pkg / (rel + ".import")).write_text(text, encoding="utf-8")
    if with_dest:
        out = pkg / CACHE_DIR / "imported" / ("%s-%s.scn" % (name, h))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"scn")


def _package(tmp_path: Path, rels=("lot/a/art/wall.glb", "lot/b/site_base.glb")):
    pkg = tmp_path / "LF_x.portable-godot"
    for rel in rels:
        p = pkg / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"glTF")
    return pkg


# ------------------------------------------------------- what "imported" means

def test_a_model_is_imported_when_its_sidecar_and_its_scene_are_there(tmp_path):
    pkg = _package(tmp_path)
    assert unimported_models(pkg) == ["lot/a/art/wall.glb", "lot/b/site_base.glb"]
    _import_one(pkg, "lot/a/art/wall.glb")
    _import_one(pkg, "lot/b/site_base.glb")
    assert unimported_models(pkg) == []


def test_a_sidecar_without_its_imported_scene_is_not_an_import(tmp_path):
    """A shipped package keeps its sidecars and drops the cache; so does a
    second pass that started over and stopped short."""
    pkg = _package(tmp_path)
    _import_one(pkg, "lot/a/art/wall.glb")
    _import_one(pkg, "lot/b/site_base.glb", with_dest=False)
    assert unimported_models(pkg) == ["lot/b/site_base.glb"]


def test_a_sidecar_that_names_no_files_fails_rather_than_passes(tmp_path):
    """An unrecognised shape is not evidence of an import."""
    pkg = _package(tmp_path)
    _import_one(pkg, "lot/a/art/wall.glb")
    _import_one(pkg, "lot/b/site_base.glb", dest_files=False)
    assert unimported_models(pkg) == ["lot/b/site_base.glb"]


def test_a_folder_godot_ignores_is_ignored(tmp_path):
    pkg = _package(tmp_path, rels=("lot/a/art/wall.glb", "docs/ref/model.glb"))
    (pkg / "docs" / ".gdignore").write_text("", encoding="utf-8")
    _import_one(pkg, "lot/a/art/wall.glb")
    assert unimported_models(pkg) == []


# ------------------------------------------------------ the export's own pass

class _Godot:
    """`subprocess.run` for `--import`: the first `short` passes leave the
    cache and nothing in it, cold run 9214's first pass; the rest import
    every model."""

    def __init__(self, short):
        self.short = short
        self.calls = 0

    def __call__(self, argv, **kw):
        assert "--import" in argv, argv
        self.calls += 1
        pkg = Path(argv[argv.index("--path") + 1])
        (pkg / CACHE_DIR).mkdir(parents=True, exist_ok=True)
        if self.calls > self.short:
            for p in pkg.rglob("*.glb"):
                _import_one(pkg, p.relative_to(pkg).as_posix())
        return subprocess.CompletedProcess(argv, 0, b"pass %d\n" % self.calls, b"")


def test_a_pass_that_imports_no_model_is_run_again(tmp_path, monkeypatch):
    """FAILS ON 0.163.0: one pass, nothing checked, 425 models unimported."""
    from packages.exporting import export
    pkg = _package(tmp_path)
    godot = _Godot(short=1)
    monkeypatch.setattr(subprocess, "run", godot)
    export._write_import_sidecars(pkg, "godot.exe")
    assert godot.calls == 2
    assert unimported_models(pkg) == []
    log = (pkg.parent / (pkg.name + ".import.log")).read_text(encoding="utf-8")
    assert "import pass 1" in log and "import pass 2" in log, log


def test_an_import_that_never_completes_stops_the_export(tmp_path, monkeypatch):
    """FAILS ON 0.163.0, which returned and let the occluder bake measure 0."""
    from packages.exporting import export
    pkg = _package(tmp_path)
    godot = _Godot(short=99)
    monkeypatch.setattr(subprocess, "run", godot)
    with pytest.raises(export.ExportImportError) as exc:
        export._write_import_sidecars(pkg, "godot.exe")
    assert godot.calls == export.IMPORT_PASSES
    assert "2 of 2 model(s)" in str(exc.value)


def test_no_godot_is_still_a_setup_problem_not_an_export_failure(tmp_path):
    from packages.exporting import export
    pkg = _package(tmp_path)
    assert export._write_import_sidecars(pkg, None) == 0


# ------------------------------------------- the bake's and the merge's guard

def test_a_cache_folder_alone_is_not_an_imported_project(tmp_path, monkeypatch):
    """FAILS ON 0.163.0: `ensure_imported` returned False on `is_dir()`."""
    pkg = _package(tmp_path)
    (pkg / CACHE_DIR).mkdir()
    godot = _Godot(short=0)
    monkeypatch.setattr(subprocess, "run", godot)
    assert ensure_imported(pkg, "godot.exe") is True
    assert godot.calls == 1
    assert unimported_models(pkg) == []
    assert ensure_imported(pkg, "godot.exe") is False
    assert godot.calls == 1


def test_ensure_imported_refuses_an_import_that_left_models_behind(tmp_path, monkeypatch):
    pkg = _package(tmp_path)
    monkeypatch.setattr(subprocess, "run", _Godot(short=99))
    with pytest.raises(OccluderError) as exc:
        ensure_imported(pkg, "godot.exe")
    assert "2 model(s)" in str(exc.value)
