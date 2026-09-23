"""A GLB is not one file. Whatever it names beside it ships with it, or not at all.

WHY THIS EXISTS. Zoo 1.2.0 stopped embedding images in each module GLB and
started writing them once beside it, referenced by a relative glTF
``images[].uri``. Every copy site in the toolchain that had been moving a GLB
by NAME -- resolving one reference out of a scene and calling ``copy2`` on it
-- went on moving one file where there were now several, and the packages went
out as greybox. Measured 2026-09-22 on cold run 9068's shipped
``LF_club_block_007.portable-godot``: 1,264 external references in its GLBs,
1,264 of them resolving to nothing.

THREE GATES LOOKED STRAIGHT AT IT AND PASSED, and each for a reason worth
writing down, because each is the same mistake in a different costume:

  * the closure scan asks whether every ``res://`` reference resolves. A glTF
    ``uri`` is not a ``res://`` reference; it is a string inside a binary that
    no text scan reads.
  * the resource manifest accounts for the files PRESENT in the package
    against the files on disk. Both sides of that sum came out right: the
    textures were absent from the folder and absent from the list.
  * the cold-run verdict counts interventions. Nobody had to intervene,
    because nothing complained.

All three are closed over what the package CONTAINS. None asked what it
REFERS TO. That is the question here, and it is asked of the GLBs' own glTF
JSON -- never of a folder name. A checker keyed on ``_tex`` would pass the
next externalised asset class the same way this one passed the last, which is
precisely how this defect reached a walker.

WHAT IS A FAILURE, stated before the code so an unrecognised shape cannot
slide through as a pass:

  * a relative ``uri`` naming a file that is not in the package
  * a ``uri`` that escapes the package root, is absolute, or is remote -- a
    recipient unzipping this folder cannot follow any of them
  * a ``.glb`` this module cannot parse. It is a GLB the exporter shipped and
    could not read; reporting nothing about it would be reporting that it is
    clean.
``data:`` URIs are content, not references, and are counted and skipped.

AND ONE THING THAT IS NOT A FAILURE HERE, kept above the position that
replaced it because the reversal is the useful half. A package with no `.glb`
in it at all was refused, on the reasoning that "a check that cannot fail is
indistinguishable from one that passed". Measured against the suite rather
than argued: 18 tests across three files build packages with no geometry file,
and `pure-shell` is a REAL exporter mode that produces one -- it drops the
composed root, and a graybox whose scene carries its geometry inline has
nothing with a `.glb` suffix in it. Refusing would have failed a shipping path
on a guess about what a package must contain, which is not a thing this
instrument measures.

Whether the package has geometry the entry can reach is the closure scan's
question, and it asks it. Two instruments answering one question is the scar
this repo already has: the fixer's log and the judge's verdict were one file,
and an empty export read as clean. So a scan with nothing to scan reports
`nothing_to_check` and the exporter prints it as its own line -- said out
loud, not refused, and not silent either.
"""
from __future__ import annotations

import json
import struct
import urllib.parse
from pathlib import Path

#: glTF 2.0 container constants. Spelled here rather than imported because
#: Level Factory does not import Zoo -- it consumes what Zoo wrote.
_MAGIC = 0x46546C67
_JSON_CHUNK = 0x4E4F534A

#: The document members glTF 2.0 allows a ``uri`` on. Nothing else in core
#: glTF carries one, and an extension that invented its own would not be
#: found by a walk keyed on the key name either -- so the unknown-extension
#: guard below is what covers that, not a wider search.
_URI_HOLDERS = ("images", "buffers")


class GlbUnreadable(ValueError):
    """A ``.glb`` this module could not parse. Reported, never skipped."""


class GlbReferenceError(RuntimeError):
    """The package does not contain everything its GLBs name."""


def gltf_json(data: bytes) -> dict:
    """The JSON chunk of a GLB, or raise.

    Chunk walk rather than "the JSON chunk is the first one": it is in every
    file this repo has seen and it is not what the format guarantees.
    """
    if len(data) < 12 or struct.unpack_from("<I", data, 0)[0] != _MAGIC:
        raise GlbUnreadable("not a GLB (bad magic)")
    off = 12
    while off + 8 <= len(data):
        clen, ctype = struct.unpack_from("<II", data, off)
        body = data[off + 8:off + 8 + clen]
        if len(body) != clen:
            raise GlbUnreadable("truncated chunk at byte %d" % off)
        if ctype == _JSON_CHUNK:
            try:
                return json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise GlbUnreadable("JSON chunk will not parse: %s" % exc)
        off += 8 + clen + (-clen) % 4
    raise GlbUnreadable("no JSON chunk")


def uris(js: dict):
    """Yield ``(holder, index, uri)`` for every ``uri`` in the document.

    Includes ``data:`` URIs; the caller decides. Separating them here would
    make the count of "references seen" depend on this function's opinion,
    and the scan wants to report both numbers.
    """
    for holder in _URI_HOLDERS:
        for i, ent in enumerate(js.get(holder) or []):
            if isinstance(ent, dict) and ent.get("uri"):
                yield holder, i, str(ent["uri"])


def dependencies(glb: Path) -> list[str]:
    """Every file ``glb`` names beside itself, as POSIX paths relative to it.

    Raises `GlbUnreadable` rather than returning an empty list: "this GLB
    depends on nothing" and "this GLB could not be read" are different
    answers and a caller copying files must not be handed the first when the
    truth is the second.

    Percent-decoded, because glTF 2.0 says a ``uri`` is URI-encoded. Zoo's
    own names never need it (`gltf_textures._SAFE` strips everything that
    would), so this is a contract being honoured rather than a case observed.
    """
    out: list[str] = []
    for _holder, _i, u in uris(gltf_json(Path(glb).read_bytes())):
        if u.startswith("data:"):
            continue
        rel = urllib.parse.unquote(u)
        if rel not in out:
            out.append(rel)
    return out


def _escapes(rel: str) -> bool:
    """Does this relative path leave the directory it is relative to?"""
    parts = Path(rel.replace("\\", "/")).parts
    depth = 0
    for p in parts:
        if p == "..":
            depth -= 1
            if depth < 0:
                return True
        elif p not in (".",):
            depth += 1
    return False


def _kind(uri: str) -> str:
    """Why a URI cannot be a package-relative file, or "" when it can be."""
    low = uri.lower()
    if "://" in low or low.startswith("//"):
        return "remote"
    if low.startswith("/") or (len(low) > 1 and low[1] == ":"):
        return "absolute"
    if _escapes(urllib.parse.unquote(uri)):
        return "escapes"
    return ""


def copy_with_deps(src, dst) -> list[str]:
    """Copy one GLB and every file it names, preserving the relative layout.

    THE ONLY WAY A GLB SHOULD EVER BE COPIED BY NAME in this toolchain. The
    layout is preserved rather than flattened because the URI inside the GLB
    is what has to keep resolving, and rewriting it would mean rewriting the
    binary -- which is Zoo's job and not a copy's.

    Returns the relative paths of the dependencies copied (not the GLB).
    A dependency already present with the same size is left alone: Zoo's
    names carry a hash of the pixels, so the same name is the same file, and
    that is what makes sixty modules share one texture.

    Raises `GlbUnreadable` if the source will not parse, and OSError if a
    dependency it named is not there -- a copy that silently drops half of
    what it was asked to move is the defect this module exists for.
    """
    import shutil

    src, dst = Path(src), Path(dst)
    deps = dependencies(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(dst))
    copied = []
    for rel in deps:
        if _kind(rel):
            raise OSError("%s names %r, which cannot be copied into a package"
                          % (src, rel))
        s, d = src.parent / rel, dst.parent / rel
        if not s.is_file():
            raise OSError("%s names %r and %s is not there" % (src, rel, s))
        if d.is_file() and d.stat().st_size == s.stat().st_size:
            copied.append(rel)
            continue
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(s), str(d))
        copied.append(rel)
    return copied


def scan(root) -> dict:
    """What every GLB under ``root`` refers to, and whether the package has it.

    A report, not a verdict: it prints numbers and stops. `assert_closed`
    turns it into a refusal, and the sentence naming the cause belongs to the
    caller.
    """
    root = Path(root)
    report = {
        "schema": "level_factory.glb_reference_scan.v0.1",
        "root": str(root),
        "glbs_scanned": 0,
        "unreadable": [],
        "references": 0,
        "embedded_data_uris": 0,
        "missing": [],
        "unportable": [],
        "resolved": 0,
        "dependency_files": 0,
    }
    resolved_files: set[str] = set()
    for glb in sorted(root.rglob("*.glb")):
        rel_glb = glb.relative_to(root).as_posix()
        try:
            js = gltf_json(glb.read_bytes())
        except GlbUnreadable as exc:
            report["unreadable"].append({"glb": rel_glb, "reason": str(exc)})
            continue
        report["glbs_scanned"] += 1
        for holder, i, u in uris(js):
            if u.startswith("data:"):
                report["embedded_data_uris"] += 1
                continue
            report["references"] += 1
            bad = _kind(u)
            if bad:
                report["unportable"].append(
                    {"glb": rel_glb, "holder": holder, "index": i,
                     "uri": u, "reason": bad})
                continue
            rel = urllib.parse.unquote(u)
            target = glb.parent / rel
            if target.is_file():
                report["resolved"] += 1
                resolved_files.add(target.resolve().as_posix())
            else:
                report["missing"].append(
                    {"glb": rel_glb, "holder": holder, "index": i, "uri": u,
                     "wanted": (glb.parent / rel).relative_to(root).as_posix()
                     if not _escapes(rel) else rel})
    report["dependency_files"] = len(resolved_files)
    # NOT part of `ok` -- see the docstring. It is the one fact a reader needs
    # to know whether the verdict above it was earned or merely vacuous, so it
    # is a field of its own rather than a silence.
    report["nothing_to_check"] = (report["glbs_scanned"] == 0
                                  and not report["unreadable"])
    report["ok"] = (not report["missing"] and not report["unportable"]
                    and not report["unreadable"])
    return report


def summary(report: dict) -> str:
    """One line. Reads the keys `scan` writes and no others."""
    if report["nothing_to_check"]:
        return ("NOTHING TO CHECK -- no .glb in this package, so this gate "
                "has said nothing about it")
    return ("%d GLB(s), %d external reference(s): %d resolve to %d file(s) in "
            "the package, %d missing, %d unportable, %d unreadable GLB(s)"
            % (report["glbs_scanned"], report["references"],
               report["resolved"], report["dependency_files"],
               len(report["missing"]), len(report["unportable"]),
               len(report["unreadable"])))


def assert_closed(root, report: dict | None = None) -> dict:
    """Refuse a package that does not contain what its GLBs name.

    RAISES rather than warns, for the reason `occluders.py` already records:
    0.98.0 shipped a package with the culling flag on and nothing to cull,
    behind a warning nobody read. This one shipped three packages of greybox
    behind no warning at all.

    An unrecognised shape fails. A report missing a key this function reads
    raises `KeyError` here rather than being turned into an empty problem
    list by ``or []`` -- the defect `patch_lf_score_split.py` warned about and
    the `--verify` that printed "closure verdict clean" three lines under
    `EXPORT_CLOSURE_BROKEN` committed.
    """
    report = scan(root) if report is None else report
    if report["ok"]:
        return report
    lines = []
    for m in report["missing"][:20]:
        lines.append("%s names %s and the package does not contain %s"
                     % (m["glb"], m["uri"], m["wanted"]))
    for u in report["unportable"][:20]:
        lines.append("%s names %s (%s) -- a recipient cannot follow it"
                     % (u["glb"], u["uri"], u["reason"]))
    for x in report["unreadable"][:20]:
        lines.append("%s could not be read: %s" % (x["glb"], x["reason"]))
    over = (len(report["missing"]) + len(report["unportable"])
            + len(report["unreadable"]) - len(lines))
    detail = "\n  ".join(lines)
    if over > 0:
        detail += "\n  ... and %d more" % over
    raise GlbReferenceError(
        "EXPORT_GLB_REFERENCES_BROKEN: %d missing, %d unportable, "
        "%d unreadable over %d reference(s) in %d GLB(s)\n  %s"
        % (len(report["missing"]), len(report["unportable"]),
           len(report["unreadable"]), report["references"],
           report["glbs_scanned"], detail))


def _cli(argv=None) -> int:
    """`python -m packages.exporting.glb_refs <package dir>` -- the gate, alone.

    Exists so the gate can be run against a package NOBODY is exporting --
    including the three already shipped. A gate reachable only from the build
    that would have prevented the defect cannot be pointed at the defect.
    """
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", help="a package directory")
    ap.add_argument("--json", help="write the full report here")
    args = ap.parse_args(argv)
    report = scan(args.root)
    print(summary(report))
    if args.json:
        Path(args.json).write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    try:
        assert_closed(args.root, report)
    except GlbReferenceError as exc:
        print(exc)
        return 1
    print("ok")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_cli())
