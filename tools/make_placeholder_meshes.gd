extends SceneTree

# Write a trivial BoxMesh .tres per dressing asset.
#
# The A/B tests ONE thing: whether the MultiMesh buffer decodes to the same
# transforms as the node scene. That question is entirely independent of which
# mesh is drawn -- and how a .glb becomes an addressable Mesh resource is a
# SEPARATE unknown (import settings, subresource paths) that would otherwise
# be tangled into the same run. Two unknowns in one experiment is one
# experiment that answers neither.
#
# So the A/B runs on placeholder boxes sized like the real assets, and the
# real mesh wiring is a question you answer once, afterwards, on its own.
#
#   godot --headless --path <project> --script res://make_placeholder_meshes.gd

func _initialize() -> void:
	var sizes := {
		"pebble": Vector3(0.197, 0.062, 0.119),
		"rubble_frag": Vector3(0.316, 0.053, 0.251),
		"weed_tuft": Vector3(0.077, 0.068, 0.113),
		"litter_scrap": Vector3(0.229, 0.023, 0.152),
	}
	for name in sizes:
		var m := BoxMesh.new()
		m.size = sizes[name]
		var path := "res://dressing/%s.tres" % name
		var err := ResourceSaver.save(m, path)
		if err != OK:
			print("FAIL: could not save %s (err %d)" % [path, err])
			quit(1)
			return
		print("wrote %s  %s" % [path, str(sizes[name])])
	quit(0)
