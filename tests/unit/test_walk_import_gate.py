"""A walk whose preview did not finish importing fails, and says why (0.257.0).

The walker fell through the floor of the first building they walked into: the walk's headless import had been killed
at 600 s with 96 of 758 imports unwritten, every building's shell among them, and the walk finished ``ok`` (the
factory's docs/findings/walk_2026-10-26_panel/, L1). The import is now judged by what it left. FAILS ON 0.256.0.
"""
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.preview import import_gate  # noqa: E402


def _project(tmp_path, written):
    """A project with two imports; ``written`` of their cache files exist."""
    p = tmp_path / "preview"
    (p / ".godot" / "imported").mkdir(parents=True)
    for i, name in enumerate(("shell.glb", "brick.png")):
        dest = ".godot/imported/%s-abc.scn" % name
        (p / (name + ".import")).write_text('[remap]\nimporter="x"\npath="res://%s"\n' % dest, encoding="utf-8")
        if i < written:
            (p / dest).write_text("x", encoding="utf-8")
    (p / "skipped.txt.import").write_text("[remap]\nvalid=false\n", encoding="utf-8")
    return p


def _ok(argv, **kw):
    return SimpleNamespace(returncode=0)


def test_an_import_that_wrote_everything_is_ok(tmp_path):
    ok, said = import_gate.import_preview("godot", _project(tmp_path, 2), run=_ok)
    assert ok and "every import written" in said


def test_unwritten_imports_fail_and_are_named(tmp_path):
    p = _project(tmp_path, 1)
    assert import_gate.missing_imports(p) == ["brick.png.import"]
    ok, said = import_gate.import_preview("godot", p, run=_ok)
    assert not ok and "1 of the preview's imports were not written" in said and "brick.png.import" in said


def test_a_timeout_is_a_failure_and_the_light_bakes_bound_is_used(tmp_path):
    from packages.exporting.light_bake import IMPORT_TIMEOUT_S
    seen = {}

    def slow(argv, **kw):
        seen["timeout"] = kw["timeout"]
        raise subprocess.TimeoutExpired(argv, kw["timeout"])
    ok, said = import_gate.import_preview("godot", _project(tmp_path, 1), run=slow)
    assert not ok and "did not finish in %d s" % IMPORT_TIMEOUT_S in said
    assert seen["timeout"] == IMPORT_TIMEOUT_S == 1800


def test_a_failing_exit_is_a_failure_even_with_everything_written(tmp_path):
    ok, said = import_gate.import_preview("godot", _project(tmp_path, 2),
                                          run=lambda argv, **kw: SimpleNamespace(returncode=3))
    assert not ok and "exited 3" in said


def test_the_walk_blocks_on_a_failed_import(tmp_path, monkeypatch):
    """`cmd_walk` stops with EXIT_BLOCKED and a BLOCKED line, before the self-check, when the gate says no."""
    from apps.cli import commands
    src = (ROOT / "apps" / "cli" / "commands" / "__init__.py").read_text(encoding="utf-8")
    walk = src[src.index("def cmd_walk("):]
    walk = walk[:walk.index("\ndef ", 1)]
    assert "import_gate.import_preview(" in walk and "return EXIT_BLOCKED" in walk.split("import_gate.import_preview(")[1][:900]
    assert "headless import failed" not in walk                       # the warning that let it through is gone
    assert commands.EXIT_BLOCKED == 2
