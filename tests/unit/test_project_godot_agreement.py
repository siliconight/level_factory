"""The two project.godot writers must not drift, and the light cap must be earned.

`walk_preview._PROJECT` says it itself -- "Verbatim from
export.py::_write_project_godot, and it must stay verbatim" -- and then gives
the cost: "Two projects disagreeing about what a complete project.godot
contains is how a human signs off lighting that was missing a rig." On
2026-08-12 that is what happened. 0.43.2 removed the possibility by giving both
writers one shared `rendering_block`; these tests hold the rest of the promise.

Run:  python -m pytest tests/unit/test_project_godot_agreement.py
"""
import pytest

from packages.core.godot_project import (ENGINE_DEFAULT_RENDERABLE_LIGHTS,
                                         count_package_lights, rendering_block)
from packages.exporting.export import _write_project_godot
from packages.preview.walk_preview import _PROJECT

_SCENE = ('[gd_scene format=3]\n'
          '[node name="R" type="Node3D"]\n')
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


# --- the count is real, not assumed --------------------------------------

def test_the_counter_sees_lights_in_the_package(tmp_path):
    _package(tmp_path, 7)
    assert count_package_lights(tmp_path) == 7


def test_the_counter_is_zero_on_an_unlit_package(tmp_path):
    (tmp_path / "a.tscn").write_text(_SCENE, encoding="utf-8")
    assert count_package_lights(tmp_path) == 0


# --- the cap is derived, and only when it is needed -----------------------

def test_an_unlit_package_carries_no_cap_at_all(tmp_path):
    """An export with no lights must not pay for a rendering override."""
    t = _exported(tmp_path, 0)
    assert "max_renderable_lights" not in t


def test_a_package_at_the_engine_default_carries_no_cap(tmp_path):
    t = _exported(tmp_path, ENGINE_DEFAULT_RENDERABLE_LIGHTS)
    assert "max_renderable_lights" not in t


def test_a_package_over_the_default_caps_at_its_own_light_count(tmp_path):
    """Exact, not rounded: the package cannot render more lights than it has,
    so its own count is sufficient by construction and costs nothing extra."""
    n = ENGINE_DEFAULT_RENDERABLE_LIGHTS + 9
    v = _settings(_exported(tmp_path, n), "rendering")["limits/opengl/max_renderable_lights"]
    assert int(v) == n


# --- the expensive cap stays gone ----------------------------------------

@pytest.mark.parametrize("lights", [0, 40, 200])
def test_the_per_object_cap_is_never_written(tmp_path, lights):
    """Measured 2026-08-18: per-object 64 with the global cap at its default
    still blinked, and the default per-object with the global cap raised was
    clean AND had less first-load stutter. That value sizes the shader light
    loop for every object; writing it costs frame time for no measured gain."""
    assert "max_lights_per_object" not in _exported(tmp_path, lights)


# --- and the two writers still agree -------------------------------------

@pytest.mark.parametrize("lights", [0, 40])
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
    text = _exported(tmp_path, 40) if which == "exported" else _preview(tmp_path, 40)
    keys = [l.split("=", 1)[0].strip() for l in text.splitlines()
            if "=" in l and not l.strip().startswith((";", "["))]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    assert dupes == [], f"{which} writes these more than once: {dupes}"


def test_the_package_stays_plugin_free_and_autoload_free(tmp_path):
    t = _exported(tmp_path, 40)
    assert "[autoload]" not in t
    assert "[editor_plugins]" not in t
    assert "enabled=" not in t
