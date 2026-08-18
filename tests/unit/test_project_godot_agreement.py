"""Both light caps are derived from the package, and neither is a round number.

`walk_preview._PROJECT` says the two project.godot writers "must stay verbatim"
and gives the cost of drift: "Two projects disagreeing about what a complete
project.godot contains is how a human signs off lighting that was missing a
rig." 0.43.2 removed the possibility by giving both one shared `rendering_block`;
these tests hold the rest.

The caps have been wrong in both directions inside one day -- 0.43.0 wrote the
per-object cap for the wrong reason, 0.43.2 removed it for a reason that only
covered half the symptoms -- so each property below is pinned rather than left
to a comment.

Run:  python -m pytest tests/unit/test_project_godot_agreement.py
"""
import pytest

from packages.core.godot_project import (ENGINE_DEFAULT_LIGHTS_PER_OBJECT,
                                         ENGINE_DEFAULT_RENDERABLE_LIGHTS,
                                         PER_OBJECT_CEILING,
                                         count_package_lights, rendering_block)
from packages.exporting.export import _write_project_godot
from packages.preview.walk_preview import _PROJECT

_SCENE = '[gd_scene format=3]\n[node name="R" type="Node3D"]\n'
_LIGHT = '[node name="L{i}" type="OmniLight3D" parent="."]\n'


def _package(root, lights: int):
    (root / "presentation").mkdir(parents=True, exist_ok=True)
    (root / "presentation" / "lit.tscn").write_text(
        _SCENE + "".join(_LIGHT.format(i=i) for i in range(lights)),
        encoding="utf-8")
    return root


def _settings(text: str, section: str) -> dict:
    out, cur = {}, None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            cur = s[1:-1]; continue
        if not s or s.startswith(";") or "=" not in s:
            continue
        if cur == section:
            k, v = s.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _exported(tmp_path, lights):
    _package(tmp_path, lights)
    _write_project_godot(tmp_path, "mission.tscn", "m")
    return (tmp_path / "project.godot").read_text(encoding="utf-8")


def _preview(tmp_path, lights):
    _package(tmp_path, lights)
    return _PROJECT.format(name="m", level="mission.tscn",
                           rendering=rendering_block(count_package_lights(tmp_path)))


# --- the count is real -----------------------------------------------------

def test_the_counter_sees_lights_in_the_package(tmp_path):
    _package(tmp_path, 7)
    assert count_package_lights(tmp_path) == 7


def test_the_counter_is_zero_on_an_unlit_package(tmp_path):
    (tmp_path / "a.tscn").write_text(_SCENE, encoding="utf-8")
    assert count_package_lights(tmp_path) == 0


# --- nothing is written until it is earned --------------------------------

def test_an_unlit_package_carries_no_cap_at_all(tmp_path):
    t = _exported(tmp_path, 0)
    assert "max_renderable_lights" not in t
    assert "max_lights_per_object" not in t


def test_a_small_package_carries_neither_cap(tmp_path):
    """8 lights cannot exceed either engine default, so it pays nothing."""
    t = _exported(tmp_path, ENGINE_DEFAULT_LIGHTS_PER_OBJECT)
    assert "max_renderable_lights" not in t
    assert "max_lights_per_object" not in t


# --- the global cap is the package's own count ----------------------------

def test_the_global_cap_is_the_exact_light_count(tmp_path):
    n = ENGINE_DEFAULT_RENDERABLE_LIGHTS + 9
    v = _settings(_exported(tmp_path, n), "rendering")["limits/opengl/max_renderable_lights"]
    assert int(v) == n


# --- the per-object cap is bounded BOTH ways ------------------------------

def test_the_per_object_cap_is_bounded_by_the_measured_ceiling(tmp_path):
    """A 136-light package gets the ceiling, not 136: the value sizes the
    shader light loop for every object, so it must not track the count up."""
    v = _settings(_exported(tmp_path, 136), "rendering")["limits/opengl/max_lights_per_object"]
    assert int(v) == PER_OBJECT_CEILING


def test_the_per_object_cap_is_bounded_by_the_package_too(tmp_path):
    """A 20-light package cannot put more than 20 on one mesh, so it gets 20
    rather than paying for the ceiling."""
    n = 20
    assert n < PER_OBJECT_CEILING
    v = _settings(_exported(tmp_path, n), "rendering")["limits/opengl/max_lights_per_object"]
    assert int(v) == n


def test_the_ceiling_covers_the_worst_measured_mesh():
    """36 lights on pvp_station_ref's roof, measured 2026-08-18. If this
    ceiling ever drops below that, the seam this cap exists for comes back."""
    assert PER_OBJECT_CEILING >= 36


# --- and the two writers still agree --------------------------------------

@pytest.mark.parametrize("lights", [0, 40, 136])
@pytest.mark.parametrize("section", ["rendering", "debug"])
def test_every_exported_setting_appears_in_the_preview(section, lights, tmp_path):
    e = _settings(_exported(tmp_path, lights), section)
    p = _settings(_preview(tmp_path, lights), section)
    missing = {k: v for k, v in e.items() if p.get(k) != v}
    assert missing == {}, f"[{section}] drifted: {missing} (preview has {p})"


def test_the_sections_being_compared_are_not_empty(tmp_path):
    t = _exported(tmp_path, 0)
    assert _settings(t, "rendering"), "no [rendering] settings parsed"
    assert _settings(t, "debug"), "no [debug] settings parsed"


@pytest.mark.parametrize("which", ["exported", "preview"])
def test_no_setting_is_written_twice(which, tmp_path):
    """`_settings` returns a dict, so a duplicated line is invisible to every
    other test here. 0.43.0's first draft emitted its cap twice and the suite
    stayed green. Read the LINES."""
    text = _exported(tmp_path, 136) if which == "exported" else _preview(tmp_path, 136)
    keys = [l.split("=", 1)[0].strip() for l in text.splitlines()
            if "=" in l and not l.strip().startswith((";", "["))]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    assert dupes == [], f"{which} writes these more than once: {dupes}"


def test_the_package_stays_plugin_free_and_autoload_free(tmp_path):
    t = _exported(tmp_path, 136)
    assert "[autoload]" not in t
    assert "[editor_plugins]" not in t
    assert "enabled=" not in t
