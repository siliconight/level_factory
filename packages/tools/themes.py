"""Does the theme a brief names actually exist in the installed tools?

Roadmap item 72. The question is asked BEFORE anything is spent, which is the
entire point of the module. Cold run `cold_7002` put three candidates through
Deli Counter in Blender, then Lot, then Laser Tag and walktest -- tens of
minutes of real compute -- and then `pixelcoat_build` exited 1 in two seconds:

    pixelcoat: error: no theme profile for 'delco_1997' at
      ...\\pixelcoat\\profiles\\themes\\delco_1997.json

`doctor` passed. `plan` printed a twelve-job DAG without a word about the
theme. The missing profile was a content gap and arguably not a pipeline
defect at all; **the absence of the check was the defect**, and it is the same
species as most of `PIPELINE_ROADMAP.md`: a precondition discovered only by
violating it, expensively, late.

WHERE THE ANSWERS LIVE, read off the tools rather than assumed:

  pixelcoat   `profiles/themes/<theme>.json` -- the very path the Pixelcoat
              adapter already builds in `fingerprint_inputs` to hash the
              profile into its fingerprint. It has always known where the file
              goes; it just never asked whether the file was there.

  zoo         every species under `zoo_keeper/genome/species/*.json` carries a
              `styles` object, and a theme resolves for Zoo when it is a key in
              there. Reported as a COUNT rather than a boolean, because
              "3 of 48 species carry it" and "48 of 48" are different answers
              and a yes/no would flatten them.

WHY ONLY PIXELCOAT BLOCKS. A missing theme profile stops `pixelcoat_build`
dead -- the tool exits 1 and the art pass has nothing to skin with. A style
Zoo does not carry is a quieter outcome: the zoo adapter's own comment records
that a themed library resolves ONLY under its own theme, so the kit falls back
to flat colour rather than failing. One is a wall, the other is a
disappointment, and reporting them the same way would be its own small lie.

NOT A NEW MECHANISM. Nothing here decides anything or writes anything. It
reads two directories and says what is on disk.
"""
from __future__ import annotations

import json
from pathlib import Path


def pixelcoat_themes(repo: str | Path | None) -> list[str]:
    """Theme profiles installed in a Pixelcoat checkout, sorted."""
    if not repo:
        return []
    d = Path(repo) / "profiles" / "themes"
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def pixelcoat_profile_path(repo: str | Path | None, theme: str) -> Path | None:
    """Where Pixelcoat will look. Mirrors the adapter's fingerprint path."""
    if not repo or not theme:
        return None
    return Path(repo) / "profiles" / "themes" / f"{theme}.json"


def zoo_styles(repo: str | Path | None) -> tuple[dict[str, int], int]:
    """(style name -> how many species carry it, species scanned).

    A species whose JSON will not parse is skipped rather than guessed at; it
    is a Zoo problem and this module does not get to have an opinion on it.
    """
    counts: dict[str, int] = {}
    if not repo:
        return counts, 0
    d = Path(repo) / "zoo_keeper" / "genome" / "species"
    if not d.is_dir():
        return counts, 0
    scanned = 0
    for p in sorted(d.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        scanned += 1
        styles = data.get("styles")
        if isinstance(styles, dict):
            for name in styles:
                counts[str(name)] = counts.get(str(name), 0) + 1
    return counts, scanned


def resolve(theme: str, repositories: dict) -> dict:
    """What the installed tools will do with `theme`.

    `ok` is False only when Pixelcoat cannot resolve it, because that is the
    one that stops a run. Everything else is reported for the human.
    """
    pc_repo = (repositories or {}).get("pixelcoat", "")
    zoo_repo = (repositories or {}).get("zoo", "")

    available = pixelcoat_themes(pc_repo)
    profile = pixelcoat_profile_path(pc_repo, theme)
    pc_ok = bool(theme) and profile is not None and profile.is_file()

    styles, species = zoo_styles(zoo_repo)
    carried = styles.get(theme, 0)

    return {
        "theme": theme,
        "ok": pc_ok,
        "pixelcoat": {
            "ok": pc_ok,
            "configured": bool(pc_repo),
            "path": str(profile) if profile else "",
            "available": available,
        },
        "zoo": {
            "configured": bool(zoo_repo),
            "species_with_style": carried,
            "species_scanned": species,
            "available": sorted(styles),
        },
    }


def summary_lines(res: dict) -> list[str]:
    """The report, in the words a reader needs and no more."""
    theme = res.get("theme") or "(none)"
    out: list[str] = []
    pc = res.get("pixelcoat", {})
    zoo = res.get("zoo", {})

    if not theme or theme == "(none)":
        out.append("theme:      (none declared) — the art pass has nothing to skin with")
        return out

    if not pc.get("configured"):
        out.append(f"theme:      {theme} — pixelcoat repository not configured, cannot check")
    elif pc.get("ok"):
        out.append(f"theme:      {theme} — pixelcoat profile found")
    else:
        out.append(f"theme:      {theme} — NO PIXELCOAT PROFILE at {pc.get('path')}")
        avail = pc.get("available") or []
        out.append("            pixelcoat carries: "
                   + (", ".join(avail) if avail else "(none)"))

    if zoo.get("configured"):
        n, total = zoo.get("species_with_style", 0), zoo.get("species_scanned", 0)
        if n == 0:
            out.append(f"            zoo: no species carry a '{theme}' style "
                       f"({total} scanned) — the kit falls back to flat colour")
        elif total and n < total:
            out.append(f"            zoo: {n} of {total} species carry '{theme}'")
        else:
            out.append(f"            zoo: all {total} species carry '{theme}'")
    return out
