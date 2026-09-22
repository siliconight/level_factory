extends SceneTree
## Count the occluders the scene a recipient ACTUALLY RUNS can reach.
##
## WHY THIS EXISTS, and it is the second instance of one defect in one
## feature. LF 0.98.0 added an audit written to make "flag on, occluders
## absent" unrepresentable. It counted `OccluderInstance3D` in the package's
## scenes -- in ALL of them, by `rglob` -- and cold run 9066's package passed
## it with 301 nodes present and ZERO of them reachable: `occluders.tscn` was
## instanced from `site.tscn`, and `run/main_scene` is `mission.tscn`, which
## instances `presentation/lux.applied.tscn` and the dressing layer and never
## names `site.tscn` at all. A recipient got the culler's per-frame cost and
## nothing to cull, which is the exact state 0.98.0 existed to prevent, one
## scene along.
##
## So this asks the only question that settles it: load what `project.godot`
## says the engine loads, let it become what it will be, and count what is
## in the tree. `packages/exporting/occluders.py` parses the same question
## statically and needs no Godot; this one is the arbiter, and the export
## runs both so that a disagreement between them is a build failure rather
## than a choice of which to believe.
##
## HEADLESS IS ENOUGH and is what this uses. The question is what nodes exist
## in the tree, which a run that draws nothing can answer; nothing here reads
## a frame time. See CLAUDE.md on how a probe is launched -- this `extends
## SceneTree`, drives itself, and quits.
##
## Usage:
##   godot --headless --path <package> --script res://count_occluders.gd \
##       -- <report_fs_path>

#: The entry scene instances its content from `_ready()`, so the tree is not
#: what it will be until a frame has passed. Four rather than one because a
#: scene that defers a level of its own would otherwise be counted half-built,
#: and three spare frames on a headless run cost nothing.
const SETTLE_FRAMES := 4

const SCHEMA := "lf.occluders.runtime.v1"
const MAIN_SCENE_KEY := "application/run/main_scene"
const OCCLUSION_KEY := "rendering/occlusion_culling/use_occlusion_culling"


func _initialize() -> void:
	var args: PackedStringArray = OS.get_cmdline_user_args()
	if args.size() < 1:
		print("[occ-runtime] USAGE: <report>")
		quit(2)
		return
	_run(args[0])


func _walk(n: Node, out: Array) -> void:
	out.append(n)
	for c in n.get_children():
		_walk(c, out)


func _run(report_path: String) -> void:
	var main_scene: String = String(
		ProjectSettings.get_setting(MAIN_SCENE_KEY, ""))
	if main_scene == "":
		_fail(report_path, "project.godot names no %s" % [MAIN_SCENE_KEY])
		return
	var packed: PackedScene = load(main_scene) as PackedScene
	if packed == null:
		_fail(report_path, "cannot load %s" % [main_scene])
		return
	var entry: Node = packed.instantiate()
	if entry == null:
		_fail(report_path, "cannot instantiate %s" % [main_scene])
		return
	root.add_child(entry)
	for i in range(SETTLE_FRAMES):
		await process_frame

	var nodes: Array = []
	_walk(entry, nodes)
	var occluders: int = 0
	var holders: int = 0
	var with_shape: int = 0
	for x in nodes:
		var occ: OccluderInstance3D = x as OccluderInstance3D
		if occ == null:
			continue
		occluders += 1
		# A node with no shape is a node that costs a node and occludes
		# nothing -- the worst of both, and invisible to a text count.
		if occ.occluder != null:
			with_shape += 1
	for x in nodes:
		var n: Node = x as Node
		if n != null and n.scene_file_path.get_file() == "occluders.tscn":
			holders += 1

	var report := {
		"schema": SCHEMA,
		"ok": true,
		"main_scene": main_scene,
		"nodes_in_tree": nodes.size(),
		"occluder_nodes": occluders,
		"occluders_with_a_shape": with_shape,
		"occluder_holders": holders,
		# NAMED FOR WHEN IT WAS READ, because the export settles that flag
		# from the count that shipped and does it AFTER this runs. A package
		# with 301 reachable occluders records `false` here and ships `true`,
		# and a key called `use_occlusion_culling` would read as the package
		# contradicting itself.
		"occlusion_flag_when_counted": bool(
			ProjectSettings.get_setting(OCCLUSION_KEY, false)),
	}
	var fh: FileAccess = FileAccess.open(report_path, FileAccess.WRITE)
	if fh == null:
		print("[occ-runtime] cannot write report %s" % [report_path])
		_cleanup(entry)
		quit(3)
		return
	fh.store_string(JSON.stringify(report, "  "))
	fh.close()
	var line: String = ("[occ-runtime] main_scene=%s nodes=%d occluders=%d"
		+ " with_shape=%d holders=%d")
	print(line % [main_scene, nodes.size(), occluders, with_shape, holders])
	_cleanup(entry)
	quit(0)


func _cleanup(entry: Node) -> void:
	## Without this the run ends on a wall of leaked-RID errors, which makes a
	## clean count look like a failed one in the export log.
	if entry != null and is_instance_valid(entry):
		root.remove_child(entry)
		entry.free()


func _fail(report_path: String, why: String) -> void:
	## An unrecognised shape FAILS. A report that cannot say what it loaded
	## must not read as a package whose entry scene had no occluders in it.
	var fh: FileAccess = FileAccess.open(report_path, FileAccess.WRITE)
	if fh != null:
		fh.store_string(JSON.stringify({
			"schema": SCHEMA, "ok": false, "error": why,
		}, "  "))
		fh.close()
	print("[occ-runtime] FAILED: %s" % [why])
	quit(4)
