"""Stage the rain drip's two assets into a Godot project directory.

ONE PLACE THAT KNOWS. The drip needs a shader and a drop atlas, and two
consumers want them staged: `wet_ab_run.py`, which PRICES the fragment, and
`walk_export.py`, which puts it in front of a person. If those two staged
different atlases or different shader text, the walk would be judging something
other than what was measured -- the same reason `walk_export.py` reads Level
Factory's debug overlay instead of carrying a copy.

THE ATLAS IS GENERATED, NEVER CHECKED IN. It is Pixelcoat's output
(`pixelcoat/core/droplets.py`, 0.50.0); a PNG sitting beside the probe would be
a second copy to drift from its generator. SIZE and SEED are fixed here because
they are part of what was measured: change either and the +1.85 ms figure is
about a different texture.
"""
from __future__ import annotations

import sys
from pathlib import Path

#: The atlas the drip was priced against. 512 px, and the seed is pinned so a
#: walk and a measurement see the same drops.
ATLAS_PX = 512
ATLAS_SEED = 1999

#: The shader both consumers attach. Extracted from `wet_ab.gd` when it was
#: split out, so the text that was measured and the text that ships are the
#: same bytes.
SHADER = (Path(__file__).resolve().parents[1] / "assets" / "godot"
          / "rain_drip.gdshader")

#: The runtime node that attaches it, for consumers that need one. The probe
#: does its own attaching; a walk copy needs this.
NODE = (Path(__file__).resolve().parents[1] / "assets" / "godot"
        / "rain_drip.gd")

#: Pixelcoat, guessed from the factory layout. Both callers can override.
DEFAULT_PIXELCOAT = Path(__file__).resolve().parents[2] / "pixelcoat"


def stage(dest: Path, pixelcoat: Path | None = None,
          node: bool = False) -> list[str]:
    """Write the shader, the atlas and optionally the node into ``dest``.

    Returns the filenames written, in order. Raises rather than half-staging:
    a drip missing its texture is not a cheap drip, it is a shader sampling
    nothing, and the last time a pass was measured without being drawn the
    figure had to be withdrawn.
    """
    dest = Path(dest)
    pixelcoat = Path(pixelcoat) if pixelcoat else DEFAULT_PIXELCOAT
    if not SHADER.is_file():
        raise FileNotFoundError(
            "the drip shader is not at %s -- Level Factory's copy is the "
            "only one, so there is nothing to stage." % SHADER)

    written: list[str] = []
    (dest / SHADER.name).write_bytes(SHADER.read_bytes())
    written.append(SHADER.name)

    sys.path.insert(0, str(pixelcoat))
    try:
        from pixelcoat.core import droplets
    except ImportError as exc:
        raise SystemExit(
            "the drip needs pixelcoat on the path (%s); point --pixelcoat at "
            "the repo. The atlas is generated, never carried." % exc) from exc
    from PIL import Image
    a = droplets.drop_atlas(ATLAS_PX, seed=ATLAS_SEED)
    Image.fromarray(a, "RGBA").save(dest / "drop_atlas.png")
    written.append("drop_atlas.png")

    if node:
        if not NODE.is_file():
            raise FileNotFoundError(
                "the drip node is not at %s -- refusing to stage a shader "
                "nothing will attach." % NODE)
        (dest / NODE.name).write_bytes(NODE.read_bytes())
        written.append(NODE.name)
    return written
