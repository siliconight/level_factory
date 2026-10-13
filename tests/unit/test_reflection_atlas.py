"""The reflection atlas is sized to the package's probes (Level Factory 0.198.0, factory roadmap 238).

Godot allocates the reflection atlas the first time any ReflectionProbe renders -- a player's camera, or the
Warmup's sweep at load -- at the size two project settings give it, read when the renderer starts. The
defaults, 64 slots of 256 x 256 x 6 faces in half-float with mips, are 256 MiB: on cold run 9273's package,
257 of its 314.6 MiB of texture memory, for 23 probes, each an interior room's ambient (the factory's
`docs/findings/texture_memory/`). The package's project.godot now writes the atlas from the package, as it
writes the light cap: its slots the probe count rounded up to a power of two, its face size the priced
`REFLECTION_ATLAS_SIZE`. A package with no probe never allocates one, and carries no line.

Run:  python -m pytest tests/unit/test_reflection_atlas.py
"""
import inspect

from packages.core.godot_project import (ENGINE_DEFAULT_REFLECTION_COUNT,
                                         ENGINE_DEFAULT_REFLECTION_SIZE,
                                         REFLECTION_ATLAS_SIZE, count_package_probes,
                                         reflection_atlas_count, reflection_atlas_mib,
                                         rendering_block)
from packages.exporting.export import _write_project_godot
from packages.preview import walk_preview
from packages.preview.walk_preview import _PROJECT

_SCENE = '[gd_scene format=3]\n[node name="R" type="Node3D"]\n'
_PROBE = '[node name="P{i}" type="ReflectionProbe" parent="."]\n'
COUNT = "reflections/reflection_atlas/reflection_count"
SIZE = "reflections/reflection_atlas/reflection_size"


def _package(root, probes: int):
    (root / "presentation").mkdir(parents=True, exist_ok=True)
    (root / "presentation" / "lux.applied.tscn").write_text(
        _SCENE + "".join(_PROBE.format(i=i) for i in range(probes)), encoding="utf-8")
    return root


def _rendering(text: str) -> dict:
    """The `[rendering]` section's settings, a line at a time (`test_project_godot_agreement`'s reading)."""
    out, cur = {}, None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            cur = s[1:-1]
            continue
        if not s or s.startswith(";") or "=" not in s:
            continue
        if cur == "rendering":
            k, v = s.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def test_the_counter_sees_the_package_s_probes(tmp_path):
    assert count_package_probes(_package(tmp_path, 23)) == 23


def test_a_package_without_probes_carries_no_atlas_line(tmp_path):
    assert "reflection_atlas" not in rendering_block(40, 0, 0)
    _package(tmp_path, 0)
    _write_project_godot(tmp_path, "mission.tscn", "m", "4.7")
    assert "reflection_atlas" not in (tmp_path / "project.godot").read_text(encoding="utf-8")


def test_the_slots_hold_every_probe_rounded_up():
    assert [reflection_atlas_count(n) for n in (1, 2, 3, 23, 32, 33, 100)] == [1, 2, 4, 32, 32, 64, 128]
    # a package with more probes than the engine's 64 slots gets more slots, not the default's overflow:
    # four slots for 23 probes raised `rpi->atlas_index < 0` 113,494 times and stalled the run
    assert reflection_atlas_count(100) > ENGINE_DEFAULT_REFLECTION_COUNT


def test_the_block_writes_the_atlas_for_a_package_with_probes():
    s = _rendering(rendering_block(40, 0, 23))
    assert s[COUNT] == "32"
    assert s[SIZE] == str(REFLECTION_ATLAS_SIZE)
    assert REFLECTION_ATLAS_SIZE < ENGINE_DEFAULT_REFLECTION_SIZE


def test_the_atlas_costs_what_was_measured():
    # cold run 9273's package: the defaults read 257.3 MiB, and a 64-pixel face took 241.1 away
    assert abs(reflection_atlas_mib(ENGINE_DEFAULT_REFLECTION_COUNT, ENGINE_DEFAULT_REFLECTION_SIZE) - 256.0) < 1e-9
    assert abs(reflection_atlas_mib(64, 64) - 16.0) < 1e-9
    # and what that package's 23 probes cost now
    assert abs(reflection_atlas_mib(reflection_atlas_count(23), REFLECTION_ATLAS_SIZE) - 8.0) < 1e-9


def test_the_export_writes_the_atlas_from_its_own_folder(tmp_path):
    _package(tmp_path, 23)
    _write_project_godot(tmp_path, "mission.tscn", "m", "4.7")
    s = _rendering((tmp_path / "project.godot").read_text(encoding="utf-8"))
    assert s[COUNT] == "32" and s[SIZE] == str(REFLECTION_ATLAS_SIZE)


def test_the_export_and_the_preview_write_the_same_atlas(tmp_path):
    _package(tmp_path, 23)
    _write_project_godot(tmp_path, "mission.tscn", "m", "4.7")
    exported = _rendering((tmp_path / "project.godot").read_text(encoding="utf-8"))
    preview = _rendering(_PROJECT.format(name="m", level="mission.tscn",
                                         rendering=rendering_block(0, 0, count_package_probes(tmp_path))))
    assert (exported[COUNT], exported[SIZE]) == (preview[COUNT], preview[SIZE])
    # and the preview asks its own folder for the count, as the export does
    assert "count_package_probes(dest)" in inspect.getsource(walk_preview)
