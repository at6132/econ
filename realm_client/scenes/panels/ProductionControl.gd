extends VBoxContainer
## Per-building recipe start/stop UI (embedded in PlotDetail).

@onready var title_label: Label = %TitleLabel
@onready var recipe_selector: OptionButton = %RecipeSelector
var substitution_note: Label
var cluster_label: Label
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
var _throughput_label: Label
var _start_in_flight: bool = false
var _energy_info: Dictionary = {}
var _grid_info: Dictionary = {}
var _last_start_error: String = ""

# Mirror engine ``ROAD_REQUIREMENT_GRACE_TICKS`` / ``ROAD_EXEMPT_RECIPES``.
const ROAD_GRACE_TICKS: int = 43_200
const ROAD_EXEMPT_RECIPES: Array = [
	"hand_mine_coal", "hand_mine_ore", "hand_dig_clay", "hand_mine_sulfur", "hand_mine_tin",
	"fishing", "gather_herbs", "grow_grain", "coal_generator", "tidal_power",
]


func _ready() -> void:
	substitution_note = get_node_or_null("%SubstitutionNote") as Label
	cluster_label = get_node_or_null("%ClusterLabel") as Label
	if is_instance_valid(substitution_note):
		substitution_note.hide()
	if is_instance_valid(cluster_label):
		cluster_label.hide()
	if not is_instance_valid(start_btn) or not is_instance_valid(recipe_selector):
		push_error(
			"ProductionControl: missing required nodes — open ProductionControl.tscn "
			+ "and ensure %%StartBtn / %%RecipeSelector have Unique Name enabled."
		)
		return
	_apply_local_theme()
	start_btn.pressed.connect(_on_start)
	stop_btn.pressed.connect(_on_stop)
	buy_inputs_btn.pressed.connect(_on_buy_inputs)
	run_mode_btn.pressed.connect(_toggle_run_mode)
	auto_list_toggle.toggled.connect(_on_auto_list_toggle)
	run_mode_btn.text = "One-shot"
	_throughput_label = Label.new()
	_throughput_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_throughput_label.add_theme_font_size_override("font_size", 11)
	_throughput_label.add_theme_color_override("font_color", RealmColors.MUTED)
	_throughput_label.visible = false
	add_child(_throughput_label)
	recipe_selector.item_selected.connect(func(_i: int) -> void:
		_last_start_error = ""
		_refresh_status()
		_refresh_recipe_hints()
		_refresh_throughput()
	)
	margin_spinbox.min_value = 10
	margin_spinbox.max_value = 100
	margin_spinbox.value = 30
	margin_spinbox.editable = false
	margin_spinbox.tooltip_text = "Listing margin is fixed server-side for now."
	WorldState.world_updated.connect(_on_world_refreshed)
	WorldState.player_updated.connect(_on_world_refreshed)
	WorldState.recipes_updated.connect(_on_recipes_catalog_ready)
	WorldState.building_auto_list_changed.connect(_on_building_auto_list_changed)
	WS.tick_event.connect(_on_ws_tick)


func _exit_tree() -> void:
	if WorldState.world_updated.is_connected(_on_world_refreshed):
		WorldState.world_updated.disconnect(_on_world_refreshed)
	if WorldState.player_updated.is_connected(_on_world_refreshed):
		WorldState.player_updated.disconnect(_on_world_refreshed)
	if WorldState.recipes_updated.is_connected(_on_recipes_catalog_ready):
		WorldState.recipes_updated.disconnect(_on_recipes_catalog_ready)
	if WorldState.building_auto_list_changed.is_connected(_on_building_auto_list_changed):
		WorldState.building_auto_list_changed.disconnect(_on_building_auto_list_changed)
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
	_last_start_error = ""
	_energy_info = {}
	_grid_info = {}
	var bname := WorldState.building_display_name(_building)
	title_label.text = bname
	auto_list_toggle.set_pressed_no_signal(bool(_building.get("auto_list_output", false)))
	if WorldState.recipes.is_empty():
		recipe_selector.clear()
		recipe_selector.add_item("Loading recipe catalog…")
		recipe_selector.disabled = true
		WorldState.ensure_recipes_catalog(_on_recipes_catalog_ready)
	else:
		_apply_setup_refresh()


func _on_recipes_catalog_ready() -> void:
	if _plot_id.is_empty():
		return
	_apply_setup_refresh()


func _apply_setup_refresh() -> void:
	_populate_recipes()
	_fetch_plot_logistics()
	_on_world_refreshed()
	_refresh_recipe_hints()
	_refresh_throughput()
	_refresh_status()


func _building_id() -> String:
	return WorldState.workshop_id_for_building(_building)


func _populate_recipes() -> void:
	var previous_rid := _selected_recipe_id()
	recipe_selector.clear()
	var bid := _building_id()
	if bid.is_empty():
		recipe_selector.add_item("No recipes available")
		recipe_selector.set_item_metadata(0, "")
		recipe_selector.disabled = true
		return
	var idx := 0
	var skipped := 0
	for r in _recipes_for_this_building():
		if not (r is Dictionary):
			continue
		var row: Dictionary = r
		var rid := str(row.get("id", ""))
		if rid.is_empty() or not _recipe_listable_on_plot(rid):
			skipped += 1
			continue
		recipe_selector.add_item(str(row.get("display_name", rid)))
		recipe_selector.set_item_metadata(idx, rid)
		idx += 1
	if idx == 0:
		if WorldState.recipes.is_empty():
			recipe_selector.add_item("Recipe catalog not loaded — reopen in a moment")
		elif skipped > 0:
			recipe_selector.add_item(
				"No recipes for this plot — survey, terrain, or subsurface grades block the rest"
			)
		else:
			recipe_selector.add_item("No recipes for this building type")
		recipe_selector.set_item_metadata(0, "")
		recipe_selector.disabled = true
	else:
		recipe_selector.disabled = false
		if not previous_rid.is_empty() and _select_recipe_by_id(previous_rid):
			pass
		else:
			_ensure_runnable_recipe_selected()


func _index_for_recipe_id(recipe_id: String) -> int:
	if recipe_id.is_empty():
		return -1
	for i in recipe_selector.item_count:
		if str(recipe_selector.get_item_metadata(i)) == recipe_id:
			return i
	return -1


func _select_recipe_by_id(recipe_id: String) -> bool:
	var idx := _index_for_recipe_id(recipe_id)
	if idx < 0:
		return false
	recipe_selector.select(idx)
	return true


func _recipe_is_ready(recipe_id: String) -> bool:
	return not recipe_id.is_empty() and _production_blocker(recipe_id).is_empty()


func _first_ready_recipe_index() -> int:
	for i in recipe_selector.item_count:
		var rid := str(recipe_selector.get_item_metadata(i))
		if _recipe_is_ready(rid):
			return i
	return -1


func _ensure_runnable_recipe_selected() -> void:
	if recipe_selector.disabled or recipe_selector.item_count == 0:
		return
	var rid := _selected_recipe_id()
	if _recipe_is_ready(rid):
		return
	var fallback := _first_ready_recipe_index()
	if fallback >= 0:
		recipe_selector.select(fallback)


func _recipes_for_this_building() -> Array:
	return WorldState.recipes_for_workshop_building(_building)


func _recipe_row_in_array(rows: Array, recipe_id: String) -> bool:
	for r in rows:
		if r is Dictionary and str((r as Dictionary).get("id", "")) == recipe_id:
			return true
	return false


func _plot_recipe_ids() -> Array:
	var pd: Dictionary = WorldState.plots.get(_plot_id, {})
	var pr: Variant = pd.get("recipe_ids", [])
	return pr if pr is Array else []


func count_plot_listable_recipes() -> int:
	var n := 0
	for r in _recipes_for_this_building():
		if r is Dictionary and _recipe_listable_on_plot(str((r as Dictionary).get("id", ""))):
			n += 1
	return n


func _recipe_listable_on_plot(recipe_id: String) -> bool:
	## Hard plot/building eligibility — recipes that cannot run here are omitted from the picker.
	return _recipe_plot_gate_reason(recipe_id).is_empty()


func _recipe_plot_gate_reason(recipe_id: String) -> String:
	var pd: Dictionary = WorldState.get_plot_ui(_plot_id)
	if str(pd.get("owner", "")) != WorldState.party_id:
		return ""
	if not bool(pd.get("surveyed", false)):
		return "survey plot first"
	var plot_recipes := _plot_recipe_ids()
	if plot_recipes.is_empty():
		return ""
	if recipe_id in plot_recipes:
		return ""
	var done_at: int = int(_building.get("completes_at_tick", 0))
	if done_at > WorldState.current_tick:
		return "building under construction"
	var eff := int(_building.get("_efficiency_pct", 100))
	if eff <= 0:
		return "maintain building first"
	var sub_block := _subsurface_gate_reason(recipe_id)
	if not sub_block.is_empty():
		return sub_block
	var terr_block := _terrain_gate_reason(recipe_id)
	if not terr_block.is_empty():
		return terr_block
	return "not allowed on this plot (terrain or discovery)"


func _subsurface_gate_reason(recipe_id: String) -> String:
	var row := _recipe_row(recipe_id)
	var subs: Variant = row.get("requires_subsurface", [])
	if not (subs is Array) or (subs as Array).is_empty():
		return ""
	var grades: Dictionary = WorldState.subsurface_for_plot_ui(_plot_id, WorldState.get_plot_ui(_plot_id))
	for entry in subs as Array:
		if not (entry is Dictionary):
			continue
		var field := str((entry as Dictionary).get("field", ""))
		var need := float((entry as Dictionary).get("min", 0.3))
		var have := float(grades.get(field, 0.0))
		if have < need:
			var nice := field.replace("_grade", "").replace("_", " ")
			return "needs %s grade ≥ %d%% (have %d%%)" % [nice, int(need * 100.0), int(have * 100.0)]
	return ""


func _terrain_gate_reason(recipe_id: String) -> String:
	var allowed: Array = _terrain_allowed_for_recipe(recipe_id)
	if allowed.is_empty():
		return ""
	if _terrain in allowed:
		return ""
	var nice_allowed: PackedStringArray = PackedStringArray()
	for t in allowed:
		nice_allowed.append(str(t))
	return "needs %s terrain (this plot is %s)" % [", ".join(nice_allowed), _terrain]


func _terrain_allowed_for_recipe(recipe_id: String) -> Array:
	# Mirror engine ``RECIPE_ALLOWED_TERRAINS`` for strip-mine / foundry lines (client UX only).
	const TABLE: Dictionary = {
		"mine_iron_ore": ["mountain"],
		"mine_copper_ore": ["mountain"],
		"mine_coal": ["mountain", "desert", "plains", "forest", "tundra"],
		"dig_clay": ["plains", "forest", "swamp", "tundra"],
		"mine_phosphate": ["plains", "forest"],
		"mine_tin_ore": ["mountain", "plains"],
		"mine_lead_ore": ["mountain"],
		"mine_sulfur_ore": ["swamp", "tundra", "mountain", "plains"],
		"mine_saltpeter": ["desert", "plains"],
		"mine_raw_silica": ["desert", "plains", "mountain"],
		"smelt_iron": ["mountain"],
		"smelt_copper": ["mountain"],
		"steel_alloy": ["mountain"],
		"wire_draw": ["mountain", "plains"],
	}
	if TABLE.has(recipe_id):
		return TABLE[recipe_id] as Array
	return []


func _recipe_needs_mountain(recipe_id: String) -> bool:
	var mountain_only := [
		"smelt_iron", "smelt_copper", "steel_alloy", "mine_iron_ore", "mine_copper_ore",
	]
	return recipe_id in mountain_only


func selected_recipe_id() -> String:
	return _selected_recipe_id()


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
	_populate_recipes()
	_fetch_plot_logistics()
	_refresh_status()


func _fetch_plot_logistics() -> void:
	if _plot_id.is_empty():
		_energy_info = {}
		_grid_info = {}
		return
	API.get_plot_energy(_plot_id, _on_plot_energy_loaded)
	API.get_plot_grid(_plot_id, _on_plot_grid_loaded)


func _on_plot_energy_loaded(data: Dictionary) -> void:
	if not is_instance_valid(self):
		return
	_energy_info = data.duplicate(true) if not data.is_empty() else {}
	if is_inside_tree():
		_refresh_status()


func _on_plot_grid_loaded(data: Dictionary) -> void:
	if not is_instance_valid(self):
		return
	_grid_info = data.duplicate(true) if not data.is_empty() else {}
	if is_inside_tree():
		_refresh_status()


func _on_ws_tick(event: Dictionary) -> void:
	if str(event.get("kind", "")) == "production_done" and str(event.get("plot_id", "")) == _plot_id:
		_refresh_status()


func _refresh_status() -> void:
	if not _last_start_error.is_empty():
		_set_stalled(_last_start_error)
		return
	_ensure_runnable_recipe_selected()
	var rid := _selected_recipe_id()
	var run: Dictionary = WorldState.active_production_run_for_building(_plot_id, _building)
	if run.is_empty():
		var blocker := _production_blocker(rid)
		if blocker.is_empty():
			_set_idle_ready(rid)
		else:
			_set_blocked(blocker)
		return
	var ticks_left: int = int(run.get("ticks_remaining", 0))
	var active_rid := str(run.get("recipe_id", ""))
	if ticks_left <= 0:
		_set_idle_ready(rid)
		return
	_set_running(active_rid, ticks_left)


func _plot_ui() -> Dictionary:
	return WorldState.get_plot_ui(_plot_id)


func _production_blocker(recipe_id: String) -> String:
	var pd := _plot_ui()
	if str(pd.get("owner", "")) != WorldState.party_id:
		return "You do not own this plot"
	if not bool(pd.get("surveyed", false)):
		return "Survey the plot first (Plot detail → Survey this plot)"
	var done_at: int = int(_building.get("completes_at_tick", 0))
	if done_at > WorldState.current_tick:
		var eta := done_at - WorldState.current_tick
		return "Building still under construction — ready in %s" % WorldState.format_ticks_as_gametime(eta)
	var eff := int(_building.get("_efficiency_pct", 100))
	if eff <= 0:
		return "Building stopped — use Maintain on this building first"
	if WorldState.recipes.is_empty():
		return "Recipe catalog still loading from server"
	if recipe_selector.disabled or recipe_id.is_empty():
		return _empty_recipe_hint()
	var gate := _recipe_plot_gate_reason(recipe_id)
	if not gate.is_empty():
		return gate.capitalize()
	if recipe_id.is_empty():
		return "Select a recipe"
	var energy := _energy_blocker(recipe_id)
	if not energy.is_empty():
		return energy
	var road := _road_blocker(recipe_id)
	if not road.is_empty():
		return road
	return _missing_inputs_reason(recipe_id)


func _energy_power_view() -> Dictionary:
	if _energy_info.get("power") is Dictionary:
		return _energy_info["power"] as Dictionary
	return _energy_info


func _energy_blocker(recipe_id: String) -> String:
	var row := _recipe_row(recipe_id)
	var inputs: Variant = row.get("inputs", {})
	if not (inputs is Dictionary) or int((inputs as Dictionary).get("electricity", 0)) <= 0:
		return ""
	# Same source as Plot detail Energy (``GET /plots/{id}/energy``), not map ``powered``
	# which historically meant road-linked grid only and skipped on-plot microgrids.
	if not _energy_info.is_empty():
		var pw := _energy_power_view()
		if bool(_energy_info.get("may_draw_grid_energy", pw.get("powered", false))):
			if bool(pw.get("brownout", false)):
				return "Grid brownout — demand exceeds capacity; add generation or wait"
			return ""
		var reason := str(_energy_info.get("block_reason", pw.get("reason", "")))
		if not reason.is_empty():
			return reason
		return "No grid capacity for this recipe — sign a utility contract or build a generator"
	if bool(_plot_ui().get("powered", false)):
		return ""
	return ""


func _road_blocker(recipe_id: String) -> String:
	if WorldState.current_tick < ROAD_GRACE_TICKS:
		return ""
	if recipe_id in ROAD_EXEMPT_RECIPES:
		return ""
	if not _grid_info.is_empty():
		if bool(_grid_info.get("road_accessible", false)):
			return ""
		if bool(_grid_info.get("site_roads_connect_workshops", false)):
			return ""
		if bool(_grid_info.get("site_roads_link_world", false)):
			return ""
		return (
			"No road access — route site roads beside each workshop (Build → Roads) "
			+ "or link this plot to the world road network"
		)
	for seg in WorldState.road_segments:
		if seg is Dictionary:
			var s: Dictionary = seg
			if str(s.get("from_plot", "")) == _plot_id or str(s.get("to_plot", "")) == _plot_id:
				return ""
	return (
		"No road access — connect workshops to site roads (Build → Roads) "
		+ "or link this plot to the world road network"
	)


func _response_error_message(data: Dictionary) -> String:
	if data.is_empty():
		return "No response from server"
	if bool(data.get("ok", false)):
		return ""
	if data.has("reason"):
		return str(data.get("reason", ""))
	if data.has("detail"):
		return str(data.get("detail", ""))
	return "Failed to start production"


func _upsert_active_run_from_response(data: Dictionary) -> void:
	var rid := str(data.get("recipe_id", ""))
	if rid.is_empty():
		return
	var ticks: int = int(data.get("ticks_remaining", 0))
	var run_id := str(data.get("run_id", ""))
	if ticks <= 0 and run_id.is_empty():
		return
	var run := {
		"run_id": run_id,
		"party": WorldState.party_id,
		"plot_id": str(data.get("plot_id", _plot_id)),
		"recipe_id": rid,
		"ticks_remaining": ticks,
		"runs_remaining": int(data.get("runs_remaining", 0)),
	}
	var kept: Array = []
	for existing in WorldState.active_production:
		if not (existing is Dictionary):
			continue
		var ex: Dictionary = existing
		if str(ex.get("plot_id", "")) == _plot_id and str(ex.get("party", "")) == WorldState.party_id:
			continue
		kept.append(ex)
	kept.append(run)
	WorldState.active_production = kept
	WorldState.player_updated.emit()


func _missing_inputs_reason(recipe_id: String) -> String:
	var row := _recipe_row(recipe_id)
	var inputs: Variant = row.get("inputs", {})
	if not (inputs is Dictionary) or (inputs as Dictionary).is_empty():
		return ""
	var missing: PackedStringArray = []
	for mat in (inputs as Dictionary).keys():
		var mid := str(mat)
		if mid == "electricity":
			continue
		var need := int((inputs as Dictionary)[mat])
		if not WorldState.player_has_material(mid, need):
			if WorldState.player_has_substitute(recipe_id, mid):
				continue
			var have := WorldState.player_material_total(mid)
			missing.append(
				"%s need %d (have %d)" % [WorldState.material_display_name(mid), need, have]
			)
	if missing.is_empty():
		return ""
	var labor := int(row.get("labor_cents", 0))
	if labor > 0 and WorldState.player_cash_cents < labor:
		return "Need %s cash for labor (have %s)" % [
			WorldState.format_money(labor),
			WorldState.format_money(WorldState.player_cash_cents),
		]
	return "Missing: " + ", ".join(missing) + " — Bazaar or Buy inputs"


func _empty_recipe_hint() -> String:
	var wid := _building_id()
	var bname := WorldState.building_display_name(_building)
	if WorldState.recipes.is_empty():
		return "Recipe catalog not loaded yet — close and reopen Production"
	if wid.is_empty():
		return "Unknown building — no recipes"
	if wid == "strip_mine":
		return (
			"Strip mine recipes depend on survey grades and terrain. "
			+ "Iron/copper ore need mountain; coal, clay, and phosphate work on many land tiles."
		)
	var bp := WorldState.blueprint_dict(wid)
	var desc := str(bp.get("description", ""))
	if not desc.is_empty():
		return "%s — %s" % [bname, desc]
	if wid == "foundry" and _terrain != "mountain":
		return (
			"%s: smelting needs a mountain plot (this tile is %s). "
			+ "Wire draw may still work if the plot is surveyed."
		) % [bname, _terrain]
	return "No recipes enabled for %s — check blueprint recipes, survey, and terrain" % bname


func _set_idle_ready(recipe_id: String) -> void:
	status_icon.text = "⏸"
	if recipe_id.is_empty():
		status_label.text = "Idle — pick a recipe and press Start"
	else:
		status_label.text = "Ready — press Start to run %s" % str(
			_recipe_row(recipe_id).get("display_name", recipe_id)
		)
	status_label.modulate = Color(0.55, 0.85, 0.55)
	progress_bar.value = 0.0
	start_btn.show()
	start_btn.disabled = recipe_selector.disabled
	stop_btn.hide()
	buy_inputs_btn.hide()


func _set_blocked(reason: String) -> void:
	status_icon.text = "⚠"
	status_label.text = reason
	status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status_label.modulate = Color(1.0, 0.55, 0.25)
	progress_bar.value = 0.0
	start_btn.show()
	start_btn.disabled = true
	stop_btn.hide()
	var rid := _selected_recipe_id()
	var needs_inputs := not _missing_inputs_reason(rid).is_empty()
	buy_inputs_btn.visible = needs_inputs


func _refresh_recipe_hints() -> void:
	var rid := _selected_recipe_id()
	var plot_data: Dictionary = WorldState.plots.get(_plot_id, {})
	var cluster_bonus := float(plot_data.get("cluster_bonus", 0.0))
	if is_instance_valid(cluster_label):
		if cluster_bonus > 0.0:
			cluster_label.text = "🏭 Cluster bonus: +%d%% yield" % int(cluster_bonus * 100.0)
			cluster_label.modulate = Color(0.4, 1.0, 0.4)
			cluster_label.show()
		else:
			cluster_label.hide()
	if rid.is_empty():
		if is_instance_valid(substitution_note):
			substitution_note.hide()
		return
	var row := _recipe_row(rid)
	var inputs: Variant = row.get("inputs", {})
	if not (inputs is Dictionary) or (inputs as Dictionary).is_empty():
		if is_instance_valid(substitution_note):
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
	if not is_instance_valid(substitution_note):
		return
	if show_sub:
		substitution_note.text = "⚡ Will use substitute input"
		substitution_note.modulate = Color(1.0, 0.85, 0.2)
		substitution_note.show()
	else:
		substitution_note.hide()


func _set_idle() -> void:
	_set_idle_ready(_selected_recipe_id())


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
	if _start_in_flight:
		return
	var rid := _selected_recipe_id()
	var blocker := _production_blocker(rid)
	if not blocker.is_empty():
		_set_blocked(blocker)
		MainFeedback.toast(blocker, true)
		return
	var run_count := -1 if _run_continuous else 1
	_start_in_flight = true
	start_btn.disabled = true
	status_label.text = "Starting…"
	API.start_production(_plot_id, rid, run_count, _on_start_completed)


func _on_start_completed(data: Dictionary) -> void:
	_start_in_flight = false
	start_btn.disabled = false
	var err := _response_error_message(data)
	if not err.is_empty():
		_last_start_error = err
		_set_stalled(err)
		MainFeedback.toast(err, true)
		return
	_last_start_error = ""
	var started := bool(data.get("started", false))
	var snap := data.duplicate(true)
	if started:
		_upsert_active_run_from_response(snap)
	var rid := str(data.get("recipe_id", _selected_recipe_id()))
	var label := str(_recipe_row(rid).get("display_name", rid))
	if started:
		MainFeedback.toast("Production started: %s" % label, false)
		_refresh_status()
	else:
		var msg := str(data.get("message", "Production already active on this plot"))
		MainFeedback.toast(msg, false)
		_last_start_error = msg
		_set_stalled(msg)
	API.get_world_player(
		func(p: Dictionary) -> void:
			if not p.is_empty():
				WorldState.apply_player(p)
			elif started:
				WorldState.player_updated.emit()
			if started and is_instance_valid(self):
				if WorldState.active_production_run_for_building(_plot_id, _building).is_empty():
					_upsert_active_run_from_response(snap)
			if is_instance_valid(self):
				_refresh_status(),
		WorldState.party_id,
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


func _refresh_throughput() -> void:
	if not is_instance_valid(_throughput_label):
		return
	var rid := _selected_recipe_id()
	if rid.is_empty() or _plot_id.is_empty():
		_throughput_label.hide()
		return
	API.get_plot_throughput(
		_plot_id,
		rid,
		func(data: Dictionary) -> void:
			if not is_instance_valid(_throughput_label):
				return
			if not bool(data.get("ok", false)):
				_throughput_label.hide()
				return
			var combined: int = int(data.get("combined_bps", 10_000))
			var pct := float(combined) / 100.0
			var row := _recipe_row(rid)
			var dur: int = int(row.get("duration_ticks", 0))
			_throughput_label.text = (
				"Throughput %+.0f%% · ~%s per run · building eff %d%% · labor %d bps"
				% [
					pct - 100.0,
					WorldState.format_ticks_as_gametime(dur),
					int(data.get("efficiency_pct", 100)),
					int(data.get("labour_bps", data.get("labor_bps", 10_000))),
				]
			)
			_throughput_label.show(),
	)


func _on_building_auto_list_changed(instance_id: String, enabled: bool) -> void:
	if str(_building.get("instance_id", "")) != instance_id:
		return
	_building["auto_list_output"] = enabled
	auto_list_toggle.set_pressed_no_signal(enabled)


func _on_auto_list_toggle(on: bool) -> void:
	var instance_id: String = str(_building.get("instance_id", ""))
	WorldState.set_building_auto_list_enabled(instance_id, on)
