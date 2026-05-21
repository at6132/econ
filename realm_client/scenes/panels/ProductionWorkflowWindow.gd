extends CanvasLayer
## Centered production workflow — run, I/O routing (client-persisted), warehouse replenish.

signal closed

const ProductionControlScene := preload("res://scenes/panels/ProductionControl.tscn")

@onready var _title: Label = %TitleLabel
@onready var _close_btn: Button = %CloseBtn
@onready var _subtitle: Label = %SubtitleLabel
@onready var _tab_run: Button = %TabRunBtn
@onready var _tab_routing: Button = %TabRoutingBtn
@onready var _tab_warehouse: Button = %TabWarehouseBtn
@onready var _run_page: VBoxContainer = %RunPage
@onready var _routing_page: ScrollContainer = %RoutingPage
@onready var _routing_inner: VBoxContainer = %RoutingInner
@onready var _warehouse_page: HBoxContainer = %WarehousePage
@onready var _warehouse_list: ItemList = %WarehouseList
@onready var _warehouse_rules_inner: VBoxContainer = %WarehouseRulesInner
@onready var _center_panel: PanelContainer = %CenterPanel

var _plot_id: String = ""
var _building: Dictionary = {}
var _plot_data: Dictionary = {}
var _workshop_id: String = ""
var _profile_mode: String = "production"  # production | warehouse
var _production_control: Node = null
var _tab_group: ButtonGroup = null
var _warehouse_plot_ids: PackedStringArray = PackedStringArray()
var _selected_warehouse_plot: String = ""
var _routing_selectors: Array = []


func _ready() -> void:
	set_process_unhandled_input(true)
	_tab_group = ButtonGroup.new()
	_tab_group.allow_unpress = false
	for btn in [_tab_run, _tab_routing, _tab_warehouse]:
		btn.button_group = _tab_group
		btn.pressed.connect(_on_tab_pressed.bind(btn))
	_close_btn.pressed.connect(close)
	var dim := get_node_or_null("DimBackground")
	if dim is ColorRect:
		(dim as ColorRect).gui_input.connect(_on_dim_clicked)
	_apply_panel_theme()
	_show_tab("run")
	WorldState.world_updated.connect(_on_world_updated)
	WorldState.player_updated.connect(_on_world_updated)
	WorldState.recipes_updated.connect(_on_recipes_catalog_ready)
	WorldState.building_auto_list_changed.connect(_on_building_auto_list_changed)
	WS.tick_event.connect(_on_tick_event)


func _exit_tree() -> void:
	if WorldState.world_updated.is_connected(_on_world_updated):
		WorldState.world_updated.disconnect(_on_world_updated)
	if WorldState.player_updated.is_connected(_on_world_updated):
		WorldState.player_updated.disconnect(_on_world_updated)
	if WorldState.recipes_updated.is_connected(_on_recipes_catalog_ready):
		WorldState.recipes_updated.disconnect(_on_recipes_catalog_ready)
	if WorldState.building_auto_list_changed.is_connected(_on_building_auto_list_changed):
		WorldState.building_auto_list_changed.disconnect(_on_building_auto_list_changed)
	if WS.tick_event.is_connected(_on_tick_event):
		WS.tick_event.disconnect(_on_tick_event)


func _apply_panel_theme() -> void:
	if _center_panel == null:
		return
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.07, 0.07, 0.09, 0.98)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.45)
	sb.set_corner_radius_all(8)
	sb.set_content_margin_all(4)
	_center_panel.add_theme_stylebox_override("panel", sb)
	PanelUI.style_btn(_close_btn)
	for btn in [_tab_run, _tab_routing, _tab_warehouse]:
		PanelUI.style_btn(btn, btn.button_pressed)
	_subtitle.add_theme_color_override("font_color", Color(0.65, 0.62, 0.55))
	_title.add_theme_font_size_override("font_size", 20)
	_title.add_theme_color_override("font_color", RealmColors.TEXT)


func open(plot_id: String, building: Dictionary, plot_data: Dictionary) -> void:
	_plot_id = plot_id
	_building = building.duplicate(true)
	_plot_data = plot_data.duplicate(true)
	_workshop_id = WorldState.workshop_id_for_building(_building)
	_apply_building_profile()
	_mount_production_control()
	_refresh_routing_tab()
	_refresh_warehouse_list()
	_try_warehouse_replenish_all()


func _apply_building_profile() -> void:
	var bname := WorldState.building_display_name(_building)
	var bp := WorldState.blueprint_dict(_workshop_id)
	var cat := str(bp.get("category", "processing"))
	var desc := str(bp.get("description", ""))
	var recipe_n := WorldState.recipes_for_workshop_building(_building).size()
	var fw := int(bp.get("footprint_w", 0))
	var fh := int(bp.get("footprint_h", 0))
	var footprint := ""
	if fw > 0 and fh > 0:
		footprint = " · %d×%d cells" % [fw, fh]
	var terrain := str(_plot_data.get("terrain", "plains"))
	if WorldState.building_is_warehouse(_building):
		_profile_mode = "warehouse"
		_title.text = "Warehouse — %s" % bname
		_subtitle.text = (
			"Plot %s%s\nAuto-buy rules for materials stored on this plot."
			% [_plot_id, footprint]
		)
		_tab_run.visible = false
		_tab_routing.visible = false
		_tab_warehouse.visible = true
		_tab_warehouse.text = "This warehouse"
		_tab_run.text = "Run"
		_selected_warehouse_plot = _plot_id
		_show_tab("warehouse")
		for b in [_tab_run, _tab_routing, _tab_warehouse]:
			PanelUI.style_btn(b, b == _tab_warehouse)
		return
	_profile_mode = "production"
	_title.text = "Production — %s" % bname
	var lines: PackedStringArray = PackedStringArray([
		"Plot %s · %s · %s%s" % [_plot_id, _workshop_id, terrain, footprint],
		"%d recipe(s) on this blueprint · category %s" % [recipe_n, cat],
	])
	if not desc.is_empty():
		lines.append(desc)
	lines.append("I/O routing syncs to the engine on change.")
	_subtitle.text = "\n".join(lines)
	var can_run := WorldState.building_supports_production(_building)
	_tab_run.visible = can_run
	_tab_routing.visible = can_run
	_tab_warehouse.visible = false
	_tab_run.text = "Run"
	_tab_routing.text = "I/O routing"
	_tab_warehouse.text = "Warehouses"
	if can_run:
		_show_tab("run")
		for b in [_tab_run, _tab_routing, _tab_warehouse]:
			PanelUI.style_btn(b, b == _tab_run)
	else:
		_show_tab("routing")


func close() -> void:
	closed.emit()
	queue_free()


func _on_dim_clicked(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.pressed and mb.button_index == MOUSE_BUTTON_LEFT:
			close()


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		close()
		get_viewport().set_input_as_handled()


func _on_tab_pressed(btn: Button) -> void:
	for b in [_tab_run, _tab_routing, _tab_warehouse]:
		PanelUI.style_btn(b, b == btn)
	if btn == _tab_run:
		_show_tab("run")
	elif btn == _tab_routing:
		_show_tab("routing")
	else:
		_show_tab("warehouse")


func _show_tab(which: String) -> void:
	_run_page.visible = which == "run"
	_routing_page.visible = which == "routing"
	_warehouse_page.visible = which == "warehouse"
	if which == "routing":
		_refresh_routing_tab()
	if which == "warehouse":
		_refresh_warehouse_rules_panel()


func _mount_production_control() -> void:
	if _production_control and is_instance_valid(_production_control):
		_production_control.queue_free()
	_production_control = ProductionControlScene.instantiate()
	_run_page.add_child(_production_control)
	if _production_control.has_method("setup"):
		_production_control.call(
			"setup",
			_plot_id,
			_building,
			str(_plot_data.get("terrain", "plains")),
		)
	var sel: OptionButton = _production_control.get_node_or_null("%RecipeSelector") as OptionButton
	if sel != null and not sel.item_selected.is_connected(_on_recipe_changed):
		sel.item_selected.connect(_on_recipe_changed)


func _on_recipe_changed(_i: int = 0) -> void:
	_refresh_routing_tab()


func _instance_id() -> String:
	return str(_building.get("instance_id", ""))


func _selected_recipe_id() -> String:
	if _production_control != null and _production_control.has_method("selected_recipe_id"):
		return str(_production_control.call("selected_recipe_id"))
	return ""


func _recipe_row(rid: String) -> Dictionary:
	return WorldState.recipe_by_id(rid)


func _owned_plots() -> Array:
	var out: Array = []
	var party := WorldState.party_id
	for pid in WorldState.plots.keys():
		var row: Dictionary = WorldState.plots[pid] as Dictionary
		if str(row.get("owner", "")) == party:
			out.append({"id": str(pid), "data": row})
	out.sort_custom(func(a, b): return str(a["id"]) < str(b["id"]))
	return out


func _plot_has_warehouse(plot_id: String) -> bool:
	var ui := WorldState.get_plot_ui(plot_id)
	for b in ui.get("buildings", []):
		if b is Dictionary and str((b as Dictionary).get("building_id", "")) == "warehouse":
			return true
	return false


func _stash_qty(plot_id: String, material: String) -> int:
	var pd: Dictionary = WorldState.plots.get(plot_id, {})
	var stock: Variant = pd.get("output_stock", {})
	if not (stock is Dictionary):
		return 0
	return int((stock as Dictionary).get(material, 0))


func _source_options() -> Array:
	var opts: Array = [
		{"id": "stash_this", "label": "This plot stash"},
		{"id": "player_inv", "label": "Personal carry (portable only)"},
		{"id": "market_buy", "label": "Buy from market if short"},
	]
	for row in _owned_plots():
		var pid := str(row["id"])
		if pid == _plot_id:
			continue
		var tag := " (warehouse)" if _plot_has_warehouse(pid) else ""
		opts.append({"id": "stash_plot:%s" % pid, "label": "Plot stash: %s%s" % [pid, tag]})
	return opts


func _dest_options() -> Array:
	var opts: Array = [
		{"id": "stash_this", "label": "This plot stash"},
		{"id": "harvest_player", "label": "To personal carry (portable only)"},
		{"id": "auto_list", "label": "Auto-list on market (building flag)"},
	]
	for row in _owned_plots():
		var pid := str(row["id"])
		if pid == _plot_id:
			continue
		var tag := " (warehouse)" if _plot_has_warehouse(pid) else ""
		opts.append({"id": "stash_plot:%s" % pid, "label": "Ship to plot stash: %s%s" % [pid, tag]})
		opts.append({"id": "ship_to:%s" % pid, "label": "Dispatch shipment → %s" % pid})
	return opts


func _fill_option(sel: OptionButton, options: Array, current_id: String) -> void:
	sel.clear()
	var pick := 0
	for i in options.size():
		var o: Dictionary = options[i]
		sel.add_item(str(o["label"]))
		sel.set_item_metadata(i, str(o["id"]))
		if str(o["id"]) == current_id:
			pick = i
	sel.select(pick)


func _refresh_routing_tab() -> void:
	PanelUI.clear_children(_routing_inner)
	_routing_selectors.clear()
	var rid := _selected_recipe_id()
	if rid.is_empty():
		var hint := Label.new()
		hint.text = "Pick a recipe on the Run tab first."
		hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_routing_inner.add_child(hint)
		return
	var row := _recipe_row(rid)
	var inst := _instance_id()
	var inputs: Variant = row.get("inputs", {})
	var outputs: Variant = row.get("outputs", {})
	_add_section_title("Inputs — where materials come from")
	if inputs is Dictionary and not (inputs as Dictionary).is_empty():
		for mat in (inputs as Dictionary).keys():
			_add_io_row(true, str(mat), int((inputs as Dictionary)[mat]), inst)
	else:
		_add_muted("No recipe inputs.")
	_add_section_title("Outputs — what happens when a batch finishes")
	if outputs is Dictionary and not (outputs as Dictionary).is_empty():
		for mat in (outputs as Dictionary).keys():
			_add_io_row(false, str(mat), int((outputs as Dictionary)[mat]), inst)
	else:
		_add_muted("No recipe outputs.")
	var note := Label.new()
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	note.add_theme_color_override("font_color", Color(0.55, 0.52, 0.45))
	note.text = (
		"After each production_done event, outputs are harvested/shipped/auto-listed per these routes. "
		+ "Market buy runs before start when an input route is set to buy-from-market."
	)
	_routing_inner.add_child(note)


func _add_section_title(text: String) -> void:
	var lbl := Label.new()
	lbl.text = text
	lbl.add_theme_color_override("font_color", RealmColors.ACCENT)
	_routing_inner.add_child(lbl)


func _add_muted(text: String) -> void:
	var lbl := Label.new()
	lbl.text = text
	lbl.add_theme_color_override("font_color", Color(0.55, 0.52, 0.45))
	_routing_inner.add_child(lbl)


func _mat_label(mat_id: String, qty: int) -> String:
	var name := mat_id.replace("_", " ")
	return "%s × %d" % [name, qty]


func _add_io_row(is_input: bool, material: String, qty: int, instance_id: String) -> void:
	var grid := GridContainer.new()
	grid.columns = 3
	grid.add_theme_constant_override("h_separation", 10)
	grid.add_theme_constant_override("v_separation", 6)
	var mat_lbl := Label.new()
	mat_lbl.text = _mat_label(material, qty)
	mat_lbl.custom_minimum_size.x = 140
	grid.add_child(mat_lbl)
	var stash_lbl := Label.new()
	if is_input:
		var here := _stash_qty(_plot_id, material)
		stash_lbl.text = "On plot: %d" % here
	else:
		stash_lbl.text = ""
	grid.add_child(stash_lbl)
	var sel := OptionButton.new()
	sel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var opts := _source_options() if is_input else _dest_options()
	var cur := (
		RealmWorkflowSettings.get_input_source(instance_id, material, _plot_id)
		if is_input
		else RealmWorkflowSettings.get_output_dest(instance_id, material, _plot_id)
	)
	_fill_option(sel, opts, cur)
	sel.item_selected.connect(
		func(_i: int) -> void:
			var picked := str(sel.get_item_metadata(sel.selected))
			if is_input:
				RealmWorkflowSettings.set_input_source(instance_id, material, picked)
			else:
				RealmWorkflowSettings.set_output_dest(instance_id, material, picked)
	)
	grid.add_child(sel)
	_routing_inner.add_child(grid)
	_routing_selectors.append({"is_input": is_input, "material": material, "selector": sel})


func _refresh_warehouse_list() -> void:
	_warehouse_list.clear()
	_warehouse_plot_ids = PackedStringArray()
	if _profile_mode == "warehouse" and not _plot_id.is_empty():
		_warehouse_plot_ids.append(_plot_id)
		var pd: Dictionary = WorldState.get_plot_ui(_plot_id)
		var stash_n := 0
		var stock: Variant = pd.get("output_stock", {})
		if stock is Dictionary:
			for k in (stock as Dictionary).keys():
				stash_n += int((stock as Dictionary)[k])
		_warehouse_list.add_item("%s — stash %d u (this building)" % [_plot_id, stash_n])
		_warehouse_list.select(0)
		_selected_warehouse_plot = _plot_id
		_refresh_warehouse_rules_panel()
		return
	for row in _owned_plots():
		var pid := str(row["id"])
		if not _plot_has_warehouse(pid):
			continue
		_warehouse_plot_ids.append(pid)
		var stash_n := 0
		var pd: Dictionary = row["data"]
		var stock: Variant = pd.get("output_stock", {})
		if stock is Dictionary:
			for k in (stock as Dictionary).keys():
				stash_n += int((stock as Dictionary)[k])
		var label := "%s — stash %d u" % [pid, stash_n]
		_warehouse_list.add_item(label)
	if _warehouse_plot_ids.is_empty():
		_warehouse_list.add_item("(No warehouse buildings on owned plots)")
		_selected_warehouse_plot = ""
		PanelUI.clear_children(_warehouse_rules_inner)
		var hint := Label.new()
		hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		hint.text = "Place a warehouse blueprint on a plot to configure auto bulk buy and inbound delivery targets here."
		_warehouse_rules_inner.add_child(hint)
		return
	if not _warehouse_list.item_selected.is_connected(_on_warehouse_selected):
		_warehouse_list.item_selected.connect(_on_warehouse_selected)
	if _selected_warehouse_plot.is_empty() or not (_selected_warehouse_plot in _warehouse_plot_ids):
		_warehouse_list.select(0)
		_on_warehouse_selected(0)


func _on_warehouse_selected(index: int) -> void:
	if index < 0 or index >= _warehouse_plot_ids.size():
		return
	_selected_warehouse_plot = _warehouse_plot_ids[index]
	_refresh_warehouse_rules_panel()


func _refresh_warehouse_rules_panel() -> void:
	PanelUI.clear_children(_warehouse_rules_inner)
	if _selected_warehouse_plot.is_empty():
		return
	var title := Label.new()
	title.text = "Replenish rules — %s" % _selected_warehouse_plot
	title.add_theme_color_override("font_color", RealmColors.ACCENT)
	_warehouse_rules_inner.add_child(title)
	var materials := _common_materials()
	for mid in materials:
		_add_warehouse_rule_row(_selected_warehouse_plot, mid)
	var run_btn := Button.new()
	run_btn.text = "Run replenishment now"
	PanelUI.style_btn(run_btn, true)
	run_btn.pressed.connect(func() -> void: _replenish_warehouse_plot(_selected_warehouse_plot))
	_warehouse_rules_inner.add_child(run_btn)
	var ship_hint := Label.new()
	ship_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	ship_hint.add_theme_color_override("font_color", Color(0.55, 0.52, 0.45))
	ship_hint.text = (
		"When enabled, ticks and world refresh check stash vs target; shortfall triggers market buy "
		+ "(max price per unit). Link input routes on other buildings to this plot's stash for delivery via Ship."
	)
	_warehouse_rules_inner.add_child(ship_hint)


func _common_materials() -> PackedStringArray:
	return PackedStringArray([
		"grain", "coal", "timber", "stone", "brick", "lumber", "iron_ore", "electricity",
	])


func _add_warehouse_rule_row(plot_id: String, material: String) -> void:
	var rule := RealmWorkflowSettings.get_warehouse_rule(plot_id, material)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	var en := CheckButton.new()
	en.text = material
	en.button_pressed = bool(rule.get("enabled", false))
	var tgt := SpinBox.new()
	tgt.prefix = "Target"
	tgt.min_value = 0
	tgt.max_value = 99999
	tgt.value = int(rule.get("target_qty", 0))
	var price := SpinBox.new()
	price.prefix = "Max ¢/u"
	price.min_value = 0
	price.max_value = 999999
	price.value = int(rule.get("max_price_cents", 0))
	var save_rule := func() -> void:
		RealmWorkflowSettings.set_warehouse_rule(
			plot_id,
			material,
			{
				"enabled": en.button_pressed,
				"target_qty": int(tgt.value),
				"max_price_cents": int(price.value),
			},
		)
	en.toggled.connect(func(_on: bool) -> void: save_rule.call())
	tgt.value_changed.connect(func(_v: float) -> void: save_rule.call())
	price.value_changed.connect(func(_v: float) -> void: save_rule.call())
	row.add_child(en)
	row.add_child(tgt)
	row.add_child(price)
	_warehouse_rules_inner.add_child(row)


func _on_recipes_catalog_ready() -> void:
	if _plot_id.is_empty():
		return
	_apply_building_profile()
	_mount_production_control()


func _on_world_updated() -> void:
	_sync_building_from_world()
	if _routing_page.visible:
		_refresh_routing_tab()
	if _warehouse_page.visible:
		_refresh_warehouse_list()
	_try_warehouse_replenish_all()
	_try_buy_inputs_before_start()


func _on_tick_event(event: Dictionary) -> void:
	if str(event.get("kind", "")) == "production_done" and str(event.get("plot_id", "")) == _plot_id:
		_apply_output_routing()
	_sync_building_from_world()


func _on_building_auto_list_changed(instance_id: String, enabled: bool) -> void:
	if _instance_id() != instance_id:
		return
	_building["auto_list_output"] = enabled
	if _production_control != null:
		var toggle: CheckButton = _production_control.get_node_or_null("%AutoListToggle") as CheckButton
		if toggle != null:
			toggle.set_pressed_no_signal(enabled)


func _sync_building_from_world() -> void:
	var inst := _instance_id()
	if inst.is_empty():
		return
	var ui: Dictionary = WorldState.get_plot_ui(_plot_id)
	for b in ui.get("buildings", []):
		if b is Dictionary and str((b as Dictionary).get("instance_id", "")) == inst:
			_building = (b as Dictionary).duplicate(true)
			_workshop_id = WorldState.workshop_id_for_building(_building)
			break
	if _production_control != null and _production_control.has_method("setup"):
		_production_control.call(
			"setup",
			_plot_id,
			_building,
			str(_plot_data.get("terrain", "plains")),
		)


func _apply_output_routing() -> void:
	var inst := _instance_id()
	if inst.is_empty():
		return
	var rid := _selected_recipe_id()
	if rid.is_empty():
		return
	var row := _recipe_row(rid)
	var outputs: Variant = row.get("outputs", {})
	if not (outputs is Dictionary):
		return
	for mat in (outputs as Dictionary).keys():
		var mid := str(mat)
		var qty: int = int((outputs as Dictionary)[mat])
		if qty <= 0:
			continue
		var dest := RealmWorkflowSettings.get_output_dest(inst, mid, _plot_id)
		_execute_output_dest(dest, mid, qty)


func _execute_output_dest(dest_id: String, material: String, qty: int) -> void:
	if dest_id == "stash_this" or dest_id.is_empty():
		return
	if dest_id == "harvest_player":
		API.harvest_plot_output(_plot_id, material, qty, func(_d: Dictionary) -> void: pass)
		return
	if dest_id == "auto_list":
		var iid := _instance_id()
		if not bool(_building.get("auto_list_output", false)):
			WorldState.set_building_auto_list_enabled(iid, true)
		return
	if dest_id.begins_with("stash_plot:"):
		var to_pid := dest_id.substr(11)
		API.ship(_plot_id, to_pid, material, qty, func(_d: Dictionary) -> void: pass)
		return
	if dest_id.begins_with("ship_to:"):
		var to_pid := dest_id.substr(8)
		API.ship(_plot_id, to_pid, material, qty, func(_d: Dictionary) -> void: pass)


func _try_warehouse_replenish_all() -> void:
	for row in _owned_plots():
		var pid := str(row["id"])
		if _plot_has_warehouse(pid):
			_replenish_warehouse_plot(pid)


func _replenish_warehouse_plot(plot_id: String) -> void:
	for mid in _common_materials():
		var rule := RealmWorkflowSettings.get_warehouse_rule(plot_id, mid)
		if not bool(rule.get("enabled", false)):
			continue
		var target: int = int(rule.get("target_qty", 0))
		if target <= 0:
			continue
		var have := _stash_qty(plot_id, mid)
		var need: int = target - have
		if need <= 0:
			continue
		var max_p: int = int(rule.get("max_price_cents", 0))
		API.market_buy(mid, need, 0, func(_d: Dictionary) -> void: pass, WorldState.party_id, max_p)


func _try_buy_inputs_before_start() -> void:
	var inst := _instance_id()
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
		var src := RealmWorkflowSettings.get_input_source(inst, mid, _plot_id)
		if src != "market_buy":
			continue
		var need: int = int((inputs as Dictionary)[mat])
		if WorldState.player_has_material(mid, need):
			continue
		var shortfall: int = need - WorldState.player_material_qty(mid)
		if shortfall > 0:
			API.market_buy(mid, shortfall, 0, func(_d: Dictionary) -> void: pass)
