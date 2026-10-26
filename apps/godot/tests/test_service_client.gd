extends SceneTree
## End to end, headless: the panel's service client runs real factory operations and reads their results.
##
##     godot --headless --path <this project> --script res://tests/test_service_client.gd -- [<python> <cli main.py>]
##
## With the two arguments the client runs that CLI (`launch_prefix`), so a Level Factory checkout can be tested
## before it is installed; without them, the factory's own launcher. Prints PASS or FAIL lines and quits 0 only
## when every case passed. Cases: a real `discover_installation` returns checks with labels; an unknown operation
## comes back as an error result, not a success; events arrive in order.

const ServiceClient := preload("res://addons/gabagool_factory/service_client.gd")
const FactoryDock := preload("res://addons/gabagool_factory/factory_dock.gd")

var _failures := 0


func _initialize() -> void:
	_run.call_deferred()


func _check(ok: bool, what: String) -> void:
	print(("PASS " if ok else "FAIL ") + what)
	if not ok:
		_failures += 1


func _call(client: Node, operation: String, arguments: Dictionary) -> Array:
	var events: Array = []
	var cb := func(e: Dictionary) -> void: events.append(e)
	client.event_received.connect(cb)
	var why: String = client.start(operation, arguments)
	if why != "":
		client.event_received.disconnect(cb)
		return [{"status": "not_started", "error": {"message": why}}, events]
	var result: Dictionary = await client.finished
	client.event_received.disconnect(cb)
	return [result, events]


func _run() -> void:
	var found := FactoryDock.find_factory_root(ProjectSettings.globalize_path("res://"))
	_check(found != "", "the factory is found above the project: %s" % found)
	var client: Node = ServiceClient.new()
	root_node().add_child(client)
	client.factory_root = found
	var user_args := OS.get_cmdline_user_args()
	if user_args.size() >= 2:
		client.launch_prefix = PackedStringArray([user_args[0], user_args[1]])

	var got := await _call(client, "discover_installation", {})
	var result: Dictionary = got[0]
	_check(result.get("status") == "ok", "discover_installation succeeds: %s" % result.get("error"))
	var data: Dictionary = result.get("data", {}) if result.get("data") is Dictionary else {}
	var checks: Array = data.get("checks", [])
	_check(checks.size() >= 5, "it returns the doctor's checks (%d)" % checks.size())
	var labelled := checks.all(func(c: Dictionary) -> bool: return str(c.get("label", "")) != "")
	_check(labelled, "every check has a plain-language label")
	var stages: Array = got[1].map(func(e: Dictionary) -> String: return str(e.get("stage", "")))
	_check(stages.size() >= 2 and stages[0] == "start" and stages[stages.size() - 1] == "finish",
		"events arrive in order: %s" % [stages])

	got = await _call(client, "make_me_a_sandwich", {})
	result = got[0]
	var err: Dictionary = result.get("error", {}) if result.get("error") is Dictionary else {}
	_check(result.get("status") == "error" and err.get("code") == "unknown_operation",
		"an unknown operation is an error result: %s" % err.get("code"))

	client.queue_free()
	print("DONE failures=%d" % _failures)
	quit(1 if _failures else 0)


func root_node() -> Node:
	return root
