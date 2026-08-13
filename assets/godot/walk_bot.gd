extends SceneTree
## Headless WALK BOT: proves a composed package is traversable by simulating a
## player with real physics -- no rendering, no input, no human.
##
## Usage:
##   godot --headless --path <walk_preview_dir> --script res://walk_bot.gd \
##       -- <out_json> [scene_res_path]
##
## What it proves, per ladder in the package (the climb contract,
## DC docs/LADDER_CLIMB_CONTRACT.md):
##   ground        spawn point has floor collision beneath it (no fall-through)
##   approach      the bot can WALK to the ladder base (nothing blocks the way)
##   latch         the climb Area3D overlaps from the approach side
##   climb         driving the contract climb motion gains height to the top
##                 (the slab hole is real; the backside plane doesn't block)
##   top_exit      stepping away at the top lands on standable upper floor
##   landed_on     the collider it came to rest on, by name ("" = nothing)
##   overhead      the collider above the exit, by name ("" = open sky)
##   no_fall       bot never fell through the world at any point
##
## The bot uses the same movement law as player_walk.gd (climb = up+into over
## sqrt2, snap to the climb plane, top-exit push) but drives the wish vector
## itself, so what it certifies is the PACKAGE (colliders, areas, metadata),
## not any particular player script. Writes a JSON verdict and exits 0/1.

const MOVE_SPEED := 4.5
const CLIMB_SPEED := 6.0
# Must match the player capsule and the climb contract (DC ladder_geom
# CLIMB_STANDOFF): the bot is only a valid proof if it is the same size and
# rides the same distance off the ladder face as the real controller.
const CAPSULE_R := 0.35
const CAPSULE_H := 1.8
const CLIMB_STANDOFF := 0.5
const STEP_H := 0.5
const FRAME_DT := 1.0 / 60.0
const MAX_WALK_S := 20.0
const MAX_CLIMB_S := 20.0
const FALL_Y := -5.0

var _out_path := ""
var _scene_path := "res://site.tscn"
var _result := {"ok": false, "ladders": [], "error": ""}


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() >= 1:
		_out_path = args[0]
	if args.size() >= 2:
		_scene_path = args[1]
	_run()  # async: runs to its first await, then frame-driven


func _run() -> void:
	# let the tree come up before touching it
	await process_frame
	var packed: PackedScene = load(_scene_path)
	if packed == null:
		_fail("cannot load scene %s" % _scene_path)
		return
	var site: Node = packed.instantiate()
	root.add_child(site)
	# let physics settle / colliders register
	for i in range(5):
		await physics_frame

	var ladders: Array = []
	for l in get_nodes_in_group("ladder_area3d"):
		if l is Area3D:
			ladders.append(l)
	if ladders.is_empty():
		# a package without ladders passes vacuously but says so
		_result["ok"] = true
		_result["note"] = "no ladder_area3d in scene; traversal vacuous"
		_finish()
		return

	var all_ok := true
	for l in ladders:
		var verdict: Dictionary = await _test_ladder(l)
		_result["ladders"].append(verdict)
		all_ok = all_ok and verdict.get("ok", false)
	_result["ok"] = all_ok
	_finish()


func _make_bot() -> CharacterBody3D:
	var bot := CharacterBody3D.new()
	var shape := CollisionShape3D.new()
	var caps := CapsuleShape3D.new()
	caps.radius = CAPSULE_R
	caps.height = CAPSULE_H
	shape.shape = caps
	shape.position = Vector3(0, CAPSULE_H / 2.0, 0)
	bot.add_child(shape)
	bot.floor_snap_length = STEP_H
	bot.floor_max_angle = deg_to_rad(60)
	root.add_child(bot)
	return bot


func _test_ladder(l: Area3D) -> Dictionary:
	var v := {"ladder": String(l.name), "ok": false,
			  "ground": false, "approach": false, "latch": false,
			  "climb": false, "top_exit": false, "no_fall": true}
	var lt: Transform3D = l.global_transform
	var climb_h: float = float(l.get_meta("climb_height", 3.0))
	# spawn 1.6 m out on the APPROACH side (+Z of the area), at base height
	var base: Vector3 = lt.origin
	var out_dir: Vector3 = lt.basis.z.normalized()
	var spawn: Vector3 = base + out_dir * 1.6 + Vector3.UP * 0.2

	var bot := _make_bot()
	bot.global_position = spawn

	# GROUND: must find floor under the spawn within 3 m.
	var space := bot.get_world_3d().direct_space_state
	var q := PhysicsRayQueryParameters3D.create(
		spawn + Vector3.UP * 1.0, spawn + Vector3.DOWN * 3.0)
	q.exclude = [bot.get_rid()]
	var hit := space.intersect_ray(q)
	v["ground"] = not hit.is_empty()
	if not v["ground"]:
		bot.queue_free()
		return v
	bot.global_position = Vector3(spawn.x, hit["position"].y + 0.05, spawn.z)

	# APPROACH: walk toward the ladder base until the area overlaps the bot.
	var t := 0.0
	while t < MAX_WALK_S and not l.overlaps_body(bot):
		var to: Vector3 = base - bot.global_position
		to.y = 0.0
		var dir: Vector3 = to.normalized() if to.length() > 0.01 else Vector3.ZERO
		if not bot.is_on_floor():
			bot.velocity.y -= 9.8 * FRAME_DT
		else:
			bot.velocity.y = 0.0
		bot.velocity.x = dir.x * MOVE_SPEED
		bot.velocity.z = dir.z * MOVE_SPEED
		var before: Vector3 = bot.global_position
		bot.move_and_slide()
		_step_up(bot, before)
		if bot.global_position.y < FALL_Y:
			v["no_fall"] = false
			bot.queue_free()
			return v
		t += FRAME_DT
		await physics_frame
	v["approach"] = l.overlaps_body(bot)
	if not v["approach"]:
		v["blocked_at"] = _v3(bot.global_position)
		bot.queue_free()
		return v

	# LATCH: must be on the approach side of the climb plane.
	var linv: Transform3D = lt.affine_inverse()
	var rel: Vector3 = linv * bot.global_position
	v["latch"] = rel.z >= -0.05
	if not v["latch"]:
		bot.queue_free()
		return v

	# CLIMB: contract motion -- snap to the climb plane, drive straight up.
	t = 0.0
	var top_reached := false
	while t < MAX_CLIMB_S:
		rel = linv * bot.global_position
		if rel.y > climb_h + 0.9:
			top_reached = true
			break
		rel.z = CLIMB_STANDOFF
		bot.global_position = lt * rel
		bot.velocity = lt.basis * Vector3(0.0, CLIMB_SPEED, 0.0)
		bot.move_and_slide()
		if bot.global_position.y < FALL_Y:
			v["no_fall"] = false
			bot.queue_free()
			return v
		var new_rel: Vector3 = linv * bot.global_position
		if new_rel.y <= rel.y - 0.001 and t > 1.0:
			break  # pinned: something blocks the climb path
		t += FRAME_DT
		await physics_frame
	v["climb"] = top_reached
	v["climb_height_reached"] = snappedf((linv * bot.global_position).y, 0.01)
	if not top_reached:
		# A stalled climb is almost always geometry, not the bot: the slab cut
		# the ladder passes through is too small, or biased onto the wrong
		# side, so the capsule jams on the rim. Measure it and say so -- a
		# verdict of "climb: false" alone sends a human back into Blender to
		# guess.
		v["stall"] = _diagnose_stall(bot, l, lt, linv)
		bot.queue_free()
		return v

	# TOP EXIT: push away from the face (+Z), settle, must stand on floor at
	# roughly climb height (the upper story / roof is real and standable).
	t = 0.0
	while t < 3.0:
		bot.velocity = lt.basis * Vector3(0.0, 0.5, 2.5) \
			if t < 0.5 else bot.velocity + Vector3.DOWN * 9.8 * FRAME_DT
		bot.move_and_slide()
		if bot.global_position.y < FALL_Y:
			v["no_fall"] = false
			bot.queue_free()
			return v
		if t > 0.5 and bot.is_on_floor():
			break
		t += FRAME_DT
		await physics_frame
	rel = linv * bot.global_position
	v["top_exit"] = bot.is_on_floor() and rel.y > climb_h - 1.2
	v["final_rel_y"] = snappedf(rel.y, 0.01)
	# WHAT it exited onto, and whether anything is above -- not just that it
	# stood somewhere. `top_exit` alone reads true for a ladder through a
	# correctly-holed roof AND for a ladder with no roof at all, because both
	# end on a floor at climb height. Roadmap addendum item E: "missing
	# geometry and extra geometry are opposite failure modes; one scalar
	# cannot carry both." `_diagnose_stall` has always named its blocker; the
	# success path named nothing, and that asymmetry misled two diagnoses.
	v["landed_on"] = _name_below(bot)
	v["overhead"] = _name_above(bot)

	v["ok"] = v["ground"] and v["approach"] and v["latch"] \
		and v["climb"] and v["top_exit"] and v["no_fall"]
	bot.queue_free()
	return v


func _name_below(bot: CharacterBody3D) -> String:
	## The collider the bot is standing on, by node name; "" for nothing.
	## Same idiom as `_diagnose_stall`'s blocker ray, pointed the other way.
	var space: PhysicsDirectSpaceState3D = bot.get_world_3d().direct_space_state
	var q := PhysicsRayQueryParameters3D.create(
		bot.global_position + Vector3.UP * 0.2,
		bot.global_position + Vector3.DOWN * 1.5)
	q.exclude = [bot.get_rid()]
	var hit: Dictionary = space.intersect_ray(q)
	if hit.is_empty():
		return ""
	return String((hit["collider"] as Node).name)


func _name_above(bot: CharacterBody3D) -> String:
	## The collider above the exit point, by node name; "" is open sky.
	## THE PRESENCE TERM. A roof with its ladder void cut still has roof either
	## side of the hole, so stepping off the ladder and looking up finds one.
	## A building with no roof at all finds nothing. That is the difference
	## `top_exit` could not carry, and `void %` could not either -- it reads
	## 52.66% for a correctly-open roof and 52.66% for no roof.
	var space: PhysicsDirectSpaceState3D = bot.get_world_3d().direct_space_state
	var q := PhysicsRayQueryParameters3D.create(
		bot.global_position + Vector3.UP * 0.2,
		bot.global_position + Vector3.UP * 6.0)
	q.exclude = [bot.get_rid()]
	var hit: Dictionary = space.intersect_ray(q)
	if hit.is_empty():
		return ""
	return String((hit["collider"] as Node).name)


func _diagnose_stall(bot: CharacterBody3D, l: Area3D, lt: Transform3D,
		linv: Transform3D) -> Dictionary:
	## Why did the climb stop? Names the collider in the way and measures the
	## aperture at that height in LADDER-LOCAL axes: X across the ladder, Z out
	## from its face. The climb column the capsule needs is
	## z in [CLIMB_STANDOFF - r, CLIMB_STANDOFF + r]; a cut centred on the
	## ladder instead of biased onto the approach side fails exactly here.
	var d := {}
	var rel: Vector3 = linv * bot.global_position
	var space: PhysicsDirectSpaceState3D = bot.get_world_3d().direct_space_state

	# what is directly overhead?
	var q := PhysicsRayQueryParameters3D.create(
		bot.global_position + Vector3.UP * 0.9,
		bot.global_position + Vector3.UP * 3.0)
	q.exclude = [bot.get_rid()]
	var hit: Dictionary = space.intersect_ray(q)
	if hit.is_empty():
		# nothing straight above: the rim is off to one side of the capsule
		q = PhysicsRayQueryParameters3D.create(
			lt * Vector3(0.0, rel.y + 0.9, CLIMB_STANDOFF + CAPSULE_R),
			lt * Vector3(0.0, rel.y + 3.0, CLIMB_STANDOFF + CAPSULE_R))
		q.exclude = [bot.get_rid()]
		hit = space.intersect_ray(q)
	if not hit.is_empty():
		d["blocker"] = String((hit["collider"] as Node).name)
		d["blocker_rel_y"] = snappedf((linv * (hit["position"] as Vector3)).y, 0.01)

	# map the aperture at the blocking height
	var probe_y: float = float(d.get("blocker_rel_y", rel.y + 1.0))
	var open_z_lo := 9.9
	var open_z_hi := -9.9
	var z := -1.0
	while z <= 2.0:
		var rq := PhysicsRayQueryParameters3D.create(
			lt * Vector3(0.0, probe_y + 0.6, z),
			lt * Vector3(0.0, probe_y - 0.2, z))
		rq.exclude = [bot.get_rid()]
		if space.intersect_ray(rq).is_empty():
			open_z_lo = minf(open_z_lo, z)
			open_z_hi = maxf(open_z_hi, z)
		z += 0.05
	if open_z_hi > open_z_lo:
		d["aperture_z"] = [snappedf(open_z_lo, 0.02), snappedf(open_z_hi, 0.02)]
		d["climb_column_z"] = [CLIMB_STANDOFF - CAPSULE_R,
							   CLIMB_STANDOFF + CAPSULE_R]
		var fits: bool = (open_z_lo <= CLIMB_STANDOFF - CAPSULE_R
			and open_z_hi >= CLIMB_STANDOFF + CAPSULE_R)
		d["aperture_admits_capsule"] = fits
		if not fits:
			d["reason"] = ("slab cut does not cover the climb column: the "
				+ "capsule climbs at z=%.2f +/- %.2f but the opening is "
				+ "z %.2f..%.2f -- bias the cut onto the approach side") % [
					CLIMB_STANDOFF, CAPSULE_R, open_z_lo, open_z_hi]
	else:
		d["aperture_z"] = []
		d["aperture_admits_capsule"] = false
		d["reason"] = "no opening at all at rel_y %.2f -- the slab is solid " \
			% probe_y + "over the ladder"
	return d


func _step_up(bot: CharacterBody3D, before: Vector3) -> void:
	if not bot.is_on_wall():
		return
	var horiz := Vector3(bot.velocity.x, 0.0, bot.velocity.z)
	if horiz.length() < 0.05:
		return
	var wanted := horiz * FRAME_DT
	var moved := bot.global_position - before
	moved.y = 0.0
	var remaining := wanted - moved
	remaining.y = 0.0
	if remaining.length() < 0.001:
		return
	var raised := bot.global_transform
	raised.origin += Vector3.UP * STEP_H
	if bot.test_move(raised, remaining):
		return
	raised.origin += remaining
	var landing := KinematicCollision3D.new()
	if bot.test_move(raised, Vector3.DOWN * (STEP_H + 0.05), landing):
		bot.global_position = raised.origin + landing.get_travel()


func _v3(p: Vector3) -> Array:
	return [snappedf(p.x, 0.01), snappedf(p.y, 0.01), snappedf(p.z, 0.01)]


func _fail(msg: String) -> void:
	_result["error"] = msg
	_finish()


func _finish() -> void:
	var text := JSON.stringify(_result, "  ")
	if _out_path != "":
		var f := FileAccess.open(_out_path, FileAccess.WRITE)
		if f:
			f.store_string(text)
			f.close()
	print("[walkbot] " + ("OK" if _result.get("ok", false) else "FAIL"))
	print(text)
	quit(0 if _result.get("ok", false) else 1)
