"""The two project.godot writers must not drift apart.

`walk_preview._PROJECT` says so itself -- "Verbatim from
export.py::_write_project_godot, and it must stay verbatim" -- and then explains
the cost: "Two projects disagreeing about what a complete project.godot contains
is how a human signs off lighting that was missing a rig." On 2026-08-12 that is
exactly what happened; the preview lacked the debug block and
`lux_area_light_rig.gd:61` failed to parse in a walk of the same package whose
portability test had scored `parser_error_count 0`.

That invariant lived in a comment. This makes it a test.

It is deliberately ONE-DIRECTIONAL: everything the exporter writes must appear
in the preview, but the preview may add things (it has a player, a main scene of
its own, and `config/features`). A two-directional test would fail on the
preview's legitimate extras and would get deleted the first time it did.

Run:  python -m pytest tests/unit/test_project_godot_agreement.py
"""
import re

import pytest

from packages.exporting.export import _write_project_godot
from packages.preview.walk_preview import _PROJECT


@pytest.fixture()
def exported(tmp_path) -> str:
    _write_project_godot(tmp_path, "mission.tscn", "m")
    return (tmp_path / "project.godot").read_text(encoding="utf-8")


@pytest.fixture()
def preview() -> str:
    return _PROJECT.format(level="mission.tscn", name="m")


def _settings(text: str, section: str) -> dict:
    """key=value pairs under one [section], comments and blanks dropped."""
    out, cur = {}, None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            cur = s[1:-1]
            continue
        if not s or s.startswith(";") or "=" not in s:
            continue
        if cur == section:
            k, v = s.split("=", 1)
            out[k.strip()] = v.strip()
    return out


@pytest.mark.parametrize("section", ["rendering", "debug"])
def test_every_exported_setting_appears_in_the_preview(section, exported, preview):
    e, p = _settings(exported, section), _settings(preview, section)
    missing = {k: v for k, v in e.items() if p.get(k) != v}
    assert missing == {}, f"[{section}] drifted: {missing} (preview has {p})"


def test_the_sections_being_compared_are_not_empty(exported):
    """Without this, the test above passes trivially if a section is renamed
    and _settings silently returns {} for both."""
    assert _settings(exported, "rendering"), "no [rendering] settings parsed"
    assert _settings(exported, "debug"), "no [debug] settings parsed"


def test_the_light_cap_is_written_by_both(exported, preview):
    for name, text in (("export", exported), ("preview", preview)):
        v = _settings(text, "rendering").get("limits/opengl/max_lights_per_object")
        assert v is not None, f"{name} writes no per-object light cap"
        assert int(v) >= 64, f"{name} caps at {v}; measured worst case is 36"


def test_the_cap_is_only_meaningful_on_the_compatibility_renderer(exported):
    """If the profile ever moves to forward_plus the cap is dead weight and
    this test should be the thing that says so out loud."""
    assert _settings(exported, "rendering")["renderer/rendering_method"] == \
        '"gl_compatibility"'


@pytest.mark.parametrize("which", ["exported", "preview"])
def test_no_setting_is_written_twice(which, exported, preview):
    """`_settings` returns a dict, so a duplicated line is invisible to every
    other test in this file. The first draft of 0.43.0 emitted the light cap
    twice and the suite stayed green. Read the LINES, not the dict."""
    text = exported if which == "exported" else preview
    keys = [l.split("=", 1)[0].strip() for l in text.splitlines()
            if "=" in l and not l.strip().startswith(";")
            and not l.strip().startswith("[")]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    assert dupes == [], f"{which} writes these settings more than once: {dupes}"


def test_the_package_stays_plugin_free_and_autoload_free(exported):
    """The portable profile's whole claim. A light cap must not smuggle in a
    dependency."""
    assert "[autoload]" not in exported
    assert "[editor_plugins]" not in exported
    assert "enabled=" not in exported
