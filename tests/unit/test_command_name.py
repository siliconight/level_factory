"""A hint names the command the person typed (0.170.0, roadmap 202).

`level-factory` is the console script an installed copy has. Somebody who unpacked the factory
runs its launcher, `.\\factory` or `sh factory.sh`, which says so in LEVEL_FACTORY_COMMAND; the
first install test printed "then run: level-factory -C ... doctor" to a person who had no such
command.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from apps.cli import commands
from packages.adapters.registry import AdapterRegistry
from packages.tools import discovery, doctor, interpreter

TYPED = ".\\factory"


def test_unset_it_is_the_console_script(monkeypatch):
    monkeypatch.delenv(discovery.COMMAND_ENV, raising=False)
    assert discovery.command_name() == "level-factory"
    monkeypatch.setenv(discovery.COMMAND_ENV, "   ")
    assert discovery.command_name() == "level-factory"


def test_set_it_is_what_the_launcher_says(monkeypatch):
    monkeypatch.setenv(discovery.COMMAND_ENV, " sh factory.sh ")
    assert discovery.command_name() == "sh factory.sh"


def test_init_names_it_in_its_next_step(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(discovery.COMMAND_ENV, TYPED)
    root = tmp_path / "factory"
    root.mkdir()
    (root / "factory.manifest.json").write_text(json.dumps({"tools": {}}), encoding="utf-8")
    monkeypatch.setattr(discovery, "factory_root", lambda: root)
    monkeypatch.setattr(discovery, "blender_installs", lambda: [])
    monkeypatch.setattr(discovery.shutil, "which", lambda _n: None)
    for var in ("BLENDER", "GODOT", "LOT_GODOT", "DC_GODOT"):
        monkeypatch.delenv(var, raising=False)
    args = SimpleNamespace(path=str(tmp_path / "ws"), name="", project_id="", blender="",
                           godot="", python="")
    commands.cmd_init(args)
    out = capsys.readouterr().out
    assert f"then run: {TYPED} -C" in out and f"run `{TYPED} setup`" in out
    assert "level-factory" not in out


def test_the_doctor_names_it_for_setup_venv(monkeypatch):
    monkeypatch.setenv(discovery.COMMAND_ENV, TYPED)
    monkeypatch.setattr(interpreter, "TOOL_IMPORTS", interpreter.TOOL_IMPORTS + (
        ("no_such_module_for_this_test", "no-such-dist", "nobody"),))
    report = doctor.run_doctor({}, {}, registry=AdapterRegistry({}))
    check = [c for c in report.checks if c.name == "tools_python"][0]
    assert f"`{TYPED} setup --venv`" in check.detail


def test_make_names_it_for_the_walk(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(discovery.COMMAND_ENV, TYPED)
    root = tmp_path / "ws"
    (root / ".level_factory" / "jobs" / "m.lot_assemble.candidate.seed_1").mkdir(parents=True)
    w = root / ".level_factory" / "jobs" / "m.walktest_navqa.candidate.seed_1" / "1" / "out"
    w.mkdir(parents=True)
    (w / "x.walktest.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (root / ".level_factory" / "validation").mkdir()
    (root / ".level_factory" / "validation" / "m.json").write_text(
        json.dumps({"issues": []}), encoding="utf-8")
    (root / "factory.project.json").write_text("{}", encoding="utf-8")
    batch = tmp_path / "batch.json"
    batch.write_text(json.dumps({"missions": ["m"]}), encoding="utf-8")

    def legs(argv):
        if "run" in argv:
            return 0, "(blockers open: 0, total findings: 0)\n"
        if "export" in argv:
            return 0, "exported m [portable-godot] -> /x/LF_m\n"
        return 0, ""
    args = SimpleNamespace(chdir=str(root), batch_json=str(batch), mission="", seed=None,
                           no_bake_lights=False)
    assert commands.cmd_make(args, run_leg=legs) == commands.EXIT_OK
    assert f"walk it:   {TYPED} -C {root} walk m --play" in capsys.readouterr().out
