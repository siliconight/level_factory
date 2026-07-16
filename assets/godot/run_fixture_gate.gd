extends SceneTree
## Headless fixture gate driver for Level Factory (pairs Zoo v0.30 / Lux v0.15).
##
## Gates a Zoo fixtures GLB against the emitter-marker contract: spawns one
## lamp per LuxEmit_* marker via LuxFixtureSpawner, checks lamp<->hardware
## co-location via LuxValidator, and exercises set_fixtures_powered
## kill/restore. Writes fixture_gate.report.json; exit 0 = evaluated
## (findings live in the report — LF's adapter turns them into blocking
## issues), exit 2 = could not evaluate.
##
## Lux scripts are load()ed BY PATH — no class_name annotations — so this
## driver never depends on a staged global script class cache (the
## LT_MapEvalHarness lesson). Run an --import pass on the staged project
## first so the GLB has import artifacts.
##
## Usage:
##   godot --headless --path <project> -s res://run_fixture_gate.gd -- \
##     --fixtures res://fixtures.glb [--tolerance 0.1] [--out <abs_dir>]

const SPAWNER := "res://addons/lux/runtime/lux_fixture_spawner.gd"
const VALIDATOR := "res://addons/lux/runtime/lux_validator.gd"
const ROOT := "res://addons/lux/runtime/lux_root.gd"

func _parse_args() -> Dictionary:
	var out := {}
	var argv := OS.get_cmdline_user_args()
	var i := 0
	while i < argv.size():
		var a: String = argv[i]
		if a.begins_with("--"):
			var key := a.substr(2)
			if i + 1 < argv.size() and not argv[i + 1].begins_with("--"):
				out[key] = argv[i + 1]
				i += 1
			else:
				out[key] = true
		i += 1
	return out

func _initialize() -> void:
	_main()

func _main() -> void:
	# Nodes added during _initialize are not in-tree and _ready hasn't fired
	# (hardware-proven); wait one frame before touching Lux.
	await process_frame

	var args := _parse_args()
	var fixtures_path: String = args.get("fixtures", "")
	var out_dir: String = args.get("out", "user://fixture_gate")
	var tolerance: float = float(args.get("tolerance", "0.1"))

	if fixtures_path.is_empty():
		push_error("run_fixture_gate: --fixtures res://... is required")
		quit(2)
		return

	var Spawner: GDScript = load(SPAWNER) as GDScript
	var Validator: GDScript = load(VALIDATOR) as GDScript
	var RootScript: GDScript = load(ROOT) as GDScript
	if Spawner == null or Validator == null or RootScript == null:
		push_error("run_fixture_gate: lux runtime scripts not found under addons/lux (need lux v0.15+)")
		quit(2)
		return

	var packed: PackedScene = load(fixtures_path) as PackedScene
	if packed == null:
		push_error("run_fixture_gate: could not load %s (was --import run?)" % fixtures_path)
		quit(2)
		return
	var stage: Node3D = Node3D.new()
	stage.name = "FixtureGate"
	root.add_child(stage)
	var fixtures: Node = packed.instantiate()
	fixtures.name = "Fixtures"
	stage.add_child(fixtures)

	var lux_obj: Object = RootScript.new()
	if not (lux_obj is Node):
		push_error("run_fixture_gate: lux_root.gd did not produce a Node")
		quit(2)
		return
	var lux: Node = lux_obj as Node
	lux.name = "LuxRoot"
	stage.add_child(lux)
	await process_frame  # LuxRoot._ready: modules + group registration

	var markers: Array = []
	Spawner.collect_markers(stage, markers)
	var report: Dictionary = {"markers": markers.size(), "driver": "run_fixture_gate",
		"tolerance": tolerance}

	if markers.is_empty():
		# Pre-v0.30 GLB: nothing to gate. Evaluated, not failed — the adapter
		# surfaces it as a non-blocking contract finding.
		report["spawned"] = 0
		report["spawnable"] = 0
		report["colocation_errors"] = []
		report["powered"] = {"kill": true, "restore": true}
		_finish(report, out_dir)
		return

	var spawn: Dictionary = Spawner.spawn(stage)
	await process_frame
	var spawnable: int = markers.size() - _unspawnable(Spawner, markers)
	report["spawned"] = int(spawn.get("count", 0))
	report["spawnable"] = spawnable
	report["skipped"] = spawn.get("skipped", [])

	var coloc_errors: Array = []
	for f in Validator.check_fixture_colocation(stage, tolerance):
		if f.severity == Validator.Severity.ERROR:
			coloc_errors.append(String(f.message))
	report["colocation_errors"] = coloc_errors

	# Powered gate on the spawned set (visibility-kill; alarm group exempt;
	# preset-owned DirectionalLight LuxSun excluded by design).
	var lamps: Array = []
	_collect_fixture_lights(stage, lamps)
	var pre: float = _energy(lamps)
	lux.set_fixtures_powered(false)
	var off: float = _energy(lamps)
	lux.set_fixtures_powered(true)
	var back: float = _energy(lamps)
	report["powered"] = {"kill": off == 0.0, "restore": back == pre,
		"energy_before": pre, "energy_off": off, "energy_restored": back}

	_finish(report, out_dir)

func _finish(report: Dictionary, out_dir: String) -> void:
	DirAccess.make_dir_recursive_absolute(out_dir)
	var f := FileAccess.open(out_dir + "/fixture_gate.report.json", FileAccess.WRITE)
	if f != null:
		f.store_string(JSON.stringify(report, "  "))
		f.close()
	print("[fixture_gate] markers=%d spawned=%d colocation_errors=%d" % [
		int(report.get("markers", 0)), int(report.get("spawned", 0)),
		(report.get("colocation_errors", []) as Array).size()])
	quit(0)

func _unspawnable(Spawner: GDScript, markers: Array) -> int:
	var n: int = 0
	for m in markers:
		var t: String = Spawner.marker_type(m as Node)
		if t == "" or t == "window" or t == "sun":
			n += 1
	return n

func _collect_fixture_lights(n: Node, out: Array) -> void:
	if n is Light3D and not n is DirectionalLight3D \
			and not (n as Node).is_in_group(&"lux_alarm"):
		out.append(n)
	for c in n.get_children():
		_collect_fixture_lights(c, out)

func _energy(lamps: Array) -> float:
	var total: float = 0.0
	for lo in lamps:
		var li: Light3D = lo as Light3D
		if is_instance_valid(li):
			total += li.light_energy * (1.0 if li.visible else 0.0)
	return total
