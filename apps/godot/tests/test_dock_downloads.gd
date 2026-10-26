extends SceneTree
## The Setup tab says what Prepare environment downloads, licences included, before anybody presses it, and only
## when the button is offered.
##
##     godot --headless --path <this project> --script res://tests/test_dock_downloads.gd

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
	await process_frame
	var said := "Downloads 12 packages from PyPI, once, each under its own licence (MIT): x 1 (MIT)."
	dock.show_installation({"checks": [], "ready": false, "blocking": ["tools_python"], "downloads_said": said})
	_check(dock._prepare_button.visible and dock._downloads.visible, "the downloads are said beside the button")
	_check(dock._downloads.text == said, "as the factory says them: %s" % dock._downloads.text)
	dock.show_installation({"checks": [], "ready": true, "blocking": [], "downloads_said": said})
	_check(not dock._downloads.visible, "and not when nothing needs downloading")
	dock.queue_free()
	print("DONE failures=%d" % _failures)
	quit(1 if _failures else 0)
