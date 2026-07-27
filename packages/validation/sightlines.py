"""Where the map is open enough to shoot across, and where cover would fix it.

The standoff check answers "is this enemy too close". That question has an
answer and it is the wrong question, because moving an enemy is the cheapest
possible response to an unfair opening and almost never the right one. Push it
far enough out and the map still grades badly -- now for ``BLIND_MAP`` and a
first contact past the thirty-second ceiling instead -- and the site is no
better than it was. What made the opening unfair was that the crew and the
enemy could see each other across ninety metres of empty ground. The distance
was a symptom.

So this module measures the thing itself: for each pair of mission points, the
straight sightline between them, how much of it crosses open ground, and where
along it a solid would break the line. That output is not a complaint, it is a
placement instruction -- ``put something 1.8 m tall near (x, z)`` -- and it is
the form Lot can act on, because Lot is the tool that owns collision.

A note on why the answer is a *segment* and not a point. Cover works over a
range of positions and not everywhere, because the requirement is not one line
but two: each side sights from its own eye at the other's chest, the two lines
cross at the midpoint, and a solid that occludes only one of them leaves the
other side a free shot -- which stamps first contact just the same. So the
interval this returns spans the positions where a blocker of the given height
occludes *both*, and it narrows to a single point as the blocker approaches
`MIN_COVER_HEIGHT` and vanishes below it.

Within that interval the caller picks, and where it picks is a design choice
rather than a geometric one: the crew walks the route and the enemy holds
ground, so cover near the crew's end protects a moving target for a second and
cover near the enemy's end shortens the engagement the crew is walking into.
Lot biases towards the crew's approach for exactly the reason its ladder
slab-holes bias that way.

Pure geometry in, intervals out. No scene text, no Godot: `spawn_placement`
hands over the boxes it already read and this module never touches a file.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

Vec3 = tuple[float, float, float]

#: Eye heights, from the Laser Tag scripts. ``LT_BotPlayerController`` sights
#: from ``body.global_position + Vector3.UP * 1.4``; the enemy sights from its
#: ``Marker3D_Eye``, and both aim at ``LT_LineOfSightTester.CHEST_OFFSET``,
#: which is 1.0 m above the target's origin.
EYE_HEIGHT = 1.4
CHEST_HEIGHT = 1.0

#: The shortest solid that can break a *mutual* sightline on flat ground, and
#: not a round number chosen for looking like cover. Each side sights from
#: ``EYE_HEIGHT`` at a target's ``CHEST_HEIGHT``, so the two lines cross at the
#: midpoint at ``(EYE_HEIGHT + CHEST_HEIGHT) / 2``; a solid that height stops
#: both sides at exactly one position along the line, and anything shorter
#: stops one side while leaving the other a free shot -- which does not help,
#: because Laser Tag stamps first contact on the first shot fired by either
#: side. See `break_interval`.
MIN_COVER_HEIGHT = (EYE_HEIGHT + CHEST_HEIGHT) / 2.0

#: How far apart to sample a sightline when deciding what it crosses.
SAMPLE = 1.0


@dataclass(frozen=True)
class Sightline:
    """One open line between two mission points.

    ``open_length`` is the part of the line that no solid interrupts. A line
    that is fully blocked has an ``open_length`` of zero and is not a problem;
    a line that is fully open has ``open_length == length`` and is the whole
    problem when ``length`` is large.
    """

    a_name: str
    b_name: str
    a: Vec3
    b: Vec3
    length: float
    open_length: float
    blocked_by: tuple[str, ...] = ()

    @property
    def is_open(self) -> bool:
        return self.open_length >= self.length - 1e-6

    def point_at(self, t: float) -> tuple[float, float]:
        return (self.a[0] + (self.b[0] - self.a[0]) * t,
                self.a[2] + (self.b[2] - self.a[2]) * t)


def _rect(box) -> tuple[float, float, float, float]:
    cx, _cy, cz = box.centre
    sx, _sy, sz = box.size
    return (cx - sx / 2.0, cz - sz / 2.0, cx + sx / 2.0, cz + sz / 2.0)


def _top(box) -> float:
    return box.centre[1] + box.size[1] / 2.0


def _bottom(box) -> float:
    return box.centre[1] - box.size[1] / 2.0


def _crossings(a: Vec3, b: Vec3, rect) -> tuple[float, float] | None:
    """The ``t`` interval of segment ``a``->``b`` inside ``rect`` (Liang-Barsky).

    Returns ``None`` when the segment misses the rectangle. Shared shape with
    Lot's ``site_spawns._segment_crosses``: this one keeps the interval because
    the interval is what says how much of the line was blocked, and the boolean
    is only ever "was the interval non-empty".
    """
    x0, z0 = a[0], a[2]
    dx, dz = b[0] - x0, b[2] - z0
    lo, hi = 0.0, 1.0
    for p, q in ((-dx, x0 - rect[0]), (dx, rect[2] - x0),
                 (-dz, z0 - rect[1]), (dz, rect[3] - z0)):
        if abs(p) < 1e-12:
            if q < 0.0:
                return None
            continue
        t = q / p
        if p < 0.0:
            lo = max(lo, t)
        else:
            hi = min(hi, t)
        if lo > hi:
            return None
    return (lo, hi)


def _occludes(box, a: Vec3, b: Vec3, span: tuple[float, float]) -> bool:
    """Does ``box`` actually stand in the line, or only under it?

    The 2-D crossing test is not enough. A kerb is in the way on a plan view
    and a rifle shoots over it, and a first-floor slab is in the way on a plan
    view and the fight happens beneath it. So the box has to straddle the line's
    own height where it crosses -- which is what makes ``MIN_COVER_HEIGHT`` a
    real constraint rather than a stylistic one.

    Both directions, and both must be blocked. A solid that stops the crew
    shooting out but not the enemy shooting in has not closed the sightline; it
    has made the crew's half of it worse. Same rule as `required_height`, and
    it has to be the same rule or a line this function calls closed is one
    `propose_cover` would still be asked to break.
    """
    for eye, chest in ((a, b), (b, a)):
        blocked = False
        for t in (span[0], (span[0] + span[1]) / 2.0, span[1]):
            # ``t`` is measured along a->b, so the b-eye line is read backwards.
            lo = eye[1] + EYE_HEIGHT
            hi = chest[1] + CHEST_HEIGHT
            at = t if eye is a else 1.0 - t
            y = lo + (hi - lo) * at
            if _bottom(box) <= y <= _top(box):
                blocked = True
                break
        if not blocked:
            return False
    return True


def sightline(a_name: str, a: Vec3, b_name: str, b: Vec3, boxes) -> Sightline:
    """How much of the line from ``a`` to ``b`` nothing interrupts.

    A box containing either endpoint is skipped, for the reason Lot skips it:
    the building you are standing in is not cover from the building you are
    standing in, and counting it lets a crew spawn that landed indoors pass
    every sightline test on the map.
    """
    length = math.dist((a[0], a[2]), (b[0], b[2]))
    if length < 1e-6:
        return Sightline(a_name, b_name, a, b, 0.0, 0.0)

    spans: list[tuple[float, float, str]] = []
    for box in boxes:
        rect = _rect(box)
        if _contains(rect, a) or _contains(rect, b):
            continue
        span = _crossings(a, b, rect)
        if span is None or span[1] - span[0] < 1e-9:
            continue
        if not _occludes(box, a, b, span):
            continue
        spans.append((span[0], span[1], getattr(box, "name", "?")))

    covered = 0.0
    names: list[str] = []
    cursor = 0.0
    for lo, hi, name in sorted(spans):
        if hi <= cursor:
            continue
        covered += hi - max(lo, cursor)
        cursor = hi
        names.append(name)
    return Sightline(a_name, b_name, a, b, length,
                     max(0.0, length - covered * length), tuple(names))


def _contains(rect, p: Vec3) -> bool:
    return rect[0] <= p[0] <= rect[2] and rect[1] <= p[2] <= rect[3]


def open_sightlines(points: dict, boxes, *, limit: float,
                    pairs=None) -> list[Sightline]:
    """Every pair that can see each other across more than ``limit`` metres.

    ``limit`` is the engagement opening range, so what comes back is the set of
    lines along which somebody can open fire the moment the run starts. Sorted
    longest first: the worst sightline on a site is usually the one whose fix
    also shortens three others.
    """
    out: list[Sightline] = []
    names = sorted(points)
    chosen = pairs if pairs is not None else [
        (names[i], names[j])
        for i in range(len(names)) for j in range(i + 1, len(names))]
    for a_name, b_name in chosen:
        if a_name not in points or b_name not in points:
            continue
        line = sightline(a_name, points[a_name], b_name, points[b_name], boxes)
        if line.is_open and line.length > limit:
            out.append(line)
    out.sort(key=lambda s: -s.length)
    return out


# ---------------------------------------------------------------------------
# what to do about it
# ---------------------------------------------------------------------------
#: How close to an endpoint a solid may be proposed. A blocker at ``t = 0`` is
#: a blocker on somebody's head.
_MARGIN = 0.1


def required_height(line: Sightline, t: float, boxes=()) -> float:
    """How tall a solid at ``t`` must be to stop *both* sides shooting.

    Two lines run between the same pair of points, not one: the crew sights
    from its eye at the enemy's chest, and the enemy sights from its eye at the
    crew's chest. They cross at the midpoint and diverge towards the ends, and
    a solid that occludes only one of them hands the other side a free shot --
    which changes nothing, because ``LT_MetricsCollector.record_shot`` stamps
    first contact on the first shot fired by either side.

    So the requirement is the higher of the two lines, measured from the floor
    the solid would actually stand on rather than from a straight line between
    the endpoints. That distinction is the whole of the rooftop case: a crew on
    the ground and an enemy on a 3 m roof are not looking along a ramp, and a
    crate at the midpoint stands on the yard at zero, not at 1.5 m.
    """
    x, z = line.point_at(t)
    a_floor, b_floor = line.a[1], line.b[1]
    eye_a = a_floor + EYE_HEIGHT
    eye_b = b_floor + EYE_HEIGHT
    chest_a = a_floor + CHEST_HEIGHT
    chest_b = b_floor + CHEST_HEIGHT
    sight = max(eye_a + (chest_b - eye_a) * t, chest_a + (eye_b - chest_a) * t)
    return sight - _floor_under(x, z, sight, boxes, default=min(a_floor, b_floor))


def _floor_under(x: float, z: float, ceiling: float, boxes,
                 *, default: float) -> float:
    """The highest surface below ``ceiling`` at ``(x, z)`` -- what cover stands on.

    Bounded above by the sightline itself: a solid whose top is already over
    the line is not a floor for the purposes of this question, it is the reason
    the line was blocked in the first place, and treating it as a floor would
    propose stacking cover on top of a building.
    """
    best = default
    for box in boxes:
        rect = _rect(box)
        if not (rect[0] <= x <= rect[2] and rect[1] <= z <= rect[3]):
            continue
        top = _top(box)
        if top <= ceiling and top > best:
            best = top
    return best


def break_interval(line: Sightline, height: float,
                   *, min_height: float = MIN_COVER_HEIGHT,
                   boxes=()) -> tuple[float, float] | None:
    """The ``t`` range where a solid ``height`` tall would occlude ``line``.

    Cover does not work everywhere along a line, and this is the fact that
    makes naive cover placement useless. On flat ground the requirement is
    lowest at the midpoint and rises towards both ends, so a solid at exactly
    `MIN_COVER_HEIGHT` has one position that works and a shorter one has none.
    Returning ``None`` rather than a midpoint is the honest answer to "where
    should the crate go" when the answer is that a crate will not do -- the
    caller's next move is a taller solid or a building, and it cannot make that
    call if it was handed a coordinate.

    Sampled rather than solved because the floor under the line is whatever the
    boxes say it is, and a closed form would only be closed for a flat site.
    """
    if height < min_height:
        return None
    steps = max(20, int(line.length / SAMPLE))
    lo = hi = None
    for i in range(steps + 1):
        t = _MARGIN + (1.0 - 2.0 * _MARGIN) * (i / steps)
        if height + 1e-9 >= required_height(line, t, boxes):
            if lo is None:
                lo = t
            hi = t
        elif lo is not None:
            break   # the first contiguous run; the requirement is unimodal
    if lo is None:
        return None
    return (lo, hi)


@dataclass(frozen=True)
class CoverProposal:
    """A place to put something solid, and the line it was asked to break."""

    line: Sightline
    x: float
    z: float
    height: float
    bias: float

    def as_dict(self) -> dict:
        return {"x": round(self.x, 3), "z": round(self.z, 3),
                "height": self.height, "bias": self.bias,
                "breaks": f"{self.line.a_name}->{self.line.b_name}",
                "length": round(self.line.length, 1)}


def propose_cover(lines, *, height: float = 1.8, bias: float = 0.35,
                  min_height: float = MIN_COVER_HEIGHT,
                  boxes=()) -> list[CoverProposal]:
    """One cover position per open sightline, biased towards the crew's end.

    ``bias`` is where in the usable interval to sit, 0 being the ``a`` end.
    A third of the way from the crew is deliberate: it gives the crew something
    to move between on its approach rather than handing the far end a wall to
    hold, and it is the same reasoning that puts a ladder's slab-hole on the
    approach side rather than the middle.

    This proposes, it does not place. Whether the position is standable, clear
    of a building and not on top of another proposal is the producer's
    question, and the producer is the only one holding the site layout.
    """
    out: list[CoverProposal] = []
    for line in lines:
        interval = break_interval(line, height, min_height=min_height,
                                  boxes=boxes)
        if interval is None:
            continue
        lo, hi = interval
        t = lo + (hi - lo) * bias
        x, z = line.point_at(t)
        out.append(CoverProposal(line, x, z, height, bias))
    return out


def describe(lines, *, limit: float, boxes=()) -> list[str]:
    """Findings for open sightlines. Advisory: this is a design note, not a gate.

    Named by what to do rather than what is wrong. "LT_PlayerSpawn can see
    Enemy_3 across 91.9 m of open ground" is a fact somebody has to translate
    before they can act; "put cover near (52.1, -12.4)" is the translation, and
    the fact is kept alongside it so the proposal can be argued with.
    """
    return [(message + fix) if fix else message
            for message, fix in advise(lines, limit=limit, boxes=boxes)]


def advise(lines, *, limit: float, boxes=()) -> list[tuple[str, str]]:
    """The same findings as ``(what is open, what to do about it)``.

    Split because they answer to different people. The first half is a
    measurement of the site and stands whether or not anyone acts on it; the
    second is a placement instruction with a coordinate in it, and a findings
    model that carries a ``suggested_fix`` field should be given the fix rather
    than a sentence with the fix buried in its tail.

    The fix is empty for the tail entry, which counts the lines that did not fit
    -- and it has to be reported rather than dropped, because "six open
    sightlines" and "six shown of nineteen" are different sites.
    """
    if not lines:
        return []
    proposals = {id(p.line): p for p in propose_cover(lines, boxes=boxes)}
    out: list[tuple[str, str]] = []
    for line in lines[:6]:
        where = proposals.get(id(line))
        fix = (f"; cover near ({where.x:.1f}, {where.z:.1f}) would break it"
               if where else
               "; no chest-high solid breaks this line — it needs a building")
        out.append((
            f"{line.a_name} and {line.b_name} see each other across "
            f"{line.length:.1f} m of open ground, past the {limit:g} m at which "
            f"Laser Tag opens fire", fix))
    if len(lines) > 6:
        out.append((f"and {len(lines) - 6} more open sightline(s) over "
                    f"{limit:g} m", ""))
    return out
