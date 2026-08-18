"""The `[rendering]` block of a generated project.godot -- one rule, two callers.

`export.py` writes the shipped package's project.godot and `walk_preview.py`
writes the dev preview's, and the preview's own comment says they must not
drift: "Two projects disagreeing about what a complete project.godot contains
is how a human signs off lighting that was missing a rig." Two hand-kept copies
is how that happens, so there is one function here and two importers -- the
same shape `packages.core.hashing` already has for scene payloads.

THE TWO LIGHT LIMITS, AND WHAT EACH ONE ACTUALLY DOES.

GL Compatibility carries two, they fail differently, and this file has been
wrong about them once already:

    rendering/limits/opengl/max_renderable_lights   default 32
        A GLOBAL budget. Above it, lights are simply not drawn -- so on a
        136-light package most were not, and whole areas stayed dark
        PERMANENTLY while which ones won changed as the camera moved.

    rendering/limits/opengl/max_lights_per_object   default 8
        A PER-MESH budget. Above it, a mesh drops lights. On building-sized
        floor and ceiling slabs this shows up standing still, as a hard
        brightness STEP where two slabs meet -- not as blinking.

level_factory 0.43.0 set the per-object cap and named it as the cause of the
blinking; it was not. 0.43.2 then removed it, having tested only for blinking,
and that reintroduced the seam. Measured in the walk preview, one interior,
three runs: default 8 -> hard cut across the floor; 64 -> gone; 40 -> gone.

BOTH VALUES ARE DERIVED FROM THE PACKAGE. Neither is a round number picked to
make a symptom go away:

  * The global cap is the package's own light count, counted by globbing the
    scenes (`closure.py`'s approach). A package cannot render more lights than
    it contains, so its total is a true upper bound -- sufficient by
    construction, with no headroom to pay for.

  * The per-object cap is `min(light count, PER_OBJECT_CEILING)`. Also bounded
    by the package: a 20-light package cannot put more than 20 on one mesh and
    gets 20. The ceiling is the measured worst case across lot_demo_001's five
    buildings -- one mesh at 36 lights -- plus a small margin.

Below the engine defaults neither line is written, and an unlit package carries
no rendering override at all.

THE PER-OBJECT CAP COSTS SOMETHING. It sizes the light loop in the shader for
every object, so the smallest sufficient value is the correct one, and this is
a MITIGATION. The seam only exists because a single floor mesh spans a whole
room; room-sized meshes would sit inside the engine default and need no cap.
That is roadmap 54, and it is the actual fix.
"""
from __future__ import annotations

import re
from pathlib import Path

# Every node type that consumes a slot in the light budgets.
_LIGHT_TYPES = ("OmniLight3D", "SpotLight3D", "DirectionalLight3D")

#: The engine's own defaults. At or below these, a package needs no override.
ENGINE_DEFAULT_RENDERABLE_LIGHTS = 32
ENGINE_DEFAULT_LIGHTS_PER_OBJECT = 8

#: Measured ceiling for the per-mesh cap. The worst mesh across lot_demo_001's
#: five buildings sees 36 lights (pvp_station_ref's roof); 40 leaves margin and
#: was confirmed seam-free in the walk preview. RAISE THIS FIRST if a denser
#: mission shows a brightness step between adjacent slabs.
PER_OBJECT_CEILING = 40

_LIGHT_RE = re.compile(r'type="(?:' + "|".join(_LIGHT_TYPES) + r')"')


def count_package_lights(root: Path) -> int:
    """Light nodes across every `.tscn` under `root`.

    Globbed, not walked: a scene-graph traversal would need every instanced
    sub-scene resolved, and this only has to be an upper bound.
    """
    total = 0
    for scene in sorted(Path(root).rglob("*.tscn")):
        try:
            text = scene.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        total += len(_LIGHT_RE.findall(text))
    return total


def per_object_cap(light_count: int) -> int:
    """The per-mesh cap this package needs, bounded by what it contains."""
    return min(light_count, PER_OBJECT_CEILING)


def rendering_block(light_count: int) -> str:
    """The `[rendering]` section, ending with a blank line.

    Each cap is written only when the package exceeds the engine's own default
    for it, so a small or unlit package carries no override.
    """
    out = ['[rendering]', 'renderer/rendering_method="gl_compatibility"']

    if light_count > ENGINE_DEFAULT_RENDERABLE_LIGHTS:
        out += [
            "; RENDERABLE-LIGHTS BUDGET -- a GLOBAL cap, engine default 32.",
            "; Above it lights are not drawn at all, so on a package this size",
            f"; most were not: measured on lot_demo_001 2026-08-18 with {light_count}",
            "; lights as areas that stay dark permanently, plus blinking as",
            "; which lights win changes with the camera. The value is this",
            "; package's own light count -- a true upper bound, sufficient by",
            "; construction, with no headroom to pay for.",
            f"limits/opengl/max_renderable_lights={light_count}",
        ]

    cap = per_object_cap(light_count)
    if cap > ENGINE_DEFAULT_LIGHTS_PER_OBJECT:
        out += [
            "; PER-MESH BUDGET -- engine default 8. A mesh over it drops",
            "; lights, and on building-sized floor and ceiling slabs that shows",
            "; STANDING STILL, as a hard brightness step where two slabs meet.",
            "; 0.43.2 removed this cap having tested only for blinking, and the",
            "; seam came back. Measured in the walk preview, one interior:",
            "; default 8 -> hard cut; 64 -> gone; 40 -> gone. The worst mesh",
            "; across five buildings sees 36 lights, so 40 is the smallest",
            "; value the data supports -- and this one COSTS: it sizes the",
            "; shader light loop for every object. It is a mitigation; the fix",
            "; is that one mesh should not span a room. Roadmap 54.",
            f"limits/opengl/max_lights_per_object={cap}",
        ]

    return "\n".join(out) + "\n\n"
