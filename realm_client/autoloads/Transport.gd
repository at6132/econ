extends Node
## Transport layer: routes engine calls through either
##   SOLO   → local TCP socket (Godot-spawned Python child process)
##   SERVER → HTTP to a remote FastAPI server (multiplayer)

enum Mode { SOLO, SERVER }

var mode: Mode = Mode.SOLO
var _server_base: String = "http://127.0.0.1:8000"
const SOLO_HOST := "127.0.0.1"
const SOLO_PORT := 9000

var _stream: StreamPeerTCP = null
var _read_buf: String = ""
var _pending: Dictionary = {}  # request_id → Callable
var _pending_started_ms: Dictionary = {}  # request_id → msec timestamp
const REQUEST_TIMEOUT_MS := 300_000  # genesis bootstrap can take 2+ minutes
var _queued: Array = []  # [method, path, body, callback]
var _next_id: int = 1
var _python_pid: int = -1
var _ready_flag: bool = false
var _connect_attempts: int = 0
const MAX_CONNECT_ATTEMPTS := 40

signal engine_ready
signal engine_error(msg: String)
## Server-initiated push frame (no ``id`` matched a pending request). Carries
## ``kind`` plus arbitrary payload. See ``realm.api.sim_loop`` and
## ``realm.api.routes_sim`` for shapes (``tick``, ``sim_status``, …).
signal engine_push(payload: Dictionary)


func _ready() -> void:
	set_process(true)
	use_solo_mode()


func is_engine_ready() -> bool:
	return _ready_flag


func use_solo_mode() -> void:
	mode = Mode.SOLO
	if _ready_flag:
		return
	_spawn_python_async()


## Kill and respawn the solo Python child so code changes apply and no stale
## in-memory world survives between "New world" runs.
func restart_solo_engine() -> void:
	if mode != Mode.SOLO:
		return
	_kill_python()
	_stream = null
	_read_buf = ""
	_pending.clear()
	_pending_started_ms.clear()
	_queued.clear()
	_ready_flag = false
	_connect_attempts = 0
	await get_tree().create_timer(0.75).timeout
	await _spawn_python_async()


func repo_saves_dir() -> String:
	return ProjectSettings.globalize_path("res://../saves")


func solo_log_path() -> String:
	return ProjectSettings.globalize_path("res://../engine/logs/realm_solo.log")


func use_server_mode(base_url: String) -> void:
	_kill_python()
	_stream = null
	_ready_flag = false
	mode = Mode.SERVER
	_server_base = base_url.rstrip("/")


func _spawn_python_async() -> void:
	var engine_path := _find_engine_path()
	if engine_path.is_empty():
		push_error("Transport: cannot find realm_solo.py")
		engine_error.emit("Engine not found")
		return

	# Always purge anything still bound to :9000 before starting a fresh Python.
	# Windows allows multiple processes to bind the same port (SO_REUSEADDR), and
	# orphaned realm_solo workers running OLD bytecode silently win the race.
	_free_solo_listen_port()
	await get_tree().create_timer(0.4).timeout

	var python := _find_python()
	var err := OS.create_process(python, PackedStringArray([engine_path]), false)
	if err == -1:
		push_error("Transport: failed to spawn Python engine")
		engine_error.emit("Failed to spawn engine")
		return
	_python_pid = err if err > 0 else -1

	await get_tree().create_timer(1.5).timeout
	_connect_socket()


func _find_engine_path() -> String:
	var candidates: Array[String] = [
		ProjectSettings.globalize_path("res://../engine/realm_solo.py"),
		OS.get_executable_path().get_base_dir().path_join("../engine/realm_solo.py"),
	]
	for c in candidates:
		if FileAccess.file_exists(c):
			return c
	return ""


func _find_python() -> String:
	var is_win := OS.get_name() == "Windows"
	var candidates: Array[String] = []
	if is_win:
		candidates.append(ProjectSettings.globalize_path("res://../engine/.venv/Scripts/python.exe"))
		candidates.append(ProjectSettings.globalize_path("res://../.venv/Scripts/python.exe"))
	else:
		candidates.append(ProjectSettings.globalize_path("res://../engine/.venv/bin/python3"))
		candidates.append(ProjectSettings.globalize_path("res://../.venv/bin/python3"))
	candidates.append_array(["python3", "python"])
	for c in candidates:
		if c.contains("/") or c.contains("\\"):
			if FileAccess.file_exists(c):
				return c
		else:
			return c
	return "python3"


func _connect_socket() -> void:
	_stream = StreamPeerTCP.new()
	var err := _stream.connect_to_host(SOLO_HOST, SOLO_PORT)
	if err != OK:
		_connect_attempts += 1
		if _connect_attempts >= MAX_CONNECT_ATTEMPTS:
			push_error("Transport: could not connect to solo engine on %s:%d" % [SOLO_HOST, SOLO_PORT])
			_fail_queued_requests("solo engine not running (port %d)" % SOLO_PORT)
			engine_error.emit("Socket connect failed")
			return
		await get_tree().create_timer(0.25).timeout
		_connect_socket()
		return
	_ready_flag = true
	_connect_attempts = 0
	engine_ready.emit()
	_flush_queued()


func _flush_queued() -> void:
	while not _queued.is_empty():
		var item: Array = _queued.pop_front()
		_socket_request(str(item[0]), str(item[1]), item[2] as Dictionary, item[3] as Callable)


func _kill_python() -> void:
	if _python_pid > 0:
		if OS.get_name() == "Windows":
			OS.execute("taskkill", ["/PID", str(_python_pid), "/F", "/T"], [], false)
		else:
			OS.kill(_python_pid)
		_python_pid = -1
	_free_solo_listen_port()


func _free_solo_listen_port() -> void:
	# Orphan realm_solo children can keep :9000 while Godot talks to a stuck bootstrap.
	if OS.get_name() == "Windows":
		OS.execute(
			"powershell",
			[
				"-NoProfile",
				"-Command",
				(
					"Get-NetTCPConnection -LocalPort %d -State Listen -ErrorAction SilentlyContinue "
					+ "| ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
				)
				% SOLO_PORT,
			],
			[],
			true,
		)
	elif OS.get_name() == "macOS":
		OS.execute(
			"sh",
			[
				"-c",
				"lsof -ti tcp:%d | xargs kill -9 2>/dev/null || true" % SOLO_PORT,
			],
			[],
			true,
		)
	elif OS.get_name() == "Linux":
		OS.execute(
			"sh",
			[
				"-c",
				"fuser -k %d/tcp 2>/dev/null || true" % SOLO_PORT,
			],
			[],
			true,
		)


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST or what == NOTIFICATION_EXIT_TREE:
		_kill_python()


func _safe_call(callback: Callable, data: Dictionary) -> void:
	if not callback.is_valid():
		return
	# Lambdas and other unbound callables have no ``get_object()`` — still invoke.
	var obj := callback.get_object()
	if obj is Node:
		var n := obj as Node
		if not is_instance_valid(n) or not n.is_inside_tree():
			return
	callback.call(data)


func get_request(endpoint: String, callback: Callable) -> void:
	if mode == Mode.SERVER:
		_http_get(endpoint, callback)
	else:
		_socket_request("GET", endpoint, {}, callback)


func post_request(endpoint: String, payload: Dictionary, callback: Callable) -> void:
	if mode == Mode.SERVER:
		_http_post(endpoint, payload, callback)
	else:
		_socket_request("POST", endpoint, payload, callback)


func delete_request(endpoint: String, callback: Callable) -> void:
	if mode == Mode.SERVER:
		_http_delete(endpoint, callback)
	else:
		_socket_request("DELETE", endpoint, {}, callback)


func _socket_request(method: String, path: String, body: Dictionary, callback: Callable) -> void:
	if not _ready_flag or _stream == null:
		_queued.append([method, path, body, callback])
		return

	var req_id := str(_next_id)
	_next_id += 1
	_pending[req_id] = callback
	_pending_started_ms[req_id] = Time.get_ticks_msec()

	var msg := JSON.stringify({
		"id": req_id,
		"method": method,
		"path": path,
		"body": body,
	}) + "\n"
	_stream.put_data(msg.to_utf8_buffer())


func _process(_delta: float) -> void:
	if mode != Mode.SOLO or _stream == null:
		return
	_stream.poll()
	var status := _stream.get_status()
	if status != StreamPeerTCP.STATUS_CONNECTED:
		if _ready_flag:
			_on_solo_disconnected("engine socket closed")
		return
	_check_pending_timeouts()
	var available := _stream.get_available_bytes()
	if available <= 0:
		return
	var raw := _stream.get_data(available)
	if raw[0] != OK:
		return
	_read_buf += raw[1].get_string_from_utf8()
	while "\n" in _read_buf:
		var nl := _read_buf.find("\n")
		var line := _read_buf.substr(0, nl).strip_edges()
		_read_buf = _read_buf.substr(nl + 1)
		if line.is_empty():
			continue
		var parsed: Variant = JSON.parse_string(line)
		if not parsed is Dictionary:
			push_error(
				"Transport: failed to parse engine response (%d chars) — map load may stall"
				% line.length()
			)
			_fail_oldest_pending("JSON parse error")
			continue
		var resp: Dictionary = parsed
		var rid: String = str(resp.get("id", ""))
		if rid.is_empty() and resp.has("kind"):
			# Server-initiated push (tick frame, sim_status, …). No callback to
			# match; broadcast to listeners.
			engine_push.emit(resp)
			continue
		if _pending.has(rid):
			var cb: Callable = _pending[rid]
			_pending.erase(rid)
			_pending_started_ms.erase(rid)
			_safe_call(cb, resp)
		elif resp.has("kind"):
			# Push frame whose ``id`` accidentally collided with an unused
			# numeric — still route as a push.
			engine_push.emit(resp)
		elif not _pending.is_empty():
			push_warning("Transport: response id %s did not match a pending request" % rid)


func _fail_oldest_pending(reason: String) -> void:
	if _pending.is_empty():
		return
	var oldest_id: String = str(_pending.keys()[0])
	var cb: Callable = _pending[oldest_id]
	_pending.erase(oldest_id)
	_pending_started_ms.erase(oldest_id)
	_safe_call(cb, {"ok": false, "reason": reason})


func _fail_all_pending(reason: String) -> void:
	var fail := {"ok": false, "reason": reason}
	var ids: Array = _pending.keys()
	for rid in ids:
		var cb: Callable = _pending[rid]
		_pending.erase(rid)
		_pending_started_ms.erase(rid)
		_safe_call(cb, fail)


func _check_pending_timeouts() -> void:
	if _pending.is_empty():
		return
	var now := Time.get_ticks_msec()
	var timed_out: Array[String] = []
	for rid in _pending_started_ms.keys():
		var started: int = int(_pending_started_ms.get(rid, now))
		if now - started > REQUEST_TIMEOUT_MS:
			timed_out.append(str(rid))
	for rid in timed_out:
		if not _pending.has(rid):
			continue
		var cb: Callable = _pending[rid]
		_pending.erase(rid)
		_pending_started_ms.erase(rid)
		_safe_call(cb, {"ok": false, "reason": "request timed out"})


func _on_solo_disconnected(reason: String) -> void:
	_ready_flag = false
	_stream = null
	_read_buf = ""
	_fail_all_pending(reason)
	engine_error.emit(reason)


func _fail_queued_requests(reason: String) -> void:
	var fail := {"ok": false, "reason": reason}
	while not _queued.is_empty():
		var item: Array = _queued.pop_front()
		_safe_call(item[3] as Callable, fail)


func _http_get(endpoint: String, callback: Callable) -> void:
	var h := HTTPRequest.new()
	add_child(h)
	h.request_completed.connect(
		func(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
			h.queue_free()
			if response_code != 200:
				_safe_call(callback, {})
				return
			var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
			_safe_call(callback, parsed if parsed is Dictionary else {})
	)
	h.request(_server_base + endpoint)


func _http_post(endpoint: String, payload: Dictionary, callback: Callable) -> void:
	var h := HTTPRequest.new()
	add_child(h)
	h.request_completed.connect(
		func(_result: int, _response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
			h.queue_free()
			var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
			_safe_call(callback, parsed if parsed is Dictionary else {})
	)
	var body_str := "{}" if payload.is_empty() else JSON.stringify(payload)
	h.request(
		_server_base + endpoint,
		PackedStringArray(["Content-Type: application/json"]),
		HTTPClient.METHOD_POST,
		body_str,
	)


func _http_delete(endpoint: String, callback: Callable) -> void:
	var h := HTTPRequest.new()
	add_child(h)
	h.request_completed.connect(
		func(_result: int, _response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
			h.queue_free()
			var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
			_safe_call(callback, parsed if parsed is Dictionary else {})
	)
	h.request(
		_server_base + endpoint,
		PackedStringArray(["Content-Type: application/json"]),
		HTTPClient.METHOD_DELETE,
		"",
	)
