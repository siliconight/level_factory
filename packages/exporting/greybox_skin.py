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

SINCE 0.218.0 IT REFUSES ANY GREYBOX ROLE in a themed package (factory
roadmap 168), because the reason it reported the rest has run out: every class
that census reported now has an owner -- ladders a worldskin pass (0.136.0),
roof parapets wall slots the composer dresses (Deli Counter 0.177.0), vault
ledges a worldskin pass (0.217.0) -- and every package exported since
2026-10-10 that drew greybox at all drew only vault ledges. A greybox surface
in a themed package now means a pass failed or base geometry of a new kind
arrived without one, and both are defects to see at the export rather than in
a walk. `ExportProfile.require_no_greybox = False` reports without refusing
(slabs only, as before), for a build that knowingly ships a new kind early.

THAT CLAIM WAS WRONG FOR TWO CLASSES, and is kept above the passes that
answered it (0.220.0). "Every class that census reported now has an owner"
rested on the packages exported since 2026-10-10, and no lot in that window
drew a shell carrying either. The factory's cold run 9342 (precinct_yard_001,
2026-10-20) was refused on apartment_walkup_a01's legacy fire escape --
`FIREESCAPE_*`, two surfaces on `gb_floor` -- which cold run 9172 had shipped,
reported and not refused, on 2026-10-06; and cold runs 9168, 9174 and 9177 had
shipped a garage's vehicle ramp (`ramp<n>`, on `gb_ramp`) the same way. A
census of every base in Deli Counter's library against the passes' name tests
(the factory's `docs/findings/base_greybox_owners/census.py`) found exactly
those two kinds in the shells a themed lot can draw -- one fire escape, five
ramps in four garages -- and each now has a worldskin pass.

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


def _engine_tail(proc, lines: int = 12) -> str:
    """The last few lines the engine printed, for an error message.

    A census that produced no report has ALREADY failed; the only useful thing
    left is what Godot said on the way out. Returns "" when there is nothing,
    so the caller's message reads cleanly either way.
    """
    if proc is None:
        return ""
    out = []
    for stream, label in ((getattr(proc, "stdout", ""), "stdout"),
                          (getattr(proc, "stderr", ""), "stderr")):
        for line in (stream or "").strip().splitlines()[-lines:]:
            out.append(f"    [godot {label}] {line}")
    return ("\n" + "\n".join(out)) if out else ""


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
    # why this comment is long. Taking the census needs an import cache. The
    # exporter keeps the bake's until this has run (0.181.0), so in an export
    # this finds one and imports nothing; called on a package without one it
    # imports, and then it must remove what it made, because the closure
    # verdict below it scans every file in the package. Cold run 9071's export died
    # exit 5 -- EXPORT_CLOSURE_BROKEN on `.godot/editor/project_metadata.cfg`
    # holding an absolute path to the Godot binary -- because the first
    # version of this module re-imported and walked away. The package shipped
    # without its manifests and the run was misread as a zero.
    had_cache = (export_dir / ".godot").exists()
    occluders.ensure_imported(export_dir, godot_executable)
    bundled = export_dir / Path(script).name
    bundled.write_bytes(Path(script).read_bytes())
    proc = None
    try:
        proc = subprocess.run(
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
        # SAY WHAT THE ENGINE SAID. This raised "census wrote no report" and
        # discarded the output that explains it, which is a probe failing
        # silently -- the reader is told the instrument produced nothing and
        # not why. The same shape cost a round-trip on tools/navmesh_demo.py,
        # where a one-line parse error hid behind that exact sentence.
        raise GreyboxCensusError(
            "census wrote no report (godot exit %s)%s"
            % (getattr(proc, "returncode", "?"), _engine_tail(proc)))
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


def summary(report: dict, any_role: bool = True) -> str:
    """One line for the export log. Says which question it answered."""
    if report.get("nothing_to_check"):
        return ("this package carries no M_Skin_* material, so no theming was "
                "applied and its greybox is the product rather than a defect")
    roles = report.get("by_role") or {}
    parts = ", ".join(
        "%s %d" % (name, int(row["surfaces"]))
        for name, row in sorted(roles.items(),
                                key=lambda kv: -int(kv[1]["surfaces"])))
    if any_role:
        return ("%d surface(s) on a greybox material (%s), %d of them slabs; "
                "any one is refused (require_no_greybox)"
                % (int(report["greybox_surfaces"]), parts or "none",
                   int(report["slab_surfaces"])))
    return ("%d surface(s) on a greybox material (%s); slabs %d -- the class "
            "this gate refuses on"
            % (int(report["greybox_surfaces"]), parts or "none",
               int(report["slab_surfaces"])))


def assert_skinned(export_dir, report: dict, any_role: bool = True) -> dict:
    """Raise `GreyboxSkinError` when a themed package draws a greybox slab, and
    -- with `any_role`, the default since 0.218.0 -- any greybox surface at all.

    A slab keeps its own message, because its cause is one pass. The reasoning
    for each threshold, and the census that set it, are in this module's
    docstring. `any_role=False` is the pre-0.218.0 verdict: slabs only.
    """
    if report.get("nothing_to_check"):
        return report
    bad = int(report.get("slab_surfaces", 0))
    if not bad:
        return _assert_no_greybox(export_dir, report) if any_role else report
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


def _assert_no_greybox(export_dir, report: dict) -> dict:
    """Raise `GreyboxSkinError` when a themed package draws any greybox
    surface (0.218.0). Called past the slab check, so slabs are 0 here."""
    bad = int(report.get("greybox_surfaces", 0))
    if not bad:
        return report
    roles = report.get("by_role") or {}
    lines = [
        "GREYBOX_IN_A_THEMED_PACKAGE: %d surface(s) still carry a greybox "
        "material (%s)" % (bad, ", ".join(
            "%s %d" % (name, int(row["surfaces"]))
            for name, row in sorted(roles.items())) or "no role named"),
        "  every kind of base geometry the census has met has an owner -- "
        "slabs, flights, ladders, vault ledges, fire escapes and vehicle "
        "ramps a worldskin pass, parapets a wall slot -- so this is a pass "
        "that failed (its own log line says which, and it push_error()s) or a "
        "new kind that arrived without one",
        "  a build that knowingly ships a new kind before its pass sets "
        "ExportProfile.require_no_greybox = False",
    ]
    for w in (report.get("worst") or [])[:6]:
        lines.append("    %s  on %s" % (w.get("node"), w.get("material")))
    lines.append("  full report: %s" % (Path(export_dir) / REPORT_NAME))
    raise GreyboxSkinError("\n".join(lines))
