@tool
extends EditorPlugin
## Adds the Gabagool Factory panel to the editor's right dock and removes it when the plugin is disabled.

const FactoryDock := preload("res://addons/gabagool_factory/factory_dock.gd")

var _dock: Control


func _enter_tree() -> void:
	_dock = FactoryDock.new()
	add_control_to_dock(DOCK_SLOT_RIGHT_UL, _dock)


func _exit_tree() -> void:
	if _dock != null:
		remove_control_from_docks(_dock)
		_dock.queue_free()
		_dock = null
