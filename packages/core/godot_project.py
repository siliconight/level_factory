"""The `[rendering]` block of a generated project.godot -- one rule, two callers.

`export.py` writes the shipped package's project.godot and `walk_preview.py`
writes the dev preview's, and the preview's own comment says they must not
drift: "Two projects disagreeing about what a complete project.godot contains
is how a human signs off lighting that was missing a rig." Two hand-kept copies
is how that happens, so there is one function here and two importers -- the
same shape `packages.core.hashing` already has for scene payloads.

WHAT THE CAP IS FOR, measured on lot_demo_001, 2026-08-18.

A package shipping 136 fixture lights blinked when walked, and whole areas
stayed dark permanently. GL Compatibility carries TWO separate light limits and
only one of them was the problem:

    rendering/limits/opengl/max_renderable_lights   default 32   <- binding
    rendering/limits/opengl/max_lights_per_object   default  8

Tested on hardware, in this order:

    per-object 64, global 32     still blinks, areas stay dark
    per-object  8, global 256    clean, and first-load stutter is SMALLER

`max_renderable_lights` is a GLOBAL budget: with 136 lights and a cap of 32,
most of them are never drawn at all, which is why areas stayed dark rather than
flickering. `max_lights_per_object` was never the binding constraint, and
raising it is actively expensive -- it sizes the light loop in the shader for
EVERY object, multiplying variants and per-fragment work. level_factory 0.43.0
wrote it anyway, on a mechanism that had not been isolated. It is not written
any more.

WHY THE VALUE IS EXACT. The cap is the number of light nodes the package
actually ships, counted by globbing the scenes rather than reasoning about
them (`closure.py`'s approach). A package cannot render more lights than it
contains, so the total is a true upper bound: sufficient by construction, with
no headroom to pay for. Below the engine default, nothing is written at all --
an unlit package should not carry a rendering override.
"""
from __future__ import annotations

import re
from pathlib import Path

# Every node type that consumes a slot in the renderable-lights budget.
_LIGHT_TYPES = ("OmniLight3D", "SpotLight3D", "DirectionalLight3D")

#: The engine's own default for `max_renderable_lights`. At or below this, the
#: package needs no override and should not carry one.
ENGINE_DEFAULT_RENDERABLE_LIGHTS = 32

_LIGHT_RE = re.compile(
    r'type="(?:' + "|".join(_LIGHT_TYPES) + r')"')


def count_package_lights(root: Path) -> int:
    """Light nodes across every `.tscn` under `root`.

    Globbed, not walked: a scene graph traversal would need every instanced
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

    `light_count` at or below the engine default produces no cap line at all.
    """
    out = ['[rendering]', 'renderer/rendering_method="gl_compatibility"']
    if light_count > ENGINE_DEFAULT_RENDERABLE_LIGHTS:
        out += [
            "; RENDERABLE-LIGHTS BUDGET. GL Compatibility renders at most N",
            "; lights in total, engine default 32. This package ships",
            f"; {light_count}, so without this the majority are never drawn:",
            "; measured on lot_demo_001 2026-08-18 as areas that stay dark",
            "; permanently, plus blinking as which lights win changes with the",
            "; camera. The value is the package's own light count, which is a",
            "; true upper bound -- sufficient by construction, no headroom to",
            "; pay for. The per-OBJECT cap is deliberately NOT set: it was",
            "; tested at 64 and was never the binding constraint, and raising",
            "; it sizes the shader light loop for every object.",
            f"limits/opengl/max_renderable_lights={light_count}",
        ]
    return "\n".join(out) + "\n\n"
