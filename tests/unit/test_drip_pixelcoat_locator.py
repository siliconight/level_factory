"""The drip's tools find Pixelcoat by searching, not by counting (0.138.1).

`drip_assets.DEFAULT_PIXELCOAT` and `wet_ab_run.py`'s `--pixelcoat` default
were both `Path(__file__).resolve().parents[2] / "pixelcoat"`: the factory
from a checkout sitting beside its siblings, and `scratchpad` from a git
worktree (`gabagool_factory/scratchpad/<branch>/tools/`), where there is no
Pixelcoat. `test_sibling_locator`'s guard failed on both lines.

These load a COPY of `drip_assets.py` placed where a worktree puts it, under a
factory that does carry Pixelcoat, so the search is exercised from the layout
that broke the count -- not from this checkout, where both answer the same.
"""
from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

_TOOL = Path(__file__).resolve().parents[2] / "tools" / "drip_assets.py"
_MARKER = Path("pixelcoat") / "core" / "droplets.py"


def _factory(tmp_path: Path) -> tuple[Path, Path]:
    """A factory holding a Pixelcoat, and a worktree copy of the tool in it."""
    factory = tmp_path / "gabagool_factory"
    (factory / "pixelcoat" / _MARKER).parent.mkdir(parents=True)
    (factory / "pixelcoat" / _MARKER).write_text("", encoding="utf-8")
    tool = factory / "scratchpad" / "lf_branch" / "tools" / "drip_assets.py"
    tool.parent.mkdir(parents=True)
    shutil.copyfile(_TOOL, tool)
    return factory, tool


def _load(tool: Path):
    spec = importlib.util.spec_from_file_location("drip_assets_copy", tool)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_worktree_copy_finds_the_factory_s_pixelcoat(tmp_path, monkeypatch):
    """FAILS ON 0.138.0: the count answered `scratchpad/pixelcoat`."""
    monkeypatch.delenv("LF_PIXELCOAT_ROOT", raising=False)
    factory, tool = _factory(tmp_path)
    assert _load(tool).DEFAULT_PIXELCOAT == factory / "pixelcoat"


def test_the_override_takes_either_spelling(tmp_path, monkeypatch):
    factory, tool = _factory(tmp_path)
    for value in (factory / "pixelcoat", factory):
        monkeypatch.setenv("LF_PIXELCOAT_ROOT", str(value))
        assert _load(tool).DEFAULT_PIXELCOAT == factory / "pixelcoat"


def test_a_missing_pixelcoat_is_said_with_the_file_and_the_override(tmp_path, monkeypatch):
    """A wrong override does not fall back to the walk, and `stage` says what
    it looked for and how to point it, rather than importing from nowhere."""
    _, tool = _factory(tmp_path)
    monkeypatch.setenv("LF_PIXELCOAT_ROOT", str(tmp_path / "nowhere"))
    mod = _load(tool)
    assert mod.DEFAULT_PIXELCOAT is None
    (tool.parents[1] / "assets" / "godot").mkdir(parents=True)
    (tool.parents[1] / "assets" / "godot" / "rain_drip.gdshader").write_text("", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        mod.stage(tmp_path / "out")
    msg = str(exc.value)
    assert "pixelcoat/core/droplets.py" in msg and "LF_PIXELCOAT_ROOT" in msg
