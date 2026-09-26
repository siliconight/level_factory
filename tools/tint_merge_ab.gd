extends SceneTree

## WHAT WOULD COLLAPSING THE TINT VARIANTS ACTUALLY BUY, IN DRAW CALLS.
##
## Cold run 9080's package ships 43 materials named
## `M_Skin_metal_painted_delco_1997_<hex>` that differ in nothing but
## `baseColorFactor` -- same albedo image, same roughness image, same atlas
## rect, same flags. Across the package 284 materials are of that shape, in 75
## of 295 `.glb` files. That is CLAUDE.md's first rule under "draw calls are
## the budget" being broken, and it is broken deliberately:
## `zoo/zoo_keeper/bpylayer/materials.py:157` puts the tint in the shader graph,
## the glTF exporter folds it into `baseColorFactor`, and a factor is a MATERIAL
## property, so one material per colour follows necessarily.
##
## A MATERIAL COUNT IS NOT A PRICE, which this repo measured the hard way five
## hours before this file was written: 13.16x the material resources cost 4.65x
## the milliseconds. So 284 is not an answer, it is a question.
##
## WHAT THE COUNT ACTUALLY COSTS, and why sharing a material is not itself the
## saving. A draw call is per surface per instance, so giving two meshes the
## same material merges nothing on its own. But MERGING requires a shared
## material -- Zoo 1.1.0's merge is by material, "118 meshes to 4, triangles
## identical, interiors 59-63% faster" -- so every tint variant is a merge that
## cannot happen. This probe performs that merge at runtime and measures the
## difference at fixed stations.
##
## THE CONTROL IS THE TRIANGLE COUNT, and it is the same control the merge that
## preceded this used. A merge that drops geometry gets faster for the wrong
## reason and looks exactly like a win. `primitives` must come back IDENTICAL
## between the arms; the runner refuses the row otherwise. Frame luminance is
## recorded beside it because the merged arm should also look the same: the
## tint is moved from `albedo_color` into the vertex colour channel, which is
## what glTF multiplies anyway (`base = factor * texture * COLOR_0`) and what
## Zoo already uses for wear one function away from the line that mints these.
##
## A WINDOW IS OPENED ON PURPOSE. Headless draws nothing, so every
## `RENDERING_INFO_*` counter reads 0 and there is no frame to time.
##
## Usage:
##   godot --path <pkg> --script res://tint_merge_ab.gd -- <out.json> <arm>
##     arm: as_is | merged

## THE SAME FRAME EVERY OTHER FIGURE IN THIS REPO WAS TAKEN IN. A draw-call
## figure at a different window size is not comparable to the ones already
## published.
const W := 1280
const H := 720
const EYE := 1.6
const WARMUP := 120
const SAMPLE := 300


func _initialize() -> void:
	var a: PackedStringArray = OS.get_cmdline_user_args()
	if a.size() < 2:
		print("[tint_merge_ab] USAGE: <out.json> <arm>   arm: as_is | merged")
		quit(2)
		return
	_run(a[0], a[1])


func _walk(n: Node, out: Array) -> void:
	out.append(n)
	for c in n.get_children():
		_walk(c, out)


## The module a mesh belongs to: the nearest ancestor that was instanced from
## its own file.
##
## MERGE WITHIN A MODULE, NEVER ACROSS ONE. "The chunk to merge is the largest
## unit that becomes visible and invisible as one thing" -- a whole street
## merged into one mesh would submit faster and play slower, because looking at
## one storefront would keep the rest alive. A placed `.glb` is that unit, and
## `scene_file_path` is how a node says it is one.
func _module_of(n: Node) -> int:
	var cur: Node = n
	while cur != null:
		if not String(cur.scene_file_path).is_empty():
			return cur.get_instance_id()
		cur = cur.get_parent()
	return 0


## Two materials that differ only in their colour.
##
## READ WHAT IT POINTS AT, not what it is called. The name carries the hex
## suffix and stripping it would be a name test -- which is the version of this
## check that reports a package clean, because a writer emits its own texture
## slot per material even when every slot resolves to one image. So the key is
## the resources and the flags, and the NAME STEM is appended only as a
## tie-break so two unrelated families sharing one neutral texture are not
## merged into each other.
func _tint_key(m: BaseMaterial3D) -> String:
	var alb: Texture2D = m.albedo_texture
	var orm: Texture2D = m.orm_texture if m.orm_texture != null else m.roughness_texture
	var nrm: Texture2D = m.normal_texture
	var stem: String = String(m.resource_name)
	# `M_Skin_metal_painted_delco_1997_807d75` -> drop the 6-hex tail, and only
	# when it really is one.
	var bits: PackedStringArray = stem.split("_")
	if bits.size() > 1:
		var tail: String = bits[bits.size() - 1]
		if tail.length() == 6 and tail.is_valid_hex_number(false):
			stem = stem.substr(0, stem.length() - 7)
	return "%s|%s|%s|%s|%s|%d|%d|%d|%s" % [
		(alb.resource_path if alb != null else "-"),
		(orm.resource_path if orm != null else "-"),
		(nrm.resource_path if nrm != null else "-"),
		str(m.uv1_scale), str(m.uv1_offset),
		int(m.cull_mode), int(m.transparency), int(m.shading_mode), stem]


## Fold one surface's arrays into an accumulator, in the module's space, with
## the material's colour written into the vertex colour channel.
func _accumulate(acc: Dictionary, src: ArrayMesh, idx: int,
		xform: Transform3D, tint: Color) -> bool:
	var arrays: Array = src.surface_get_arrays(idx)
	if arrays.is_empty():
		return false
	var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var idxs: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	if verts.is_empty() or idxs.is_empty():
		return false
	var norms: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
	var uvs: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
	var cols: PackedColorArray = arrays[Mesh.ARRAY_COLOR]

	var base: int = acc["vertex"].size()
	var basis: Basis = xform.basis
	var nbasis: Basis = basis.inverse().transposed()
	for v in verts:
		acc["vertex"].append(xform * v)
	if norms.is_empty():
		for i in range(verts.size()):
			acc["normal"].append(Vector3.UP)
	else:
		for n in norms:
			acc["normal"].append((nbasis * n).normalized())
	if uvs.is_empty():
		for i in range(verts.size()):
			acc["uv"].append(Vector2.ZERO)
	else:
		for u in uvs:
			acc["uv"].append(u)
	# `base = factor * texture * COLOR_0`, so folding the factor into COLOR_0
	# reproduces the same pixel. A mesh that already carries a colour (Zoo's
	# wear) keeps it: the two multiply.
	if cols.is_empty():
		for i in range(verts.size()):
			acc["color"].append(tint)
	else:
		for c in cols:
			acc["color"].append(Color(c.r * tint.r, c.g * tint.g,
				c.b * tint.b, c.a * tint.a))
	for i in idxs:
		acc["index"].append(base + i)
	return true


## Merge every group of single-surface meshes that share a tint key inside one
## module. Returns what it did, because a merge that silently did nothing is
## the arm measured twice.
func _merge(scene: Node) -> Dictionary:
	var nodes: Array = []
	_walk(scene, nodes)

	var groups: Dictionary = {}
	var skipped_multi: int = 0
	var considered: int = 0
	for n in nodes:
		var mi: MeshInstance3D = n as MeshInstance3D
		if mi == null or mi.mesh == null or not mi.visible:
			continue
		if mi.mesh.get_surface_count() != 1:
			# A multi-surface mesh cannot have one of its surfaces removed, so
			# it is left alone and COUNTED. Every figure this probe reports is
			# therefore a floor on what the fix would buy, not a total.
			skipped_multi += 1
			continue
		var am: ArrayMesh = mi.mesh as ArrayMesh
		if am == null:
			skipped_multi += 1
			continue
		var mat: BaseMaterial3D = mi.get_active_material(0) as BaseMaterial3D
		if mat == null:
			continue
		considered += 1
		var key: String = "%d|%s" % [_module_of(mi), _tint_key(mat)]
		if not groups.has(key):
			groups[key] = []
		groups[key].append(mi)

	var merged_groups: int = 0
	var surfaces_before: int = 0
	var surfaces_after: int = 0
	var colours_folded: int = 0
	# GEOMETRY CONSERVATION, counted where the merge happens. The first
	# version of this probe checked the triangle count IN FRAME and refused
	# when it moved -- see the runner for why that was the wrong control.
	var tris_in: int = 0
	var tris_out: int = 0
	var widest_span: float = 0.0
	for key in groups:
		var members: Array = groups[key]
		if members.size() < 2:
			continue
		var distinct: Dictionary = {}
		for m in members:
			var mm: BaseMaterial3D = (m as MeshInstance3D).get_active_material(0) as BaseMaterial3D
			distinct[String(mm.albedo_color.to_html(false))] = true
		if distinct.size() < 2:
			# Same material, same colour: this is duplication and merging it is
			# a different change with a different justification. Not this
			# probe's question.
			continue

		var host: MeshInstance3D = members[0] as MeshInstance3D
		var inv: Transform3D = host.global_transform.affine_inverse()
		var acc: Dictionary = {
			"vertex": PackedVector3Array(), "normal": PackedVector3Array(),
			"uv": PackedVector2Array(), "color": PackedColorArray(),
			"index": PackedInt32Array()}
		var folded: Array = []
		var group_box: AABB = AABB()
		var got_box: bool = false
		for m in members:
			var mi2: MeshInstance3D = m as MeshInstance3D
			var mat2: BaseMaterial3D = mi2.get_active_material(0) as BaseMaterial3D
			var src: ArrayMesh = mi2.mesh as ArrayMesh
			var before_idx: int = acc["index"].size()
			var ok: bool = _accumulate(acc, src, 0,
				inv * mi2.global_transform, mat2.albedo_color)
			if ok:
				folded.append(mi2)
				tris_in += (acc["index"].size() - before_idx) / 3
				var wb: AABB = mi2.global_transform * mi2.get_aabb()
				group_box = wb if not got_box else group_box.merge(wb)
				got_box = true
		if folded.size() < 2:
			continue

		var arrays: Array = []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = acc["vertex"]
		arrays[Mesh.ARRAY_NORMAL] = acc["normal"]
		arrays[Mesh.ARRAY_TEX_UV] = acc["uv"]
		arrays[Mesh.ARRAY_COLOR] = acc["color"]
		arrays[Mesh.ARRAY_INDEX] = acc["index"]
		var out_mesh := ArrayMesh.new()
		out_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)

		var src_mat: BaseMaterial3D = host.get_active_material(0) as BaseMaterial3D
		var new_mat: BaseMaterial3D = src_mat.duplicate() as BaseMaterial3D
		new_mat.albedo_color = Color(1, 1, 1, src_mat.albedo_color.a)
		new_mat.vertex_color_use_as_albedo = true
		new_mat.resource_name = String(src_mat.resource_name) + "_merged"
		out_mesh.surface_set_material(0, new_mat)

		var holder := MeshInstance3D.new()
		holder.mesh = out_mesh
		host.get_parent().add_child(holder)
		holder.global_transform = host.global_transform
		for m in folded:
			(m as MeshInstance3D).visible = false

		merged_groups += 1
		surfaces_before += folded.size()
		surfaces_after += 1
		colours_folded += folded.size()
		tris_out += acc["index"].size() / 3
		# HOW BIG THE MERGED THING IS, reported rather than capped. "The chunk
		# to merge is the largest unit that becomes visible and invisible as
		# one thing" -- a group spanning a whole building defeats culling, and
		# the span is what a bound would have to be derived from. Nobody has
		# measured what that bound should be, so this prints and does not
		# choose.
		if got_box:
			var sp: float = maxf(group_box.size.x,
				maxf(group_box.size.y, group_box.size.z))
			widest_span = maxf(widest_span, sp)

	return {
		"considered": considered,
		"skipped_multi_surface": skipped_multi,
		"groups_merged": merged_groups,
		"surfaces_before": surfaces_before,
		"surfaces_after": surfaces_after,
		"surfaces_removed": surfaces_before - surfaces_after,
		"triangles_in": tris_in,
		"triangles_out": tris_out,
		"widest_group_span_m": snappedf(widest_span, 0.01),
	}


func _run(out_path: String, arm: String) -> void:
	await process_frame
	DisplayServer.window_set_size(Vector2i(W, H))
	root.content_scale_size = Vector2i(W, H)
	Engine.max_fps = 0
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	RenderingServer.viewport_set_measure_render_time(root.get_viewport_rid(),
		true)

	var report: Dictionary = {
		"schema": "lf.tint_merge_ab.v1", "ok": false, "error": "",
		"arm": arm, "merge": {}, "stations": [],
	}
	var main_scene: String = String(ProjectSettings.get_setting(
		"application/run/main_scene", ""))
	if main_scene.is_empty():
		report["error"] = "the package declares no main scene"
		_write(out_path, report)
		quit(0)
		return
	report["main_scene"] = main_scene
	var packed: PackedScene = load(main_scene) as PackedScene
	if packed == null:
		report["error"] = "could not load %s" % main_scene
		_write(out_path, report)
		quit(0)
		return
	var scene: Node = packed.instantiate()
	root.add_child(scene)
	for i in range(30):
		await process_frame

	if arm == "merged":
		report["merge"] = _merge(scene)
		for i in range(10):
			await process_frame

	var nodes: Array = []
	_walk(scene, nodes)
	var box: AABB = AABB()
	var got: bool = false
	for n in nodes:
		var v3: VisualInstance3D = n as VisualInstance3D
		if v3 == null:
			continue
		var b: AABB = v3.global_transform * v3.get_aabb()
		box = b if not got else box.merge(b)
		got = true
	if not got:
		report["error"] = "nothing drawable in the scene"
		_write(out_path, report)
		quit(0)
		return

	# THE SAME SIX STATIONS the wet and drip figures were taken at, so the
	# numbers can be put beside each other.
	var c: Vector3 = box.get_center()
	var d: float = maxf(box.size.x, box.size.z)
	var fy: float = box.position.y + EYE
	var stations: Array = [
		{"n": "street_down", "eye": Vector3(c.x, box.position.y + EYE, c.z),
			"look": Vector3(c.x + d, box.position.y, c.z)},
		{"n": "street_along", "eye": Vector3(c.x - d * 0.4, fy, c.z),
			"look": Vector3(c.x + d, box.position.y + 1.0, c.z)},
		{"n": "ground_near", "eye": Vector3(c.x, box.position.y + 2.5, c.z),
			"look": Vector3(c.x + 4.0, box.position.y, c.z)},
		{"n": "exterior_high", "eye": c + Vector3(d * 0.7, box.size.y * 0.6,
			d * 0.7), "look": c},
		{"n": "interior_a", "eye": Vector3(c.x, fy, c.z),
			"look": Vector3(c.x + d, fy, c.z)},
		{"n": "interior_b", "eye": Vector3(c.x - d * 0.3, fy, c.z - d * 0.3),
			"look": Vector3(c.x + d, fy, c.z + d)},
	]

	var cam := Camera3D.new()
	cam.fov = 70.0
	cam.far = 4000.0
	root.add_child(cam)
	cam.make_current()
	var vp: RID = root.get_viewport_rid()

	for s in stations:
		cam.global_position = s["eye"]
		cam.look_at(s["look"], Vector3.UP)
		for i in range(WARMUP):
			await process_frame
		var samples: Array = []
		var cpu_sum: float = 0.0
		var gpu_sum: float = 0.0
		var last: int = Time.get_ticks_usec()
		for i in range(SAMPLE):
			await process_frame
			var now: int = Time.get_ticks_usec()
			samples.append(float(now - last) / 1000.0)
			last = now
			cpu_sum += RenderingServer.viewport_get_measured_render_time_cpu(vp)
			gpu_sum += RenderingServer.viewport_get_measured_render_time_gpu(vp)
		samples.sort()
		var total: float = 0.0
		for x in samples:
			total += float(x)
		var n_s: float = float(samples.size())
		# `primitives` is carried out of both arms as a MEASUREMENT, not as a
		# control: merging coarsens culling, so the merged arm submits more
		# triangles for the same view and that rise is part of what the fix
		# costs. The control that geometry was not LOST is counted at the
		# merge itself (`triangles_in` / `triangles_out`), where the answer
		# does not depend on where a camera is standing.
		var img: Image = root.get_texture().get_image()
		var lum: float = 0.0
		var step_px: int = maxi(1, img.get_width() / 160)
		var taken: int = 0
		for py in range(0, img.get_height(), step_px):
			for px in range(0, img.get_width(), step_px):
				var texel: Color = img.get_pixel(px, py)
				lum += 0.2126 * texel.r + 0.7152 * texel.g + 0.0722 * texel.b
				taken += 1
		report["stations"].append({
			"frame_luma": snappedf(lum / maxf(float(taken), 1.0), 0.0001),
			"station": String(s["n"]),
			"draw_calls": int(RenderingServer.get_rendering_info(
				RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME)),
			"primitives": int(RenderingServer.get_rendering_info(
				RenderingServer.RENDERING_INFO_TOTAL_PRIMITIVES_IN_FRAME)),
			"ms_mean": snappedf(total / n_s, 0.001),
			"ms_median": snappedf(float(samples[int(n_s / 2.0)]), 0.001),
			"cpu_ms": snappedf(cpu_sum / n_s, 0.001),
			"gpu_ms": snappedf(gpu_sum / n_s, 0.001),
		})

	report["ok"] = true
	_write(out_path, report)
	print("[tint_merge_ab] arm=%s merged=%s stations=%d"
		% [arm, str(report["merge"]), report["stations"].size()])
	quit(0)


func _write(out_path: String, report: Dictionary) -> void:
	var fh: FileAccess = FileAccess.open(out_path, FileAccess.WRITE)
	if fh == null:
		push_error("[tint_merge_ab] could not write %s" % out_path)
		return
	fh.store_string(JSON.stringify(report, "  "))
	fh.close()
