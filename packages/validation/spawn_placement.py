"""Refuse a map whose enemies cannot walk to the player (TDD 24.3, 29.1).

``ground_contact`` answers "is there a floor under this point". That turned out
to be a much weaker question than it sounds, and the gap between the two cost a
full evaluation to find.

Laser Tag's ``validate_map()`` asks every enemy spawn to path to the player
spawn before it plays a single run, and refuses the whole map with
``UNREACHABLE_SPAWN`` when one cannot. On the site this module was written for,
all six enemies were floored -- every one of them had a slab beneath it, and
``check_ground_contact`` passed them without comment -- and all six were sealed
inside building interiors the crew has no route into. The producer had placed
them by sampling the straight line from the crew spawn to the objective to the
extraction and nudging each sample a metre and a half to the side, which on a
site whose buildings are 44 m across runs the whole sequence through two of
them. "Standing on something" and "standing somewhere the player can get to"
are different claims, and only the second one is what the evaluator checks.

So this module builds the smallest honest model of walkability that can be read
out of scene text: a 2.5-D heightfield over the box colliders, and a flood fill
across it from the player spawn. That is a coarse imitation of what Recast does
during the navmesh bake, and it is deliberately *optimistic* -- it does not
erode by agent radius, so a gap a 0.4 m agent cannot squeeze through still reads
as open. Optimism is the safe direction for a check that blocks a build: this
module under-reports rather than inventing a wall, and everything it does report
is something the bake will refuse too.

Two smaller faults ride along, because the same field answers them:

* a spawn hanging in the air above the floor it names. The producer interpolates
  spawn height linearly along its route, so an objective standing on a 1.1 m
  counter lifts every enemy between it and the extraction off the ground;
* an enemy close enough to the crew that first contact happens before the player
  has moved. That is Laser Tag's ``INSTANT_CONTACT`` / ``NO_REACTION_TIME``
  pair, and it is measured here as *walking* distance across the field rather
  than straight-line distance, because an enemy three metres away through a wall
  is not an ambush.

Those two families do not carry the same authority, and the module used to hand
them over as one list. `check` is what Laser Tag will *refuse*: a map whose
enemies cannot reach the crew is returned by ``validate_map()`` before a single
run, and 900 seconds of Godot buys a report about a match nobody played. `advise`
is what Laser Tag will *play, and grade badly*. A firefight evaluator is a design
instrument, not a building code -- it says the opening was unfair, which is a
claim about tactics, and tactics are the thing the producer is allowed to be
wrong about while it iterates. Blocking a build on it stops the level existing
long enough to be improved; the finding is worth more pointed forward, at where
cover belongs, than backward as a refusal. So the standoff and the lifted
markers advise, and only the reachability failures gate.

Pure text in, findings out -- the same functions back the adapter's pre-flight
and run in the tests. No Godot, no filesystem beyond the scene the caller hands
over.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from pathlib import Path

from packages.validation import lasertag_contract
from packages.validation.ground_contact import (
    Reading, mission_points, read_scene_text, resolver, support_under)

Vec3 = tuple[float, float, float]

#: Grid resolution. Lot bakes its navmesh at 0.15 m cells; this field is only
#: deciding connectivity, not carving doorways, so it trades precision for the
#: ability to finish a 270 x 100 m site in about a second.
CELL = 0.5

#: The pill Laser Tag walks. Matches Lot's authored NavigationMesh so this
#: check and the bake disagree as rarely as possible.
AGENT_HEIGHT = 1.8
AGENT_CLIMB = 0.5

#: How far above or below the player spawn's own floor a surface may be and
#: still count as part of the same storey. A single heightfield cannot describe
#: a building's upper floors; rather than silently treating a roof as ground,
#: the field is built around the storey the mission starts on and anything
#: outside the band is reported as out of view instead of as unreachable.
FIELD_BAND = 3.0

#: A marker names a position on a floor. Lot lifts its spawn markers by 1.0 m
#: so a capsule dropped there settles rather than clips, which is legitimate;
#: past this the marker is not naming a floor position, it is hanging over one.
MAX_SPAWN_LIFT = 1.25

#: Enemies nearer than this *by walking distance* meet the player before the
#: player has done anything. Laser Tag calls the result INSTANT_CONTACT and
#: grades the map on it.
#:
#: Sized against `lasertag_contract`, not by eye. The number this was originally
#: written with was 8.0, chosen to mean "in the crew's lap"; the evaluator opens
#: fire at `Engagement.opening_range`, which is 45 m on the shipped scenario
#: because the bot's sight range is ten metres longer than the enemy's and the
#: bot shoots first. Eight metres described a fistfight. The default below
#: describes the fight Laser Tag actually plays.
MIN_ENGAGEMENT_STANDOFF = lasertag_contract.MEASURED.opening_range

#: Above this the grid is coarsened rather than refused, and the coarsening is
#: stated. A check that quietly stops checking on big sites is the failure mode
#: this whole family of modules exists to avoid.
MAX_CELLS = 4_000_000

#: Codes for the two advisory families, so a caller can file them without
#: reading the sentence. Neither is ever a blocker: see the module docstring.
CODE_STANDOFF = "LT_OPENING_STANDOFF"
CODE_FLOATING = "LT_MARKER_OFF_FLOOR"

#: A seal that exists only in geometry this reader had to infer. Advisory for
#: the reason the others are: the claim cannot be stood behind, and a refusal
#: this module cannot defend is worse than a finding nobody acts on.
CODE_UNVERIFIED_SEAL = "LT_SEAL_UNVERIFIED"

#: `_placement`'s verdict for a cell the flood fill never reached. Named
#: because two functions now have to agree on it, and a sentence duplicated
#: across two call sites is a sentence that drifts.
_SEAL = "sealed off from the crew spawn"

_PLAYER = "LT_PlayerSpawn"
_ENEMY_GROUP = "LT_EnemySpawnPoints"
_ROUTE_GROUP = "LT_PlayerRoutePoints"
_OBJECTIVE = "LT_ObjectivePoint"

_DIAGONAL = math.sqrt(2.0)
_NEIGHBOURS = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
               (1, 1, _DIAGONAL), (1, -1, _DIAGONAL),
               (-1, 1, _DIAGONAL), (-1, -1, _DIAGONAL))


# ---------------------------------------------------------------------------
# the field
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Field:
    """Where an agent could stand, and how high the standing surface is.

    ``floor[i]`` is the top of the highest surface in cell ``i`` that belongs to
    the storey the field was built around, or ``None`` where there is none.
    ``blocked[i]`` says a solid occupies the agent's own volume there, so the
    cell has a floor and is still not standable.
    """

    origin: tuple[float, float]
    cell: float
    nx: int
    nz: int
    reference: float
    floor: list
    blocked: list
    coarsened: bool = False

    def index(self, x: float, z: float):
        """The cell containing ``(x, z)``, or ``None`` if off the field."""
        ix = int(math.floor((x - self.origin[0]) / self.cell))
        iz = int(math.floor((z - self.origin[1]) / self.cell))
        if 0 <= ix < self.nx and 0 <= iz < self.nz:
            return iz * self.nx + ix
        return None

    def standable(self, i: int) -> bool:
        return self.floor[i] is not None and not self.blocked[i]


def _span(box, axis: int) -> tuple[float, float]:
    half = abs(box.size[axis]) / 2.0
    return box.centre[axis] - half, box.centre[axis] + half


def _cell_range(low: float, high: float, origin: float, cell: float,
                count: int) -> range:
    first = int(math.floor((low - origin) / cell))
    last = int(math.floor((high - origin) / cell))
    return range(max(0, first), min(count - 1, last) + 1)


def heightfield(boxes, reference: float, *, cell: float = CELL,
                agent_height: float = AGENT_HEIGHT,
                agent_climb: float = AGENT_CLIMB,
                band: float = FIELD_BAND):
    """A walkability field over ``boxes`` for the storey around ``reference``.

    Returns ``None`` when there is nothing to build one from. Two passes: the
    first takes the highest in-band surface per cell, the second knocks out
    cells where a solid stands in the space the agent would occupy above it.
    """
    solids = [b for b in boxes if b.size[0] > 0 and b.size[2] > 0]
    if not solids:
        return None

    xs = [_span(b, 0) for b in solids]
    zs = [_span(b, 2) for b in solids]
    x0, x1 = min(s[0] for s in xs), max(s[1] for s in xs)
    z0, z1 = min(s[0] for s in zs), max(s[1] for s in zs)

    coarsened = False
    while True:
        nx = max(1, int(math.ceil((x1 - x0) / cell)) + 1)
        nz = max(1, int(math.ceil((z1 - z0) / cell)) + 1)
        if nx * nz <= MAX_CELLS:
            break
        cell *= 2.0
        coarsened = True

    floor: list = [None] * (nx * nz)
    for box in solids:
        top = box.top
        if not (reference - band <= top <= reference + band):
            continue
        bx = _cell_range(*_span(box, 0), x0, cell, nx)
        bz = _cell_range(*_span(box, 2), z0, cell, nz)
        for iz in bz:
            row = iz * nx
            for ix in bx:
                current = floor[row + ix]
                if current is None or top > current:
                    floor[row + ix] = top

    blocked = [False] * (nx * nz)
    for box in solids:
        low, high = _span(box, 1)
        # A surface cannot block the space above its own top.
        if high <= reference - band:
            continue
        bx = _cell_range(*_span(box, 0), x0, cell, nx)
        bz = _cell_range(*_span(box, 2), z0, cell, nz)
        for iz in bz:
            row = iz * nx
            for ix in bx:
                i = row + ix
                if blocked[i]:
                    continue
                surface = floor[i]
                if surface is None:
                    continue
                if low < surface + agent_height and high > surface + agent_climb:
                    blocked[i] = True

    return Field((x0, z0), cell, nx, nz, reference, floor, blocked, coarsened)


def walk_distances(field: Field, start: int, *,
                   agent_climb: float = AGENT_CLIMB) -> dict:
    """Walking distance in metres from ``start`` to every cell it can reach.

    A step is only taken between surfaces within ``agent_climb`` of each other,
    which is the same rule the navmesh bake applies -- a kerb joins, a wall top
    does not.
    """
    if not field.standable(start):
        return {}
    best = {start: 0.0}
    queue = [(0.0, start)]
    while queue:
        distance, i = heapq.heappop(queue)
        if distance > best.get(i, math.inf):
            continue
        ix, iz = i % field.nx, i // field.nx
        here = field.floor[i]
        for dx, dz, step in _NEIGHBOURS:
            nx_, nz_ = ix + dx, iz + dz
            if not (0 <= nx_ < field.nx and 0 <= nz_ < field.nz):
                continue
            j = nz_ * field.nx + nx_
            if not field.standable(j):
                continue
            if abs(field.floor[j] - here) > agent_climb:
                continue
            through = distance + step * field.cell
            if through < best.get(j, math.inf):
                best[j] = through
                heapq.heappush(queue, (through, j))
    return best


# ---------------------------------------------------------------------------
# reading the points
# ---------------------------------------------------------------------------
def _leaf(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _group(path: str) -> str:
    return path.split("/", 1)[0]


def classify(points: dict) -> tuple:
    """``(player, enemies, destinations)`` out of the mission points.

    Destinations are the objective and the route waypoints: the bot has to walk
    to those too, and a route it cannot finish is Laser Tag's ``TRAVERSAL``
    finding rather than its ``UNREACHABLE_SPAWN`` one.
    """
    player = None
    enemies: dict = {}
    ranked: dict = {}
    for path, point in points.items():
        head = _group(path)
        if head == _PLAYER:
            player = point
        elif head == _ENEMY_GROUP:
            enemies[_leaf(path)] = point
        elif head in (_OBJECTIVE, _ROUTE_GROUP):
            # The objective outranks a route point at the same spot: see
            # _one_name_per_position.
            ranked[_leaf(path)] = (point, 0 if head == _OBJECTIVE else 1)
    return player, enemies, _one_name_per_position(ranked)


def _one_name_per_position(ranked: dict) -> dict:
    """Collapse destinations that are the same point under two names.

    Lot builds its route as ``[spawn, objective, extraction]``, so ``Route_1``
    is not a waypoint near the objective -- it is the objective, emitted a
    second time under the name Laser Tag's traversal test reads. Reporting both
    turns one unreachable marker into "2 of 4 mission destinations" and makes a
    single placement defect read as a map riddled with them, which is the wrong
    signal to hand someone deciding what to fix first.

    Which name survives is not cosmetic. ``LT_ObjectivePoint`` says what is
    wrong with the map; ``Route_1`` says only that the second waypoint of
    something is unreachable, and sends whoever reads it looking for a route
    generator that is working fine. So the objective wins its own position, and
    an index-named waypoint is what gets dropped.
    """
    best: dict = {}
    for name, (point, rank) in ranked.items():
        key = tuple(round(c, 3) for c in point)
        keep = best.get(key)
        if keep is None or (rank, name) < (keep[1], keep[0]):
            best[key] = (name, rank)
    return {name: ranked[name][0] for name, _rank in best.values()}


def _named(names, limit: int = 6) -> str:
    ordered = sorted(names)
    shown = ", ".join(ordered[:limit])
    if len(ordered) > limit:
        shown += f", and {len(ordered) - limit} more"
    return shown


# ---------------------------------------------------------------------------
# the check
# ---------------------------------------------------------------------------
def _survey(text: str, reading: Reading):
    """Everything both answers are built on, or ``None`` when neither can be.

    One walk of the field serves the refusals and the advisories: they disagree
    about authority, not about geometry, and computing the field twice on a
    270 x 100 m site to keep two call sites tidy is a second of wall clock per
    candidate for nothing.
    """
    points = mission_points(text)
    player, enemies, destinations = classify(points)
    # check_scene_hooks owns "there are no hooks" and check_ground_contact owns
    # "there is no readable collision". Repeating either here would turn one
    # defect into three messages.
    if player is None or not enemies or not reading.readable:
        return None

    support = support_under(player, reading.boxes)
    if support is None:
        # The player spawn is over a hole. check_ground_contact says so, and
        # every answer this module could give would be built on that hole.
        return None

    field = heightfield(reading.boxes, support.top)
    start = field.index(player[0], player[2]) if field else None
    if field is None or start is None or not field.standable(start):
        return (None, player, enemies, destinations, support, None)
    return (field, player, enemies, destinations, support,
            walk_distances(field, start))


def check_spawn_placement(scene: Path) -> list[str]:
    """Problems that would make Laser Tag refuse the scene at ``scene``."""
    return _from_file(scene, check_spawn_placement_text)


def check_spawn_placement_text(text: str, reading: Reading) -> list[str]:
    """What Laser Tag refuses: the pure form, scene text plus what was read.

    Refusal is a narrow claim and it is kept narrow on purpose. Everything here
    ends in ``validate_map()`` returning before a run, or in a route no bot can
    finish on any seed -- outcomes where playing the map cannot produce
    information. Anything the evaluator would happily play and then mark down
    belongs in `advise_spawn_placement_text`.
    """
    survey = _survey(text, reading)
    if survey is None:
        return []
    field, player, enemies, destinations, support, reach = survey
    if field is None:
        return [
            "the player spawn is not standable in this scene's own collision "
            f"(spawn {_point(player)} over {support.name}, top {support.top:.2f}) "
            "— Laser Tag would find nowhere to put the crew"
        ]
    return _unreachable(field, reach, enemies, destinations, reading,
                        _optimistic_reach(field, reading, player))


def advise_spawn_placement(scene: Path) -> list[str]:
    """Tactical findings for the scene at ``scene``. Never a reason to refuse."""
    return _from_file(scene, advise_spawn_placement_text)


def advise_spawn_placement_text(text: str, reading: Reading,
                                *, opening_range: float | None = None) -> list[str]:
    """What Laser Tag will play and grade badly.

    ``opening_range`` overrides the default measured from the Laser Tag
    checkout, so a caller that has read the real scenario this run reports
    against that rather than against the snapshot in `lasertag_contract`.
    """
    return [message for _code, message in
            advise_spawn_placement_coded(text, reading,
                                         opening_range=opening_range)]


def advise_spawn_placement_coded(
        text: str, reading: Reading,
        *, opening_range: float | None = None) -> list[tuple[str, str]]:
    """The same advisories, each paired with the code it should be filed under.

    Two different defects come back from here -- an enemy standing inside the
    range somebody opens fire at, and a marker naming a position in the air --
    and they are fixed by different people in different files. A caller
    normalizing these into findings needs to tell them apart without matching on
    the prose, which is the sort of coupling that survives exactly until someone
    improves a sentence.
    """
    survey = _survey(text, reading)
    if survey is None:
        return []
    field, player, enemies, destinations, _support, reach = survey
    if field is None:
        # Nowhere to stand is `check`'s finding, and every tactical claim built
        # on a crew that has no floor would be built on the same hole.
        return []
    loose = _optimistic_reach(field, reading, player)
    _v, unverified_enemies = _split_seals(
        _strand(field, reach, enemies), enemies, loose)
    _v, unverified_dests = _split_seals(
        _strand(field, reach, destinations), destinations, loose)
    return ([(CODE_STANDOFF, m)
             for m in _standoff(field, reach, enemies, opening_range)]
            + [(CODE_FLOATING, m)
               for m in _floating(field, player, enemies, destinations)]
            + [(CODE_UNVERIFIED_SEAL, m)
               for m in _unverified_findings("enemy spawn",
                                             unverified_enemies, len(enemies))]
            + [(CODE_UNVERIFIED_SEAL, m)
               for m in _unverified_findings("mission destination",
                                             unverified_dests,
                                             len(destinations))])


def _from_file(scene: Path, pure) -> list[str]:
    scene = Path(scene)
    if not scene.is_file():
        return []
    text = scene.read_text(encoding="utf-8", errors="replace")
    return pure(text, read_scene_text(text, resolve=resolver(scene.parent),
                                      _seen=frozenset({scene})))


def _point(p: Vec3) -> str:
    return f"({p[0]:.1f}, {p[1]:.1f}, {p[2]:.1f})"


def _placement(field: Field, point: Vec3, reach: dict):
    """``(cell, why)`` -- why is None when the point is reachable."""
    i = field.index(point[0], point[2])
    if i is None:
        return None, "outside the site's collision entirely"
    if field.floor[i] is None:
        return i, "over a gap in the storey the mission starts on"
    if abs(field.floor[i] - field.reference) > FIELD_BAND:
        return i, "on a different storey than the crew spawn"
    if field.blocked[i]:
        return i, "inside solid geometry"
    if i not in reach:
        return i, _SEAL
    return i, None


def _strand(field: Field, reach: dict, points: dict) -> dict:
    stranded = {}
    for name, point in points.items():
        _, why = _placement(field, point, reach)
        if why:
            stranded[name] = why
    return stranded


def _optimistic_reach(field: Field, reading: Reading, player: Vec3):
    """The same flood fill, with the INFERRED walls set aside.

    `ground_contact` builds one box per collision MESH, taking its bounding
    box, and a doorway lives in a mesh -- so an exterior wall with openings cut
    in it arrives here as a solid box across every one of them. Measured
    2026-08-09, `cr_garage` declares seven ground-level entries and reads as an
    unbroken ring; under that model no point inside any building is reachable,
    ever.

    So this asks the counterfactual the module's docstring already promises:
    what would be reachable if the walls this reader had to INFER were not
    there? A point unreachable in both fields is sealed by geometry that was
    measured, and still gates. A point reachable only here is sealed by
    something this reader cannot see through, and refusing a build on that is
    refusing it on the reader's own blind spot.

    WHICH boxes leave is the whole care in this function. Every measured box
    stays. An inferred box stays only where its top is within a step of the
    mission's own storey -- an interior floor, a kerb, a threshold. An inferred
    box standing taller than that is the wall whose doorway could not be seen,
    and it leaves the field entirely.

    It has to LEAVE, not merely stop blocking. The first version of this kept
    each wall's floor contribution so the interior would not read as a hole,
    and a 3 m wall top is standable, unclimbable, and still uncrossable: the
    counterfactual answered exactly as the original did and the whole check was
    inert. The interior floor is a separate box and survives on its own.

    Returns ``(field, reach)`` or ``None`` when there is nothing to compare --
    no inferred walls, or no standable start once they are gone.
    """
    ceiling = field.reference + AGENT_CLIMB
    kept = [box for box in reading.boxes
            if not getattr(box, "approximate", False) or box.top <= ceiling]
    if len(kept) == len(reading.boxes):
        return None
    loose = heightfield(kept, field.reference, cell=field.cell)
    if loose is None:
        return None
    start = loose.index(player[0], player[2])
    if start is None or not loose.standable(start):
        return None
    return loose, walk_distances(loose, start)


def _split_seals(stranded: dict, points: dict, loose) -> tuple[dict, dict]:
    """``(verified, unverified)`` -- seals this reader can stand behind, and not.

    Only the seal verdict is ever moved. A point over a gap, on another storey
    or inside solid geometry is refused on evidence a doorway could not change,
    and those keep gating exactly as before.
    """
    if loose is None:
        return stranded, {}
    lfield, lreach = loose
    verified, unverified = {}, {}
    for name, why in stranded.items():
        if why == _SEAL:
            _i, still = _placement(lfield, points[name], lreach)
            if still is None:
                unverified[name] = why
                continue
        verified[name] = why
    return verified, unverified


def _unverified_findings(kind: str, stranded: dict, total: int) -> list[str]:
    if not stranded:
        return []
    return [
        f"{len(stranded)} of {total} {kind} sit(s) where this reader's own "
        f"collision has no route from the crew spawn ({_detail(stranded)}), "
        f"but every wall between is a collision MESH reduced to its bounding "
        f"box -- doorways included. With those walls set aside the point is "
        f"reachable, so the seal is this reader's blind spot rather than a "
        f"fact about the level, and it is reported instead of refused. If "
        f"Laser Tag comes back with TRAVERSAL at 0%, the seal was real"
    ]


def _caveat(field: Field, reading: Reading) -> str:
    """What this answer does not know, said on the finding rather than omitted.

    Both of these widen the walkable area rather than narrow it, so they cannot
    turn a pass into a failure -- but a reader deciding whether to trust a
    blocker deserves to know the model was incomplete.
    """
    caveat = ""
    if reading.opaque:
        # Not necessarily a missing subscene: a capsule or a cylinder is just a
        # shape this reader does not reduce to a box. Either way it is collision
        # the field does not contain, and either way that can only make the real
        # walkable area larger than the one measured here.
        caveat = (f" ({len(reading.opaque)} collider(s) could not be reduced to "
                  f"a box, so the walkable area may be larger than this: "
                  f"{_named(reading.opaque, 3)})")
    if field.coarsened:
        caveat += (f" (the site was too large for a {CELL:g} m grid, so this "
                   f"was checked at {field.cell:g} m)")
    return caveat


def _detail(stranded: dict) -> str:
    detail = "; ".join(f"{name} is {stranded[name]}"
                       for name in sorted(stranded)[:6])
    if len(stranded) > 6:
        detail += f"; and {len(stranded) - 6} more"
    return detail


def _unreachable(field: Field, reach: dict, enemies: dict, destinations: dict,
                 reading: Reading, loose=None) -> list[str]:
    """Two findings, not one.

    An enemy the crew cannot be reached from and a waypoint the crew cannot walk
    to are different defects with different consequences -- Laser Tag refuses
    the whole map for the first and scores 0% traversal on the second -- and a
    single message that counts enemies and then lists route points reads as a
    miscount even when both halves are true.
    """
    problems: list[str] = []
    caveat = _caveat(field, reading)

    stranded, _unverified = _split_seals(
        _strand(field, reach, enemies), enemies, loose)
    if stranded:
        problems.append(
            f"{len(stranded)} of {len(enemies)} enemy spawn(s) cannot be walked "
            f"to from the player spawn: {_detail(stranded)}{caveat}; Laser Tag "
            f"refuses the map with UNREACHABLE_SPAWN and completes zero runs")

    stranded, _unverified = _split_seals(
        _strand(field, reach, destinations), destinations, loose)
    if stranded:
        problems.append(
            f"{len(stranded)} of {len(destinations)} mission destination(s) "
            f"cannot be walked to from the player spawn: {_detail(stranded)}"
            f"{caveat}; the bot cannot finish the route, which Laser Tag "
            f"reports as TRAVERSAL with 0% completion")
    return problems


def _standoff(field: Field, reach: dict, enemies: dict,
              opening_range: float | None = None) -> list[str]:
    """Enemies inside the range at which somebody opens fire.

    Walking distance rather than straight line, because an enemy three metres
    away through a wall is not an ambush -- but note what that means here: a
    walking distance over the opening range is not on its own a fair opening,
    only a necessary condition for one. Whether a sightline exists across the
    open ground between them is `sightlines`' question, and the answer to it is
    where cover belongs rather than where the enemy belongs.
    """
    limit = MIN_ENGAGEMENT_STANDOFF if opening_range is None else opening_range
    close = {}
    for name, point in enemies.items():
        i, why = _placement(field, point, reach)
        if why:
            continue
        distance = reach[i]
        if distance < limit:
            close[name] = distance
    if not close:
        return []
    detail = ", ".join(f"{name} at {close[name]:.1f} m"
                       for name in sorted(close, key=lambda n: close[n]))
    return [
        f"{len(close)} enemy spawn(s) are within {limit:g} m walking distance "
        f"of the player spawn ({detail}) — the crew is in contact before it has "
        "moved, which Laser Tag grades as INSTANT_CONTACT and NO_REACTION_TIME; "
        "the crew's bot stops walking the moment it can see an enemy, so this "
        "also costs the run its route completion"
    ]


def _floating(field: Field, player: Vec3, enemies: dict,
              destinations: dict) -> list[str]:
    lifted = {}
    for name, point in [(_PLAYER, player), *enemies.items(),
                        *destinations.items()]:
        i = field.index(point[0], point[2])
        if i is None or field.floor[i] is None:
            continue
        lift = point[1] - field.floor[i]
        if lift > MAX_SPAWN_LIFT:
            lifted[name] = lift
    if not lifted:
        return []
    detail = ", ".join(f"{name} {lifted[name]:.2f} m up"
                       for name in sorted(lifted, key=lambda n: -lifted[n])[:6])
    if len(lifted) > 6:
        detail += f", and {len(lifted) - 6} more"
    return [
        f"{len(lifted)} mission point(s) hang more than {MAX_SPAWN_LIFT:g} m "
        f"above the floor beneath them ({detail}) — a marker is meant to name a "
        "position on a surface, and one interpolated between surfaces at "
        "different heights names a position in the air"
    ]
