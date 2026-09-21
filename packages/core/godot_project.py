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

THE DRIVER'S CENSUS RAISES THE CAP (0.87.0). `run_lux_apply.gd` now writes
`lights_in_tree` into `lux.quality.json`: every Light3D in the running tree
after every bake it performs -- the marker-spawned fixtures, the window rigs,
the room probes' neighbours, the club set, a `vending` rig the loader learns
tomorrow -- before the scene is packed. That is the number item 56 asked for,
measured at the one moment the whole lit tree exists in one process. The cap
is the LARGER of the text count and that census: the text count is still the
only number an export has for lights that arrive by other paths (Lot's own
scene), and the census is the only number that sees a lamp a rig builds in
_ready. Absent, unreadable or short of the key, the record contributes
nothing and the text count stands alone, as it did before -- an older driver
is not a reason to write a smaller cap than 0.86.1 would have.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

#: The Lux driver's quality record, wherever the package carries it
#: (`presentation/` in an export, beside the applied scene in a preview).
QUALITY_RECORD = "lux.quality.json"
LIGHTS_IN_TREE_KEY = "lights_in_tree"

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


def lights_reported_by_lux(root: Path) -> int | None:
    """The running-tree light census the Lux driver wrote, or None.

    None -- not 0 -- when no record is found, one cannot be parsed, or the
    record predates the key: a checker that cannot find the field it wants
    has learned nothing and must say so. Several records (a preview that
    kept two) contribute their largest.
    """
    best: int | None = None
    for rec in sorted(Path(root).rglob(QUALITY_RECORD)):
        try:
            data = json.loads(rec.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        v = data.get(LIGHTS_IN_TREE_KEY)
        if isinstance(v, bool) or not isinstance(v, int):
            continue
        best = v if best is None else max(best, v)
    return best


def package_light_budget(root: Path) -> int:
    """The light count the `[rendering]` cap is written from: the larger of
    the scene-text count and the driver's census (module docstring)."""
    text = count_package_lights(root)
    census = lights_reported_by_lux(root)
    return text if census is None else max(text, census)


def rendering_block(light_count: int) -> str:
    """The `[rendering]` section, ending with a blank line.

    Each cap is written only when the package exceeds the engine's own default
    for it, so a small or unlit package carries no override.
    """
    out = ['[rendering]', 'renderer/rendering_method="gl_compatibility"']

    # OCCLUSION CULLING, and it has to be written because the engine default
    # is false -- verified on 4.7.stable, not read off a page. It works in GL
    # Compatibility: the culler is a CPU software rasteriser in the rendering
    # server, not a backend feature. Measured on a purpose-built scene, 484
    # boxes behind one wall, on this renderer: 481 objects submitted with it
    # off and 1 with it on, against a control facing empty space that read 0
    # in both conditions.
    #
    # It costs about 0.27 ms of CPU per frame at 1280x720 with nothing to
    # cull -- the price of asking. On cold run 9062's package it bought
    # interior_c 4,635 draw calls down to 422 and 14.36 ms down to 1.86, and
    # the open view at exterior_sw 16.92 ms down to 7.96. Nothing measured
    # slower. If a package ever appears where it does, this line is the
    # switch, and `occluders.json` says what it was paying for.
    out.append("occlusion_culling/use_occlusion_culling=true")

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
