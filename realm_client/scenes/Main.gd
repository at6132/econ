extends Node2D
## Solo shell — map in SubViewport; one exclusive overlay panel at a time.

const PlotDetailScene := preload("res://scenes/panels/PlotDetail.tscn")
const BazaarPanelScene := preload("res://scenes/panels/BazaarPanel.tscn")
const BuildPanelScene := preload("res://scenes/panels/BuildPanel.tscn")
const ChroniclePanelScene := preload("res://scenes/panels/ChroniclePanel.tscn")
const PactsPanelScene := preload("res://scenes/panels/PactsPanel.tscn")
const FinancePanelScene := preload("res://scenes/panels/FinancePanel.tscn")
const LaborPanelScene := preload("res://scenes/panels/LaborPanel.tscn")
const BusinessPanelScene := preload("res://scenes/panels/BusinessPanel.tscn")
const ShippingPanelScene := preload("res://scenes/panels/ShippingPanel.tscn")
const SciencePanelScene := preload("res://scenes/panels/SciencePanel.tscn")
const EconomicsPanelScene := preload("res://scenes/panels/EconomicsPanel.tscn")
const TendersPanelScene := preload("res://scenes/panels/TendersPanel.tscn")
const ProfilePanelScene := preload("res://scenes/panels/ProfilePanel.tscn")

const OVERLAY_LAYER := 32

@onready var ui_root: Control = $UILayer/UIRoot
@onready var map_viewport: SubViewportContainer = $UILayer/UIRoot/MapViewport
@onready var sub_viewport: SubViewport = $UILayer/UIRoot/MapViewport/SubViewport
@onready var world_map: Node2D = $UILayer/UIRoot/MapViewport/SubViewport/WorldMap
@onready var shell: CanvasLayer = $CommandShell
@onready var sidebar: PanelContainer = $UILayer/UIRoot/TerritorySidebar
var _overlay_bar: HBoxContainer

var _active_overlay: Node = null
var _resume_plot_id: String = ""
var _build_return_plot_id: String = ""

## Wall-clock throttle on the realtime refresh: the engine pushes a tick every
## ``sim_seconds_per_tick`` (2.5 s at 1×, 0.625 s at 4×). We don't need to
## re-pull summary/player/feed for every push — once every ~2 real seconds is
## enough for the HUD and feed deltas.
const _REFRESH_MIN_INTERVAL_S: float = 2.0
var _last_refresh_msec: int = -1
## Avoid overlapping refreshes when an earlier round-trip is still in flight.
var _refresh_in_flight: bool = false


func _ready() -> void:
	RenderingServer.set_default_clear_color(RealmColors.BG)
	ui_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	map_viewport.mouse_filter = Control.MOUSE_FILTER_STOP
	sub_viewport.handle_input_locally = true
	shell.nav_pressed.connect(_on_nav_pressed)
	world_map.plot_clicked.connect(_on_plot_clicked)
	get_viewport().size_changed.connect(_layout_shell)
	call_deferred("_boot_shell")
	# The host engine owns the clock. We listen for pushes instead of polling
	# ``/tick`` on a client timer. Tick frames update the HUD instantly; the
	# heavier ``summary + player + feed`` GETs run throttled in
	# ``_on_engine_push`` (at most once per ``_REFRESH_MIN_INTERVAL_S``).
	Transport.engine_push.connect(_on_engine_push)


func _boot_shell() -> void:
	await get_tree().process_frame
	await get_tree().process_frame
	_setup_map_overlay_bar()
	_layout_shell()
	_refresh_shell_hud()
	if Transport.mode == Transport.Mode.SOLO and not Transport.is_engine_ready():
		await Transport.engine_ready
	_initial_world_load()


## One-shot boot fetch: read-once tables, map, player view, feed tails.
## The 2 s tick loop after this only refreshes the cheap payloads
## (summary + player + feed deltas) — the heavy /world/map is only
## re-fetched when the player does a structural action.
func _initial_world_load() -> void:
	# Map first (~10 MB on Genesis). Other boot payloads are tiny; loading
	# them before the map risks WorldMap painting the 48×36 demo placeholder
	# while this request is still in flight.
	API.get_world_map(func(m): _on_boot_map_loaded(m))


func _on_boot_map_loaded(data: Dictionary) -> void:
	if _try_apply_map_payload(data):
		_finish_boot_load()
		return
	var reason := str(data.get("reason", "empty or invalid payload"))
	push_warning("Realm: GET /world/map failed (%s); falling back to GET /world" % reason)
	API.get_world(func(w): _on_boot_world_fallback(w))


func _try_apply_map_payload(data: Dictionary) -> bool:
	if data.is_empty() or WorldState.is_api_error_payload(data):
		return false
	WorldState.apply_map(data)
	return not WorldState.plots.is_empty()


func _on_boot_world_fallback(data: Dictionary) -> void:
	if data.is_empty() or WorldState.is_api_error_payload(data):
		push_error("Realm: GET /world failed: %s" % str(data.get("reason", "no data")))
		return
	WorldState.apply_world(data)
	if WorldState.plots.is_empty():
		push_error("Realm: engine returned no plots — see engine/logs/realm_solo.log")
		return
	_finish_boot_load()


func _finish_boot_load() -> void:
	API.get_world_static(func(s): WorldState.apply_static(s))
	API.get_world_player(func(p): WorldState.apply_player(p), WorldState.party_id)
	API.get_world_feed(func(f): WorldState.apply_feed(f), -1)
	API.get_world_summary(WorldState.party_id, func(s): WorldState.apply_summary(s))


func _setup_map_overlay_bar() -> void:
	if is_instance_valid(_overlay_bar):
		return
	_overlay_bar = preload("res://scenes/MapOverlayBar.tscn").instantiate() as HBoxContainer
	ui_root.add_child(_overlay_bar)
	_overlay_bar.overlay_changed.connect(
		func(mode: String) -> void:
			if world_map.has_method("set_overlay_mode"):
				world_map.call("set_overlay_mode", mode)
	)
	_position_overlay_bar()


func _position_overlay_bar() -> void:
	if not is_instance_valid(_overlay_bar):
		return
	var top_h: float = 96.0
	if shell.has_method("shell_top_height"):
		top_h = float(shell.call("shell_top_height"))
	_overlay_bar.position = Vector2(12, top_h + 12)
	_overlay_bar.z_index = 5


func _layout_shell() -> void:
	var vp := get_viewport().get_visible_rect().size
	var top_h: float = 96.0
	if shell.has_method("shell_top_height"):
		top_h = float(shell.call("shell_top_height"))
	var side_w: float = 400.0
	if shell.has_method("sidebar_width"):
		side_w = float(shell.call("sidebar_width"))
	sidebar.set_anchors_preset(Control.PRESET_TOP_RIGHT)
	sidebar.offset_left = -side_w
	sidebar.offset_top = top_h
	sidebar.offset_right = 0.0
	sidebar.offset_bottom = 0.0
	sidebar.z_index = 10
	# Map fills the playfield; sidebar and slide-in panels draw on top (no hard clip).
	map_viewport.z_index = 0
	map_viewport.stretch = true
	map_viewport.clip_children = CanvasItem.CLIP_CHILDREN_DISABLED
	map_viewport.set_anchors_preset(Control.PRESET_FULL_RECT)
	map_viewport.anchor_left = 0.0
	map_viewport.anchor_top = 0.0
	map_viewport.anchor_right = 1.0
	map_viewport.anchor_bottom = 1.0
	map_viewport.offset_left = 0.0
	map_viewport.offset_right = 0.0
	map_viewport.offset_bottom = 0.0
	map_viewport.offset_top = top_h
	var gw := maxi(64, int(vp.x))
	var gh := maxi(64, int(vp.y - top_h))
	var map_size := Vector2i(gw, gh)
	sub_viewport.transparent_bg = false
	sub_viewport.render_target_clear_mode = SubViewport.CLEAR_MODE_ALWAYS
	sub_viewport.size = map_size
	if world_map.has_method("set_view_size"):
		world_map.call("set_view_size", Vector2(map_size))
	_position_overlay_bar()


## Sync top strip to ``WorldState`` without inventing money/ticks (demo fudge hid dead API calls).
func _refresh_shell_hud() -> void:
	if shell.has_method("_refresh_stats"):
		shell.call("_refresh_stats")
	if shell.has_method("_refresh_seed"):
		shell.call("_refresh_seed")


## Engine push handler. Two frame kinds today:
##   ``tick``       — per-tick clock + day/season + paused/speed. Cheap.
##   ``sim_status`` — pause/speed/pacing changed (from any control source).
## On tick frames we also kick a throttled HUD refresh so cash/feed/inventory
## stay current without polling on a client timer.
func _on_engine_push(payload: Dictionary) -> void:
	var kind := str(payload.get("kind", ""))
	match kind:
		"tick":
			WorldState.apply_tick_frame(payload)
			if shell.has_method("flash_tick"):
				shell.call("flash_tick")
			_maybe_refresh_from_server()
		"sim_status":
			WorldState.apply_sim_status(payload)
		_:
			# Unknown push — log once and ignore. Don't crash on future frame
			# kinds added by the engine.
			push_warning("Main: unknown engine push kind %s" % kind)


## Realtime refresh — at most once per ``_REFRESH_MIN_INTERVAL_S`` real seconds
## regardless of how often the engine pushes ticks. At 1× the engine pushes
## every 2.5 s so we hit refresh nearly every tick; at 4× we still only hit it
## every ~2 s, keeping HTTP-shaped load constant under speed changes.
##
## Only the three cheap payloads (summary + player + feed delta). The fat
## ``/world/map`` is refreshed only after structural actions.
func _maybe_refresh_from_server() -> void:
	if _refresh_in_flight:
		return
	var now_ms := Time.get_ticks_msec()
	if _last_refresh_msec >= 0 and (now_ms - _last_refresh_msec) < int(_REFRESH_MIN_INTERVAL_S * 1000.0):
		return
	_last_refresh_msec = now_ms
	_refresh_from_server()


func _refresh_from_server() -> void:
	_refresh_in_flight = true
	# Three independent gets fire in parallel; ``_refresh_in_flight`` clears
	# when the slowest (feed) returns so we don't pile up requests under load.
	API.get_world_summary(WorldState.party_id, func(s): WorldState.apply_summary(s))
	API.get_world_player(func(p): WorldState.apply_player(p), WorldState.party_id)
	API.get_world_feed(_on_feed_refreshed, WorldState.feed_seen_tick)


func _on_feed_refreshed(data: Dictionary) -> void:
	WorldState.apply_feed(data)
	_refresh_in_flight = false


## Refresh the lean map view after a structural action (claim / survey /
## build / dispatch). Pair with ``_refresh_from_server`` callsites that
## previously called ``API.get_world(...)`` and used the result to redraw
## the map.
func refresh_world_map() -> void:
	API.get_world_map(func(m): WorldState.apply_map(m))
	API.get_world_player(func(p): WorldState.apply_player(p), WorldState.party_id)


func _on_nav_pressed(panel_name: String) -> void:
	if panel_name == "market":
		if _is_overlay(BazaarPanelScene):
			_close_active_overlay()
		else:
			_open_bazaar()
		return
	if panel_name == "territory":
		return
	if panel_name == "chronicle":
		_toggle_overlay(ChroniclePanelScene)
		return
	if panel_name == "contracts":
		_toggle_overlay(PactsPanelScene)
		return
	if panel_name == "finance":
		_toggle_overlay(FinancePanelScene)
		return
	if panel_name == "labor":
		_toggle_overlay(LaborPanelScene)
		return
	if panel_name == "business":
		_toggle_overlay(BusinessPanelScene)
		return
	if panel_name == "caravans" or panel_name == "shipping":
		_toggle_overlay(ShippingPanelScene)
		return
	if panel_name == "lab" or panel_name == "science":
		_toggle_overlay(SciencePanelScene)
		return
	if panel_name == "economics":
		_toggle_overlay(EconomicsPanelScene)
		return
	if panel_name == "tenders":
		_toggle_overlay(TendersPanelScene)
		return
	if panel_name == "menu" or panel_name == "profile":
		_toggle_overlay(ProfilePanelScene)
		return
	push_warning("Panel '%s' not implemented yet" % panel_name)


func show_feedback(message: String, is_error: bool = false) -> void:
	MainFeedback.toast(message, is_error)


func _toggle_overlay(scene: PackedScene) -> void:
	if _is_overlay(scene):
		_close_active_overlay()
	else:
		_resume_plot_id = ""
		_build_return_plot_id = ""
		_mount_overlay(scene.instantiate())


func _on_plot_clicked(plot_id: String, _plot_data_unused: Dictionary) -> void:
	if _is_overlay(PlotDetailScene) and _resume_plot_id == plot_id:
		_close_active_overlay()
		return
	_open_plot_detail(plot_id)


func _open_plot_detail(plot_id: String) -> void:
	_build_return_plot_id = ""
	_resume_plot_id = plot_id
	var merged: Dictionary = WorldState.get_plot_ui(plot_id)
	if merged.is_empty():
		merged = WorldState.plots.get(plot_id, {})
	var panel: Node = PlotDetailScene.instantiate()
	_mount_overlay(panel)
	if panel.has_method("open"):
		panel.call("open", plot_id, merged)


func _open_bazaar() -> void:
	_resume_plot_id = ""
	_build_return_plot_id = ""
	_mount_overlay(BazaarPanelScene.instantiate())


func open_build_panel(plot_id: String, plot_data: Dictionary) -> void:
	_build_return_plot_id = plot_id
	_close_active_overlay()
	var panel: CanvasLayer = BuildPanelScene.instantiate() as CanvasLayer
	_mount_overlay(panel, false)
	if panel.has_method("open"):
		panel.call("open", plot_id, plot_data)
	if panel.has_signal("closed"):
		panel.closed.connect(_on_build_panel_closed, CONNECT_ONE_SHOT)


func open_building_picker(plot_id: String, terrain: String) -> void:
	var merged: Dictionary = WorldState.get_plot_ui(plot_id)
	if merged.is_empty():
		merged = WorldState.plots.get(plot_id, {})
	if merged.is_empty():
		merged = {"terrain": terrain}
	open_build_panel(plot_id, merged)


func _on_build_panel_closed() -> void:
	var plot_id: String = _build_return_plot_id
	_build_return_plot_id = ""
	_close_active_overlay()
	if plot_id != "":
		refresh_world_map()
		_open_plot_detail(plot_id)


func _is_overlay(scene: PackedScene) -> bool:
	return is_instance_valid(_active_overlay) and _active_overlay.scene_file_path == scene.resource_path


func _close_active_overlay() -> void:
	if not is_instance_valid(_active_overlay):
		_active_overlay = null
		return
	var node := _active_overlay
	_active_overlay = null
	if node.has_method("close"):
		node.call("close")
	elif node is CanvasLayer:
		_dismiss_canvas_layer(node as CanvasLayer)
	else:
		node.queue_free()


func _dismiss_canvas_layer(layer: CanvasLayer) -> void:
	var panel: Node = layer.get_node_or_null("Panel")
	if panel == null:
		panel = layer.get_node_or_null("CenterPanel")
	if panel != null and layer.has_method("close"):
		layer.call("close")
		return
	layer.queue_free()


func _mount_overlay(node: Node, close_first: bool = true) -> void:
	if close_first:
		_close_active_overlay()
	_active_overlay = node
	if node is CanvasLayer:
		(node as CanvasLayer).layer = OVERLAY_LAYER
	add_child(node)
	node.tree_exited.connect(_on_overlay_tree_exited.bind(node), CONNECT_ONE_SHOT)


func _on_overlay_tree_exited(node: Node) -> void:
	if _active_overlay == node:
		_active_overlay = null
	var path: String = node.scene_file_path
	if path == PlotDetailScene.resource_path:
		if _build_return_plot_id == "":
			_resume_plot_id = ""
		return
	if path == BuildPanelScene.resource_path:
		return
	if path == BazaarPanelScene.resource_path:
		_resume_plot_id = ""
