extends CanvasLayer
## Full-screen build UI — blueprint sidebar, plot grid, detail column.

signal closed

@onready var back_btn: Button = %BackBtn
@onready var plot_title: Label = %PlotTitle
@onready var sidebar: VBoxContainer = %BlueprintSidebar
@onready var grid_view: Control = %PlotGridView
@onready var detail_panel: PanelContainer = %BlueprintDetail
@onready var mode_buildings_btn: Button = %ModeBuildingsBtn
@onready var mode_roads_btn: Button = %ModeRoadsBtn
@onready var columns: HBoxContainer = %Columns
@onready var root_panel: PanelContainer = %Root

var _plot_id: String = ""
var _plot_data: Dictionary = {}
var _selected_blueprint_id: String = ""
var _build_mode: String = "turnkey"

const ROAD_BLUEPRINT_ID := "road_segment"
const ROAD_BLUEPRINT_FALLBACK: Dictionary = {
	"blueprint_id": "road_segment",
	"footprint_w": 1,
	"footprint_h": 1,
	"name": "Road segment",
}


func _ready() -> void:
	layer = 40
	set_process_unhandled_input(true)
	if back_btn == null or grid_view == null:
		push_error("BuildPanel: scene nodes missing — check BuildPanel.tscn")
		return
	back_btn.pressed.connect(_close)
	if sidebar.has_signal("blueprint_selected"):
		sidebar.blueprint_selected.connect(_on_blueprint_selected)
	if sidebar.has_signal("plot_layout_changed"):
		sidebar.plot_layout_changed.connect(_refresh_plot_data)
	if grid_view.has_signal("cell_clicked"):
		grid_view.cell_clicked.connect(_on_cell_clicked)
	if grid_view.has_signal("road_path_painted"):
		grid_view.road_path_painted.connect(_on_road_path_painted)
	if grid_view.has_signal("world_link_clicked"):
		grid_view.world_link_clicked.connect(_on_world_link_clicked)
	if mode_buildings_btn and mode_roads_btn:
		var mode_group := ButtonGroup.new()
		mode_group.allow_unpress = false
		mode_buildings_btn.button_group = mode_group
		mode_roads_btn.button_group = mode_group
		mode_buildings_btn.pressed.connect(func() -> void: _set_build_mode("building"))
		mode_roads_btn.pressed.connect(func() -> void: _set_build_mode("roads"))
	if detail_panel.has_signal("build_mode_changed"):
		detail_panel.build_mode_changed.connect(func(m: String) -> void: _build_mode = m)
	_apply_theme()


func _apply_theme() -> void:
	var bg := get_node_or_null("DimBackground")
	if bg is ColorRect:
		(bg as ColorRect).color = Color(0.04, 0.04, 0.06, 0.92)
	if root_panel:
		var panel_sb := StyleBoxFlat.new()
		panel_sb.bg_color = Color(0.07, 0.07, 0.09, 0.96)
		panel_sb.set_border_width_all(1)
		panel_sb.border_color = Color(0.85, 0.72, 0.2, 0.35)
		panel_sb.set_corner_radius_all(6)
		panel_sb.set_content_margin_all(12)
		root_panel.add_theme_stylebox_override("panel", panel_sb)
	for btn in [mode_buildings_btn, mode_roads_btn]:
		if btn == null:
			continue
		var sb := StyleBoxFlat.new()
		sb.bg_color = Color(0.12, 0.12, 0.14)
		sb.set_corner_radius_all(4)
		btn.add_theme_stylebox_override("normal", sb)
		var pressed := sb.duplicate() as StyleBoxFlat
		pressed.bg_color = Color(0.22, 0.20, 0.12)
		pressed.border_color = Color(0.85, 0.72, 0.2, 0.8)
		pressed.set_border_width_all(1)
		btn.add_theme_stylebox_override("pressed", pressed)
		btn.add_theme_stylebox_override("hover", pressed)


func blocks_pause_menu() -> bool:
	return grid_view.has_method("is_confirming") and bool(grid_view.call("is_confirming"))


func _unhandled_input(event: InputEvent) -> void:
	# Keys while a sidebar button still has focus — grid ``_gui_input`` never sees them.
	if not grid_view.has_method("is_confirming") or not grid_view.call("is_confirming"):
		return
	if not (event is InputEventKey and event.pressed and not event.echo):
		return
	var key := event as InputEventKey
	if grid_view.has_method("key_confirms") and grid_view.call("key_confirms", key):
		grid_view.call("finish_confirm", true)
		get_viewport().set_input_as_handled()
	elif grid_view.has_method("key_cancels") and grid_view.call("key_cancels", key):
		grid_view.call("finish_confirm", false)
		get_viewport().set_input_as_handled()


func open(plot_id: String, plot_data: Dictionary) -> void:
	_plot_id = plot_id
	_plot_data = plot_data.duplicate(true)
	var terrain: String = str(plot_data.get("terrain", "plains"))
	var is_coastal: bool = bool(plot_data.get("is_coastal", false))
	var tlabel: String = terrain.replace("_", " ").capitalize()
	if is_coastal:
		tlabel += " · Coastal"
	var area_m := int(plot_data.get("area_sq_metres", 10_000))
	var ha := float(area_m) / 10000.0
	var tile_n := int(plot_data.get("world_tile_count", 0))
	if tile_n < 1:
		var wc: Variant = plot_data.get("world_cells", [])
		if wc is Array:
			tile_n = (wc as Array).size()
	var size_lbl := "%d m² (%.1f ha)" % [area_m, ha]
	if tile_n > 1:
		size_lbl += " · %d tiles" % tile_n
	plot_title.text = "Build on Plot %s  ·  %s  ·  %s" % [plot_id, tlabel, size_lbl]
	if sidebar.has_method("set_plot_id"):
		sidebar.call("set_plot_id", plot_id)
	if sidebar.has_method("load_blueprints"):
		sidebar.call("load_blueprints", terrain, is_coastal)
	_set_build_mode("building")
	_refresh_plot_data()


func _set_build_mode(mode: String) -> void:
	if grid_view.has_method("set_interaction_mode"):
		grid_view.call("set_interaction_mode", mode)
	var roads_on := mode == "roads"
	if mode_buildings_btn:
		mode_buildings_btn.button_pressed = not roads_on
	if mode_roads_btn:
		mode_roads_btn.button_pressed = roads_on
	if sidebar:
		sidebar.visible = not roads_on
	if roads_on:
		_enable_road_paint()
		if grid_view is Control:
			(grid_view as Control).grab_focus()
	elif not roads_on:
		_selected_blueprint_id = ""
		if grid_view.has_method("set_placing_blueprint"):
			grid_view.call("set_placing_blueprint", "", {})


func _refresh_plot_data() -> void:
	_plot_data = WorldState.get_plot_ui(_plot_id)
	if _plot_data.is_empty():
		_plot_data = WorldState.plots.get(_plot_id, {}).duplicate(true)
	API.get_plot_grid(_plot_id, _on_grid_loaded)
	API.get_plot_value(_plot_id, _on_value_loaded)
	API.get_plot_sub_plots(_plot_id, _on_subplots_loaded)


func _on_grid_loaded(data: Dictionary) -> void:
	if data.has("is_coastal"):
		_plot_data["is_coastal"] = bool(data.get("is_coastal", false))
		var terrain_s := str(_plot_data.get("terrain", "plains"))
		if sidebar.has_method("load_blueprints"):
			sidebar.call("load_blueprints", terrain_s, _plot_data["is_coastal"])
	_plot_data["placed_buildings"] = data.get("placed_buildings", [])
	_plot_data["grid"] = data
	_plot_data["grid_cells_w"] = int(data.get("grid_cells_w", 10))
	_plot_data["grid_cells_h"] = int(data.get("grid_cells_h", 10))
	_plot_data["world_tiles_w"] = int(data.get("world_tiles_w", 1))
	_plot_data["world_tiles_h"] = int(data.get("world_tiles_h", 1))
	_plot_data["area_sq_metres"] = int(data.get("area_sq_metres", 10_000))
	_ensure_plot_geometry_on_grid_data(data)
	if grid_view.has_method("load_plot"):
		grid_view.call("load_plot", _plot_id, _plot_data)
	if _interaction_mode_roads():
		_enable_road_paint()
		if detail_panel.has_method("show_roads_context"):
			detail_panel.call("show_roads_context", data)
	var free_cells := int(data.get("free_cells_count", 100))
	if detail_panel.has_method("set_market_context"):
		detail_panel.call("set_market_context", int(_plot_data.get("fair_value_cents", 0)), free_cells)
	if detail_panel.has_method("set_cluster_context"):
		detail_panel.call("set_cluster_context", _plot_data)


func _on_value_loaded(data: Dictionary) -> void:
	_plot_data["market"] = data
	_plot_data["fair_value_cents"] = data.get("fair_value_cents", 0)
	if detail_panel.has_method("set_market_context"):
		detail_panel.call(
			"set_market_context",
			int(data.get("fair_value_cents", 0)),
			int(_plot_data.get("grid", {}).get("free_cells_count", 100)),
		)


func _on_subplots_loaded(data: Dictionary) -> void:
	_plot_data["sub_plots"] = data.get("sub_plots", [])
	if grid_view.has_method("load_plot"):
		grid_view.call("load_plot", _plot_id, _plot_data)


func _on_blueprint_selected(blueprint_id: String, bp_data: Dictionary) -> void:
	if _interaction_mode_roads():
		# Roads tab drives paint mode; sidebar is hidden — ignore selection echoes.
		return
	if blueprint_id == ROAD_BLUEPRINT_ID:
		_activate_road_paint(bp_data)
		return
	_selected_blueprint_id = blueprint_id
	if grid_view.has_method("set_placing_blueprint"):
		grid_view.call("set_placing_blueprint", blueprint_id, bp_data)
	if detail_panel.has_method("show_blueprint"):
		detail_panel.call("show_blueprint", bp_data)


func _activate_road_paint(bp_data: Dictionary) -> void:
	_selected_blueprint_id = ROAD_BLUEPRINT_ID
	var rd: Dictionary = bp_data if not bp_data.is_empty() else ROAD_BLUEPRINT_FALLBACK
	if grid_view.has_method("set_placing_blueprint"):
		grid_view.call("set_placing_blueprint", ROAD_BLUEPRINT_ID, rd)
	# Do not call sidebar.select_blueprint_id here — it re-emits blueprint_selected
	# and causes infinite recursion when the Roads tab enables paint mode.
	var grid: Dictionary = _plot_data.get("grid", {})
	if detail_panel.has_method("show_roads_context"):
		detail_panel.call("show_roads_context", grid)
	if grid_view is Control:
		(grid_view as Control).grab_focus()


func _on_cell_clicked(gx: int, gy: int) -> void:
	if _selected_blueprint_id.is_empty():
		return
	if grid_view.has_method("can_place_at") and not grid_view.call("can_place_at", gx, gy):
		if grid_view.has_method("show_error"):
			var msg := "Must be placed on the waterfront (blue cells touching water)"
			grid_view.call("show_error", msg)
		return
	_confirm_placement(gx, gy)


func _on_road_path_painted(cells: Array) -> void:
	_place_road_cells(cells)


func _ensure_plot_geometry_on_grid_data(grid: Dictionary) -> void:
	for key in ["world_cells", "x", "y", "parcel_shape"]:
		if not _plot_data.has(key) or _plot_data.get(key) == null:
			var ui := WorldState.get_plot_ui(_plot_id)
			if ui.has(key):
				_plot_data[key] = ui[key]
	for key in ["world_tiles_w", "world_tiles_h", "grid_cells_w", "grid_cells_h", "area_sq_metres"]:
		if grid.has(key):
			_plot_data[key] = grid[key]


func _interaction_mode_roads() -> bool:
	return mode_roads_btn != null and mode_roads_btn.button_pressed


func _enable_road_paint() -> void:
	_activate_road_paint(ROAD_BLUEPRINT_FALLBACK)


func _place_road_cells(cells: Array) -> void:
	if cells.is_empty():
		return
	API.place_road_path(
		_plot_id,
		cells,
		_build_mode,
		func(data: Dictionary) -> void:
			if bool(data.get("ok", false)):
				var n := int(data.get("placed_count", cells.size()))
				_refresh_plot_data()
				MainFeedback.toast("Road placed (%d cells)" % n, false)
				API.get_world_player(func(p): WorldState.apply_player(p), WorldState.party_id)
				API.get_world_summary(WorldState.party_id, func(s): WorldState.apply_summary(s))
			else:
				var placed := int(data.get("placed_count", 0))
				var msg := str(data.get("reason", "Road placement failed"))
				if placed > 0:
					msg += " (%d placed before stop)" % placed
					_refresh_plot_data()
				_show_placement_failed(msg),
	)


func _on_world_link_clicked(neighbor_plot_id: String) -> void:
	if neighbor_plot_id.is_empty():
		return
	API.build_road(
		_plot_id,
		neighbor_plot_id,
		func(data: Dictionary) -> void:
			if bool(data.get("ok", false)):
				_refresh_plot_data()
				API.get_world_player(func(p): WorldState.apply_player(p), WorldState.party_id)
				API.get_world_map(func(m): WorldState.apply_map(m))
				API.get_roads(func(r):
					var segs: Variant = r.get("segments", [])
					if segs is Array:
						WorldState.road_segments = segs as Array
				)
				MainFeedback.toast("World road built to %s" % neighbor_plot_id, false)
			else:
				_show_placement_failed(str(data.get("reason", "World road build failed"))),
	)


func _confirm_placement(gx: int, gy: int) -> void:
	if not detail_panel.has_method("get"):
		pass
	var bp: Dictionary = detail_panel.current_blueprint if "current_blueprint" in detail_panel else {}
	if bp.is_empty():
		return
	if not grid_view.has_method("show_confirm"):
		return
	grid_view.call(
		"show_confirm",
		gx,
		gy,
		func(confirmed: bool) -> void:
			if not confirmed:
				return
			API.place_blueprint(
				_plot_id,
				_selected_blueprint_id,
				gx,
				gy,
				_build_mode,
				func(data: Dictionary) -> void:
					if bool(data.get("ok", false)):
						_refresh_plot_data()
						API.get_world_summary(WorldState.party_id, func(s): WorldState.apply_summary(s))
						# Placing a building mutates owned-plot state + map
						# (powered flag may flip). Refresh both lean payloads.
						API.get_world_player(func(p): WorldState.apply_player(p), WorldState.party_id)
						API.get_world_map(func(m): WorldState.apply_map(m))
					else:
						_show_placement_failed(str(data.get("reason", "Placement failed"))),
			),
	)


func _show_placement_failed(reason: String) -> void:
	var msg := reason.strip_edges()
	if msg.is_empty():
		msg = "Placement failed"
	MainFeedback.toast(msg, true)
	if detail_panel.has_method("show_placement_error"):
		detail_panel.call("show_placement_error", msg)
	if grid_view.has_method("show_error"):
		grid_view.call("show_error", msg)


func _close() -> void:
	closed.emit()
	queue_free()
