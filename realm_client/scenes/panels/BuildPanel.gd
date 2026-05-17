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


func open(plot_id: String, plot_data: Dictionary) -> void:
	_plot_id = plot_id
	_plot_data = plot_data.duplicate(true)
	var terrain: String = str(plot_data.get("terrain", "plains"))
	var tlabel: String = terrain.replace("_", " ").capitalize()
	plot_title.text = "Build on Plot %s  ·  %s  ·  100m × 100m" % [plot_id, tlabel]
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
						API.get_world(func(w): WorldState.apply_world(w))
					elif grid_view.has_method("show_error"):
						grid_view.call("show_error", str(data.get("reason", "Placement failed"))),
			),
	)


func _close() -> void:
	closed.emit()
	queue_free()
