@tool
extends Node
## Runs one Gabagool Factory service operation without blocking the caller.
##
## Protocol v1 (Level Factory's `packages/service/worker.py`): a fresh run directory under `user://factory_runs/`
## gets `request.json`; the factory's own launcher (`factory.cmd` / `factory.sh`, which find a Python themselves)
## runs `service-run <dir>`; this node polls the directory from a Timer, emitting each new line of `events.jsonl`
## and, once `result.json` exists, the whole result. Nothing is read from the process's stdout.
##
## The caller owns this node: add it to the tree, call `start()`, connect `event_received` and `finished`, and free
## it when done. One operation at a time per node; `start()` refuses while one is running.

signal event_received(event: Dictionary)
signal finished(result: Dictionary)

const REQUEST_SCHEMA := "gabagool.service.request.v1"
const RESULT_SCHEMA := "gabagool.service.result.v1"
## Seconds between polls of the run directory.
const POLL_S := 0.25
## A worker that has exited gets this long to have its result.json visible before the client says it left none.
const EXIT_GRACE_S := 2.0

var factory_root: String = ""
## When set, the command that runs the CLI in place of the factory's launcher: an executable and its leading
## arguments, `service-run <dir>` appended. For a test that drives a Level Factory checkout other than the one
## beside the manifest; ordinary use leaves it empty.
var launch_prefix: PackedStringArray = PackedStringArray()
var run_dir: String = ""
var _pid: int = -1
var _timer: Timer
var _events_offset: int = 0
var _partial: String = ""
var _exited_at: float = -1.0
var _running: bool = false


func _ready() -> void:
	_timer = Timer.new()
	_timer.wait_time = POLL_S
	_timer.timeout.connect(_poll)
	add_child(_timer)


## Is an operation in flight?
func is_running() -> bool:
	return _running


## Start `operation` with `arguments`. Returns "" when started, else why not. Emits `finished` exactly once per
## started operation, with the worker's result or a client-side error result of the same shape.
func start(operation: String, arguments: Dictionary = {}) -> String:
	if _running:
		return "an operation is already running"
	if factory_root == "" or not FileAccess.file_exists(factory_root.path_join("factory.manifest.json")):
		return "no factory at %s" % factory_root
	var id := "%d_%d" % [Time.get_unix_time_from_system(), randi()]
	run_dir = ProjectSettings.globalize_path("user://factory_runs").path_join(id)
	var err := DirAccess.make_dir_recursive_absolute(run_dir)
	if err != OK:
		return "cannot make %s (error %d)" % [run_dir, err]
	var request := {"schema": REQUEST_SCHEMA, "request_id": id, "operation": operation, "arguments": arguments}
	var f := FileAccess.open(run_dir.path_join("request.json"), FileAccess.WRITE)
	if f == null:
		return "cannot write the request in %s" % run_dir
	f.store_string(JSON.stringify(request, "  "))
	f.close()
	var launch := _launch_command()
	_pid = OS.create_process(launch[0], launch[1])
	if _pid <= 0:
		return "could not start %s" % launch[0]
	_events_offset = 0
	_partial = ""
	_exited_at = -1.0
	_running = true
	_timer.start()
	return ""


## The executable and arguments that run `service-run` through the factory's launcher.
func _launch_command() -> Array:
	if not launch_prefix.is_empty():
		var args := launch_prefix.slice(1)
		args.append_array(PackedStringArray(["service-run", run_dir]))
		return [launch_prefix[0], args]
	if OS.get_name() == "Windows":
		var launcher := factory_root.path_join("factory.cmd").replace("/", "\\")
		return ["cmd.exe", PackedStringArray(["/c", launcher, "service-run", run_dir])]
	return ["sh", PackedStringArray([factory_root.path_join("factory.sh"), "service-run", run_dir])]


func _poll() -> void:
	_read_events()
	var result_path := run_dir.path_join("result.json")
	if FileAccess.file_exists(result_path):
		_finish(_read_result(result_path))
		return
	if not OS.is_process_running(_pid):
		var now := Time.get_ticks_msec() / 1000.0
		if _exited_at < 0.0:
			_exited_at = now
		elif now - _exited_at > EXIT_GRACE_S:
			_finish(_client_error("worker_no_result",
				"the factory exited without writing a result; see %s" % run_dir))


func _read_events() -> void:
	var path := run_dir.path_join("events.jsonl")
	if not FileAccess.file_exists(path):
		return
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return
	var length := f.get_length()
	if length <= _events_offset:
		return
	f.seek(_events_offset)
	var chunk := f.get_buffer(length - _events_offset).get_string_from_utf8()
	_events_offset = length
	f.close()
	var text := _partial + chunk
	var lines := text.split("\n")
	# the last piece is a line still being written, or "" after a complete one
	_partial = lines[lines.size() - 1]
	for i in range(lines.size() - 1):
		var line: String = lines[i]
		if line.strip_edges() == "":
			continue
		var parsed: Variant = JSON.parse_string(line)
		if parsed is Dictionary:
			event_received.emit(parsed)


func _read_result(path: String) -> Dictionary:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not (parsed is Dictionary) or (parsed as Dictionary).get("schema", "") != RESULT_SCHEMA:
		return _client_error("result_unrecognized", "result.json in %s is not a %s" % [run_dir, RESULT_SCHEMA])
	return parsed


func _client_error(code: String, message: String) -> Dictionary:
	return {"schema": RESULT_SCHEMA, "status": "error", "data": null,
		"error": {"code": code, "message": message}, "client_side": true}


func _finish(result: Dictionary) -> void:
	_read_events()
	_timer.stop()
	_running = false
	finished.emit(result)
