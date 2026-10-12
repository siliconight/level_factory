"""The bake's editor stops drawing for the bake; its work copy is copied in parallel and removed
in the background (0.193.0).

The bake's progress bar pumps the editor's main loop, and every pump drew the whole level again:
stopped as Bake is pressed, cold run 9258's level baked in 31.4 and 31.5 s against about 35.8,
byte for byte the same files; stopped from the start it baked 17.5 % darker (the factory's
docs/findings/grader_speed/bake_phases_probe.py, --no-viewport-at-bake and --no-viewport). The
work copy took 4.7 to 5.3 s to copy file after file and 2.1 to 2.8 s to remove.
"""
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.exporting import light_bake as LB  # noqa: E402


def _src():
    return LB.PLUGIN_SCRIPT.read_text(encoding="utf-8")


def _code(src):
    return "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))


def test_drawing_stops_as_bake_is_pressed_and_not_before():
    code = _code(_src())
    assert code.count("_stop_drawing()") == 2, "defined once, called once"
    call = code.index("\t\t\t_stop_drawing()")
    assert code.index("_lay_room_fill(") < call < code.index("b.pressed.emit()")
    enter = code[code.index("func _enter_tree("):]
    enter = enter[:enter.index("\nfunc ", 1)]
    assert "_stop_drawing" not in enter and "render_target_update_mode" not in enter, \
        "stopped before the level was drawn, the bake came out 17.5 % darker"


def test_the_stop_is_the_viewports_render_target():
    code = _code(_src())
    body = code[code.index("func _stop_drawing("):]
    assert "EditorInterface.get_editor_viewport_3d(i)" in body
    assert "render_target_update_mode = SubViewport.UPDATE_DISABLED" in body


def _tree(root):
    (root / "a" / "b").mkdir(parents=True)
    (root / ".godot" / "imported").mkdir(parents=True)
    (root / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    (root / "a" / "x.tscn").write_text("[gd_scene]\n", encoding="utf-8")
    (root / "a" / "b" / "y.bin").write_bytes(bytes(range(256)) * 40)
    (root / ".godot" / "imported" / "z.ctex").write_bytes(b"\x00\x01" * 999)
    (root / "empty_dir").mkdir()
    return root


def _listing(root):
    out = {}
    for r, ds, fs in os.walk(root):
        rel = os.path.relpath(r, root)
        out[("d", rel)] = None
        for f in fs:
            p = os.path.join(r, f)
            out[("f", os.path.join(rel, f))] = (open(p, "rb").read(), int(os.stat(p).st_mtime))
    return out


def test_the_parallel_copy_is_copytree(tmp_path):
    src = _tree(tmp_path / "src")
    shutil.copytree(src, tmp_path / "by_copytree")
    n = LB._copy_project(src, tmp_path / "by_pool")
    assert n == 4
    assert _listing(tmp_path / "by_pool") == _listing(tmp_path / "by_copytree")


def test_a_file_that_fails_to_copy_raises(tmp_path, monkeypatch):
    src = _tree(tmp_path / "src")
    real = shutil.copy2

    def failing(a, b):
        if str(a).endswith("y.bin"):
            raise OSError("no space")
        return real(a, b)
    monkeypatch.setattr(LB.shutil, "copy2", failing)
    try:
        LB._copy_project(src, tmp_path / "dst")
    except OSError as exc:
        assert "no space" in str(exc)
    else:
        raise AssertionError("a failed copy went unreported")


def test_the_work_copy_is_gone_at_once_and_removed_behind(tmp_path):
    work = _tree(tmp_path / "LF_t.portable-godot.lightbake")
    t = LB._remove_later(work)
    assert not work.exists()
    assert t is not None
    t.join(30)
    assert not t.is_alive()
    assert not (tmp_path / "LF_t.portable-godot.lightbake.old").exists()


def test_an_earlier_copy_left_aside_is_removed_first(tmp_path):
    old = _tree(tmp_path / "LF_t.portable-godot.lightbake.old")
    (old / "stale.txt").write_text("from before", encoding="utf-8")
    work = _tree(tmp_path / "LF_t.portable-godot.lightbake")
    t = LB._remove_later(work)
    t.join(30)
    assert not old.exists() and not work.exists()


def test_a_rename_that_fails_removes_it_here(tmp_path, monkeypatch):
    work = _tree(tmp_path / "LF_t.portable-godot.lightbake")

    def no_rename(self, target):
        raise OSError("in use")
    monkeypatch.setattr(LB.Path, "rename", no_rename)
    assert LB._remove_later(work) is None
    assert not work.exists()


def test_the_bake_copies_and_removes_its_work_copy_so():
    text = (ROOT / "packages" / "exporting" / "light_bake.py").read_text(encoding="utf-8")
    body = text[text.index("def bake("):]
    code = _code(body)
    assert "_copy_project(export_dir, work)" in code and "shutil.copytree(export_dir, work)" not in code
    assert "_remove_later(work)" in code and "shutil.rmtree(work, ignore_errors=True)" not in code
