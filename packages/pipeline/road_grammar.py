"""The ROAD GRAMMAR: what shape of street a site is laid out on.

WHY THIS EXISTS, and what it is not. `site_variation` decides where the
BUILDINGS go -- a walk that turns zero times (`row`), once (`L`) or three
times (`courtyard`). That axis has three options and, measured on a sweep at
matched seeds, it works: layout moves a plan 0.18-0.21 of the site diagonal
against 0.071-0.074 for a seed alone.

The ROAD had one option. `_street_for` emitted exactly two roads on every
site ever generated -- one along the plate's south edge and one cross street
running north from it, a T -- and it derived them FROM the buildings, after
they were placed. So of the level shapes a person would name (a main street, a
T-junction, a crossroads, parallel streets, an alley spine), this factory
built the second one, every time, and could not be asked for another.

LOT IS ALREADY READY FOR MORE, which is what makes this cheap.
`lot.site_streets.roads()` takes an arbitrary road list and resolves it:
road-to-road crossings found from geometry, `_slab` for a road that ENDS on
another (a T), `gaps` for a road that passes THROUGH one (an X), with kerbs,
dropped-kerb cuts, crosswalk bars, stop bars and stop signs computed per road
against docs/STREET_RULES.md. Nothing in Lot or Level Factory assumes a road
count -- checked. Lot's X handling has therefore never fired on a generated
level, because nothing has ever emitted an X.

THE DEPENDENCY IS STILL BUILDINGS -> ROADS, and that is the next step rather
than this one. A grammar here reads the placed buildings and lays streets to
suit them. The configurations that need the reverse -- a road graph first,
with buildings hung off it -- need `site_variation` and this module to swap
places, and doing that in the same change as introducing the vocabulary would
make an equivalence proof impossible. So: vocabulary first, inversion second.

`T` IS THE EXISTING FUNCTION, MOVED AND NOT REWRITTEN. `layout_offsets`
delegates `row` to `row_offsets` for the same reason -- one implementation, so
the line a thousand existing candidates stand on cannot drift away from the
line this module draws. `tests/unit/test_road_grammar.py` asserts T against
the old implementation's recorded output.
"""
from __future__ import annotations

import math

from packages.pipeline.site_variation import DEFAULT_FOOTPRINT

#: The street's dimensions, from Lot's own hand-authored specs (`gs_heist`,
#: `coldrun_kerb_probe`): a 10 m road, 3 m sidewalks, and 2 m of plate
#: between a sidewalk and anything else. A spur is a crossing's width.
ROAD_WIDTH = 10.0
SIDEWALK_WIDTH = 3.0
ROAD_MARGIN = 2.0
SPUR_WIDTH = 4.0
#: How far into the sidewalk a door spur runs, as a fraction of the walk's
#: depth from its BACK edge. Deep enough that the path and the walk overlap
#: with no seam; short of the walk's centre line, which is where Lot's
#: `kerb_crossings` tests a path for a crossing -- a spur that reached it
#: would be cut, painted and signed like a street crossing again.
SPUR_INTO_WALK = 0.15
ROAD_BAND = ROAD_MARGIN + SIDEWALK_WIDTH + ROAD_WIDTH + SIDEWALK_WIDTH + ROAD_MARGIN
#: How much plate stands between a building's front face and its sidewalk.
#: The walker's art direction (docs/DELCO_1997_ART_DIRECTION.md point 4):
#: commercial Delco grew out of ROADS, buildings close to the road with
#: parking beside or behind. 2.0 m is `ROAD_MARGIN`, the same margin this
#: module already keeps between a sidewalk and anything else, and it is a
#: stoop and a meter strip rather than a yard.
FRONTAGE = ROAD_MARGIN

#: The road graphs a site can be laid out on. `T` is the historical street and
#: stays the default for an unset or unrecognised grammar, so a brief that says
#: nothing gets the streets it has always had.
GRAMMARS = ("T", "cross")

#: What a brief may write for each. Case-insensitive; anything else is a `T`,
#: for the reason `site_variation`'s table gives -- refusing a spelling would
#: stop a build over a label. `road_grammar_known` says which, so an unknown
#: spelling and a spelling that means T stay distinguishable afterwards.
_GRAMMAR_ALIASES = {
    "": "T", "t": "T", "t_junction": "T", "tee": "T", "main_street": "T",
    "strip": "T", "street": "T",
    "cross": "cross", "crossroads": "cross", "crossroad": "cross",
    "x": "cross", "intersection": "cross", "four_corners": "cross",
}


def _norm(grammar) -> str:
    return str(grammar or "").strip().lower()


def grammar_known(grammar) -> bool:
    """Whether ``grammar`` is a spelling this table has an opinion about."""
    return _norm(grammar) in _GRAMMAR_ALIASES


def known_spellings() -> list:
    """Every spelling the table accepts, for a message that lists them."""
    return sorted(k for k in _GRAMMAR_ALIASES if k)


def grammar_of(grammar) -> str:
    """The road graph a brief's spelling names. Unknown spellings are ``T``."""
    return _GRAMMAR_ALIASES.get(_norm(grammar), "T")


def _south_face(buildings, footprints):
    """(southernmost front face, per-building [(x, face)], per-building x span,
    per-building (x0, x1, y0, y1) box).

    Shared by every grammar because they all hang a street off the SAME thing:
    where the buildings' front faces are. Yaw swaps a footprint's two extents
    rather than producing an oriented box -- Lot places in 90 degree steps.
    """
    south, faces, edges, spans = None, [], [], []
    for b, fp in zip(buildings, footprints):
        w, d = tuple(fp) if fp else DEFAULT_FOOTPRINT
        turned = int(round(float(b.get("rot", 0)))) % 180 == 90
        ext_x, ext_y = (d, w) if turned else (w, d)
        x = float(b["at"][0])
        face = float(b["at"][1]) - float(ext_y) / 2.0
        faces.append((b.get("id"), x, face))
        edges.append((x - float(ext_x) / 2.0, x + float(ext_x) / 2.0))
        south = face if south is None else min(south, face)
        spans.append((x - float(ext_x) / 2.0, x + float(ext_x) / 2.0,
                      float(b["at"][1]) - float(ext_y) / 2.0,
                      float(b["at"][1]) + float(ext_y) / 2.0))
    return south, faces, edges, spans


def _lateral_spurs(spans, ids, x_cross, y_road, span_y, flank):
    """A door from each building whose SIDE faces the cross street.

    `_spurs` derives every door from the front road, so until this existed the
    cross street had no addresses at all -- measured across every generated
    site, `street_members` read `{0: [b0, b1, b2], 1: []}`, including on the
    first crossroads ever built.

    A building fronts the cross street when its nearer lateral face is within
    `FRONTAGE` of that street's band -- the same 2.0 m the front door is given,
    applied on the other axis rather than a number chosen here. The door stops
    on the sidewalk for the reason the front one does: a path that reaches the
    centre line is read as a street crossing, and cold run 9048 shipped every
    door dropped-kerbed, crosswalked and signed.

    Skipped where a building sits across the street's line: a door needs a
    face outside the band to start from.
    """
    band = ROAD_WIDTH / 2.0 + SIDEWALK_WIDTH
    walk_in = band - SIDEWALK_WIDTH * SPUR_INTO_WALK
    out = []
    for i in flank:
        x0, x1, y0, y1 = spans[i]
        # the building's own stretch of the cross street, and its mid-point;
        # a door is put where the building actually is, not at its centre if
        # that centre lies off the street's run
        y_mid = max(min((y0 + y1) / 2.0, span_y / 2.0 - ROAD_MARGIN),
                    y_road)
        if x1 <= x_cross:                       # building lies WEST of it
            face, sign = x1, +1
        elif x0 >= x_cross:                     # EAST of it
            face, sign = x0, -1
        else:
            continue                            # straddles the line: no face
        if abs(x_cross - face) < band:
            continue                            # face inside the band
        end = x_cross - sign * walk_in
        if abs(end - (face + sign * 1.0)) <= 0.3:
            continue                            # a seam, not a route
        door = {"a": [face + sign * 1.0, y_mid], "b": [end, y_mid],
                "width": SPUR_WIDTH}
        if i < len(ids) and ids[i] is not None:
            door["building"] = ids[i]
        out.append(door)
    return out


def _spurs(faces, y_road):
    """A door path from each building to its sidewalk.

    A DOOR PATH ENDS AT THE SIDEWALK. It ran to the road's centre line so Lot
    would cut the kerb there, and Lot duly treated every door as a street
    crossing: both kerbs dropped, a crosswalk with stop bars, and a stop sign
    each side (the walker, cold run 9048). A door opens onto the sidewalk;
    crossings belong at junctions (docs/STREET_RULES.md).
    """
    walk_back = y_road + ROAD_WIDTH / 2.0 + SIDEWALK_WIDTH
    spur_end = walk_back - SIDEWALK_WIDTH * SPUR_INTO_WALK
    # `building` NAMES THE DOOR'S OWNER, and it is deliberately not `from`.
    # Lot's `site_streets._endpoints` resolves `from` to the building's CENTRE,
    # so a door carrying it would start inside the building, cross the sidewalk
    # and be read by `kerb_crossings` as a street crossing -- every door
    # dropped-kerbed, crosswalked and signed, which is cold run 9048's defect.
    # `building` is inert to that resolver and read by
    # `site_tactical.street_members`, which otherwise has to GUESS the owner
    # from the nearest centre and cannot: a 56 m wide shell's own doorstep is
    # 29 m from its centre while its neighbour's centre is 39 m away.
    out = []
    for bid, x, face in faces:
        if face - 1.0 - spur_end <= 0.3:
            continue
        door = {"a": [x, face - 1.0], "b": [x, spur_end], "width": SPUR_WIDTH}
        if bid is not None:            # a spec without ids still gets doors
            door["building"] = bid
        out.append(door)
    return out


def _through_road(south, span_x, span_y):
    """The road along the front, and the plate deep enough to hold it.

    THE ROAD IS DERIVED FROM THE FACE, AND THE PLATE FROM THE ROAD. It used to
    be the other way round -- `y_road` from `-span_y/2`, the plate's own south
    edge -- and since the plate is sized by the building row and by whatever
    the shape asked for, the distance between a front door and the kerb was a
    residue rather than a decision. Measured on cold run 9041: 21.5 m of empty
    ground between a bank's south face and its sidewalk.
    """
    y_road = south - FRONTAGE - SIDEWALK_WIDTH - ROAD_WIDTH / 2.0
    need_half = -(y_road - ROAD_WIDTH / 2.0 - SIDEWALK_WIDTH - ROAD_MARGIN)
    if span_y / 2.0 < need_half:
        span_y = int(math.ceil(2.0 * need_half))
    road = {"a": [-span_x / 2.0, y_road], "b": [span_x / 2.0, y_road],
            "width": ROAD_WIDTH, "sidewalk": SIDEWALK_WIDTH}
    return road, y_road, span_y


def _cross_line(edges, span_x):
    """Where a side street meets the front road, the plate width it needs, and
    WHICH BUILDINGS FLANK IT.

    The widest gap between two neighbouring buildings that holds a full band,
    else past the west end of the row.

    The flanking pair is returned rather than recovered later by distance,
    because the street was PLACED in their gap: they are its corner buildings
    by construction, and any threshold rediscovering that fact would be a
    number nobody chose. Measured on `crossroads_9600`: the chosen gap is
    24.0 m, so each face sits 4.0 m clear of the band -- a distance test at
    `FRONTAGE` (2.0) found neither of them, and one loose enough to find them
    would also catch a building across the plate.
    """
    order = sorted(range(len(edges)), key=lambda i: edges[i])
    x_cross, widest, flank = None, ROAD_BAND, ()
    for a, b in zip(order, order[1:]):
        gap = edges[b][0] - edges[a][1]
        if gap >= widest:
            x_cross, widest, flank = (edges[a][1] + edges[b][0]) / 2.0, gap, (a, b)
    if x_cross is None:
        # past the west end of the row: only the westmost building flanks it
        x_cross = edges[order[0]][0] - ROAD_BAND / 2.0
        flank = (order[0],)
        need_half_x = -(x_cross - ROAD_BAND / 2.0)
        if span_x / 2.0 < need_half_x:
            span_x = int(math.ceil(2.0 * need_half_x))
    return x_cross, span_x, flank


def roads_for(grammar, buildings, footprints, span_x, span_y):
    """``(roads, spurs, span_x, span_y)`` for a site on this road grammar.

    The signature `_street_for` had, so the caller changes by one argument.
    """
    if not buildings:
        return [], [], span_x, span_y
    shape = grammar_of(grammar)
    south, faces, edges, spans = _south_face(buildings, footprints)
    road, y_road, span_y = _through_road(south, span_x, span_y)
    x_cross, span_x, flank = _cross_line(edges, span_x)
    # the through road spans the plate, which `_cross_line` may have widened
    road["a"][0], road["b"][0] = -span_x / 2.0, span_x / 2.0

    if shape == "cross":
        # A CROSSROADS: the side street runs the plate's FULL depth, so it
        # passes THROUGH the front road instead of ending on it. That is the
        # only structural difference from a T, and it is the difference
        # between three approaches and four.
        #
        # Lot has carried the machinery for this since the Road model gained
        # `gaps` -- "where a lower-index road crosses THROUGH it, that road's
        # carriageway and bands own the junction's surface" -- and no
        # generated level has ever exercised it, because nothing emitted an X.
        # So the first site built on this grammar is also the first test of
        # that code against a real package.
        #
        # The plate must hold the street's south arm: far enough past the
        # front road's band that the arm is a road and not a stub.
        south_end = y_road - ROAD_WIDTH / 2.0 - SIDEWALK_WIDTH - ROAD_MARGIN
        need_half = -(south_end - ROAD_BAND / 2.0)
        if span_y / 2.0 < need_half:
            span_y = int(math.ceil(2.0 * need_half))
        cross = {"a": [x_cross, -span_y / 2.0 + ROAD_MARGIN],
                 "b": [x_cross, span_y / 2.0 - ROAD_MARGIN],
                 "width": ROAD_WIDTH, "sidewalk": SIDEWALK_WIDTH}
    else:
        cross = {"a": [x_cross, y_road],
                 "b": [x_cross, span_y / 2.0 - ROAD_MARGIN],
                 "width": ROAD_WIDTH, "sidewalk": SIDEWALK_WIDTH}

    # THE CROSS STREET GETS ITS ADDRESSES. Without these it is a road through
    # empty ground: `street_members` read `{0: [b0, b1, b2], 1: []}` on every
    # site ever generated, so the junction added approaches nobody could use.
    doors = _spurs(faces, y_road) + _lateral_spurs(
        spans, [b.get("id") for b in buildings], x_cross, y_road,
        span_y, flank)
    return [road, cross], doors, span_x, span_y
