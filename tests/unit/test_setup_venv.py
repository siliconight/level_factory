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
    assert fake.calls[1][5:7] == ["-c", str(tmp_path / ".venv" / interpreter.CONSTRAINTS)]
    assert sorted(fake.calls[1][7:]) == sorted(f"{d}=={v}" for d, v in interpreter.PINNED.items())
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


# --------------------------------------------------------------------------- #
# 0.178.1: an environment made from Blender's Python starts without an error
# --------------------------------------------------------------------------- #

def _blender_layout(tmp_path):
    """Blender's install as far as its sitecustomize reads it: the interpreter under
    <root>/5.1/python/bin and `blender.shared` three folders above it."""
    root = tmp_path / "blender"
    exe = root / "5.1" / "python" / "bin" / "python.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("stand-in\n", encoding="utf-8")
    (root / "blender.shared").mkdir()
    return root, exe


def test_an_environment_from_blenders_python_gets_its_own_sitecustomize(tmp_path):
    root, exe = _blender_layout(tmp_path)
    fake = _Fake()
    py, err = interpreter.make_venv(tmp_path / "factory", str(exe), run=fake)
    assert err == ""
    shim = tmp_path / "factory" / ".venv" / "Lib" / "site-packages" / "sitecustomize.py"
    if sys.platform.startswith("win"):
        text = shim.read_text(encoding="utf-8")
        assert repr(str(root / "blender.shared")) in text
        assert "os.add_dll_directory(SHARED)" in text
        compile(text, str(shim), "exec")                 # it is Python
    else:
        assert not shim.exists()                         # Linux keeps Blender's file
    # written before pip, which is still the second thing run
    assert fake.calls[1][1:4] == ["-m", "pip", "install"]


def test_an_environment_from_any_other_python_gets_none(tmp_path):
    interpreter.make_venv(tmp_path, "/base/python", run=_Fake())
    assert not (tmp_path / ".venv" / "Lib" / "site-packages" / "sitecustomize.py").exists()
    assert interpreter.blender_site_shim(tmp_path / ".venv", "/base/python") is None


def _blenders_python():
    import os
    exe = Path(os.environ.get("BLENDER") or r"C:\blender\blender.exe")
    found = sorted(exe.parent.glob("*/python/bin/python.exe")) if exe.parent.is_dir() else []
    return found[-1] if found else None


def test_blenders_real_python_starts_clean_in_its_environment(tmp_path):
    """Install test 4's twelve errors, on the real thing: an environment made from Blender's
    own Python (pip not run) starts clean with the shim, and -- the control that proves the
    instrument can see the difference -- prints Blender's error without it."""
    import pytest
    base = _blenders_python() if sys.platform.startswith("win") else None
    if base is None:
        pytest.skip("no Blender Python on this machine (BLENDER, or C:\\blender)")

    def run(argv, **kw):
        if argv[1:3] == ["-m", "venv"]:
            return subprocess.run(argv, **kw)
        return SimpleNamespace(returncode=0)         # no network here: pip is not run
    py, err = interpreter.make_venv(tmp_path, str(base), run=run)
    assert err == "", err
    ask = [py, "-c", "print('started')"]
    clean = subprocess.run(ask, capture_output=True, text=True, timeout=120)
    assert clean.returncode == 0 and clean.stdout.strip() == "started", clean.stderr
    assert "Error in sitecustomize" not in clean.stderr, clean.stderr
    (tmp_path / ".venv" / "Lib" / "site-packages" / "sitecustomize.py").unlink()
    control = subprocess.run(ask, capture_output=True, text=True, timeout=120)
    assert "Error in sitecustomize" in control.stderr, (
        "Blender's own sitecustomize no longer errors in an environment: the shim may be "
        "moot -- re-read Blender's file before keeping it", control.stderr)


# --------------------------------------------------------------------------- #
# 0.214.0: what the three pins bring is held too (the factory's roadmap 256)
# --------------------------------------------------------------------------- #

def test_the_constraints_file_holds_every_distribution_setup_may_install(tmp_path):
    fake = _Fake()
    interpreter.make_venv(tmp_path, "/base/python", run=fake)
    path = tmp_path / ".venv" / interpreter.CONSTRAINTS
    lines = path.read_text(encoding="utf-8").split()
    held = {**interpreter.PINNED, **interpreter.CONSTRAINED}
    # sorted by NAME, as the writer sorts: as strings, "jsonschema-specifications==..." would
    # sort before "jsonschema==..." ("-" is below "="), two spellings of one order
    assert lines == [f"{d}=={v}" for d, v in sorted(held.items())]
    assert len(lines) == 12 and not set(interpreter.PINNED) & set(interpreter.CONSTRAINED)
    # written before pip runs, which is still the second thing run, and pip is told where it is
    assert fake.calls[1][1:4] == ["-m", "pip", "install"] and fake.calls[1][5:7] == ["-c", str(path)]


def test_what_the_pins_bring_is_the_set_install_test_9_installed():
    brought = {"dataclasses-json", "deprecated", "jsonschema-specifications", "marshmallow",
               "mypy-extensions", "referencing", "rpds-py", "typing-inspect", "wrapt"}
    assert set(interpreter.CONSTRAINED) == brought
