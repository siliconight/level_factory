"""Does a themed package still draw greybox? The gate over what theming MISSED.

WHAT THIS EXISTS FOR, stated plainly because it is the point of the roadmap
item it closes (168): every other gate in this exporter measures traversal
correctness or resource closure -- can a body get from A to B, does every
`res://` reference resolve. None of them measures whether the result reads as
DESIGNED rather than generated, and the defect that produced this module was
found by a person on a ladder, not by an instrument.

THE DEFECT. `deli_counter._slab_holes_cut` boolean-subtracts a ladder shaft or
a stairwell from a structural slab. Theming skins a slab's TOP (as a floor)
and its BOTTOM (as a ceiling) and never touches the faces the hole CREATES, so
a `floor_thick`-deep collar of flat `gb_floor` rings every opening -- 1.44 m2
around a 1.10 x 1.30 m ladder hole, which is the same area as the opening it
surrounds and therefore fills the view from anywhere but straight down. Cold
run 9070's package carried 8 cut slabs and 10.44 m2 of it.

IT WAS NOT NEW AND IT WAS NOT THE PERFORMANCE PASS, which is worth recording
because that was the first guess. Every package measured back to
`walk_export_county_hospital_001` (2026-09-11, before any of that work) ships
`[('gb_floor', False)]` on its slabs. What changed is that cold run 9070 is
the first package since Zoo 1.2.0 to ship the textures its GLBs name: before
it, the greybox regression made everything grey and a grey collar was
unremarkable. Fixing the textures left it as the only untextured thing in
view. The pass revealed it rather than causing it.

WHY IT RUNS IN THE ENGINE. `zoo_worldskin.gd` is an IMPORT post-processor, so
a shipped GLB keeps its `gb_*` materials by design and the skin lives on the
imported resource. A gate reading glTF JSON would refuse every package ever
built while measuring the wrong artefact. See `assets/godot/greybox_census.gd`,
which owns the measurement; this module owns the verdict.

WHAT IT REFUSES, AND WHAT IT MERELY REPORTS -- the distinction matters, and
getting it wrong would have turned this gate into an intervention generator.
Measured on 9070's package before the threshold was chosen: 412 surfaces carry
a `gb_*` material, of which 346 are `gb_floor` (essentially all slabs), 28
`gb_wall` and 38 `gb_ladder`.

  * REFUSES on a greybox SLAB in a themed package. After the worldskin's slab
    pass a greybox slab can only mean that pass failed, so this is a
    regression detector with a real zero.
  * REPORTS the rest. A greybox ladder is not a regression -- nothing has ever
    skinned one -- it is a capability the toolchain does not have yet. Making
    it refuse would block every export over work nobody has done, and the
    honest move is to put the number where it can be seen and tracked.

AREA IS TOTAL MESH SURFACE AREA, NOT VISIBLE AREA. `gb_floor` reports 17,447
m2 on that package and almost all of it is slab faces buried under a themed
floor and ceiling; the walker saw 10.44 m2. The census docstring says this at
length. The refusal keys on the SURFACE COUNT for exactly that reason.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

_LF_ROOT = Path(__file__).resolve().parents[2]
CENSUS_SCRIPT = _LF_ROOT / "assets" / "godot" / "greybox_census.gd"
REPORT_NAME = "greybox_skin_scan.json"
SCHEMA = "greybox_census/1"


class GreyboxCensusError(RuntimeError):
    """The census could not be taken. Not the same as a clean package."""


class GreyboxSkinError(RuntimeError):
    """A themed package draws greybox where theming claims to reach."""


def measure(export_dir, godot_executable, *, script: Path = CENSUS_SCRIPT,
            timeout: int = 900) -> dict:
    """Run the census in the engine and return its report.

    The report is the evidence, not the exit code. A report that does not
    parse, or whose schema is not the one this module knows, RAISES rather
    than reading as a package with no greybox in it -- the failure written up
    in CLAUDE.md, where a `--verify` looked for keys an artefact did not have,
    turned their absence into an empty problem list with `or []`, and printed
    "closure verdict clean" three lines under the exporter shouting that 21
    resources were unresolved.
    """
    from packages.exporting import occluders

    export_dir = Path(export_dir)
    report_path = export_dir / REPORT_NAME
    if not godot_executable:
        raise GreyboxCensusError(
            "no Godot executable: the greybox census cannot be taken")
    if not Path(script).is_file():
        raise GreyboxCensusError(f"census script missing: {script}")
    # LEAVE THE PACKAGE AS THIS FOUND IT, and the cost of not doing so is
    # why this comment is long. Taking the census needs an import cache; the
    # exporter has ALREADY removed one by this point ("import cache removed;
    # the package ships sidecars, not .godot") and the closure verdict three
    # steps below scans every file in the package. Cold run 9071's export died
    # exit 5 -- EXPORT_CLOSURE_BROKEN on `.godot/editor/project_metadata.cfg`
    # holding an absolute path to the Godot binary -- because the first
    # version of this module re-imported and walked away. The package shipped
    # without its manifests and the run was misread as a zero.
    had_cache = (export_dir / ".godot").exists()
    occluders.ensure_imported(export_dir, godot_executable)
    bundled = export_dir / Path(script).name
    bundled.write_bytes(Path(script).read_bytes())
    try:
        subprocess.run(
            [str(godot_executable), "--headless", "--path", str(export_dir),
             "--script", f"res://{Path(script).name}", "--",
             f"res://{REPORT_NAME}"],
            capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        raise GreyboxCensusError(f"census did not run: {exc}") from exc
    finally:
        bundled.unlink(missing_ok=True)
        if not had_cache:
            occluders.drop_cache(export_dir)

    if not report_path.is_file():
        raise GreyboxCensusError("census wrote no report")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GreyboxCensusError(f"report unreadable: {exc}") from exc
    if not isinstance(report, dict) or report.get("schema") != SCHEMA:
        raise GreyboxCensusError(
            f"report schema is {report.get('schema')!r}, not {SCHEMA!r}")
    for key in ("themed", "greybox_surfaces", "slab_surfaces", "by_role"):
        if key not in report:
            raise GreyboxCensusError(f"report carries no {key!r}")
    if report.get("error"):
        raise GreyboxCensusError(f"census failed: {report['error']}")
    report["nothing_to_check"] = not bool(report["themed"])
    # Said out loud rather than trusted: if the cache this created is still
    # there, the closure verdict below will refuse the package and the reason
    # will read as somebody else's defect.
    if not had_cache and (export_dir / ".godot").exists():
        raise GreyboxCensusError(
            "the census left a .godot import cache in the package; the "
            "closure verdict will refuse it")
    return report


def summary(report: dict) -> str:
    """One line for the export log. Says which question it answered."""
    if report.get("nothing_to_check"):
        return ("this package carries no M_Skin_* material, so no theming was "
                "applied and its greybox is the product rather than a defect")
    roles = report.get("by_role") or {}
    parts = ", ".join(
        "%s %d" % (name, int(row["surfaces"]))
        for name, row in sorted(roles.items(),
                                key=lambda kv: -int(kv[1]["surfaces"])))
    return ("%d surface(s) on a greybox material (%s); slabs %d -- the class "
            "this gate refuses on"
            % (int(report["greybox_surfaces"]), parts or "none",
               int(report["slab_surfaces"])))


def assert_skinned(export_dir, report: dict) -> dict:
    """Raise `GreyboxSkinError` when a themed package draws a greybox slab.

    Only slabs. The reasoning, and the census that set the threshold, are in
    this module's docstring: a greybox ladder is an absent capability and
    refusing over it would block every export on work nobody has done.
    """
    if report.get("nothing_to_check"):
        return report
    bad = int(report.get("slab_surfaces", 0))
    if not bad:
        return report
    worst = [w for w in (report.get("worst") or [])
             if str(w.get("node", "")).rsplit("/", 1)[-1].startswith("slab_")]
    lines = [
        "GREYBOX_SLAB_IN_A_THEMED_PACKAGE: %d slab surface(s) still carry a "
        "greybox material" % bad,
        "  a slab's cut edge lines every ladder shaft and stairwell in the "
        "level, so this ships as a bare grey collar around each opening",
        "  the worldskin's slab pass (`_skin_slabs`) either did not run or "
        "could not find a pack -- its own log line says which, and it "
        "push_error()s when it cannot",
    ]
    for w in worst[:6]:
        lines.append("    %s  on %s" % (w.get("node"), w.get("material")))
    lines.append("  full report: %s"
                 % (Path(export_dir) / REPORT_NAME))
    raise GreyboxSkinError("\n".join(lines))
