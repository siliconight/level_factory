extends Node
## Level Factory walk preview -- DEV ONLY debug overlay.
## ----------------------------------------------------------------------------
## Says WHERE YOU ARE and WHAT YOU ARE LOOKING AT, so a screenshot of a defect
## carries its own coordinates instead of needing a conversation to locate.
##
## Written 2026-08-08, after an afternoon of screenshots that each showed a real
## defect and none of which said which of five buildings it was in. The answer
## had to be reconstructed from the site scene's node transforms every time, and
## once it was reconstructed against the WRONG building because nothing in the
## picture pinned it down.
##
## THREE LINES, and each one exists because a specific question was asked and
## could not be answered from a picture:
##
##   position  -- "which building is this?" The row runs along x; the building
##                id resolves that directly, and the raw coordinates let a
##                defect be found again after a rebuild.
##   building  -- the instanced package under the crosshair, by its own scene
##                path (`lot/construction_site_a03/site.tscn` -> b2
##                construction_site_a03). Read from `scene_file_path`, which is
##                the node's own record of where it came from, rather than
##                matched against a table this file would have to keep in step.
##   surface   -- the collider the crosshair is on, and its distance. "stairs
##                into collision" becomes "slab_1 at 2.4 m", which names the
##                thing to go and measure.
##
## It rides in the preview project with the player and the bots, never in the
## package: the package is content a stranger instances into their own project,
## and dev instrumentation is not content. Never exported.
##
## F3 toggles it. It is on by default, because an overlay you have to remember
## to enable is one that is off in the screenshot you needed it in.

const RAY_LENGTH := 60.0
const _VARIANT := "_a"

var _label: Label
var _shown := true


func _ready() -> void:
	var layer := CanvasLayer.new()
	layer.layer = 128
	add_child(layer)

	# A panel behind the text: this reads over both a white sky and a dark
	# interior, and the first version was unreadable in exactly the shot it was
	# built for.
	var panel := PanelContainer.new()
	panel.position = Vector2(12, 12)
	panel.modulate = Color(1, 1, 1, 0.88)
	layer.add_child(panel)

	_label = Label.new()
	_label.add_theme_font_size_override("font_size", 15)
	_label.add_theme_color_override("font_color", Color(0.06, 0.06, 0.08))
	panel.add_child(_label)


func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		var key := event as InputEventKey
		if key.keycode == KEY_F3:
			_shown = not _shown
			_label.get_parent().visible = _shown


func _process(_delta: float) -> void:
	if not _shown or _label == null:
		return
	var cam := get_viewport().get_camera_3d()
	if cam == null:
		_label.text = "no camera"
		return

	var eye: Vector3 = cam.global_transform.origin
	var lines: Array[String] = []
	lines.append("pos  x %.1f  y %.1f  z %.1f" % [eye.x, eye.y, eye.z])

	var hit := _look_at_hit(cam)
	if hit.is_empty():
		lines.append("look nothing within %.0f m" % RAY_LENGTH)
		_label.text = "\n".join(lines)
		return

	var collider: Node = hit.get("collider") as Node
	var point: Vector3 = hit.get("position", eye)
	var dist: float = eye.distance_to(point)

	# The building is whichever instanced package this collider sits inside.
	# `scene_file_path` is the node's OWN record of the scene it came from, so
	# this cannot drift out of step with the lot the way a name table would.
	var owner_node: Node = _instanced_ancestor(collider)
	if owner_node == null:
		lines.append("bldg (not inside an instanced package)")
	else:
		lines.append("bldg %s   %s" % [owner_node.name,
			_package_of(owner_node)])

	if collider == null:
		lines.append("look <no collider>")
	else:
		lines.append("look %s   %.2f m   y %.2f" % [collider.name, dist,
			point.y])
		var parent_name := "-"
		if collider.get_parent() != null:
			parent_name = collider.get_parent().name
		lines.append("under %s" % parent_name)
	_label.text = "\n".join(lines)


func _look_at_hit(cam: Camera3D) -> Dictionary:
	var space := get_viewport().get_world_3d().direct_space_state
	var from: Vector3 = cam.global_transform.origin
	# -Z is forward in Godot. Reading the basis rather than `project_ray_normal`
	# keeps this correct when the preview runs without a mouse (the bots).
	var to: Vector3 = from - cam.global_transform.basis.z * RAY_LENGTH
	var q := PhysicsRayQueryParameters3D.create(from, to)
	q.collide_with_areas = false
	return space.intersect_ray(q)


func _instanced_ancestor(node: Node) -> Node:
	## The nearest ancestor that was instanced from its own scene file -- the
	## per-building package. Walks UP rather than searching down, because the
	## collider is many levels deep and only its ancestry knows which package
	## owns it.
	var n: Node = node
	while n != null:
		if n.scene_file_path != "":
			return n
		n = n.get_parent()
	return null


func _package_of(node: Node) -> String:
	## `lot/construction_site_a03/site.tscn` -> `construction_site_a03`.
	## Falls back to the raw path rather than inventing a name: an unexpected
	## layout should read as unexpected, not as a confident wrong answer.
	var p: String = node.scene_file_path
	var parts: PackedStringArray = p.replace("res://", "").split("/")
	if parts.size() >= 2:
		return parts[parts.size() - 2]
	return p
