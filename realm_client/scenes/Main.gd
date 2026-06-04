extends Node2D
## Solo shell — map in SubViewport; one exclusive overlay panel at a time.

## PlotDetail uses autoloads (WorldState, API, …); preload() at class scope fails on Godot 4.3+.
const PLOT_DETAIL_SCENE_PATH := "res://scenes/panels/PlotDetail.tscn"
const BazaarPanelScene := preload("res://scenes/panels/BazaarPanel.tscn")
const BuildPanelScene := preload("res://scenes/panels/BuildPanel.tscn")
const ProductionWorkflowScene := preload("res://scenes/panels/ProductionWorkflowWindow.tscn")
const BlueprintStudioScene := preload("res://scenes/panels/build/BlueprintStudioWindow.tscn")
const ChroniclePanelScene := preload("res://scenes/panels/ChroniclePanel.tscn")
const PactsPanelScene := preload("res://scenes/panels/PactsPanel.tscn")
const FinancePanelScene := preload("res://scenes/panels/FinancePanel.tscn")
const LaborPanelScene := preload("res://scenes/panels/LaborPanel.tscn")
const BusinessPanelScene := preload("res://scenes/panels/BusinessPanel.tscn")
const ShippingPanelScene := preload("res://scenes/panels/ShippingPanel.tscn")
const InventoryPanelScene := preload("res://scenes/panels/InventoryPanel.tscn")
const OperationsPanelScene := preload("res://scenes/panels/OperationsPanel.tscn")
const CommandPaletteScene := preload("res://scenes/shell/CommandPalette.tscn")
const SciencePanelScene := preload("res://scenes/panels/SciencePanel.tscn")
const LabsMonitorPanelScene := preload("res://scenes/panels/LabsMonitorPanel.tscn")
const EconomicsPanelScene := preload("res://scenes/panels/EconomicsPanel.tscn")
const TendersPanelScene := preload("res://scenes/panels/TendersPanel.tscn")
const ProfilePanelScene := preload("res://scenes/panels/ProfilePanel.tscn")
const TerritoryPanelScene := preload("res://scenes/panels/TerritoryPanel.tscn")
const PauseMenuScene := preload("res://scenes/PauseMenu.tscn")

const OVERLAY_LAYER := 32

@onready var ui_root: Control = $UILayer/UIRoot
@onready var map_viewport: SubViewportContainer = $UILayer/UIRoot/MapViewport
@onready var sub_viewport: SubViewport = $UILayer/UIRoot/MapViewport/SubViewport
@onready var world_map: Node2D = $UILayer/UIRoot/MapViewport/SubViewport/WorldMap
@onready var shell: CanvasLayer = $CommandShell
var _overlay_bar: HBoxContainer

var _active_overlay: Node = null
var _production_workflow: CanvasLayer = null
var _blueprint_studio: CanvasLayer = null
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
var _pause_menu: CanvasLayer = null
var _command_palette: CanvasLayer = null
var _plot_detail_scene: PackedScene


func _plot_detail_packed() -> PackedScene:
	if _plot_detail_scene == null:
		var loaded: Resource = load(PLOT_DETAIL_SCENE_PATH)
		if loaded == null:
			push_error("Main: failed to load %s — check Godot Output for .tscn parse errors" % PLOT_DETAIL_SCENE_PATH)
			return null
		_plot_detail_scene = loaded as PackedScene
		if _plot_detail_scene == null:
			push_error("Main: %s is not a PackedScene" % PLOT_DETAIL_SCENE_PATH)
	return _plot_detail_scene


func _is_overlay_path(scene_path: String) -> bool:
	return is_instance_valid(_active_overlay) and _active_overlay.scene_file_path == scene_path


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
	_pause_menu = PauseMenuScene.instantiate() as CanvasLayer
	add_child(_pause_menu)
	_command_palette = CommandPaletteScene.instantiate() as CanvasLayer
	add_child(_command_palette)


func _unhandled_input(event: InputEvent) -> void:
	if not (event is InputEventKey and event.pressed and not event.echo):
		return
	var key := event as InputEventKey
	if key.keycode == KEY_K and (key.ctrl_pressed or key.meta_pressed):
		_toggle_command_palette()
		get_viewport().set_input_as_handled()
		return
	if key.keycode != KEY_ESCAPE:
		return
	if _overlay_blocks_pause_menu():
		return
	if _pause_menu != null and _pause_menu.visible:
		if _pause_menu.has_method("handle_escape") and _pause_menu.call("handle_escape"):
			get_viewport().set_input_as_handled()
		return
	if _pause_menu != null and _pause_menu.has_method("open_menu"):
		_pause_menu.call("open_menu")
		get_viewport().set_input_as_handled()


func _overlay_blocks_pause_menu() -> bool:
	if not is_instance_valid(_active_overlay):
		return false
	if _active_overlay.has_method("blocks_pause_menu"):
		return bool(_active_overlay.call("blocks_pause_menu"))
	return false


func _boot_shell() -> void:
	await get_tree().process_frame
	await get_tree().process_frame
	_setup_map_overlay_bar()
	_layout_shell()
	_refresh_shell_hud()
	if Transport.mode == Transport.Mode.SOLO:
		var err := await Transport.await_engine_ready(90.0)
		if not err.is_empty():
			push_error("Realm: %s" % err)
			return
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
	# Genesis payloads are ~8 MB — defer so the scene change can finish one frame first.
	call_deferred("_apply_boot_map_loaded", data)


func _apply_boot_map_loaded(data: Dictionary) -> void:
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
	_apply_boot_map_overlay()
	API.get_sim_status(_on_boot_sim_status)
	API.get_world_static(func(s): WorldState.apply_static(s))
	API.get_recipes(func(d): WorldState.apply_recipes_catalog(d))
	API.get_world_player(func(p): WorldState.apply_player(p), WorldState.party_id)
	API.get_world_feed(func(f): WorldState.apply_feed(f), -1)
	API.get_world_summary(WorldState.party_id, func(s): WorldState.apply_summary(s))
	API.get_roads(func(d: Dictionary) -> void:
		if not d.is_empty() and bool(d.get("ok", true)):
			var segs: Variant = d.get("segments", [])
			if segs is Array:
				WorldState.road_segments = segs as Array
	)


func _on_boot_sim_status(data: Dictionary) -> void:
	if data.is_empty():
		return
	WorldState.apply_sim_status(data)
	_apply_boot_sim_prefs()
	if shell.has_method("_refresh_sim_controls"):
		shell.call("_refresh_sim_controls")
	if shell.has_method("_refresh_stats"):
		shell.call("_refresh_stats")


func _apply_boot_map_overlay() -> void:
	if not is_instance_valid(_overlay_bar):
		return
	if _overlay_bar.has_method("apply_mode"):
		_overlay_bar.call("apply_mode", RealmSettings.default_overlay)


func _apply_boot_sim_prefs() -> void:
	var body: Dictionary = {}
	if RealmSettings.default_speed > 0.0:
		body["speed"] = RealmSettings.default_speed
	if RealmSettings.start_paused:
		body["paused"] = true
	if body.is_empty():
		return
	API.sim_control(body, Callable())


func _setup_map_overlay_bar() -> void:
	if is_instance_valid(_overlay_bar):
		return
	_overlay_bar = preload("res://scenes/MapOverlayBar.tscn").instantiate() as HBoxContainer
	ui_root.add_child(_overlay_bar)
	_overlay_bar.overlay_changed.connect(_on_map_overlay_mode_changed)
	_position_overlay_bar()


func _on_map_overlay_mode_changed(mode: String) -> void:
	if world_map.has_method("set_overlay_mode"):
		world_map.call("set_overlay_mode", mode)


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
	# Map fills the playfield; slide-in panels draw on top (no hard clip).
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
	sub_viewport.transparent_bg = false
	sub_viewport.render_target_clear_mode = SubViewport.CLEAR_MODE_ALWAYS
	# Do not assign sub_viewport.size while MapViewport.stretch is true (Godot 4.6 SIGSEGV).
	if world_map.has_method("set_view_size"):
		world_map.call("set_view_size", Vector2(gw, gh))
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
		_toggle_overlay(TerritoryPanelScene)
		return
	if panel_name == "operations":
		_toggle_overlay(OperationsPanelScene)
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
	if panel_name == "inventory":
		_toggle_overlay(InventoryPanelScene)
		return
	if panel_name == "lab":
		if WorldState.lab_mode:
			_toggle_overlay(LabsMonitorPanelScene)
		else:
			_toggle_overlay(SciencePanelScene)
		return
	if panel_name == "science":
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
	if _is_overlay_path(PLOT_DETAIL_SCENE_PATH) and _resume_plot_id == plot_id:
		_close_active_overlay()
		return
	_open_plot_detail(plot_id)


func _open_plot_detail(plot_id: String) -> void:
	if is_instance_valid(_production_workflow):
		if _production_workflow.has_method("close"):
			_production_workflow.call("close")
		else:
			_production_workflow.queue_free()
		_production_workflow = null
	_build_return_plot_id = ""
	_resume_plot_id = plot_id
	var merged: Dictionary = WorldState.get_plot_ui(plot_id)
	if merged.is_empty():
		merged = WorldState.plots.get(plot_id, {})
	var packed := _plot_detail_packed()
	if packed == null:
		show_feedback("Plot panel failed to load — see Godot Output", true)
		return
	var panel: Node = packed.instantiate()
	_mount_overlay(panel)
	if panel.has_method("open"):
		panel.call("open", plot_id, merged)


func _open_bazaar() -> void:
	_resume_plot_id = ""
	_build_return_plot_id = ""
	_mount_overlay(BazaarPanelScene.instantiate())


func open_operations_panel() -> void:
	_toggle_overlay(OperationsPanelScene)


func open_build_panel(plot_id: String, plot_data: Dictionary) -> void:
	_build_return_plot_id = plot_id
	_close_active_overlay()
	var panel: CanvasLayer = BuildPanelScene.instantiate() as CanvasLayer
	_mount_overlay(panel, false)
	if panel.has_method("open"):
		panel.call("open", plot_id, plot_data)
	if panel.has_signal("closed"):
		panel.closed.connect(_on_build_panel_closed, CONNECT_ONE_SHOT)


func _toggle_command_palette() -> void:
	if _command_palette == null:
		return
	if _command_palette.visible and _command_palette.has_method("close_palette"):
		_command_palette.call("close_palette")
	elif _command_palette.has_method("open_palette"):
		_command_palette.call("open_palette")


func open_blueprint_studio(on_created: Callable = Callable()) -> void:
	if is_instance_valid(_blueprint_studio):
		_blueprint_studio.queue_free()
		_blueprint_studio = null
	_blueprint_studio = BlueprintStudioScene.instantiate() as CanvasLayer
	add_child(_blueprint_studio)
	if on_created.is_valid() and _blueprint_studio.has_signal("blueprint_created"):
		_blueprint_studio.blueprint_created.connect(on_created)
	if _blueprint_studio.has_signal("closed"):
		_blueprint_studio.closed.connect(func() -> void: _blueprint_studio = null)


func open_building_hub(plot_id: String, building: Dictionary, plot_data: Dictionary) -> void:
	open_production_workflow(plot_id, building, plot_data)


func open_production_workflow(plot_id: String, building: Dictionary, plot_data: Dictionary) -> void:
	WorldState.ensure_recipes_catalog(
		func() -> void:
			_open_production_workflow_window(plot_id, building, plot_data)
	)
	if WorldState.blueprints_by_id.is_empty():
		API.get_blueprints(
			func(d: Dictionary) -> void:
				WorldState.merge_blueprints_list(d.get("blueprints", []))
				if is_instance_valid(_production_workflow) and _production_workflow.has_method("open"):
					_production_workflow.call("open", plot_id, building, plot_data),
			WorldState.party_id,
		)


func _open_production_workflow_window(
	plot_id: String, building: Dictionary, plot_data: Dictionary
) -> void:
	if is_instance_valid(_production_workflow):
		if _production_workflow.has_method("close"):
			_production_workflow.call("close")
		else:
			_production_workflow.queue_free()
		_production_workflow = null
	var win: CanvasLayer = ProductionWorkflowScene.instantiate() as CanvasLayer
	_production_workflow = win
	add_child(win)
	win.layer = 45
	if win.has_method("open"):
		win.call("open", plot_id, building, plot_data)
	if win.has_signal("closed"):
		win.closed.connect(_on_production_workflow_closed, CONNECT_ONE_SHOT)


func _on_production_workflow_closed() -> void:
	_production_workflow = null
	API.get_world_player(func(p): WorldState.apply_player(p), WorldState.party_id)


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
	_wire_territory_panel_signals(node)
	add_child(node)
	node.tree_exited.connect(_on_overlay_tree_exited.bind(node), CONNECT_ONE_SHOT)


func _wire_territory_panel_signals(node: Node) -> void:
	if node.has_signal("plot_selected") and not node.is_connected("plot_selected", _on_territory_plot_selected):
		node.plot_selected.connect(_on_territory_plot_selected)
	if node.has_signal("plot_locate_requested") and not node.is_connected(
		"plot_locate_requested", _on_territory_plot_locate
	):
		node.plot_locate_requested.connect(_on_territory_plot_locate)


func _on_territory_plot_selected(plot_id: String, _plot_data: Dictionary) -> void:
	_open_plot_detail(plot_id)


func _on_territory_plot_locate(plot_id: String) -> void:
	_close_active_overlay()
	focus_plot_on_map(plot_id)


func focus_plot_on_map(plot_id: String) -> void:
	if world_map.has_method("focus_plot"):
		world_map.call("focus_plot", plot_id)


func _on_overlay_tree_exited(node: Node) -> void:
	if _active_overlay == node:
		_active_overlay = null
	var path: String = node.scene_file_path
	if path == PLOT_DETAIL_SCENE_PATH:
		if _build_return_plot_id == "":
			_resume_plot_id = ""
		return
	if path == BuildPanelScene.resource_path:
		return
	if path == BazaarPanelScene.resource_path:
		_resume_plot_id = ""
