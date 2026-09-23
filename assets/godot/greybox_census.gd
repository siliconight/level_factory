extends SceneTree

## HOW MUCH GREYBOX SURVIVES INTO A THEMED PACKAGE, BY ROLE AND BY AREA.
##
## WHY THIS RUNS IN THE ENGINE AND NOT OVER THE GLBs. `zoo_worldskin.gd` is an
## IMPORT post-processor: a shipped GLB keeps its `gb_*` materials by design
## and the skin is applied to the imported resource. A gate reading glTF JSON
## would therefore refuse every package ever built, and would be measuring the
## wrong artefact besides. The question is what the running scene draws, so
## the measurement is taken from the running scene.
##
## WHAT PRODUCED THE NUMBER, said here so a reader never has to guess: this
## walks the scene named by `application/run/main_scene`, the same entry the
## occluder bake walks from, and counts SURFACES on drawn `MeshInstance3D`
## nodes. Material identity is Deli Counter's own role naming (`gb_floor`,
## `gb_stair`, `gb_ladder`, ...), which was confirmed to survive Godot's
## import before this file was written -- 412 such surfaces on cold run 9070's
## package, 346 of them `gb_floor`. A name-prefix test rather than "has no
## albedo texture", because the latter over-reports by design: a light lens
## and a bulb are emissive and carry no albedo, and ~280 of them in that same
## package would have read as defects.
##
## AREA IS TOTAL MESH SURFACE AREA, NOT VISIBLE AREA, and the difference is
## large enough that calling it "area" alone would be a lie. Measured on cold
## run 9070's package: `gb_floor` reports 17,447 m2 over 346 surfaces, and
## almost all of it is slab TOP and BOTTOM faces buried under a themed floor
## and a themed ceiling. What the walker actually saw was the 10.44 m2 of cut
## collar around 8 openings -- a thousandth of the printed figure.
##
## Exposed area is NOT attempted here and no reader should infer it. Measuring
## it means deciding what covers what, which is a visibility question this
## pass has no business answering in a gate. So the area is a magnitude for
## comparing one run against the next, the SURFACE COUNT is what the refusal
## keys on, and this paragraph exists so nobody quotes the square metres as
## though a walker could see them.
##
## IS THIS PACKAGE THEMED AT ALL? Measured from the same scene rather than
## assumed from a profile name: a package carrying no `M_Skin_*` material has
## had no theming applied, so its greybox is the product rather than a defect.
## That case reports `themed: false` and the Python side declines to judge it,
## the way `glb_refs` declines to certify a package with no GLB in it.
##
## Usage: godot --headless --path <pkg> --script res://greybox_census.gd -- <out.json>

const GREYBOX_PREFIX := "gb_"
const SKIN_PREFIX := "M_Skin_"


func _initialize() -> void:
	_run()


func _walk(n: Node, out: Array) -> void:
	out.append(n)
	for c in n.get_children():
		_walk(c, out)


## Projected surface area of one surface, in world units. Every triangle, both
## facings: a slab's collar is vertical and a floor's is not, and a measure
## that favoured one would misreport exactly the case this exists for.
func _surface_area(mi: MeshInstance3D, s: int) -> float:
	var mesh: Mesh = mi.mesh
	var arrays: Array = mesh.surface_get_arrays(s)
	if arrays.is_empty():
		return 0.0
	var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var idx: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var xf: Transform3D = mi.global_transform
	var n: int = idx.size() / 3 if idx.size() > 0 else verts.size() / 3
	var area: float = 0.0
	for t in range(n):
		var a: Vector3
		var b: Vector3
		var c: Vector3
		if idx.size() > 0:
			a = xf * verts[idx[t * 3]]
			b = xf * verts[idx[t * 3 + 1]]
			c = xf * verts[idx[t * 3 + 2]]
		else:
			a = xf * verts[t * 3]
			b = xf * verts[t * 3 + 1]
			c = xf * verts[t * 3 + 2]
		area += (b - a).cross(c - a).length() * 0.5
	return area


func _run() -> void:
	var args: PackedStringArray = OS.get_cmdline_user_args()
	var out_path: String = args[0] if args.size() > 0 else "res://greybox_census.json"
	await process_frame
	var main_scene: String = String(ProjectSettings.get_setting(
		"application/run/main_scene", ""))
	var report: Dictionary = {
		# The Python side refuses a report whose schema it does not know,
		# rather than reading an unrecognised shape as a clean package.
		"schema": "greybox_census/1",
		"main_scene": main_scene,
		"themed": false,
		"greybox_surfaces": 0,
		"greybox_area_m2": 0.0,
		"by_role": {},
		"slab_surfaces": 0,
		"slab_area_m2": 0.0,
		"worst": [],
		"error": "",
	}
	if main_scene == "":
		# An unrecognised shape FAILS rather than passing. A census that cannot
		# find the scene has learned nothing and must say so.
		report["error"] = "no application/run/main_scene in project.godot"
		_write(out_path, report)
		quit(0)
		return
	var ps: PackedScene = load(main_scene) as PackedScene
	if ps == null:
		report["error"] = "main_scene %s did not load" % main_scene
		_write(out_path, report)
		quit(0)
		return
	var scene: Node = ps.instantiate()
	root.add_child(scene)
	for i in range(20):
		await process_frame

	var nodes: Array = []
	_walk(scene, nodes)
	var by_role: Dictionary = {}
	var worst: Array = []
	for n in nodes:
		var mi: MeshInstance3D = n as MeshInstance3D
		if mi == null or mi.mesh == null:
			continue
		for s in range(mi.mesh.get_surface_count()):
			var mat: Material = mi.get_active_material(s)
			if mat == null:
				continue
			var nm: String = String(mat.resource_name)
			if nm.begins_with(SKIN_PREFIX):
				report["themed"] = true
				continue
			if not nm.begins_with(GREYBOX_PREFIX):
				continue
			var area: float = _surface_area(mi, s)
			var row: Dictionary = by_role.get(nm, {"surfaces": 0, "area_m2": 0.0})
			row["surfaces"] = int(row["surfaces"]) + 1
			row["area_m2"] = float(row["area_m2"]) + area
			by_role[nm] = row
			report["greybox_surfaces"] = int(report["greybox_surfaces"]) + 1
			report["greybox_area_m2"] = float(report["greybox_area_m2"]) + area
			# A slab is the class this gate was built to close: after the
			# worldskin's slab pass, a greybox one can only mean that pass
			# failed. Named separately so the refusal is attributable.
			if String(mi.name).begins_with("slab_"):
				report["slab_surfaces"] = int(report["slab_surfaces"]) + 1
				report["slab_area_m2"] = float(report["slab_area_m2"]) + area
			worst.append({"node": String(scene.get_path_to(mi)),
				"material": nm, "area_m2": area})
	worst.sort_custom(func(a, b): return float(a["area_m2"]) > float(b["area_m2"]))
	report["worst"] = worst.slice(0, mini(20, worst.size()))
	report["by_role"] = by_role
	_write(out_path, report)
	print("[greybox] %d surface(s) on a gb_* material, %.2f m2; slabs %d (%.2f m2); themed=%s"
		% [int(report["greybox_surfaces"]), float(report["greybox_area_m2"]),
			int(report["slab_surfaces"]), float(report["slab_area_m2"]),
			str(report["themed"])])
	quit(0)


func _write(out_path: String, report: Dictionary) -> void:
	var fh: FileAccess = FileAccess.open(out_path, FileAccess.WRITE)
	if fh == null:
		push_error("[greybox] could not write %s" % out_path)
		return
	fh.store_string(JSON.stringify(report, "  "))
	fh.close()
