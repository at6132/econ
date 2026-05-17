extends Node
## Dev WebSocket client (``/ws`` may not exist yet — reconnects quietly, never crashes the game).

const WS_URL := "ws://127.0.0.1:8000/ws"
var _socket := WebSocketPeer.new()
var _connected := false
var _reconnect_in: float = 0.0

signal tick_event(event_data: Dictionary)
signal connected
signal disconnected


func _ready() -> void:
	if Transport.mode == Transport.Mode.SERVER:
		_try_connect()
	else:
		_connected = true
		connected.emit()


func _try_connect() -> void:
	var err := _socket.connect_to_url(WS_URL)
	if err != OK:
		push_warning("WS: connect_to_url failed (%d) — retrying in 3s" % err)
		_reconnect_in = 3.0


func _process(delta: float) -> void:
	if _reconnect_in > 0.0:
		_reconnect_in -= delta
		if _reconnect_in > 0.0:
			return
		_reconnect_in = 0.0
		_try_connect()

	_socket.poll()
	var state := _socket.get_ready_state()
	if state == WebSocketPeer.STATE_OPEN:
		if not _connected:
			_connected = true
			connected.emit()
		while _socket.get_available_packet_count() > 0:
			var raw := _socket.get_packet().get_string_from_utf8()
			var data: Variant = JSON.parse_string(raw)
			if data is Dictionary:
				tick_event.emit(data)
				_route_event(data)
	elif state == WebSocketPeer.STATE_CLOSED:
		if _connected:
			_connected = false
			disconnected.emit()
		_socket = WebSocketPeer.new()
		_reconnect_in = 3.0


func _route_event(data: Dictionary) -> void:
	var kind := str(data.get("kind", ""))
	match kind:
		"summary_update":
			var pl: Variant = data.get("payload", {})
			WorldState.apply_summary(pl if pl is Dictionary else {})
		"world_feed":
			WorldState.world_feed_log.push_front(data)
			WorldState.unread_feed_count += 1
			WorldState.feed_updated.emit()
		"production_done":
			WorldState.active_production_count = maxi(0, WorldState.active_production_count - 1)
			WorldState.summary_updated.emit()
		_:
			pass
