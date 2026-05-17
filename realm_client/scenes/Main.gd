extends Node2D
## Solo shell — map in SubViewport; one exclusive overlay panel at a time.

const PlotDetailScene := preload("res://scenes/panels/PlotDetail.tscn")
const BazaarPanelScene := preload("res://scenes/panels/BazaarPanel.tscn")
const BuildPanelScene := preload("res://scenes/panels/BuildPanel.tscn")

const OVERLAY_LAYER := 32

@onready var ui_root: Control = $UILayer/UIRoot
@onready var map_viewport: SubViewportContainer = $UILayer/UIRoot/MapViewport
@onready var sub_viewport: SubViewport = $UILayer/UIRoot/MapViewport/SubViewport
@onready var world_map: Node2D = $UILayer/UIRoot/MapViewport/SubViewport/WorldMap
@onready var shell: CanvasLayer = $CommandShell
@onready var sidebar: PanelContainer = $UILayer/UIRoot/TerritorySidebar

var _active_overlay: Node = null
var _resume_plot_id: String = ""
var _build_return_plot_id: String = ""


func _ready() -> void:
	RenderingServer.set_default_clear_color(RealmColors.BG)
	ui_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	map_viewport.mouse_filter = Control.MOUSE_FILTER_STOP
	sub_viewport.handle_input_locally = true
	shell.nav_pressed.connect(_on_nav_pressed)
	world_map.plot_clicked.connect(_on_plot_clicked)
	get_viewport().size_changed.connect(_layout_shell)
	call_deferred("_boot_shell")
	var timer := Timer.new()
	timer.wait_time = 2.0
	timer.autostart = true
	timer.timeout.connect(_auto_tick)
	add_child(timer)


func _boot_shell() -> void:
	await get_tree().process_frame
	await get_tree().process_frame
	_layout_shell()
	_refresh_shell_hud()
	_refresh_from_server()


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


## Sync top strip to ``WorldState`` without inventing money/ticks (demo fudge hid dead API calls).
func _refresh_shell_hud() -> void:
	if shell.has_method("_refresh_stats"):
		shell.call("_refresh_stats")
	if shell.has_method("_refresh_seed"):
		shell.call("_refresh_seed")


func _auto_tick() -> void:
	API.tick_once(
		func(data: Dictionary) -> void:
			if bool(data.get("ok", false)):
				var tv: Variant = data.get("tick", null)
				if tv != null:
					WorldState.apply_engine_tick_hint(int(tv))
			else:
				push_warning("Realm: POST /tick missing ok — HUD refresh still runs (%s)" % str(data))
			_refresh_from_server()
			if shell.has_method("flash_tick"):
				shell.call("flash_tick")
	)


func _refresh_from_server() -> void:
	API.get_world_summary(WorldState.party_id, func(s): WorldState.apply_summary(s))
	API.get_world(func(w): WorldState.apply_world(w))


func _on_nav_pressed(panel_name: String) -> void:
	if panel_name == "market":
		if _is_overlay(BazaarPanelScene):
			_close_active_overlay()
		else:
			_open_bazaar()
		return
	if panel_name == "territory":
		return
	push_warning("Panel '%s' not implemented yet" % panel_name)


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
		API.get_world(func(w): WorldState.apply_world(w))
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
