extends VBoxContainer
## Per-building recipe start/stop UI (embedded in PlotDetail).

@onready var title_label: Label = %TitleLabel
@onready var recipe_selector: OptionButton = %RecipeSelector
@onready var substitution_note: Label = %SubstitutionNote
@onready var cluster_label: Label = %ClusterLabel
@onready var run_mode_btn: Button = %RunModeBtn
@onready var status_icon: Label = %StatusIcon
@onready var status_label: Label = %StatusLabel
@onready var progress_bar: ProgressBar = %ProgressBar
@onready var start_btn: Button = %StartBtn
@onready var stop_btn: Button = %StopBtn
@onready var buy_inputs_btn: Button = %BuyInputsBtn
@onready var auto_list_toggle: CheckButton = %AutoListToggle
@onready var margin_spinbox: SpinBox = %MarginSpinBox

var _plot_id: String = ""
var _building: Dictionary = {}
var _terrain: String = "plains"
var _run_continuous: bool = false


func _ready() -> void:
	_apply_local_theme()
	start_btn.pressed.connect(_on_start)
	stop_btn.pressed.connect(_on_stop)
	buy_inputs_btn.pressed.connect(_on_buy_inputs)
	run_mode_btn.pressed.connect(_toggle_run_mode)
	auto_list_toggle.toggled.connect(_on_auto_list_toggle)
	run_mode_btn.text = "One-shot"
	recipe_selector.item_selected.connect(func(_i: int) -> void:
		_refresh_status()
		_refresh_recipe_hints()
	)
	margin_spinbox.min_value = 10
	margin_spinbox.max_value = 100
	margin_spinbox.value = 30
	margin_spinbox.editable = false
	margin_spinbox.tooltip_text = "Listing margin is fixed server-side for now."
	WorldState.world_updated.connect(_on_world_refreshed)
	# Active production countdown comes from /world/player on the tick.
	WorldState.player_updated.connect(_on_world_refreshed)
	WS.tick_event.connect(_on_ws_tick)


func _exit_tree() -> void:
	if WorldState.world_updated.is_connected(_on_world_refreshed):
		WorldState.world_updated.disconnect(_on_world_refreshed)
	if WorldState.player_updated.is_connected(_on_world_refreshed):
		WorldState.player_updated.disconnect(_on_world_refreshed)
	if WS.tick_event.is_connected(_on_ws_tick):
		WS.tick_event.disconnect(_on_ws_tick)


func _apply_local_theme() -> void:
	title_label.add_theme_color_override("font_color", Color(0.9, 0.88, 0.82))
	_style_btn(start_btn)
	_style_btn(stop_btn)
	_style_btn(buy_inputs_btn)
	_style_btn(run_mode_btn)


func _style_btn(btn: Button) -> void:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.12, 0.12, 0.14)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.55)
	btn.add_theme_stylebox_override("normal", sb)
	var h := sb.duplicate()
	h.border_color = Color(0.95, 0.82, 0.35)
	btn.add_theme_stylebox_override("hover", h as StyleBoxFlat)
	btn.add_theme_color_override("font_color", Color(0.9, 0.88, 0.82))


func setup(plot_id: String, building: Dictionary, terrain: String) -> void:
	_plot_id = plot_id
	_building = building.duplicate(true)
	_terrain = terrain
	auto_list_toggle.set_pressed_no_signal(bool(_building.get("auto_list_output", false)))
	_populate_recipes()
	_on_world_refreshed()
	_refresh_recipe_hints()


func _building_id() -> String:
	return str(_building.get("building_id", ""))


func _populate_recipes() -> void:
	recipe_selector.clear()
	var bid := _building_id()
	var plot_recipes: Array = []
	var pd: Dictionary = WorldState.plots.get(_plot_id, {})
	var pr: Variant = pd.get("recipe_ids", [])
	if pr is Array:
		plot_recipes = pr
	var idx := 0
	for r in WorldState.recipes:
		if not (r is Dictionary):
			continue
		var row: Dictionary = r
		if str(row.get("requires_building_id", "")) != bid:
			continue
		var rid := str(row.get("id", ""))
		if not plot_recipes.is_empty() and not (rid in plot_recipes):
			continue
		var label := str(row.get("display_name", rid))
		recipe_selector.add_item(label)
		recipe_selector.set_item_metadata(idx, rid)
		idx += 1
	if idx == 0:
		recipe_selector.add_item("No recipes available")
		recipe_selector.set_item_metadata(0, "")
		recipe_selector.disabled = true
	else:
		recipe_selector.disabled = false


func _selected_recipe_id() -> String:
	var i := recipe_selector.selected
	if i < 0:
		return ""
	return str(recipe_selector.get_item_metadata(i))


func _recipe_row(rid: String) -> Dictionary:
	return WorldState.recipe_by_id(rid)


func _on_world_refreshed() -> void:
	var ui: Dictionary = WorldState.get_plot_ui(_plot_id)
	var inst: String = str(_building.get("instance_id", ""))
	for b in ui.get("buildings", []):
		if b is Dictionary and str((b as Dictionary).get("instance_id", "")) == inst:
			_building = (b as Dictionary).duplicate(true)
			auto_list_toggle.set_pressed_no_signal(bool(_building.get("auto_list_output", false)))
			break
	_refresh_status()


func _on_ws_tick(event: Dictionary) -> void:
	if str(event.get("kind", "")) == "production_done" and str(event.get("plot_id", "")) == _plot_id:
		_refresh_status()


func _refresh_status() -> void:
	var rid := _selected_recipe_id()
	if rid.is_empty() and recipe_selector.item_count > 0 and not recipe_selector.disabled:
		recipe_selector.select(0)
		rid = _selected_recipe_id()
	var run: Dictionary = WorldState.active_production_run_for_building(_plot_id, _building_id())
	if run.is_empty():
		_set_idle()
		return
	var ticks_left: int = int(run.get("ticks_remaining", 0))
	var active_rid := str(run.get("recipe_id", ""))
	if ticks_left <= 0:
		_set_idle()
		return
	_set_running(active_rid, ticks_left)


func _refresh_recipe_hints() -> void:
	var rid := _selected_recipe_id()
	var plot_data: Dictionary = WorldState.plots.get(_plot_id, {})
	var cluster_bonus := float(plot_data.get("cluster_bonus", 0.0))
	if cluster_bonus > 0.0:
		cluster_label.text = "🏭 Cluster bonus: +%d%% yield" % int(cluster_bonus * 100.0)
		cluster_label.modulate = Color(0.4, 1.0, 0.4)
		cluster_label.show()
	else:
		cluster_label.hide()
	if rid.is_empty():
		substitution_note.hide()
		return
	var row := _recipe_row(rid)
	var inputs: Variant = row.get("inputs", {})
	if not (inputs is Dictionary) or (inputs as Dictionary).is_empty():
		substitution_note.hide()
		return
	var show_sub := false
	for mat in (inputs as Dictionary).keys():
		var mid := str(mat)
		var need := int((inputs as Dictionary)[mat])
		if WorldState.player_has_material(mid, need):
			continue
		if WorldState.player_has_substitute(rid, mid):
			show_sub = true
			break
	if show_sub:
		substitution_note.text = "⚡ Will use substitute input"
		substitution_note.modulate = Color(1.0, 0.85, 0.2)
		substitution_note.show()
	else:
		substitution_note.hide()


func _set_idle() -> void:
	status_icon.text = "⏸"
	status_label.text = "Idle"
	status_label.modulate = Color(0.7, 0.7, 0.7)
	progress_bar.value = 0.0
	start_btn.show()
	start_btn.disabled = recipe_selector.disabled
	stop_btn.hide()
	buy_inputs_btn.hide()


func _set_running(recipe_id: String, ticks_remaining: int) -> void:
	var row := _recipe_row(recipe_id)
	var recipe_label := str(row.get("display_name", recipe_id))
	status_icon.text = "⚙"
	status_label.text = "Running: %s — %s left" % [
		recipe_label,
		WorldState.format_ticks_as_gametime(ticks_remaining),
	]
	status_label.modulate = Color(0.4, 1.0, 0.4)
	var dur: int = int(row.get("duration_ticks", maxi(1, ticks_remaining)))
	progress_bar.max_value = 100.0
	var done_pct := 100.0 * (1.0 - float(ticks_remaining) / float(maxi(1, dur)))
	progress_bar.value = clampf(done_pct, 0.0, 100.0)
	start_btn.hide()
	stop_btn.show()
	stop_btn.disabled = true
	stop_btn.tooltip_text = "Stopping a run is not exposed on the API yet."
	buy_inputs_btn.hide()


func _set_stalled(reason: String) -> void:
	status_icon.text = "⚠"
	status_label.text = "Cannot start: %s" % reason
	status_label.modulate = Color(1.0, 0.5, 0.2)
	start_btn.show()
	start_btn.disabled = false
	stop_btn.hide()
	buy_inputs_btn.show()


func _toggle_run_mode() -> void:
	_run_continuous = not _run_continuous
	run_mode_btn.text = "Continuous" if _run_continuous else "One-shot"
	run_mode_btn.modulate = Color(0.4, 1.0, 0.4) if _run_continuous else Color.WHITE


func _on_start() -> void:
	var rid := _selected_recipe_id()
	if rid.is_empty():
		return
	var run_count := -1 if _run_continuous else 1
	start_btn.disabled = true
	API.start_production(
		_plot_id,
		rid,
		run_count,
		func(data: Dictionary) -> void:
			start_btn.disabled = false
			if bool(data.get("ok", false)):
				API.get_world_player(func(p): WorldState.apply_player(p), WorldState.party_id)
				_refresh_status()
			else:
				_set_stalled(str(data.get("reason", "Failed to start")))
	)


func _on_stop() -> void:
	pass


func _on_buy_inputs() -> void:
	var rid := _selected_recipe_id()
	if rid.is_empty():
		return
	var row := _recipe_row(rid)
	var inputs: Variant = row.get("inputs", {})
	if not (inputs is Dictionary):
		return
	for mat in (inputs as Dictionary).keys():
		var mid := str(mat)
		if mid == "electricity":
			continue
		var qty: int = int(inputs[mid])
		API.market_buy(mid, qty, 0, func(_d: Dictionary) -> void: pass, WorldState.party_id, 99_999_999)
	status_label.text = "Buying inputs…"


func _on_auto_list_toggle(on: bool) -> void:
	var instance_id: String = str(_building.get("instance_id", ""))
	if instance_id.is_empty():
		return
	API.post_building_auto_list(instance_id, on, func(_d: Dictionary) -> void: pass)

