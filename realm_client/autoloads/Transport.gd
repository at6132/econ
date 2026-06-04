extends Node
## Transport layer: routes engine calls through either
##   SOLO   → local TCP socket (Godot-spawned Python child process)
##   SERVER → HTTP to a remote FastAPI server (multiplayer)

enum Mode { SOLO, SERVER }

var mode: Mode = Mode.SOLO
var _server_base: String = "http://127.0.0.1:8000"
const SOLO_HOST := "127.0.0.1"
const SOLO_PORT_DEFAULT := 9000
const SOLO_PORT_CANDIDATES: Array[int] = [9000, 9001, 9002, 9003]
const HANDSHAKE_PROBE_ID := "handshake"
const HANDSHAKE_TIMEOUT_MS := 8_000

var solo_port: int = SOLO_PORT_DEFAULT
var last_engine_status: String = ""
var _handshake_version: Dictionary = {}

var _stream: StreamPeerTCP = null
var _read_buf: String = ""
var _pending: Dictionary = {}  # request_id → Callable
var _pending_started_ms: Dictionary = {}  # request_id → msec timestamp
const REQUEST_TIMEOUT_MS := 300_000  # genesis bootstrap can take 2+ minutes
var _queued: Array = []  # [method, path, body, callback]
var _next_id: int = 1
var _python_pid: int = -1
var _ready_flag: bool = false
var _spawn_in_progress: bool = false
const SOLO_POST_SPAWN_WAIT_S := 1.5
const TCP_CONNECT_TIMEOUT_MS := 12_000
const PORT_FREE_POLL_MS := 200
const PORT_FREE_WAIT_MS := 8_000

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


func get_solo_port() -> int:
	return solo_port


## Version payload from the TCP handshake (``GET /version``). Empty if not connected yet.
func get_handshake_version() -> Dictionary:
	return _handshake_version.duplicate()


## Block until the solo engine is ready, ``engine_error`` fires, or timeout.
## Returns an empty string on success, otherwise a user-facing error message.
func await_engine_ready(timeout_s: float = 60.0) -> String:
	if mode != Transport.Mode.SOLO:
		return ""
	if is_engine_ready():
		return ""
	if not _spawn_in_progress and not _ready_flag:
		use_solo_mode()
	var tree := get_tree()
	if tree == null:
		return "Scene exited."
	var deadline_ms := Time.get_ticks_msec() + int(timeout_s * 1000.0)
	var error_msg := ""
	var on_err := func(msg: String) -> void:
		error_msg = msg
	engine_error.connect(on_err, CONNECT_ONE_SHOT)
	while not is_engine_ready() and error_msg.is_empty():
		if Time.get_ticks_msec() > deadline_ms:
			var st := last_engine_status.strip_edges()
			if st.is_empty():
				st = "no response from solo engine"
			return "Solo engine did not start within %d s (%s)." % [int(timeout_s), st]
		await tree.process_frame
	if not error_msg.is_empty():
		return "Solo engine failed: %s" % error_msg
	return ""


func use_solo_mode() -> void:
	mode = Mode.SOLO
	if _ready_flag or _spawn_in_progress:
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
	_handshake_version = {}
	_pending.clear()
	_pending_started_ms.clear()
	_queued.clear()
	_ready_flag = false
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
	if _spawn_in_progress:
		return
	_spawn_in_progress = true
	_ready_flag = false

	var engine_path := _find_engine_path()
	if engine_path.is_empty():
		last_engine_status = "Engine not found (realm_solo.py)"
		push_error("Transport: cannot find realm_solo.py")
		_spawn_in_progress = false
		engine_error.emit("Engine not found")
		return

	var python := _find_python()
	last_engine_status = "Freeing port %d…" % SOLO_PORT_DEFAULT
	await _clear_solo_ports_before_spawn()

	var tried: PackedStringArray = PackedStringArray()
	for port in SOLO_PORT_CANDIDATES:
		last_engine_status = "Starting engine on port %d…" % port
		tried.append(str(port))
		if port == SOLO_PORT_DEFAULT:
			await _clear_solo_ports_before_spawn()
		else:
			_kill_python()
			_free_solo_listen_port(port)
			await _await_port_free(port, 3_000)

		var err := OS.create_process(
			python,
			PackedStringArray([engine_path, "--port", str(port)]),
			false,
		)
		if err == -1:
			last_engine_status = "Failed to spawn Python on port %d" % port
			push_warning("Transport: create_process failed for port %d" % port)
			continue
		_python_pid = err if err > 0 else -1

		await get_tree().create_timer(SOLO_POST_SPAWN_WAIT_S).timeout
		var handshake := await _try_connect_handshake(port)
		if handshake.get("ok", false):
			solo_port = port
			_ready_flag = true
			last_engine_status = "Engine ready on %s:%d" % [SOLO_HOST, port]
			push_warning("Transport: solo engine on port %d (pid %s)" % [port, str(_python_pid)])
			_spawn_in_progress = false
			engine_ready.emit()
			_flush_queued()
			return

		var reason := str(handshake.get("reason", "handshake failed")).strip_edges()
		last_engine_status = "Port %d: %s" % [port, reason]
		push_warning("Transport: port %d failed handshake: %s" % [port, reason])
		_kill_python()

	last_engine_status = "No solo engine on ports %s" % ", ".join(tried)
	_spawn_in_progress = false
	var msg := (
		"Could not start solo engine on ports %s.\nPython: %s\nLog: %s"
		% [", ".join(tried), python, solo_log_path()]
	)
	push_error("Transport: %s" % msg)
	_fail_queued_requests(msg)
	engine_error.emit("All ports failed")


func _try_connect_handshake(port: int) -> Dictionary:
	var stream := StreamPeerTCP.new()
	var err := stream.connect_to_host(SOLO_HOST, port)
	if err != OK:
		return {"ok": false, "reason": "connect_to_host error %s" % err}

	# connect_to_host() returning OK only means the request was queued — poll until
	# STATUS_CONNECTED (or ERROR) before sending /version.
	last_engine_status = "Connecting %s:%d…" % [SOLO_HOST, port]
	var connect_deadline_ms := Time.get_ticks_msec() + TCP_CONNECT_TIMEOUT_MS
	while true:
		stream.poll()
		var st := stream.get_status()
		if st == StreamPeerTCP.STATUS_CONNECTED:
			break
		if st == StreamPeerTCP.STATUS_ERROR:
			stream.disconnect_from_host()
			return {"ok": false, "reason": "TCP connection error"}
		if st == StreamPeerTCP.STATUS_NONE:
			stream.disconnect_from_host()
			return {"ok": false, "reason": "TCP connect aborted"}
		if Time.get_ticks_msec() > connect_deadline_ms:
			stream.disconnect_from_host()
			return {"ok": false, "reason": "TCP connect timeout"}
		var tree := get_tree()
		if tree == null:
			stream.disconnect_from_host()
			return {"ok": false, "reason": "scene exited"}
		await tree.create_timer(0.05).timeout

	last_engine_status = "Verifying engine on port %d…" % port
	var msg := (
		JSON.stringify(
			{
				"id": HANDSHAKE_PROBE_ID,
				"method": "GET",
				"path": "/version",
				"body": {},
			}
		)
		+ "\n"
	)
	stream.put_data(msg.to_utf8_buffer())
	var resp := await _poll_stream_line(stream, HANDSHAKE_PROBE_ID, HANDSHAKE_TIMEOUT_MS)
	if not bool(resp.get("ok", false)):
		if resp.is_empty():
			resp = {"ok": false, "reason": "no /version response (stale listener?)"}
		stream.disconnect_from_host()
		return resp

	_stream = stream
	_read_buf = ""
	_handshake_version = resp.duplicate()
	_pending.clear()
	_pending_started_ms.clear()
	_next_id = 1
	return resp


func _poll_stream_line(
	stream: StreamPeerTCP,
	req_id: String,
	timeout_ms: int,
) -> Dictionary:
	var buf := ""
	var deadline_ms := Time.get_ticks_msec() + timeout_ms
	while Time.get_ticks_msec() < deadline_ms:
		stream.poll()
		if stream.get_status() != StreamPeerTCP.STATUS_CONNECTED:
			return {"ok": false, "reason": "socket closed during handshake"}
		var available := stream.get_available_bytes()
		if available > 0:
			var raw := stream.get_data(available)
			if raw[0] == OK:
				buf += raw[1].get_string_from_utf8()
			while "\n" in buf:
				var nl := buf.find("\n")
				var line := buf.substr(0, nl).strip_edges()
				buf = buf.substr(nl + 1)
				if line.is_empty():
					continue
				var parsed: Variant = JSON.parse_string(line)
				if not parsed is Dictionary:
					continue
				var resp: Dictionary = parsed
				if str(resp.get("id", "")) == req_id:
					return resp
				if resp.has("kind"):
					continue
		var tree := get_tree()
		if tree == null:
			return {"ok": false, "reason": "scene exited"}
		await tree.create_timer(0.05).timeout
	return {"ok": false, "reason": "handshake timeout", "timed_out": true}


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
	_handshake_version = {}
	_free_all_solo_ports()
	_kill_stale_realm_solo_processes()


## Stop tracked child, orphan realm_solo.py processes, and anything listening on 9000+.
func _clear_solo_ports_before_spawn() -> void:
	_kill_python()
	_free_all_solo_ports()
	_kill_stale_realm_solo_processes()
	var tree := get_tree()
	if tree != null:
		await tree.create_timer(0.35).timeout
	if not await _await_port_free(SOLO_PORT_DEFAULT, PORT_FREE_WAIT_MS):
		last_engine_status = "Port %d still in use" % SOLO_PORT_DEFAULT
		push_warning("Transport: port %d not free after cleanup" % SOLO_PORT_DEFAULT)


func _is_port_free(port: int) -> bool:
	var probe := TCPServer.new()
	var err := probe.listen(port, SOLO_HOST)
	if err == OK:
		probe.stop()
		return true
	return false


func _await_port_free(port: int, timeout_ms: int) -> bool:
	var tree := get_tree()
	if tree == null:
		return _is_port_free(port)
	var deadline_ms := Time.get_ticks_msec() + timeout_ms
	while Time.get_ticks_msec() < deadline_ms:
		if _is_port_free(port):
			return true
		_free_solo_listen_port(port)
		_kill_stale_realm_solo_processes()
		await tree.create_timer(float(PORT_FREE_POLL_MS) / 1000.0).timeout
	return _is_port_free(port)


func _free_all_solo_ports() -> void:
	for port in SOLO_PORT_CANDIDATES:
		_free_solo_listen_port(port)


func _kill_stale_realm_solo_processes() -> void:
	if OS.get_name() == "Windows":
		OS.execute(
			"powershell",
			[
				"-NoProfile",
				"-Command",
				(
					"Get-CimInstance Win32_Process -ErrorAction SilentlyContinue "
					+ "| Where-Object { $_.CommandLine -like '*realm_solo*' } "
					+ "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
				),
			],
			[],
			true,
		)
	elif OS.get_name() in ["macOS", "Linux"]:
		OS.execute(
			"sh",
			["-c", "pkill -f 'realm_solo.py' 2>/dev/null || true"],
			[],
			true,
		)


func _free_solo_listen_port(port: int) -> void:
	# Orphan realm_solo children can keep a port while Godot talks to a stuck listener.
	if OS.get_name() == "Windows":
		OS.execute(
			"powershell",
			[
				"-NoProfile",
				"-Command",
				(
					"$p=%d; "
					% port
					+ "Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue "
					+ "| ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }; "
					+ "netstat -ano | Select-String (\":$p\\s+.*LISTENING\") "
					+ "| ForEach-Object { if ($_ -match '\\s(\\d+)\\s*$') "
					+ "{ Stop-Process -Id ([int]$matches[1]) -Force -ErrorAction SilentlyContinue } }"
				),
			],
			[],
			true,
		)
	elif OS.get_name() == "macOS":
		OS.execute(
			"sh",
			["-c", "lsof -ti tcp:%d | xargs kill -9 2>/dev/null || true" % port],
			[],
			true,
		)
	elif OS.get_name() == "Linux":
		OS.execute(
			"sh",
			["-c", "fuser -k %d/tcp 2>/dev/null || true" % port],
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
			# Do not fail an unrelated pending request — a garbled line must not
			# make persistence/load or /dev/reset look like they failed.
			push_warning(
				"Transport: skipped non-JSON engine line (%d chars)" % line.length()
			)
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
