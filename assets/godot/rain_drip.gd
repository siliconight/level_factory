extends Node
## Rain running down the vertical surfaces of a level, attached at runtime.
##
## WHAT IT COSTS, measured before it was written (LF 0.116.0, cold run 9080's
## package, GL Compatibility, 1280x720, 3 rounds x 300 samples):
##
##     materials touched  19 (the set below)    250 (every wall pattern)
##     median station      +0.83 ms              +3.59 ms
##     WORST station       +1.85 ms              +8.60 ms
##
## Both controls fired: draw calls rose at 6 of 6 stations and the frame's mean
## luminance CHANGED at 5 of 6. The second is the one the withdrawn 0.110.0
## figure did not have, and without it a pass that never shades a pixel prices
## as free. `docs/proposals/RAIN_WETNESS.md` carries the retraction.
##
## MATERIAL COUNT IS NOT A PRICE, and this file exists at 5 patterns rather
## than 15 because of it: 13.16x the material resources cost only 4.65x the
## milliseconds, so scaling the wide figure down predicts +0.65 ms and the real
## answer is +1.85. Cost tracks screen coverage. Adding a pattern to
## `WALL_FAMILIES` is a performance change and needs re-measuring with
## `tools/wet_ab_run.py --arms dry drip_few`, not an estimate.
##
## AND THE 19 WERE ONE FAMILY. On the package that was measured all 19
## resources are `M_Skin_brick_delco_1997`, one copy per imported GLB; siding,
## stucco, corrugated and shingle matched NOTHING there and are unpriced. An
## empty pattern and a cheap one are indistinguishable in a total, which is
## why this node prints its matches instead of counting them.
##
## WHY A PASS AND NOT A BAKED VARIANT. The wet GROUND is a baked variant
## (Lot picks `wet_albedo` / `wet_roughness` per surface) precisely because a
## variant costs zero extra submissions. A drip MOVES -- each drop runs on its
## own clock -- and no baked map can do that, so this one pays the extra
## submission on purpose. That is the whole of the cost above.
##
## WHAT ATTACHES IT. Nothing in the pipeline yet. `walk_export.py --drip`
## stages this node, the shader and Pixelcoat's atlas into a WALK COPY so the
## look can be judged; a package built by the factory carries no drips. When
## the look is approved the attachment belongs in the presentation compose
## step, gated on the brief's weather the way the wet ground already is.

## THE SET THAT WAS PRICED -- exterior wall finishes, the ones a street sees.
## `wet_ab.gd`'s `_is_wall_few`, verbatim, because a different set is a
## different price. Drywall, panel, glass and plaster are deliberately absent:
## they are the wide arm's +8.60 ms and most of them are indoors.
const WALL_FAMILIES: Array = ["brick", "siding", "stucco", "corrugated",
	"shingle"]

const SHADER_PATH: String = "res://rain_drip.gdshader"
const ATLAS_PATH: String = "res://drop_atlas.png"

## How wet, 0 dry to 1 streaming. The probe measured at 0.9.
@export_range(0.0, 1.0) var amount: float = 0.9
## Drops per metre of wall, through the atlas's UV scale.
@export_range(0.5, 16.0) var drip_scale: float = 4.0
## How fast a drop runs down. Slow: a wall is not a waterfall.
@export_range(0.0, 1.0) var drip_speed: float = 0.08
## Print what was touched. On by default -- a pass that attached to nothing
## looks exactly like rain that is not falling, and silence is the one thing
## this must not do.
@export var verbose: bool = true


func _ready() -> void:
	var root: Node = get_tree().current_scene
	if root == null:
		root = get_parent()
	var shader: Shader = load(SHADER_PATH) as Shader
	if shader == null:
		push_error("[rain_drip] no shader at %s -- nothing attached." % SHADER_PATH)
		return
	# LOADED AS A RESOURCE FIRST. `Image.load_from_file` reads the file off
	# disk, which works in a project directory and NOT in an export -- Godot
	# says so out loud: "Loaded resource as image file, this will not work on
	# export". The imported texture is the shipping path; the raw read stays
	# as the fallback for a copy whose .godot cache has not been built, where
	# the alternative is no drips and no explanation.
	var atlas: Texture2D = load(ATLAS_PATH) as Texture2D
	if atlas == null:
		var img: Image = Image.load_from_file(ATLAS_PATH)
		if img == null:
			push_error(("[rain_drip] no drop atlas at %s. Pixelcoat's "
				+ "core/droplets.py writes it; a drip without its texture is "
				+ "not a drip, so nothing was attached.") % ATLAS_PATH)
			return
		atlas = ImageTexture.create_from_image(img)
		push_warning(("[rain_drip] %s was read off disk rather than imported. "
			+ "That path does not exist in an export.") % ATLAS_PATH)

	var meshes: Array = []
	_collect(root, meshes)
	var seen: Dictionary = {}
	var touched: Array = []
	for n in meshes:
		var mi: MeshInstance3D = n as MeshInstance3D
		if mi == null or mi.mesh == null:
			continue
		for i in range(mi.mesh.get_surface_count()):
			var bm: BaseMaterial3D = mi.mesh.surface_get_material(i) as BaseMaterial3D
			if bm == null or seen.has(bm.get_instance_id()):
				continue
			seen[bm.get_instance_id()] = true
			var nm: String = String(bm.resource_name)
			if not _is_wall(nm):
				continue
			if bm.next_pass != null:
				continue           # idempotent, as the CRT pass is
			var sm := ShaderMaterial.new()
			sm.shader = shader
			sm.resource_name = nm + "_drip"
			sm.set_shader_parameter("drops", atlas)
			sm.set_shader_parameter("amount", amount)
			sm.set_shader_parameter("drip_scale", drip_scale)
			sm.set_shader_parameter("drip_speed", drip_speed)
			bm.next_pass = sm
			touched.append(nm)

	if touched.is_empty():
		push_warning(("[rain_drip] matched 0 of %d materials against %s -- "
			+ "this level has no drips on it. Either its wall families are "
			+ "named differently or the wrong scene was walked.")
			% [seen.size(), str(WALL_FAMILIES)])
		return
	if verbose:
		touched.sort()
		print("[rain_drip] %d of %d materials, %d mesh instances visited"
			% [touched.size(), seen.size(), meshes.size()])
		print("[rain_drip] amount %.2f  scale %.1f  speed %.3f"
			% [amount, drip_scale, drip_speed])
		for nm in touched:
			print("  " + nm)


## Named families rather than a normal test: a material is attached to a mesh
## and does not know which way any one of its triangles faces. The shader's own
## up-vector term does that per fragment, which is what keeps rain off a
## soffit.
func _is_wall(nm: String) -> bool:
	var s: String = nm.to_lower()
	for p in WALL_FAMILIES:
		if s.contains(String(p)):
			return true
	return false


func _collect(n: Node, out: Array) -> void:
	out.append(n)
	for c in n.get_children():
		_collect(c, out)
