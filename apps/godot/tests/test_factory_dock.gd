extends SceneTree
## The panel itself, headless: the dock finds the factory, checks the setup through the factory's own launcher on
## its own as it opens, and fills its checks list and status line from the answer.
##
##     godot --headless --path <this project> --script res://tests/test_factory_dock.gd
##
## It runs the INSTALLED Level Factory beside the manifest (no `launch_prefix`), so it passes only once the
## factory carries `service-run`. Prints PASS or FAIL lines; quits 0 only when every case passed.

const FactoryDock := preload("res://addons/gabagool_factory/factory_dock.gd")

var _failures := 0


func _initialize() -> void:
	_run.call_deferred()


func _check(ok: bool, what: String) -> void:
	print(("PASS " if ok else "FAIL ") + what)
	if not ok:
		_failures += 1


func _run() -> void:
	var dock: Control = FactoryDock.new()
	root.add_child(dock)
	_check(dock.client.factory_root != "", "the dock found the factory: %s" % dock.client.factory_root)
	_check(dock.client.is_running(), "it checks the setup as it opens")
	var result: Dictionary = await dock.client.finished
	await process_frame
	_check(result.get("status") == "ok", "the check succeeded: %s" % result.get("error"))
	var tree: Tree = dock._checks
	var items := tree.get_root().get_children() if tree.get_root() != null else []
	_check(items.size() >= 5, "the checks list shows the doctor's checks (%d)" % items.size())
	var named := items.all(func(it: TreeItem) -> bool: return it.get_text(1) != "" and it.get_text(0) != "")
	_check(named, "each row has a readiness and a plain-language name")
	var status: String = dock._status.text
	_check(status.begins_with("Ready") or status.begins_with("Not ready"), "the status line says: %s" % status)
	# increment 2: Prepare environment shows only when the tools' Python is what blocks
	dock.show_installation({"checks": [], "ready": false, "blocking": ["tools_python"]})
	_check(dock._prepare_button.visible, "Prepare environment shows when the tools' Python blocks")
	dock.show_installation({"checks": [], "ready": true, "blocking": []})
	_check(not dock._prepare_button.visible, "and hides when nothing blocks")
	dock.queue_free()
	print("DONE failures=%d" % _failures)
	quit(1 if _failures else 0)
