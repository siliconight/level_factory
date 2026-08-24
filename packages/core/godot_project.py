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
        This one is still written, and see the caveat below.

    rendering/limits/opengl/max_lights_per_object   default 8
        A PER-MESH budget. Above it, a mesh drops lights. On building-sized
        floor and ceiling slabs this showed up standing still, as a hard
        brightness STEP where two slabs meet -- not as blinking.
        THIS ONE IS NO LONGER WRITTEN. Read on.

THE PER-OBJECT CAP IS GONE, AND WHY (roadmap 54, closed). The cap only ever
existed because a single mesh spanned a whole room -- a 34-52 m floor, roof
or path was ONE light budget for everything near it (measured on
lot_demo_001's walk preview by tools/mesh_light_census.py: 804 of 3,016
meshes over the engine default of 8, worst at 72). 0.43.0 wrote the cap and
misattributed the blinking to it; 0.43.2 removed it and brought back the
seam; 0.43.3 shipped it as a stated MITIGATION, priced honestly: it sizes
the shader light loop for EVERY object. The fix was never a setting: zoo
0.49.0, deli_counter 0.96.0 and lot 0.49.0 tile every plate visual to
light-budget-sized meshes (collision untouched), and the per-mesh census on
the recomposed package is the evidence this deletion stands on. If a future
package shows a brightness step between adjacent slabs, the answer is the
census and the tile size, not this cap's return.

THE GLOBAL CAP IS DERIVED FROM THE PACKAGE, with a known caveat. It is the
package's own light count, counted by globbing the scenes (`closure.py`'s
approach) -- but that counts DECLARATIONS in scene text, and roadmap item 56
measured the running tree at 272 visible lights against a written cap of
136: an instanced rig counts once and a runtime-spawned fixture light counts
zero. The number this writes is a floor, not the truth; item 56 owns the fix.

Below the engine default the global line is not written, and an unlit package
carries no rendering override at all.
"""
from __future__ import annotations

import re
from pathlib import Path

# Every node type that consumes a slot in the light budgets.
_LIGHT_TYPES = ("OmniLight3D", "SpotLight3D", "DirectionalLight3D")

#: The engine's own defaults. At or below these, a package needs no override.
#: The per-object default is kept as a named fact even though no per-object
#: cap is written any more: it is the budget the tiled plates were sized FOR,
#: and the number the per-mesh census gates against.
ENGINE_DEFAULT_RENDERABLE_LIGHTS = 32
ENGINE_DEFAULT_LIGHTS_PER_OBJECT = 8

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

    # No per-object cap, ON PURPOSE (roadmap 54, closed). Every plate visual
    # is tiled to light-budget-sized meshes upstream (zoo 0.49.0 /
    # deli_counter 0.96.0 / lot 0.49.0), so no mesh needs more than the
    # engine's own 8 -- proven by tools/mesh_light_census.py on the
    # recomposed package, which is the gate to run before blaming this
    # absence for a lighting defect.

    return "\n".join(out) + "\n\n"
