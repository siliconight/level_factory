extends SceneTree

## CAN A BODY WALK OFF AN EDGE THE LEVEL DID NOT MEAN TO LEAVE OPEN?
##
## WHY THIS EXISTS. Every gate in this exporter measures traversal correctness
## (can a body get from A to B) or resource closure (does every reference
## resolve). None asks whether a body can FALL somewhere it should not. Three
## defects in three days were found by the walker and by none of the five
## gates that passed their packages -- a grey collar round every cut slab,
## occluders capping the openings they sat over, and this: a stairwell whose
## walk-on gap is sized 2.05 m and clipped to nothing, so 0.98 m of it hangs
## over a descending flight.
##
## WHAT IT MEASURES, and it is a measurement rather than a verdict. For every
## standable point on a grid, whether the surface a body would move to in a
## neighbouring cell (the highest within its step-up) has something standing
## on it (`occupied_next`: walked into, not off), else whether it is further
## down than the body steps (`drop_edges`), and if so whether anything solid
## stands between the two above the height it steps over (`guarded`) or the
## body above that height meets something in the next cell (`blocked`). An
## edge with a drop and neither is `unguarded`, and is reported with its
## position and depth. Whether a given edge SHOULD be open is a judgement
## about the level -- a loading dock and a kerb are edges somebody meant -- so
## this prints them and stops.
##
## THE NUMBERS ARE THE CONTRACT'S, not this file's:
##
##   FALL_M      characters.player.max_step_up_m (0.50). What a controller
##               lifts itself over, and by symmetry the largest drop it takes
##               deliberately. Below it a transition is a step -- every stair
##               riser in the library is well under it.
##   BARRIER_Y   the same 0.50, plus a margin. A solid no taller than what a
##               body steps over does not stop it walking off, so a guard is
##               only a guard above this line. Deli Counter builds rails at
##               GUARD_HEIGHT 1.07, comfortably over.
##   STAND_M     characters.player.height_m (1.80). A surface with less
##               headroom than this is not somewhere a body stands, so it is
##               not somewhere a body walks off.
##
## Usage:
##   godot --headless --path <pkg> --script res://walkable_edge.gd -- <out.json> [cell_m] [seed_x,seed_y,seed_z] [links.json] [extent_node]
##
## With a seed (world metres: where the body starts, e.g. the package's spawn
## anchor) only the cells a body can reach from it are asked -- see pass 1b;
## with a links file (the package's `navigation_hints.json`) the flood also
## takes its ladders; with an extent node (a package's "Site") the grid covers
## what is drawn under that node and not the backdrop. An empty string skips
## an argument.
##
## Output: `edges[]`, one row per unguarded drop edge -- x, y, z of the edge's
## midpoint (Godot metres, y the cell's surface), `drop_m` (999 when nothing is
## below), `indoors`, and `on` / `to`: indexes into `owners[]`, the paths of the
## nodes whose colliders the cell stands on and the neighbour drops to (-1 for
## none) -- deepest first, capped at MAX_ROWS; and the counts.

const FALL_M := 0.50
const BARRIER_MARGIN := 0.05
const STAND_M := 1.80
#: CharacterBody3D.floor_max_angle, 45 degrees: the steepest surface a body
#: stands on rather than slides down. The contract's nav bake allows 55 and
#: the factory's CLAUDE.md records the tension; this file sides with the body.
const FLOOR_MAX_DEG := 45.0
var _steep: int = 0
#: characters.player.radius_m. NOT what the probes below are built from, and
#: nothing reads it yet: on a 0.5 m grid a capsule of the body's full radius
#: finds every cell within 0.35 m of a wall occupied, so an edge along that
#: wall is asked from the next cell out; at PROBE_R the cell at the wall asks
#: it. The cost is a solid between 0.20 and 0.35 m of a neighbour's centre that
#: the barrier ray (which ends at the centre) also misses. Neither radius has
#: been measured against the other on a package; this stays for when one is.
const BODY_R := 0.35
#: Probe from this far above a surface so a ray does not start inside it.
const EPS := 0.02
#: A SURFACE IS STANDABLE ONLY IF THE BODY FITS ON IT, AND THE BODY IS A SHAPE.
#: The downward ray that finds surfaces also finds a floor slab's edge UNDER an
#: exterior wall and a slab's own underside, and a headroom ray cast from either
#: starts inside a solid, which Godot's `intersect_ray` reports as nothing -- on
#: cold run 9317's package 2,703 of 16,739 unguarded edges were cells on a
#: footprint's own wall line and 664 were surfaces 0.3 m inside a slab (the
#: factory's docs/findings/drop_edges_173/). A ray answers "what is the floor
#: here"; "does a body fit" wants a shape (the factory's CLAUDE.md). `_stand` is
#: a capsule PROBE_R wide and STAND_M tall stood on a hit with EPS clearance: a
#: hit it overlaps anything from is not a surface, and a neighbouring column it
#: overlaps anything in at the cell's own level is a wall, not a drop.
const PROBE_R := 0.20
var _stand: PhysicsShapeQueryParameters3D
#: THE BODY ABOVE WHAT IT STEPS OVER: the same capsule from FALL_M up, stood in
#: a neighbouring column at the cell's level to ask whether the body can get
#: there at all. A solid it meets is a wall, not a drop; a solid under FALL_M
#: is stepped over (or onto, when its top is a surface), and so must not block.
const BLOCK_H := STAND_M - FALL_M - EPS
var _block: PhysicsShapeQueryParameters3D
#: WHAT EACH SURFACE BELONGS TO: the path of the node whose collider the ray
#: hit, as an index into the report's `owners[]`. A gate that excludes furniture
#: has to do it by what a surface IS -- a slab, a tread, the ground -- not by
#: its height (a desk top at 0.75 m and a mezzanine at 3.3 m are both "a
#: surface" to a ray), and this is the only place that reading can come from.
var _owners: Dictionary = {}
var _owner_paths: Array = []
#: Cap the report; the JSON is evidence, not a phone book. 4,000 until 2026-10-15,
#: which on cold run 9317's package kept the deepest 4,000 of 16,739 unguarded
#: edges -- the plate's rim and the backdrop's, not one of the 6,004 indoors --
#: so a sort by what each edge stands beside (roadmap 173,
#: docs/findings/drop_edges_173/sort_edges.py) read a sample of the wrong end.
#: A 0.5 m grid over a level is a few hundred thousand cells and the rows are
#: a few megabytes; the cap is against a runaway, not a budget.
const MAX_ROWS := 200000
#: TWO PIECES AUTHORED FLUSH ARE NOT FLUSH IN FLOAT32 (Level Factory 0.219.0,
#: the factory's roadmap 173). deli_a03's stair cut and its discharge plate
#: meet at local x -13.0, a line of the gate's 0.5 m lattice; the cut is
#: stored one float32 step west of it and the plate's body composes a step
#: east, a 1.7 um gap straddling x -64.0. A ray cast there falls through to
#: the floor below, and cold run 9333's export refused three such "drops"
#: (rays a float32 step either side meet the slab and the plate). The
#: lattice is laid these offsets off the round coordinates (in `_run`), so
#: no query -- ray or capsule -- lands where pieces meet: not multiples of
#: 0.5 mm; over 35 float32 steps within 1 km of the origin; and a body is
#: wider than a gap.
const SEAM_NUDGE_X := 0.0031
const SEAM_NUDGE_Z := 0.0023


func _initialize() -> void:
	var args: PackedStringArray = OS.get_cmdline_user_args()
	if args.size() < 1:
		print("[edge] USAGE: <out.json> [cell_m]")
		quit(2)
		return
	var seed: Array = []
	if args.size() > 2:
		for v in args[2].split(","):
			seed.append(float(v))
		if seed.size() != 3:
			print("[edge] USAGE: <out.json> [cell_m] [seed_x,seed_y,seed_z] [links.json]")
			quit(2)
			return
	_run(args[0], float(args[1]) if args.size() > 1 else 0.5, seed,
		args[3] if args.size() > 3 else "", args[4] if args.size() > 4 else "")


func _walk(n: Node, out: Array) -> void:
	out.append(n)
	for c in n.get_children():
		_walk(c, out)


## Every surface under (x, z), top down: [height, owner, free, reached], where
## `free` is whether the body fits standing on it and `reached` is set by the
## flood from the seed. A free surface is a standing point; an occupied one is
## a wall to a body arriving at its level.
func _columns(space: PhysicsDirectSpaceState3D, x: float, z: float,
		top: float, bottom: float) -> Array:
	var out: Array = []
	var y: float = top
	var guard: int = 0
	while y > bottom and guard < 24:
		guard += 1
		var q := PhysicsRayQueryParameters3D.create(
			Vector3(x, y, z), Vector3(x, bottom, z))
		var hit: Dictionary = space.intersect_ray(q)
		if hit.is_empty():
			break
		var hy: float = float(hit["position"].y)
		# A SURFACE STEEPER THAN THE BODY STANDS ON IS NOT A SURFACE: the
		# controller slides off it (`floor_max_angle`), so it is neither a
		# standing point nor a wall. And ON A SLOPE THE CAPSULE IS LIFTED by the
		# slope's rise across its own radius: stood on the hit with EPS of
		# clearance, it overlaps the ramp it stands on from about 15 degrees up
		# (at 40 degrees, Deli Counter's cap, the ramp is 8 cm higher 10 cm
		# from the contact) -- cold run 9317's eighth run read every stair
		# ramp in the level as occupied and no upper floor as reachable.
		var nrm: Vector3 = hit.get("normal", Vector3.UP)
		var cos_t: float = clampf(nrm.y, -1.0, 1.0)
		if cos_t < cos(deg_to_rad(FLOOR_MAX_DEG)):
			_steep += 1
			y = hy - EPS * 2.0
			continue
		var lift: float = PROBE_R * tan(acos(cos_t))
		# Does a body fit on this surface? ONE SHAPE, the body's own column,
		# asked once: a capsule PROBE_R wide and STAND_M tall standing on the
		# hit, overlapping nothing. The headroom ray this replaced started
		# inside whatever solid the hit belonged to and reported nothing, so a
		# slab's underside and a floor's edge under a wall read as surfaces;
		# a shin-high sphere caught the wall but not a surface inside a slab
		# (cold run 9317: 236 cells at 6.3 m on the deli's roof, 0.3 m under
		# its top, with the sphere poking out above). A capsule from the hit
		# to head height overlaps the slab it is inside.
		# A surface the capsule overlaps something on is kept as OCCUPIED, not
		# dropped. Dropping it let a column see THROUGH a slab to the storey
		# below: a roof cell beside an exhaust fan 0.2 m off its centre read a
		# 3.3 m drop to the first floor, and a first-floor cell beside a carton
		# stack one to the ground floor (cold run 9317, the sixth run) -- the
		# body cannot fall through a roof, it walks into the fan.
		_stand.transform = Transform3D(Basis(), Vector3(x, hy + EPS + lift + STAND_M * 0.5, z))
		out.append([hy, _owner(hit), space.intersect_shape(_stand, 1).is_empty(), false])
		y = hy - EPS * 2.0
	return out


func _owner(hit: Dictionary) -> int:
	var c: Object = hit.get("collider")
	var n: Node = c as Node
	var path: String = str(n.get_path()) if n != null else str(c)
	if not _owners.has(path):
		_owners[path] = _owner_paths.size()
		_owner_paths.append(path)
	return int(_owners[path])


func _transition(col: Array, y: float) -> int:
	## The surface a body at `y` moves to in that column: the index of the
	## highest one no further above `y` than it steps up, free or occupied, or
	## -1 for none. Asked of surfaces at or below `y` only, this read a planter
	## box the body steps onto as a 6.6 m drop, because the floor under the box
	## was not a surface (the capsule on it is inside the box) and the next one
	## down is two storeys below.
	var best: int = -1
	var best_y: float = -1e18
	for k in range(col.size()):
		var hh: float = float(col[k][0])
		if hh <= y + FALL_M + 0.01 and hh > best_y:
			best_y = hh
			best = k
	return best


## The standable surface nearest a world point: [ix, iz, k], or [] when no
## cell within a metre of it has a free surface within a metre of its height.
## A link's end is where the climb starts, and the cell under a ladder's foot
## or inside a hatch's hole is occupied -- cold run 9318: both ladder links
## unresolved when only the point's own cell was asked -- so the ring of cells
## around it is searched and the nearest free surface in three dimensions wins.
func _cell_at(cols: Array, box: AABB, cell: float, nx: int, nz: int, p: Array) -> Array:
	var cx: int = clampi(int(round((float(p[0]) - box.position.x) / cell)), 0, nx - 1)
	var cz: int = clampi(int(round((float(p[2]) - box.position.z) / cell)), 0, nz - 1)
	var reach: int = int(ceil(1.0 / cell))
	var best: Array = []
	var best_d: float = 1e9
	for ix in range(maxi(0, cx - reach), mini(nx - 1, cx + reach) + 1):
		for iz in range(maxi(0, cz - reach), mini(nz - 1, cz + reach) + 1):
			var col: Array = cols[ix * nz + iz]
			var dx: float = box.position.x + float(ix) * cell - float(p[0])
			var dz: float = box.position.z + float(iz) * cell - float(p[2])
			for k in range(col.size()):
				if not col[k][2]:
					continue
				var dy: float = float(col[k][0]) - float(p[1])
				if absf(dy) > 1.0:
					continue
				var d: float = sqrt(dx * dx + dy * dy + dz * dz)
				if d < best_d:
					best_d = d
					best = [ix, iz, k]
	return best


func _run(out_path: String, cell: float, seed: Array, links_path: String, extent_node: String) -> void:
	await process_frame
	var main_scene: String = String(ProjectSettings.get_setting(
		"application/run/main_scene", ""))
	var report: Dictionary = {
		"schema": "lf.walkable_edge.v1", "ok": true, "error": "",
		"cell_m": cell, "fall_m": FALL_M, "barrier_above_m": FALL_M + BARRIER_MARGIN,
		"main_scene": main_scene, "standable_cells": 0,
		"occupied_surfaces": 0, "occupied_next": 0,
		"drop_edges": 0, "guarded": 0, "blocked": 0, "unguarded": 0,
		"unguarded_indoors": 0, "edges": [],
	}
	if main_scene == "":
		report["ok"] = false
		report["error"] = "no application/run/main_scene"
		_write(out_path, report)
		quit(0)
		return
	var packed: PackedScene = load(main_scene) as PackedScene
	if packed == null:
		report["ok"] = false
		report["error"] = "main_scene did not load"
		_write(out_path, report)
		quit(0)
		return
	var scene: Node = packed.instantiate()
	root.add_child(scene)
	for i in range(20):
		await process_frame

	# The site's extent, from what is drawn -- or, given, a rectangle
	# "x0,z0,x1,z1" in world metres, or the name of a node to take it under.
	# A package's scene holds the backdrop too: on cold run 9318's package
	# the grid over everything was 1,521 cells a side and 2.5 minutes, of
	# which the site is a few hundred cells a side, and the site node's own
	# subtree reached just as far (its ground carries the backdrop's). The
	# gate that runs this in every export passes the rectangle its package's
	# nav nodes span, plus a margin; what bounded the grid is in the report.
	var extent_root: Node = scene
	var extent_rect: Array = []
	if extent_node.contains(","):
		for v in extent_node.split(","):
			extent_rect.append(float(v))
		if extent_rect.size() != 4:
			report["ok"] = false
			report["error"] = "an extent is x0,z0,x1,z1 in world metres, not %s" % extent_node
			_write(out_path, report)
			quit(0)
			return
	elif extent_node != "":
		var found: Node = scene.find_child(extent_node, true, false)
		if found == null:
			report["ok"] = false
			report["error"] = "no node named %s to bound the grid" % extent_node
			_write(out_path, report)
			quit(0)
			return
		extent_root = found
	report["extent"] = extent_node if extent_node != "" else "(the whole scene)"
	var nodes: Array = []
	_walk(extent_root, nodes)
	var box := AABB()
	var first: bool = true
	for n in nodes:
		var v: VisualInstance3D = n as VisualInstance3D
		if v == null:
			continue
		var a: AABB = v.global_transform * v.get_aabb()
		if first:
			box = a
			first = false
		else:
			box = box.merge(a)
	if first:
		report["ok"] = false
		report["error"] = "no visual geometry: refusing to report a level with no edges"
		_write(out_path, report)
		quit(0)
		return
	if extent_rect.size() == 4:
		# The given rectangle, the drawn geometry's own height range -- and
		# the rectangle's corner SNAPPED TO THE CELL LATTICE, so a bounded run
		# walks the very cells an unbounded one does. Measured on cold run
		# 9318's package: a corner at z -26.51 put every cell a centimetre
		# off the unbounded run's, no row's coordinates matched, and on that
		# lattice the flood never crossed the office stair's turn landing
		# (one cell deep) -- its upper flight and second floor unreached. The
		# same fragility the nav gate's grid sweep exists for; snapping keeps
		# a bound from changing the answer, and the sweep is still owed.
		var x0: float = floorf(minf(extent_rect[0], extent_rect[2]) / cell) * cell
		var z0: float = floorf(minf(extent_rect[1], extent_rect[3]) / cell) * cell
		var x1: float = ceilf(maxf(extent_rect[0], extent_rect[2]) / cell) * cell
		var z1: float = ceilf(maxf(extent_rect[1], extent_rect[3]) / cell) * cell
		box = AABB(Vector3(x0, box.position.y, z0), Vector3(x1 - x0, box.size.y, z1 - z0))
	# THE LATTICE IS LAID OFF THE ROUND COORDINATES (0.219.0; SEAM_NUDGE
	# above), bounded or not: every query below -- the column rays and the
	# capsules stood on them, the barrier ray, the block capsule, the sky ray,
	# the seed's cell and each link's -- asks points this far off the lines
	# pieces meet on. The first build moved the column and sky rays alone, and
	# a capsule standing exactly its radius from a face on a lattice line still
	# touched it, which Godot calls an overlap. Rows are reported to 0.01 m,
	# where the offset does not show.
	box.position += Vector3(SEAM_NUDGE_X, 0.0, SEAM_NUDGE_Z)
	report["lattice_offset_m"] = [SEAM_NUDGE_X, SEAM_NUDGE_Z]

	var space: PhysicsDirectSpaceState3D = root.world_3d.direct_space_state
	var probe := CapsuleShape3D.new()
	probe.radius = PROBE_R
	probe.height = STAND_M
	_stand = PhysicsShapeQueryParameters3D.new()
	_stand.shape = probe
	_stand.collide_with_areas = false
	_stand.collide_with_bodies = true
	var above := CapsuleShape3D.new()
	above.radius = PROBE_R
	above.height = BLOCK_H
	_block = PhysicsShapeQueryParameters3D.new()
	_block.shape = above
	_block.collide_with_areas = false
	_block.collide_with_bodies = true
	report["stand_probe_r"] = PROBE_R
	report["stand_probe_h"] = STAND_M
	report["block_above_m"] = FALL_M + EPS
	var top: float = box.position.y + box.size.y + 1.0
	var bottom: float = box.position.y - 1.0
	var nx: int = int(box.size.x / cell) + 1
	var nz: int = int(box.size.z / cell) + 1
	print("[edge] %d x %d cells of %.2f m over x %.1f..%.1f z %.1f..%.1f"
		% [nx, nz, cell, box.position.x, box.position.x + box.size.x,
		   box.position.z, box.position.z + box.size.z])

	# Pass 1: the standable height map.
	var cols: Array = []
	cols.resize(nx * nz)
	var standable: int = 0
	var occupied: int = 0
	for ix in range(nx):
		for iz in range(nz):
			var x: float = box.position.x + float(ix) * cell
			var z: float = box.position.z + float(iz) * cell
			var c: Array = _columns(space, x, z, top, bottom)
			cols[ix * nz + iz] = c
			for h in c:
				if h[2]:
					standable += 1
				else:
					occupied += 1
	report["standable_cells"] = standable
	report["occupied_surfaces"] = occupied
	report["steep_surfaces"] = _steep
	report["floor_max_deg"] = FLOOR_MAX_DEG
	var steps: Array = [[1, 0], [-1, 0], [0, 1], [0, -1]]

	# Pass 1b: WHAT A BODY CAN REACH FROM THE SEED, and only from there is an
	# edge asked. A standable surface is any top the body fits on -- a parapet,
	# the perimeter fence, a car's roof, a desk (cold run 9317: 2,464 edges on
	# the fence, 987 on parapets, 1,315 on props, 278 on the roof strip outside
	# the parapet, every one of them unguarded and none of them anywhere a
	# body walks). Rather than name what a surface is, which is this
	# toolchain's business and not the instrument's, flood from where the body
	# starts, across the transitions the edge pass itself uses: a step up to
	# FALL_M, a step down, or a fall onto a free surface. Without a seed every
	# standable cell counts, as before.
	var reached: int = 0
	if seed.size() == 3:
		var six: int = clampi(int(round((seed[0] - box.position.x) / cell)), 0, nx - 1)
		var siz: int = clampi(int(round((seed[2] - box.position.z) / cell)), 0, nz - 1)
		var sc: Array = cols[six * nz + siz]
		var start: int = -1
		var best_dy: float = 1e9
		for k in range(sc.size()):
			if sc[k][2] and absf(float(sc[k][0]) - seed[1]) < best_dy:
				best_dy = absf(float(sc[k][0]) - seed[1])
				start = k
		if start < 0:
			report["ok"] = false
			report["error"] = "no standable surface at the seed cell (%.2f, %.2f, %.2f)" % [seed[0], seed[1], seed[2]]
			_write(out_path, report)
			quit(0)
			return
		sc[start][3] = true
		# LINKS ARE CLIMBS THE FLOOD CANNOT MAKE ON ITS OWN: a ladder joins a
		# floor to a roof or a basement, and without it no roof in cold run
		# 9317's package was reached (the deli's is by its ladder). The file
		# is the package's `navigation_hints.json`, or anything with `links[]`
		# of `start_position` / `end_position` in world metres and an
		# optional `bidirectional`; each end snaps to the standable surface
		# nearest it, and an end with none within a metre leaves the link
		# unresolved and counted.
		var jumps: Dictionary = {}
		var links_used: int = 0
		var links_unresolved: int = 0
		if links_path != "":
			var lf: FileAccess = FileAccess.open(links_path, FileAccess.READ)
			if lf == null:
				report["ok"] = false
				report["error"] = "links file unreadable: " + links_path
				_write(out_path, report)
				quit(0)
				return
			var ld: Variant = JSON.parse_string(lf.get_as_text())
			lf.close()
			var arr: Array = []
			if ld is Dictionary:
				arr = ld.get("links", [])
			elif ld is Array:
				arr = ld
			for l in arr:
				var a: Array = _cell_at(cols, box, cell, nx, nz, l["start_position"])
				var b: Array = _cell_at(cols, box, cell, nx, nz, l["end_position"])
				if a.is_empty() or b.is_empty():
					links_unresolved += 1
					continue
				links_used += 1
				var ka: String = "%d,%d,%d" % [a[0], a[1], a[2]]
				if not jumps.has(ka):
					jumps[ka] = []
				jumps[ka].append(b)
				if bool(l.get("bidirectional", true)):
					var kb: String = "%d,%d,%d" % [b[0], b[1], b[2]]
					if not jumps.has(kb):
						jumps[kb] = []
					jumps[kb].append(a)
		report["links_path"] = links_path
		report["links_used"] = links_used
		report["links_unresolved"] = links_unresolved
		var queue: Array = [[six, siz, start]]
		var qi: int = 0
		while qi < queue.size():
			var cur: Array = queue[qi]
			qi += 1
			reached += 1
			var cy: float = float(cols[cur[0] * nz + cur[1]][cur[2]][0])
			for s in steps:
				var jx: int = cur[0] + int(s[0])
				var jz: int = cur[1] + int(s[1])
				if jx < 0 or jz < 0 or jx >= nx or jz >= nz:
					continue
				var there: Array = cols[jx * nz + jz]
				var k: int = _transition(there, cy)
				if k < 0 or not there[k][2] or there[k][3]:
					continue
				there[k][3] = true
				queue.append([jx, jz, k])
			var key: String = "%d,%d,%d" % [cur[0], cur[1], cur[2]]
			if jumps.has(key):
				for t in jumps[key]:
					var tcol: Array = cols[int(t[0]) * nz + int(t[1])]
					if not tcol[int(t[2])][3]:
						tcol[int(t[2])][3] = true
						queue.append([int(t[0]), int(t[1]), int(t[2])])
		report["seed"] = {"x": seed[0], "y": seed[1], "z": seed[2],
			"cell_y": float(sc[start][0]), "owner": int(sc[start][1])}
		print("[edge] reachable from the seed: %d of %d standable cells (links used %d, unresolved %d)"
			% [reached, standable, links_used, links_unresolved])
	else:
		for c in cols:
			for h in c:
				h[3] = true
		reached = standable
	report["reachable_cells"] = reached
	# Standable and reached, by owner: which floors the flood got to is the
	# first thing to read when a building's edges are missing.
	var std_by: Dictionary = {}
	var reach_by: Dictionary = {}
	for c in cols:
		for h in c:
			if h[2]:
				std_by[h[1]] = int(std_by.get(h[1], 0)) + 1
				if h[3]:
					reach_by[h[1]] = int(reach_by.get(h[1], 0)) + 1
	report["standable_by_owner"] = std_by
	report["reachable_by_owner"] = reach_by

	# Pass 2: edges, and only there does this raycast again.
	var edges: Array = []
	var drops: int = 0
	var guarded: int = 0
	var blocked: int = 0
	var occupied_next: int = 0
	var unguarded: int = 0
	var indoor: int = 0
	for ix in range(nx):
		for iz in range(nz):
			var here: Array = cols[ix * nz + iz]
			for h in here:
				if not h[2] or not h[3]:
					continue
				var y: float = float(h[0])
				var on: int = int(h[1])
				for s in steps:
					var jx: int = ix + int(s[0])
					var jz: int = iz + int(s[1])
					if jx < 0 or jz < 0 or jx >= nx or jz >= nz:
						continue
					var there: Array = cols[jx * nz + jz]
					var k: int = _transition(there, y)
					if k >= 0 and not there[k][2]:
						# THE SURFACE THE BODY WOULD MOVE TO HAS SOMETHING ON
						# IT -- a prop, a wall standing on the slab -- so the
						# body walks into that, whatever lies further down.
						occupied_next += 1
						continue
					var to: int = -1 if k < 0 else int(there[k][1])
					var drop: float = 1e9 if k < 0 else y - float(there[k][0])
					if drop <= FALL_M:
						continue
					drops += 1
					var x0: float = box.position.x + float(ix) * cell
					var z0: float = box.position.z + float(iz) * cell
					var x1: float = box.position.x + float(jx) * cell
					var z1: float = box.position.z + float(jz) * cell
					# A guard is only a guard ABOVE what a body steps over.
					var by: float = y + FALL_M + BARRIER_MARGIN
					var q := PhysicsRayQueryParameters3D.create(
						Vector3(x0, by, z0), Vector3(x1, by, z1))
					if not space.intersect_ray(q).is_empty():
						guarded += 1
						continue
					# A SOLID IN THE NEXT COLUMN IS A WALL BEFORE IT IS A FALL.
					# The part of the body above what it steps over, stood in
					# the next column at this cell's level: if it overlaps
					# anything there, the body walks into that, not off this.
					# Two artefacts on cold run 9317's package read as drops
					# until this was asked of every candidate: a column with no
					# surface at all (2,090 indoor "drops" at the foot of the
					# Empties' and the office's walls, once the cells inside a
					# wall were rejected), and a column whose next surface the
					# body fits on is a storey down because a prop or a wall
					# occupies this one -- 592 indoor "storey rims" beside
					# carton stacks, counters, planter boxes, desks and cubicle
					# banks, 183 of them 6.6 m "deep" where first-floor
					# furniture stood over the ground floor's wall line. Two
					# earlier spellings of this test are worth keeping: asked
					# only of a column with NO surface, with the capsule centred
					# 0.6 m up, it reached 0.3 m below the cell and met the
					# cell's own slab at a true rim (1,382 of the plate's rim
					# and 141 wall-line edges came back when it stopped); asked
					# of every candidate with the whole capsule from the cell's
					# level, it swallowed the guards (7,629 drops, 7,628
					# unguarded, ONE guarded) and would have read a kerb the
					# body steps over as a wall. Hence the shape starts at
					# FALL_M, the one number the step test and this share.
					_block.transform = Transform3D(Basis(),
						Vector3(x1, y + FALL_M + EPS + BLOCK_H * 0.5, z1))
					if not space.intersect_shape(_block, 1).is_empty():
						blocked += 1
						continue
					unguarded += 1
					# INDOORS OR UNDER THE SKY, and the difference is the
					# whole usefulness of this instrument. A body that walks
					# off an edge INSIDE a building has found a defect: a
					# stairwell nobody railed, a mezzanine with an open lip.
					# A roof edge or a dock is somebody's decision, and a gate
					# that refuses those refuses every level ever built. The
					# test is what is overhead: a slab or a roof means inside.
					var sky := PhysicsRayQueryParameters3D.create(
						Vector3(x0, y + STAND_M, z0),
						Vector3(x0, y + 100.0, z0))
					var indoors: bool = not space.intersect_ray(sky).is_empty()
					if indoors:
						indoor += 1
					if edges.size() < MAX_ROWS:
						edges.append({
							"x": snappedf((x0 + x1) * 0.5, 0.01),
							"y": snappedf(y, 0.01),
							"z": snappedf((z0 + z1) * 0.5, 0.01),
							"drop_m": snappedf(minf(drop, 999.0), 0.01),
							"indoors": indoors,
							"on": on,
							"to": to,
						})
	report["drop_edges"] = drops
	report["guarded"] = guarded
	report["blocked"] = blocked
	report["occupied_next"] = occupied_next
	report["unguarded"] = unguarded
	report["unguarded_indoors"] = indoor
	report["owners"] = _owner_paths
	edges.sort_custom(func(a, b): return float(a["drop_m"]) > float(b["drop_m"]))
	report["edges"] = edges
	_write(out_path, report)
	print("[edge] standable %d (occupied %d, steep %d), into things %d, drop edges %d (guarded %d, blocked %d), unguarded %d, UNGUARDED INDOORS %d"
		% [standable, occupied, _steep, occupied_next, drops, guarded, blocked, unguarded, indoor])
	quit(0)


func _write(out_path: String, report: Dictionary) -> void:
	var fh: FileAccess = FileAccess.open(out_path, FileAccess.WRITE)
	if fh == null:
		push_error("[edge] could not write %s" % out_path)
		return
	fh.store_string(JSON.stringify(report, "  "))
	fh.close()
