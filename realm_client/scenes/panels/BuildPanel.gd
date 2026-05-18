extends CanvasLayer
## Full-screen build UI — blueprint sidebar, plot grid, detail column.

signal closed

@onready var back_btn: Button = %BackBtn
@onready var plot_title: Label = %PlotTitle
@onready var sidebar: VBoxContainer = %BlueprintSidebar
@onready var grid_view: Control = %PlotGridView
@onready var detail_panel: PanelContainer = %BlueprintDetail

var _plot_id: String = ""
var _plot_data: Dictionary = {}
var _selected_blueprint_id: String = ""
var _build_mode: String = "turnkey"


func _ready() -> void:
	layer = 40
	set_process_unhandled_input(true)
	back_btn.pressed.connect(_close)
	if sidebar.has_signal("blueprint_selected"):
		sidebar.blueprint_selected.connect(_on_blueprint_selected)
	if sidebar.has_signal("plot_layout_changed"):
		sidebar.plot_layout_changed.connect(_refresh_plot_data)
	if grid_view.has_signal("cell_clicked"):
		grid_view.cell_clicked.connect(_on_cell_clicked)
	if detail_panel.has_signal("build_mode_changed"):
		detail_panel.build_mode_changed.connect(func(m: String) -> void: _build_mode = m)
	_apply_theme()


func _apply_theme() -> void:
	var bg := get_node_or_null("DimBackground")
	if bg is ColorRect:
		(bg as ColorRect).color = Color(0.04, 0.04, 0.06, 0.92)


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
	var tlabel: String = terrain.replace("_", " ").capitalize()
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
		sidebar.call("load_blueprints", terrain)
	_refresh_plot_data()


func _refresh_plot_data() -> void:
	_plot_data = WorldState.get_plot_ui(_plot_id)
	if _plot_data.is_empty():
		_plot_data = WorldState.plots.get(_plot_id, {}).duplicate(true)
	API.get_plot_grid(_plot_id, _on_grid_loaded)
	API.get_plot_value(_plot_id, _on_value_loaded)
	API.get_plot_sub_plots(_plot_id, _on_subplots_loaded)


func _on_grid_loaded(data: Dictionary) -> void:
	_plot_data["placed_buildings"] = data.get("placed_buildings", [])
	_plot_data["grid"] = data
	_plot_data["grid_cells_w"] = int(data.get("grid_cells_w", 10))
	_plot_data["grid_cells_h"] = int(data.get("grid_cells_h", 10))
	_plot_data["world_tiles_w"] = int(data.get("world_tiles_w", 1))
	_plot_data["world_tiles_h"] = int(data.get("world_tiles_h", 1))
	_plot_data["area_sq_metres"] = int(data.get("area_sq_metres", 10_000))
	if grid_view.has_method("load_plot"):
		grid_view.call("load_plot", _plot_id, _plot_data)
	var free_cells := int(data.get("free_cells_count", 100))
	if detail_panel.has_method("set_market_context"):
		detail_panel.call("set_market_context", int(_plot_data.get("fair_value_cents", 0)), free_cells)


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
	_selected_blueprint_id = blueprint_id
	if grid_view.has_method("set_placing_blueprint"):
		grid_view.call("set_placing_blueprint", blueprint_id, bp_data)
	if detail_panel.has_method("show_blueprint"):
		detail_panel.call("show_blueprint", bp_data)


func _on_cell_clicked(gx: int, gy: int) -> void:
	if _selected_blueprint_id.is_empty():
		return
	_confirm_placement(gx, gy)


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
