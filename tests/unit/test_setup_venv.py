"""`setup --venv` gives the tools a Python of their own (0.168.0, roadmap 202).

Blender's own Python carries numpy and lacks Pillow, pygltflib and jsonschema. `--venv` makes
`<factory>/.venv` from the interpreter running `setup`, keeping what it carries, and installs
`interpreter.PINNED` into it. The install itself needs the network, so these replace pip with
a stand-in; the environment is made for real once, to prove it keeps the base's packages.
"""
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from apps.cli import commands
from packages.tools import discovery, doctor, interpreter
from packages.adapters.registry import AdapterRegistry


class _Fake:
    """Stands in for `subprocess.run`: makes the environment's interpreter, records each call."""

    def __init__(self, venv_exit=0, pip_exit=0):
        self.calls = []
        self.venv_exit, self.pip_exit = venv_exit, pip_exit

    def __call__(self, argv, **kw):
        self.calls.append(list(argv))
        if argv[1:3] == ["-m", "venv"]:
            if self.venv_exit == 0:
                py = Path(argv[-1], *(("Scripts", "python.exe") if sys.platform.startswith("win")
                                      else ("bin", "python")))
                py.parent.mkdir(parents=True, exist_ok=True)
                py.write_text("stand-in\n", encoding="utf-8")
            return SimpleNamespace(returncode=self.venv_exit, stdout="", stderr="no venv here")
        return SimpleNamespace(returncode=self.pip_exit, stdout="", stderr="")


def test_the_environment_is_made_from_the_base_and_given_the_pins(tmp_path):
    fake = _Fake()
    py, err = interpreter.make_venv(tmp_path, "/base/python", run=fake)
    assert err == ""
    assert fake.calls[0] == ["/base/python", "-m", "venv", "--system-site-packages",
                             str(tmp_path / ".venv")]
    assert fake.calls[1][0] == py and fake.calls[1][1:4] == ["-m", "pip", "install"]
    assert sorted(fake.calls[1][5:]) == sorted(f"{d}=={v}" for d, v in interpreter.PINNED.items())
    assert Path(py).is_file() and Path(py).is_relative_to(tmp_path / ".venv")


def test_the_pins_are_what_the_doctor_asks_for():
    # every distribution the doctor would tell somebody to install is one setup installs,
    # except numpy, which the base must carry (Blender's does)
    asked = {d for _m, d, _w in interpreter.TOOL_IMPORTS} - {"numpy"}
    assert asked == set(interpreter.PINNED)


def test_a_venv_that_fails_says_so_and_installs_nothing(tmp_path):
    fake = _Fake(venv_exit=1)
    py, err = interpreter.make_venv(tmp_path, "/base/python", run=fake)
    assert py == "" and "exited 1" in err and "no venv here" in err
    assert len(fake.calls) == 1


def test_an_install_that_fails_says_so(tmp_path):
    py, err = interpreter.make_venv(tmp_path, "/base/python", run=_Fake(pip_exit=2))
    assert py == "" and "pip install" in err and "exited 2" in err


def test_a_real_environment_keeps_what_its_base_carries(tmp_path):
    def run(argv, **kw):
        if argv[1:3] == ["-m", "venv"]:
            return subprocess.run(argv, **kw)
        return SimpleNamespace(returncode=0)        # no network here: pip is not run
    py, err = interpreter.make_venv(tmp_path, sys.executable, run=run)
    assert err == "", err
    # json is the standard library; what matters is that the base's own site-packages are
    # visible, so ask for the location of one the suite itself runs on
    seen = subprocess.run([py, "-c", "import pytest, sys; print(sys.prefix); "
                                     "print(sys.base_prefix)"],
                          capture_output=True, text=True, timeout=60)
    assert seen.returncode == 0, seen.stderr
    prefix, base = seen.stdout.split("\n")[:2]
    assert Path(prefix).resolve() == (tmp_path / ".venv").resolve()
    assert Path(base).resolve() == Path(sys.base_prefix).resolve()


def _factory(tmp_path):
    root = tmp_path / "factory"
    root.mkdir()
    (root / "factory.manifest.json").write_text(json.dumps({"tools": {}}), encoding="utf-8")
    return root


def test_setup_records_the_environments_interpreter(tmp_path, monkeypatch, capsys):
    root = _factory(tmp_path)
    made = tmp_path / "made" / "python.exe"
    made.parent.mkdir()
    made.write_text("stand-in\n", encoding="utf-8")
    monkeypatch.setattr(interpreter, "make_venv", lambda r, base: (str(made), ""))
    args = SimpleNamespace(factory=str(root), blender="", godot="", python="", venv=True)
    commands.cmd_setup(args)
    rec = json.loads((root / discovery.LOCAL_FILE).read_text(encoding="utf-8"))
    assert rec["python_executable"] == str(made)
    assert "setup --venv" in capsys.readouterr().out


def test_setup_refuses_venv_and_python_together(tmp_path, capsys):
    args = SimpleNamespace(factory=str(_factory(tmp_path)), blender="", godot="",
                           python="/x/python", venv=True)
    assert commands.cmd_setup(args) == commands.EXIT_CONFIG
    assert "not both" in capsys.readouterr().err


def test_a_failed_environment_records_nothing(tmp_path, monkeypatch):
    root = _factory(tmp_path)
    monkeypatch.setattr(interpreter, "make_venv", lambda r, base: ("", "pip install exited 1"))
    args = SimpleNamespace(factory=str(root), blender="", godot="", python="", venv=True)
    assert commands.cmd_setup(args) == commands.EXIT_CONFIG
    assert not (root / discovery.LOCAL_FILE).exists()


def test_the_doctor_points_at_setup_venv(monkeypatch):
    monkeypatch.setattr(interpreter, "TOOL_IMPORTS", interpreter.TOOL_IMPORTS + (
        ("no_such_module_for_this_test", "no-such-dist", "nobody"),))
    report = doctor.run_doctor({}, {}, registry=AdapterRegistry({}))
    check = [c for c in report.checks if c.name == "tools_python"][0]
    assert "setup --venv" in check.detail
