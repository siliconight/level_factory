"""`init` fills `tools.local.json` from what the machine has, and `setup` records it
(0.167.0, roadmap 202).

`init` used to write every path blank and print "edit tools.local.json"; the cold driver
copied the previous run's file instead, and cold run 9194 stopped when that run's workspace
had been retired. These build a factory in a temporary directory -- a manifest, checkouts with
a VERSION, stand-in executables -- and hold discovery to it.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from apps.cli import commands
from packages.tools import discovery

KEYS = ("deli_counter", "lot", "laser_tag", "pixelcoat", "zoo", "patina", "lux", "dispatch")


def _exe(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("stand-in\n", encoding="utf-8")
    return str(path)


@pytest.fixture()
def factory(tmp_path):
    root = tmp_path / "factory"
    tools = {}
    for key in KEYS:
        folder = "lasertag" if key == "laser_tag" else key
        (root / folder).mkdir(parents=True)
        (root / folder / "VERSION").write_text("1.0.0", encoding="utf-8")
        tools[key] = {"version": "1.0.0", **({"path": folder} if folder != key else {})}
    (root / "factory.manifest.json").write_text(
        json.dumps({"schema": "gabagool.factory.manifest.v1", "tools": tools}), encoding="utf-8")
    return root


def _nothing(_name):
    return None


def test_repositories_are_the_checkouts_the_manifest_names(factory):
    found = discovery.discover(factory, env={}, which=_nothing, installs=[])
    repos = found.tools_local["repositories"]
    assert set(repos) == set(KEYS)
    assert repos["laser_tag"] == (factory / "lasertag").as_posix()   # the entry's `path`
    assert repos["lot"] == (factory / "lot").as_posix()              # else its key
    assert not [k for k in KEYS if k in found.gaps]


def test_a_named_checkout_without_a_version_is_a_gap_not_a_path(factory):
    (factory / "zoo" / "VERSION").unlink()
    found = discovery.discover(factory, env={}, which=_nothing, installs=[])
    assert found.tools_local["repositories"]["zoo"] == ""
    assert "zoo" in found.missing and "VERSION" in found.gaps["zoo"]


def test_executables_come_from_the_flag_then_the_record_then_env_then_path(factory, tmp_path):
    flag = _exe(tmp_path / "flag" / "blender")
    rec = _exe(tmp_path / "rec" / "blender")
    env = _exe(tmp_path / "env" / "blender")
    on_path = _exe(tmp_path / "path" / "blender")
    which = {"blender": on_path}.get

    def got(**kw):
        return discovery.discover(factory, which=which, installs=[], **kw)

    discovery.write_local(factory, {"blender_executable": rec})
    assert got(blender=flag, env={"BLENDER": env}).tools_local["blender_executable"] == flag
    found = got(env={"BLENDER": env})
    assert found.tools_local["blender_executable"] == rec
    assert found.sources["blender_executable"] == discovery.LOCAL_FILE
    (factory / discovery.LOCAL_FILE).unlink()
    assert got(env={"BLENDER": env}).tools_local["blender_executable"] == env
    found = got(env={})
    assert found.tools_local["blender_executable"] == on_path
    assert found.sources["blender_executable"] == "PATH (blender)"


def test_blender_falls_back_to_an_install_and_godot_does_not(factory, tmp_path):
    installed = _exe(tmp_path / "Blender Foundation" / "Blender 5.1" / "blender.exe")
    found = discovery.discover(factory, env={}, which=_nothing, installs=[Path(installed)])
    assert found.tools_local["blender_executable"] == installed
    assert found.sources["blender_executable"] == "installed"
    assert found.tools_local["godot_executable"] == ""
    assert "--godot" in found.gaps["godot_executable"]


def test_godot_is_read_from_the_walk_tests_variables(factory, tmp_path):
    godot = _exe(tmp_path / "godot" / "Godot_v4.7-stable_win64_console.exe")
    found = discovery.discover(factory, env={"LOT_GODOT": godot}, which=_nothing, installs=[])
    assert found.tools_local["godot_executable"] == godot
    assert found.sources["godot_executable"] == "$LOT_GODOT"


def test_a_recorded_path_that_is_not_a_file_is_named(factory, tmp_path):
    discovery.write_local(factory, {"godot_executable": str(tmp_path / "gone" / "godot.exe")})
    found = discovery.discover(factory, env={}, which=_nothing, installs=[])
    assert "godot_executable" in found.missing
    assert "not a file" in found.gaps["godot_executable"]


def test_a_blank_python_is_not_a_gap(factory):
    found = discovery.discover(factory, env={}, which=_nothing, installs=[])
    assert found.tools_local["python_executable"] == ""
    assert "python_executable" not in found.gaps


def test_a_record_in_another_shape_refuses_rather_than_reading_empty(factory):
    (factory / discovery.LOCAL_FILE).write_text(json.dumps({"blender": "x"}), encoding="utf-8")
    with pytest.raises(ValueError, match="factory_local"):
        discovery.discover(factory, env={}, which=_nothing, installs=[])


def test_no_manifest_leaves_every_repository_blank_and_says_why(tmp_path):
    found = discovery.discover(tmp_path, env={}, which=_nothing, installs=[])
    assert all(v == "" for v in found.tools_local["repositories"].values())
    assert all("factory.manifest.json" in found.gaps[k] for k in KEYS)


def test_the_factory_is_searched_for_not_counted(tmp_path):
    # the nearest manifest above, at any depth -- a worktree sits deeper than a checkout
    (tmp_path / "factory.manifest.json").write_text("{}", encoding="utf-8")
    deep = tmp_path / "scratchpad" / "branch" / "level_factory" / "packages" / "tools"
    deep.mkdir(parents=True)
    assert discovery.factory_root(deep / "discovery.py") == tmp_path
    assert discovery.factory_root(tmp_path.parent / "elsewhere" / "x.py") is None


def test_outside_any_factory_every_repository_says_so(monkeypatch):
    monkeypatch.setattr(discovery, "factory_root", lambda start=None: None)
    found = discovery.discover(env={}, which=_nothing, installs=[])
    assert all(v == "" for v in found.tools_local["repositories"].values())
    assert all("at or above" in found.gaps[k] for k in KEYS)


def test_installs_are_newest_first(tmp_path, monkeypatch):
    for v in ("4.2", "5.1", "4.5"):
        _exe(tmp_path / "Blender Foundation" / f"Blender {v}" / "blender.exe")
    monkeypatch.setattr(discovery.sys, "platform", "win32")
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    monkeypatch.delenv("ProgramW6432", raising=False)
    monkeypatch.delenv("ProgramFiles(x86)", raising=False)
    got = [p.parent.name for p in discovery.blender_installs()]
    assert got == ["Blender 5.1", "Blender 4.5", "Blender 4.2"]


def test_init_writes_what_was_found(factory, tmp_path, monkeypatch, capsys):
    godot = _exe(tmp_path / "godot" / "godot.exe")
    monkeypatch.setattr(discovery, "factory_root", lambda: factory)
    monkeypatch.setattr(discovery, "blender_installs", lambda: [])
    monkeypatch.setattr(discovery.shutil, "which", _nothing)
    for var in ("BLENDER", "GODOT", "LOT_GODOT", "DC_GODOT"):
        monkeypatch.delenv(var, raising=False)
    ws = tmp_path / "ws"
    args = SimpleNamespace(path=str(ws), name="", project_id="", blender="", godot=godot,
                           python="")
    assert commands.cmd_init(args) == commands.EXIT_OK
    written = json.loads((ws / "tools.local.json").read_text(encoding="utf-8"))
    assert written["godot_executable"] == godot
    assert written["repositories"]["lot"] == (factory / "lot").as_posix()
    out = capsys.readouterr().out
    assert "blender_executable" in out and "NOT FOUND" in out
    assert "edit tools.local.json" not in out


def test_setup_records_what_it_found_and_init_reads_it(factory, tmp_path, monkeypatch, capsys):
    godot = _exe(tmp_path / "godot" / "godot.exe")
    blender = _exe(tmp_path / "blender" / "blender.exe")
    monkeypatch.setattr(discovery, "factory_root", lambda: factory)
    monkeypatch.setattr(discovery, "blender_installs", lambda: [])
    monkeypatch.setattr(discovery.shutil, "which", _nothing)
    for var in ("BLENDER", "GODOT", "LOT_GODOT", "DC_GODOT"):
        monkeypatch.delenv(var, raising=False)
    args = SimpleNamespace(factory="", blender=blender, godot=godot, python="")
    commands.cmd_setup(args)   # the stand-ins do not answer --version; the record is the point
    rec = json.loads((factory / discovery.LOCAL_FILE).read_text(encoding="utf-8"))
    assert rec["schema"] == discovery.LOCAL_SCHEMA
    assert rec["blender_executable"] == blender and rec["godot_executable"] == godot
    capsys.readouterr()
    ws = tmp_path / "ws2"
    args = SimpleNamespace(path=str(ws), name="", project_id="", blender="", godot="",
                           python="")
    assert commands.cmd_init(args) == commands.EXIT_OK
    written = json.loads((ws / "tools.local.json").read_text(encoding="utf-8"))
    assert written["blender_executable"] == blender
    assert written["godot_executable"] == godot
    assert discovery.LOCAL_FILE in capsys.readouterr().out
