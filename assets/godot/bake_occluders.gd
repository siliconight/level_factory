extends SceneTree
## Measure the package's occluders: the solid shells a body cannot see through.
##
## WHY THIS EXISTS. Measured on cold run 9062's package, standing inside the
## card shop, by hiding one top-level branch at a time and reading the draw
## count back: of 4,635 draw calls at `interior_c`, 1,599 were the country
## club across the street and 1,481 were the market hall -- 99.8% and 99.6%
## of every mesh those two buildings own, their interiors included. Frustum
## culling cannot reject them, because they ARE in front of the camera; only
## the wall between can, and nothing was telling the engine there was a wall.
##
## WHY GODOT MEASURES AND PYTHON WRITES. The occluder has to match the
## module's real extent. A module's filename carries its width
## (`wall_..._w200_...`) and not its height or its thickness, and deriving
## those from the genome would be a second source of truth for a number the
## mesh already knows -- so Godot, which is the only thing that has imported
## these GLBs, measures them into a report. It does NOT write the scene, for
## two reasons both measured on this package rather than assumed:
##
##   * `ResourceSaver` names sub-resources non-deterministically. Two runs
##     over an unchanged package produced two different files, and the
##     package is supposed to be reproducible.
##   * 395 occluders used 17 distinct sizes. Godot's packer wrote 395
##     sub-resources; `packages/exporting/occluders.py` writes 17 and shares
##     them, which is the same rule as never expressing variation as a new
##     resource.
##
## Same division of labour as `assets/godot/extract_meshes.gd`: Godot does
## what only Godot can, Python verifies the report rather than an exit code.
##
## WHAT BECOMES AN OCCLUDER, and the rule is the module's own GLB name:
##
##   solid   wall_ roof_ floor_ ceiling_   a body cannot see through it
##   porous  window_ doorway_ breach_      the opening IS the module
##   glass   anything carrying `mglass`    a storefront shows the street, and
##                                         an occluder there would cull what
##                                         is visibly through it
##   never   prop_ and everything else
##
## `wallEnd_` is solid brick and is skipped: it is a corner filler, and the
## count of them is in the report so the skip is priced rather than assumed.
##
## ORIENTED, NOT AXIS-ALIGNED. The box is built from the module's LOCAL
## bounds and carries the module's own transform. A world-space AABB would
## inflate a rotated wall to its diagonal -- on this package every building
## happens to sit square, so that error would have measured zero here and
## shipped a generator that over-occludes the first time a brief asks for a
## street at an angle.
##
## The box is shrunk by SHRINK_M per side. An occluder flush with the surface
## it describes can cull that surface at a grazing angle; too small only
## costs submissions, too large costs a hole in the level.
##
## Usage:
##   godot --headless --path <package> --script res://bake_occluders.gd \
##       -- <scene_res_path> <report_fs_path>

const SOLID_PREFIXES := ["wall_", "roof_", "floor_", "ceiling_"]
const POROUS_PREFIXES := ["window_", "doorway_", "breach_"]
const FILLER_PREFIXES := ["wallend_"]
const GLASS_TOKEN := "mglass"

#: Metres trimmed from each side of every box (see the header).
const SHRINK_M := 0.02

#: A module whose longest side is under this is not worth twelve triangles.
const MIN_EXTENT_M := 0.5

#: Decimals kept in the report. 4 is a tenth of a millimetre -- three orders
#: below SHRINK_M, so it cannot move a face across the margin -- and it is
#: what makes two runs over one package produce one file. Nothing downstream
#: asks a float question of these; the shrink is decided here, at full
#: precision, and the report carries the answer.
const ROUND_DP := 4

var _counts := {
	"solid": 0, "porous": 0, "glass": 0, "filler": 0, "other": 0,
	"no_bounds": 0, "too_small": 0,
}


func _initialize() -> void:
	var args: PackedStringArray = OS.get_cmdline_user_args()
	if args.size() < 2:
		print("[occluders] USAGE: <scene> <report>")
		quit(2)
		return
	_run(args[0], args[1])


func _walk(n: Node, out: Array) -> void:
	out.append(n)
	for c in n.get_children():
		_walk(c, out)


func _local_bounds(n: Node3D) -> AABB:
	## The module's extent in its OWN frame, so the occluder can be placed
	## with the module's rotation instead of swelling to a world-space AABB.
	var inv: Transform3D = n.global_transform.affine_inverse()
	var nodes: Array = []
	_walk(n, nodes)
	var box := AABB()
	var first := true
	for x in nodes:
		var v: VisualInstance3D = x as VisualInstance3D
		if v == null:
			continue
		var a: AABB = (inv * v.global_transform) * v.get_aabb()
		if first:
			box = a
			first = false
		else:
			box = box.merge(a)
	return box


func classify(stem: String) -> String:
	var s: String = stem.to_lower()
	if s.contains(GLASS_TOKEN):
		return "glass"
	for p in FILLER_PREFIXES:
		if s.begins_with(p):
			return "filler"
	for p in POROUS_PREFIXES:
		if s.begins_with(p):
			return "porous"
	for p in SOLID_PREFIXES:
		if s.begins_with(p):
			return "solid"
	return "other"


func _r(v: float) -> float:
	return snappedf(v, pow(10.0, -ROUND_DP))


func _run(scene_path: String, report_path: String) -> void:
	var packed: PackedScene = load(scene_path) as PackedScene
	if packed == null:
		_fail(report_path, "cannot load %s" % [scene_path])
		return
	var site: Node = packed.instantiate()
	if site == null:
		_fail(report_path, "cannot instantiate %s" % [scene_path])
		return
	root.add_child(site)
	await process_frame

	var site3: Node3D = site as Node3D
	var site_inv := Transform3D()
	if site3 != null:
		site_inv = site3.global_transform.affine_inverse()

	var nodes: Array = []
	_walk(site, nodes)
	# Tree order, which is file order: the same package produces the same
	# report, row for row.
	var rows: Array = []
	for x in nodes:
		var n: Node3D = x as Node3D
		if n == null:
			continue
		var src: String = n.scene_file_path
		if src == "":
			continue
		var stem: String = src.get_file().get_basename()
		var kind: String = classify(stem)
		_counts[kind] = int(_counts[kind]) + 1
		if kind != "solid":
			continue
		var box: AABB = _local_bounds(n)
		if box.size.x <= 0.0 or box.size.y <= 0.0 or box.size.z <= 0.0:
			_counts["no_bounds"] = int(_counts["no_bounds"]) + 1
			continue
		if maxf(box.size.x, maxf(box.size.y, box.size.z)) < MIN_EXTENT_M:
			_counts["too_small"] = int(_counts["too_small"]) + 1
			continue
		var size := Vector3(
			maxf(SHRINK_M, box.size.x - SHRINK_M * 2.0),
			maxf(SHRINK_M, box.size.y - SHRINK_M * 2.0),
			maxf(SHRINK_M, box.size.z - SHRINK_M * 2.0))
		var t: Transform3D = site_inv * n.global_transform \
			* Transform3D(Basis(), box.get_center())
		rows.append({
			"node": String(n.name),
			"module": stem,
			"size": [_r(size.x), _r(size.y), _r(size.z)],
			"basis": [
				_r(t.basis.x.x), _r(t.basis.x.y), _r(t.basis.x.z),
				_r(t.basis.y.x), _r(t.basis.y.y), _r(t.basis.y.z),
				_r(t.basis.z.x), _r(t.basis.z.y), _r(t.basis.z.z)],
			"origin": [_r(t.origin.x), _r(t.origin.y), _r(t.origin.z)],
		})

	var report := {
		"schema": "lf.occluders.v1",
		"ok": true,
		"scene": scene_path,
		"occluders": rows.size(),
		"shrink_m": SHRINK_M,
		"min_extent_m": MIN_EXTENT_M,
		"round_dp": ROUND_DP,
		"classified": _counts,
		"modules": rows,
	}
	var fh: FileAccess = FileAccess.open(report_path, FileAccess.WRITE)
	if fh == null:
		print("[occluders] cannot write report %s" % [report_path])
		_cleanup(site)
		quit(3)
		return
	fh.store_string(JSON.stringify(report, "  "))
	fh.close()
	print("[occluders] measured=%d solid=%d porous=%d glass=%d filler=%d other=%d"
		% [rows.size(), int(_counts["solid"]), int(_counts["porous"]),
		   int(_counts["glass"]), int(_counts["filler"]), int(_counts["other"])])
	_cleanup(site)
	quit(0)


func _cleanup(site: Node) -> void:
	## Without this the run ends on a wall of leaked-RID errors, which makes a
	## clean bake look like a failed one in the export log.
	if site != null and is_instance_valid(site):
		root.remove_child(site)
		site.free()


func _fail(report_path: String, why: String) -> void:
	## An unrecognised shape FAILS. A report that cannot say what it produced
	## must not read as a package with no occluders in it.
	var fh: FileAccess = FileAccess.open(report_path, FileAccess.WRITE)
	if fh != null:
		fh.store_string(JSON.stringify({
			"schema": "lf.occluders.v1", "ok": false, "error": why,
		}, "  "))
		fh.close()
	print("[occluders] FAILED: %s" % [why])
	quit(4)
