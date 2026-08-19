extends SceneTree

# Does the MultiMesh buffer decode to the same transforms as the node scene?
#
# `packages/exporting/dressing_scene.py` writes the same placements two ways:
# a MultiMesh whose per-instance transforms live in a PackedFloat32Array, and
# ordinary MeshInstance3D nodes whose transforms use the `Transform3D(...)`
# literal Lot already ships on hardware. The node form is verified; the buffer
# layout -- which twelve floats, in which order -- is a convention the writer
# could not verify without Godot.
#
# This asks Godot. `MultiMesh.get_instance_transform(i)` decodes the buffer
# through the engine's own accessor, so comparing it to the node's transform
# tests the exact assumption and nothing else. Eyeballing two viewports would
# have answered "they look the same" for a shear of a few degrees; this
# answers in metres.
#
#   godot --headless --path <project> --script res://dressing_ab.gd

const TOL := 0.0005          # half a millimetre; %g in the .tscn carries 6 s.f.

func _initialize() -> void:
	var mm_path := "res://dressing_mm.tscn"
	var nd_path := "res://dressing_nodes.tscn"
	# Explicit types, not `:=`. `load()` returns an untyped Variant, so the
	# inference on `.instantiate()` has nothing to work from and the script
	# fails to PARSE -- which looks like the A/B failing rather than the A/B
	# never having run.
	var mm_scene: PackedScene = load(mm_path)
	var nd_scene: PackedScene = load(nd_path)
	if mm_scene == null or nd_scene == null:
		print("AB FAIL: could not load %s or %s" % [mm_path, nd_path])
		quit(2)
		return

	var a: Node = mm_scene.instantiate()
	var b: Node = nd_scene.instantiate()

	var from_buffer := {}
	for child in a.get_children():
		if child is MultiMeshInstance3D:
			var mm: MultiMesh = child.multimesh
			var arr: Array[Transform3D] = []
			for i in range(mm.instance_count):
				arr.append(mm.get_instance_transform(i))
			from_buffer[String(child.name)] = arr

	var from_nodes := {}
	for child in b.get_children():
		var arr: Array[Transform3D] = []
		for gc in child.get_children():
			if gc is MeshInstance3D:
				arr.append(gc.transform)
		if arr.size() > 0:
			from_nodes[String(child.name)] = arr

	var groups := from_buffer.keys()
	groups.sort()
	var node_groups := from_nodes.keys()
	node_groups.sort()
	if groups != node_groups:
		print("AB FAIL: different groups. multimesh=%s nodes=%s"
			% [str(groups), str(node_groups)])
		quit(2)
		return

	var total := 0
	var worst := 0.0
	var worst_where := ""
	var mismatches := 0
	var all_identity := true
	var any_node_moved := false

	for g in groups:
		var xa: Array = from_buffer[g]
		var xb: Array = from_nodes[g]
		if xa.size() != xb.size():
			print("AB FAIL: %s has %d instances in the buffer and %d nodes"
				% [g, xa.size(), xb.size()])
			quit(2)
			return
		for i in range(xa.size()):
			total += 1
			if not xa[i].is_equal_approx(Transform3D.IDENTITY):
				all_identity = false
			if not xb[i].is_equal_approx(Transform3D.IDENTITY):
				any_node_moved = true
			var d := _deviation(xa[i], xb[i])
			if d > worst:
				worst = d
				worst_where = "%s[%d]" % [g, i]
			if d > TOL:
				mismatches += 1
				if mismatches <= 3:
					print("  %s[%d] deviates %.6f" % [g, i, d])
					print("    buffer: %s" % str(xa[i]))
					print("    node  : %s" % str(xb[i]))

	print("compared %d instances across %d groups" % [total, groups.size()])
	print("worst deviation %.8f at %s (tolerance %.6f)"
		% [worst, worst_where, TOL])
	# EVERY buffer transform being exactly identity is not a wrong layout --
	# a wrong layout produces garbage, not the identity matrix. It means the
	# buffer was never read. `MultiMesh.get_instance_transform` goes through
	# the RenderingServer, and under --headless that is RendererDummy, whose
	# MultiMesh storage keeps nothing. Measured: 4374 of 4374 instances came
	# back identity on a manifest whose node transforms were all over the map.
	#
	# Without this branch the run prints "the layout is wrong" and indicts
	# correct code. Telling "the experiment did not run" apart from "the
	# thing under test failed" is the whole job of a harness.
	if all_identity and any_node_moved:
		print("AB INVALID: every MultiMesh transform read back as identity "
			+ "while the node scene's transforms vary.")
		print("  The buffer was not read. MultiMesh transforms live in the "
			+ "RenderingServer, and --headless uses RendererDummy, which "
			+ "stores none.")
		print("  Re-run the A/B step WITHOUT --headless. This says nothing "
			+ "about multimesh_floats() either way.")
		quit(3)
	elif mismatches > 0:
		print("AB FAIL: %d of %d instances disagree -- the MultiMesh buffer "
			% [mismatches, total]
			+ "layout in multimesh_floats() is wrong")
		quit(1)
	else:
		print("AB OK: the buffer decodes to the node transforms")
		quit(0)

func _deviation(x: Transform3D, y: Transform3D) -> float:
	# Largest single component difference across basis and origin. A shear or
	# a transposed basis shows up here even when the origin matches, which is
	# the failure mode a screenshot hides.
	var worst := 0.0
	for i in range(3):
		var ba: Vector3 = x.basis[i]
		var bb: Vector3 = y.basis[i]
		for k in range(3):
			worst = max(worst, abs(ba[k] - bb[k]))
	for k in range(3):
		worst = max(worst, abs(x.origin[k] - y.origin[k]))
	return worst
