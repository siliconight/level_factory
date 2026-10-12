"""The class-name scan of a localized script skips the names its text does not contain (0.192.0).

`_rewrite_text` pulls a tool's script into the package when a localized `.gd` names its global
class (`\bName\b`). It asked that of every class name the tools declare, building a pattern for
each and searching the whole script with it, though a name that is not in the text cannot match:
on cold run 9257's package, 1,804 searches a pass over 44 scripts, twelve of them a 95 KB
`zoo_worldskin.gd`, 1.67 of the pass's 1.69 s (the factory's
docs/findings/grader_speed/export_timeline_probe.py found the step; the export runs about three
passes). A plain substring test now comes first; the pattern still decides.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.exporting import localize as L  # noqa: E402


def _repo(tmp_path):
    repo = tmp_path / "repos" / "lux"
    rt = repo / "addons" / "lux" / "runtime"
    rt.mkdir(parents=True)
    (rt / "lux_lighting.gd").write_text("class_name LuxLighting\nextends RefCounted\n", encoding="utf-8")
    (rt / "lux_binder.gd").write_text("class_name LuxEmissiveBinder\nextends RefCounted\n", encoding="utf-8")
    return repo


def _searches(monkeypatch):
    calls = []
    real = re.search

    def counting(pattern, string, flags=0):
        calls.append(pattern)
        return real(pattern, string, flags)
    monkeypatch.setattr(L.re, "search", counting)
    return calls


def test_a_script_naming_no_class_runs_no_search(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    export = tmp_path / "export"
    export.mkdir()
    gd = export / "plain.gd"
    gd.write_text("extends Node\nfunc _ready() -> void:\n\tpass\n", encoding="utf-8")
    class_map = L._build_class_map({"lux": repo})
    assert set(class_map) == {"LuxLighting", "LuxEmissiveBinder"}
    calls = _searches(monkeypatch)
    L._rewrite_text(gd, export, {"lux": repo}, L.LocalizeReport(), class_map)
    assert calls == []
    assert not (export / "runtime").exists()


def test_a_name_inside_a_longer_one_is_still_decided_by_the_pattern(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    export = tmp_path / "export"
    export.mkdir()
    gd = export / "near.gd"
    gd.write_text("extends Node\nvar x := LuxLightingSettings.new()\n", encoding="utf-8")
    calls = _searches(monkeypatch)
    changed = L._rewrite_text(gd, export, {"lux": repo}, L.LocalizeReport(), L._build_class_map({"lux": repo}))
    assert changed is False
    assert len(calls) == 1, calls          # LuxLighting is in the text, so the pattern was asked
    assert not (export / "runtime" / "lux" / "runtime" / "lux_lighting.gd").exists()


def test_a_name_used_as_a_word_still_pulls_its_script(tmp_path):
    repo = _repo(tmp_path)
    export = tmp_path / "export"
    export.mkdir()
    gd = export / "uses.gd"
    gd.write_text("extends Node\nfunc go() -> void:\n\tLuxEmissiveBinder.new()\n", encoding="utf-8")
    changed = L._rewrite_text(gd, export, {"lux": repo}, L.LocalizeReport(), L._build_class_map({"lux": repo}))
    assert changed is True
    assert (export / "runtime" / "lux" / "runtime" / "lux_binder.gd").exists()
    assert not (export / "runtime" / "lux" / "runtime" / "lux_lighting.gd").exists()
