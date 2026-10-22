"""The scout window: the screen a player scouts a level's buildings on, shipped in every package (0.235.0, the
factory's roadmap 295).

The walker: "Goal is we have the ability to open up a 'window' at runtime that shows the various buildings and their
3d schematics", the handheld it shows on the game's own asset -- "make sure the window can be called by something on
the gameplay layer (seam is clear and visible)". This copies Level Factory's `assets/godot/scout/` into the package's
`scout/`: `scout_window.gd` (class `LFScoutWindow`, the seam: `open`, `close`, `select`, `get_screen_texture`,
`set_points`, `turn`, `set_spread`, `buildings`; signals `opened`, `closed`, `building_selected`) and `README.md`
stating it. Nothing is wired into the level's scenes: the gameplay layer decides when a player scouts, and a window
nobody opens costs nothing.

It reads what the export already writes: `buildings.json` (`buildings_index`) and each building's
`drawings/scout.glb` (Deli Counter 0.259.0 on). A package with no `buildings.json` gets no window and says why --
a screen with nothing to list is not shipped.
"""
from __future__ import annotations

import shutil
from pathlib import Path

_LF_ROOT = Path(__file__).resolve().parents[2]
SOURCE = _LF_ROOT / "assets" / "godot" / "scout"
FILES = ("scout_window.gd", "README.md")
DEST = "scout"


def install(export_dir) -> dict:
    """Copy the window into ``<export_dir>/scout/``. Returns {"installed": [...], "why_not": str|None,
    "models": n} -- ``models`` the buildings the index names a scout model for."""
    export_dir = Path(export_dir)
    index = export_dir / "buildings.json"
    if not index.is_file():
        return {"installed": [], "why_not": "no buildings.json to list", "models": 0}
    missing = [f for f in FILES if not (SOURCE / f).is_file()]
    if missing:
        raise FileNotFoundError("Level Factory's assets/godot/scout/ lacks %s" % ", ".join(missing))
    dest = export_dir / DEST
    dest.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        shutil.copyfile(SOURCE / f, dest / f)
    import json
    entries = json.loads(index.read_text(encoding="utf-8")).get("buildings") or []
    models = len({e["id"] for e in entries if e.get("scout_model")})
    return {"installed": ["%s/%s" % (DEST, f) for f in FILES], "why_not": None, "models": models}
