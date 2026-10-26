"""A top-down plan of each layout, drawn from the build that made it (the factory's roadmap 314).

THE SOURCE IS THE CANDIDATE'S OWN SITE. Lot's shell leg writes ``site.site.drawn.json`` into each candidate's
``lot_assemble`` job; the plan reads the newest attempt's copy -- the attempt `pick` numbers the same way -- and
nothing else, so the picture and the row beside it describe one build. The SVG names that file and its SHA-256, and
a plan whose source is missing is not drawn: the row says so rather than showing another build's picture.

WHAT IS DRAWN, in site metres with north up (Lot's fronts face ``S``, toward lower y): the ground, roads with their
sidewalks, parking fields, the buildings the level uses (the objective outlined and labelled), the empty blockers,
cover as dots (its yaw convention is not read here, so no rectangle is claimed), and the crew spawn, extraction and
responder markers, and a 10 m bar in the bottom-left corner. NO TEXT: Godot's SVG loader draws no ``<text>``
(measured: labels and key came out blank in the first render), so the key is `KEY`, which the panel shows beside the
picture, and a building's name is the row's. A building's rectangle is `site_extent.rotated_footprint`'s: right angles swap the axes, any other
angle is its enclosing box, so the drawing is never smaller than the building.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from html import escape
from pathlib import Path

PX = 4.0                       # pixels per site metre
MARGIN = 6.0                   # metres of paper round the ground
_SEED = re.compile(r"seed_(\d+)$")
COLOURS = {"ground": "#3b4038", "road": "#24262a", "walk": "#6d6f72", "field": "#4a4d55", "building": "#c9b48f",
           "objective": "#e0533d", "blocker": "#7c7f84", "cover": "#9fd3ff", "spawn": "#5fd068",
           "extraction": "#f2c94c", "responder": "#4f8cff", "text": "#f4f1ea"}


def drawn_site(internal_dir: Path, mission_id: str, seed: int) -> Path | None:
    """The newest attempt's ``site.site.drawn.json`` for one candidate, or None when the build left none."""
    from packages.pipeline.pick import _newest
    job = Path(internal_dir) / "jobs" / ("%s.lot_assemble.candidate.seed_%d" % (mission_id, seed))
    return _newest(list(job.glob("*/out/site.site.drawn.json")))


def _rect(at, sx, sy, rot=0.0):
    """``(x0, y0, x1, y1)`` in site metres, rotated as `site_extent.rotated_footprint` rotates a footprint."""
    rot = (float(rot or 0) % 360 + 360) % 360
    if rot % 180 == 90:
        sx, sy = sy, sx
    elif rot % 90 != 0:
        th = math.radians(rot)
        sx, sy = (abs(sx * math.cos(th)) + abs(sy * math.sin(th)), abs(sx * math.sin(th)) + abs(sy * math.cos(th)))
    x, y = float(at[0]), float(at[1])
    return x - sx / 2, y - sy / 2, x + sx / 2, y + sy / 2


KEY = ("Green: crew spawn. Yellow: extraction. Blue: responders. Light blue dots: cover. Tan: the level's "
       "buildings, the objective outlined red. Grey: empty buildings. The bar is 10 m; north is up.")


def svg(site: dict, source: str = "", digest: str = "") -> str:
    """The plan as SVG text. Raises ValueError when the site has no ground to frame it."""
    try:
        gx, gy = float(site["ground"]["size_x"]), float(site["ground"]["size_y"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("the site has no ground size") from None
    x0, y1 = -gx / 2 - MARGIN, gy / 2 + MARGIN
    w, h = (gx + 2 * MARGIN) * PX, (gy + 2 * MARGIN) * PX
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (w, h, w, h),
           "<!-- plan of %s, drawn from %s (sha256 %s) -->" % (escape(str(site.get("site_id", "?"))),
                                                              escape(source), digest),
           '<rect width="%d" height="%d" fill="#1b1d1f"/>' % (w, h)]

    def px(x, y):
        return (x - x0) * PX, (y1 - y) * PX

    def box(r, fill, stroke="none", sw=0.0, opacity=1.0):
        ax, ay = px(r[0], r[3])
        out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" stroke="%s" stroke-width="%.1f" '
                   'fill-opacity="%.2f"/>' % (ax, ay, (r[2] - r[0]) * PX, (r[3] - r[1]) * PX, fill, stroke, sw,
                                              opacity))

    def segment(a, b, width, colour):
        (ax, ay), (bx, by) = px(*a), px(*b)
        out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="%.1f" '
                   'stroke-linecap="butt"/>' % (ax, ay, bx, by, colour, width * PX))

    def dot(at, r, colour):
        cx, cy = px(float(at[0]), float(at[1]))
        out.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s"/>' % (cx, cy, r, colour))

    box((-gx / 2, -gy / 2, gx / 2, gy / 2), COLOURS["ground"])
    for road in site.get("roads") or []:
        segment(road["a"], road["b"], float(road.get("width", 0)) + 2 * float(road.get("sidewalk", 0)), COLOURS["walk"])
    for road in site.get("roads") or []:
        segment(road["a"], road["b"], float(road.get("width", 0)), COLOURS["road"])
    for d in site.get("driveways") or []:
        segment(d["a"], d["b"], float(d.get("width", 0)), COLOURS["road"])
    for f in site.get("fields") or []:
        r = f.get("rect")
        if r and len(r) == 4:
            box(r, COLOURS["field"])
    for b in site.get("blockers") or []:
        try:
            box(_rect(b["at"], float(b["size_x"]), float(b["size_y"]), b.get("rot")), COLOURS["blocker"])
        except (KeyError, TypeError, ValueError):
            continue
    objective = site.get("objective")
    for b in site.get("buildings") or []:
        fp = b.get("_footprint") or b.get("footprint")
        if not fp or not b.get("at"):
            continue
        r = _rect(b["at"], float(fp[0]), float(fp[1]), b.get("rot"))
        is_obj = b.get("id") == objective
        box(r, COLOURS["building"], COLOURS["objective"] if is_obj else "#5a5040", 3.0 if is_obj else 1.0)
    for c in site.get("cover") or []:
        if c.get("at"):
            dot(c["at"], 2.2, COLOURS["cover"])
    kinds = {"crew_spawn": "spawn", "extraction": "extraction", "responder_spawn": "responder"}
    for m in site.get("site_markers") or []:
        kind = kinds.get(m.get("type"))
        if kind and m.get("at"):
            dot(m["at"], 7.0 if kind != "extraction" else 5.0, COLOURS[kind])
    y = h - MARGIN * PX / 2                # the 10 m bar, in the margin below the ground
    out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="3"/>'
               % (MARGIN * PX, y, (MARGIN + 10) * PX, y, COLOURS["text"]))
    out.append("</svg>")
    return "\n".join(out) + "\n"


def write_plans(internal_dir: Path, mission_id: str, candidates: list[dict], into: Path) -> None:
    """Draw each candidate's plan into ``into/<candidate seed>.svg`` and set the row's ``plan`` to its path, or to
    None with ``plan_problem`` saying why. Rows are changed in place."""
    into = Path(into)
    for row in candidates:
        row["plan"], row["plan_problem"] = None, None
        src = drawn_site(internal_dir, mission_id, int(row["seed"]))
        if src is None:
            row["plan_problem"] = "the build left no drawn site for this layout"
            continue
        raw = src.read_bytes()
        try:
            text = svg(json.loads(raw.decode("utf-8")), str(src), hashlib.sha256(raw).hexdigest())
        except (ValueError, UnicodeDecodeError) as exc:
            row["plan_problem"] = "the drawn site cannot be read: %s" % exc
            continue
        into.mkdir(parents=True, exist_ok=True)
        dest = into / ("seed_%d.svg" % int(row["seed"]))
        tmp = dest.with_name(".%s.tmp" % dest.name)
        tmp.write_text(text, encoding="utf-8", newline="\n")
        tmp.replace(dest)
        row["plan"] = str(dest)
