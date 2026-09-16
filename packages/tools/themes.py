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
    per_species: list[set[str]] = []
    for p in sorted(d.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        scanned += 1
        styles = data.get("styles")
        if isinstance(styles, dict):
            per_species.append({str(name) for name in styles})
            for name in styles:
                counts[str(name)] = counts.get(str(name), 0) + 1
    return counts, scanned


def zoo_species_styles(repo: str | Path | None) -> list[set[str]]:
    """One set of style names per species, for asking resolution PER SPECIES.

    `zoo_styles` aggregates, and aggregating loses the answer here: on the
    shipped genome 42 of 56 species carry `delco`, 14 carry `1990s` and NONE
    carries both, so `delco_1997` resolves for all 56 while any single
    map-level style name accounts for at most 42. Zoo asks the question of one
    species at a time and so does this.
    """
    out: list[set[str]] = []
    if not repo:
        return out
    d = Path(repo) / "zoo_keeper" / "genome" / "species"
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        styles = data.get("styles")
        if isinstance(styles, dict):
            out.append({str(name) for name in styles})
    return out


def zoo_style_for(theme: str, styles: dict[str, int]) -> str | None:
    """The style name Zoo will actually use for `theme`, or None.

    MIRRORS `zoo_keeper/core/dna.py::theme_style`, and mirroring is a cost paid
    on purpose. Level Factory cannot import Zoo -- it reads tool checkouts, it
    does not run them -- and the alternative was to keep reporting a gap that
    had been closed.

    THAT IS NOT HYPOTHETICAL. Zoo 0.57.0 taught the theme path the fallback its
    prompt path always had, taking `delco_1997` from 0 of 56 species to 56 of
    56 without a single new style being authored for it. This module went on
    reading the raw KEYS, so cold run 9004's pre-flight said "no species carry
    a 'delco_1997' style (56 scanned) -- the kit falls back to flat colour" of
    a kit that resolves it everywhere. Under-reporting a closed gap is how one
    gets closed twice.

    The rule, widest first, exactly as Zoo applies it:

      1. the exact name;
      2. the name minus a trailing qualifier -- `delco_1997` -> `delco`;
      3. that qualifier read as a DECADE -- `_1997` -> `1990s`.

    `species_with_style` beside this stays the LITERAL count, so a reader can
    still see that nothing carries the name itself. `test_theme_zoo_resolution`
    runs this against Zoo's own implementation over the shipped species corpus
    and fails when the two disagree, which is the only thing that keeps a
    mirrored rule honest.
    """
    name = (theme or "").strip()
    if not name or not styles:
        return None
    if name in styles:
        return name
    head, _, tail = name.rpartition("_")
    if head:
        if head in styles:
            return head
        if tail.isdigit() and len(tail) == 4:
            decade = f"{int(tail) // 10 * 10}s"
            if decade in styles:
                return decade
    return None


def theme_kinds(repo: str | Path | None, theme: str) -> set[str] | None:
    """The material KINDS `<theme>.json` maps, or None when it cannot be read.

    None and `set()` are different answers and the caller must be able to tell
    them apart: a profile that is absent, unparseable or carries no
    `materials` object has not said it maps nothing, it has said nothing. Both
    of the last two return None deliberately -- an unrecognised shape FAILS
    here rather than resolving to an empty set that makes every kind look
    missing (or, with the comparison the other way round, makes none look
    missing).
    """
    path = pixelcoat_profile_path(repo, theme)
    if path is None or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    materials = data.get("materials")
    if not isinstance(materials, dict):
        return None
    return {str(k) for k in materials}


def shell_kinds(slots_paths) -> tuple[dict[str, list[str]], list[str]]:
    """(kind -> the shells asking for it, shells that could not be read).

    READ OFF ONE REAL ARTEFACT before this was written --
    `deli_counter/build/card_shop_a01.slots.json`, whose top level is
    `slot_manifest_version / building_id / theme / module_library /
    module_size / space / coverage / slots` and whose every slot carries a
    `material` that is ALREADY a kind (Deli Counter ran it through
    `material_kind.kind_for` before writing). 189 slots, 16 distinct kinds,
    19 of them `wood_panel` and 2 `slatwall` -- which is exactly the count of
    `_mwood_panel` / `_mslatwall` modules cold run 9061's `site.tscn`
    instanced, so this file and the scene agree about the same 21 surfaces.

    A manifest with no `slots` LIST is reported in the second return value,
    not treated as a shell that asks for nothing. The difference is the whole
    point: a shell that asks for nothing passes any coverage check ever
    written, and a schema this function did not recognise must say so.
    """
    kinds: dict[str, list[str]] = {}
    unreadable: list[str] = []
    for entry in slots_paths or []:
        if isinstance(entry, (tuple, list)):
            shell_id, path = str(entry[0]), Path(str(entry[1]))
        else:
            path = Path(str(entry))
            shell_id = path.name[: -len(".slots.json")] \
                if path.name.endswith(".slots.json") else path.stem
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            unreadable.append(f"{shell_id}: cannot read {path}")
            continue
        slots = data.get("slots")
        if not isinstance(slots, list):
            unreadable.append(
                f"{shell_id}: {path.name} has no 'slots' list "
                f"(keys: {', '.join(sorted(map(str, data)))[:120]})")
            continue
        for slot in slots:
            if not isinstance(slot, dict):
                continue
            kind = slot.get("material")
            if not kind:
                continue
            kinds.setdefault(str(kind), [])
            if shell_id not in kinds[str(kind)]:
                kinds[str(kind)].append(shell_id)
    return kinds, unreadable


def kind_coverage(repo: str | Path | None, theme: str, slots_paths) -> dict:
    """Does every kind the SHELLS ask for resolve to a pack in `theme`?

    The defect this exists for, measured on cold run 9061's package
    (`_runs/walk_export_card_block_001`): Pixelcoat 0.44.0 added
    `wood_panel_delco` and `slatwall_retail` and mapped them in a new
    `card_shop` theme only. The mission ran on `delco_1997`, which mapped
    neither kind, so `lot/card_shop_a01/site.tscn` instanced 21 modules whose
    stems end `_mwood_panel` or `_mslatwall` and Zoo's `find_pack` returned
    None for every one of them. Of the 11 kinds that package's GLBs carry,
    those two are the ONLY ones whose kind-named material has no
    `baseColorTexture` -- the card shop's panelling, its pack walls and its
    display cases shipped flat, in a package that passed every gate. The
    walker photographed it from the shop floor.

    Nothing here is new machinery. `<id>.slots.json` is the same manifest
    `building_library.index` already requires of every placeable shell, and
    the theme profile is the same file `resolve` already stats.

    `checked` is False when the question could not be asked -- no profile, or
    no shells handed in (a single-shell mission builds its shell during the
    run, so at pre-flight time there is no manifest to read). A question that
    was not asked is not an answer of yes.
    """
    have = theme_kinds(repo, theme)
    asked, unreadable = shell_kinds(slots_paths)
    if have is None or not asked:
        return {"checked": False, "ok": True, "theme": theme,
                "kinds_in_theme": sorted(have) if have else [],
                "kinds_asked": sorted(asked), "shells": len(
                    {s for shells in asked.values() for s in shells}),
                "missing": {}, "unreadable": unreadable,
                "why": ("no theme profile to read" if have is None
                        else "no shell manifests to read")}
    missing = {k: sorted(v) for k, v in sorted(asked.items()) if k not in have}
    return {"checked": True, "ok": not missing and not unreadable,
            "theme": theme,
            "kinds_in_theme": sorted(have), "kinds_asked": sorted(asked),
            "shells": len({s for shells in asked.values() for s in shells}),
            "missing": missing, "unreadable": unreadable, "why": ""}


def resolve(theme: str, repositories: dict, shells=None) -> dict:
    """What the installed tools will do with `theme`.

    `ok` is False when Pixelcoat cannot resolve the theme at all, and -- when
    `shells` is given -- when the theme resolves but a kind those shells ask
    for does not. Both stop a run for the same reason: the art pass has
    nothing to skin with. The difference is that the second one used to stop
    it silently, by shipping the surface flat.

    `shells` is `(shell_id, <id>.slots.json path)` pairs, or bare paths.
    Omitted, the kind check is not performed and `ok` keeps its old meaning
    exactly -- which is what every caller that has not been taught to hand
    them in still gets.
    """
    pc_repo = (repositories or {}).get("pixelcoat", "")
    zoo_repo = (repositories or {}).get("zoo", "")

    available = pixelcoat_themes(pc_repo)
    profile = pixelcoat_profile_path(pc_repo, theme)
    pc_ok = bool(theme) and profile is not None and profile.is_file()

    styles, species = zoo_styles(zoo_repo)
    carried = styles.get(theme, 0)
    # ASKED PER SPECIES, the way Zoo asks it -- see `zoo_species_styles`.
    per_species = zoo_species_styles(zoo_repo)
    carried_resolved = sum(
        1 for names in per_species
        if zoo_style_for(theme, {n: 1 for n in names}) is not None)

    kinds = kind_coverage(pc_repo, theme, shells)

    return {
        "theme": theme,
        "ok": pc_ok and kinds["ok"],
        "kinds": kinds,
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
            # What Zoo will ACTUALLY use, which is not the same question.
            "species_with_resolved_style": carried_resolved,
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

    # WHAT THE SHELLS ASK FOR, which is the half that shipped flat. A theme
    # profile existing says the art pass will run; it says nothing about
    # whether the surfaces in the buildings this mission places have a pack to
    # resolve to. Cold run 9061's `delco_1997` profile was present and 21
    # modules still came out untextured.
    kinds = res.get("kinds") or {}
    if kinds.get("checked"):
        n_shell = kinds.get("shells", 0)
        n_kind = len(kinds.get("kinds_asked") or [])
        if kinds.get("ok"):
            out.append(f"            kinds: all {n_kind} asked for by "
                       f"{n_shell} shell(s) resolve in '{theme}'")
        else:
            for kind, shells in (kinds.get("missing") or {}).items():
                out.append(f"            kinds: NO '{kind}' PACK in theme "
                           f"'{theme}' — asked for by "
                           + ", ".join(shells[:4])
                           + (f" (+{len(shells) - 4} more)"
                              if len(shells) > 4 else ""))
            for line in kinds.get("unreadable") or []:
                out.append(f"            kinds: UNREADABLE SHELL {line}")
    elif kinds:
        out.append(f"            kinds: not checked — {kinds.get('why')}")

    if zoo.get("configured"):
        n = zoo.get("species_with_style", 0)
        total = zoo.get("species_scanned", 0)
        # WHAT ZOO WILL USE, not what it spells. Zoo resolves a theme name to
        # the style a species carries, so the literal count answers a question
        # nobody asked -- it read "no species carry a 'delco_1997' style
        # (56 scanned) — the kit falls back to flat colour" of a kit that
        # resolves it on all 56.
        resolved = zoo.get("species_with_resolved_style", n)
        if resolved == 0:
            out.append(f"            zoo: no species resolve a '{theme}' style "
                       f"({total} scanned) — the kit falls back to flat colour")
        elif total and resolved < total:
            out.append(f"            zoo: {resolved} of {total} species resolve "
                       f"'{theme}'")
        else:
            out.append(f"            zoo: all {total} species resolve '{theme}'")
        if resolved and n != resolved:
            out.append(f"            zoo: {n} carry the name itself; the rest "
                       f"reach it through Zoo's own fallback")
    return out
