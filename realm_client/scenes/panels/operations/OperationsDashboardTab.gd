extends VBoxContainer
## Multi-plot production, automation, shipments, and quick actions.

var _scroll: ScrollContainer
var _inner: VBoxContainer


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	_scroll = ScrollContainer.new()
	_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_inner = VBoxContainer.new()
	_inner.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_inner.add_theme_constant_override("separation", 10)
	_scroll.add_child(_inner)
	add_child(_scroll)
	WorldState.player_updated.connect(refresh)
	WorldState.world_updated.connect(refresh)
	WorldState.building_auto_list_changed.connect(func(_iid: String, _on: bool) -> void: refresh())
	refresh()


func refresh() -> void:
	if not is_instance_valid(_inner):
		return
	PanelUI.clear_children(_inner)
	_add_kpi_strip()
	_add_quick_nav()
	_add_section("Active production", _production_section())
	_add_section("Output automation", _automation_section())
	_add_section("In transit", _transit_section())
	_add_section("Revenue contracts (supply)", _supply_section())


func _add_section(title: String, body: Control) -> void:
	var hdr := Label.new()
	hdr.text = title
	hdr.add_theme_color_override("font_color", RealmColors.ACCENT)
	_inner.add_child(hdr)
	_inner.add_child(body)


func _add_kpi_strip() -> void:
	var grid := GridContainer.new()
	grid.columns = 3
	grid.add_theme_constant_override("h_separation", 12)
	grid.add_theme_constant_override("v_separation", 6)
	for text in [
		"Cash: %s" % WorldState.format_money(WorldState.player_cash_cents),
		"Inventory est.: %s" % WorldState.format_money(WorldState.player_inventory_value_cents),
		"Net worth est.: %s" % WorldState.format_money(WorldState.player_net_worth_cents),
		"Active runs: %d" % WorldState.active_production.size(),
		"In transit: %d" % WorldState.in_transit.size(),
		"Contracts: %d" % WorldState.active_contracts_count,
	]:
		var lbl := Label.new()
		lbl.text = text
		lbl.add_theme_color_override("font_color", RealmColors.TEXT)
		grid.add_child(lbl)
	_inner.add_child(grid)


func _add_quick_nav() -> void:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	for spec in [
		["inventory", "Inventory"],
		["market", "Bazaar"],
		["caravans", "Shipping"],
		["contracts", "Pacts"],
		["finance", "Finance"],
		["business", "Business"],
		["labor", "Labor"],
	]:
		var btn := Button.new()
		btn.text = spec[1]
		PanelUI.style_btn(btn)
		btn.pressed.connect(_nav.bind(spec[0]))
		row.add_child(btn)
	_inner.add_child(row)


func _nav(panel_id: String) -> void:
	var host := get_tree().current_scene
	if host != null and host.has_method("_on_nav_pressed"):
		host.call("_on_nav_pressed", panel_id)


func _production_section() -> VBoxContainer:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 6)
	var any := false
	for run in WorldState.active_production:
		if not (run is Dictionary):
			continue
		if str((run as Dictionary).get("party", "")) != WorldState.party_id:
			continue
		any = true
		box.add_child(_run_card(run as Dictionary))
	if not any:
		box.add_child(_muted("No active production runs."))
	return box


func _run_card(run: Dictionary) -> PanelContainer:
	var pc := PanelContainer.new()
	var v := VBoxContainer.new()
	pc.add_child(v)
	var rid := str(run.get("recipe_id", ""))
	var plot_id := str(run.get("plot_id", ""))
	var row := WorldState.recipe_by_id(rid)
	var lbl := Label.new()
	lbl.text = "%s on %s — %s left" % [
		str(row.get("display_name", rid)),
		plot_id,
		WorldState.format_ticks_as_gametime(int(run.get("ticks_remaining", 0))),
	]
	v.add_child(lbl)
	var btn_row := HBoxContainer.new()
	var open_plot := Button.new()
	open_plot.text = "Plot"
	PanelUI.style_btn(open_plot)
	open_plot.pressed.connect(_open_plot.bind(plot_id))
	btn_row.add_child(open_plot)
	var workflow := Button.new()
	workflow.text = "Production"
	PanelUI.style_btn(workflow, true)
	workflow.pressed.connect(_open_workflow_for_plot.bind(plot_id))
	btn_row.add_child(workflow)
	v.add_child(btn_row)
	return pc


func _automation_section() -> VBoxContainer:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 4)
	var any := false
	for b in WorldState.plot_buildings:
		if not (b is Dictionary):
			continue
		var row: Dictionary = b
		var plot_id := str(row.get("plot_id", ""))
		var pd: Dictionary = WorldState.plots.get(plot_id, {})
		if str(pd.get("owner", "")) != WorldState.party_id:
			continue
		var bid := str(row.get("building_id", ""))
		if bid == "road_segment":
			continue
		var recipes := WorldState.recipes_for_workshop_building(row)
		if recipes.is_empty() and not bool(row.get("auto_list_output", false)):
			continue
		any = true
		var line := HBoxContainer.new()
		var lbl := Label.new()
		lbl.text = "%s · %s on %s" % [bid, row.get("instance_id", ""), plot_id]
		lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		line.add_child(lbl)
		var auto := CheckButton.new()
		auto.text = "Auto-list output"
		auto.button_pressed = bool(row.get("auto_list_output", false))
		var iid := str(row.get("instance_id", ""))
		auto.toggled.connect(
			func(on: bool) -> void: WorldState.set_building_auto_list_enabled(iid, on)
		)
		line.add_child(auto)
		var cfg := Button.new()
		cfg.text = "Workflow"
		PanelUI.style_btn(cfg)
		cfg.pressed.connect(_open_workflow_for_building.bind(plot_id, row))
		line.add_child(cfg)
		box.add_child(line)
	if not any:
		box.add_child(_muted("Place production buildings and enable auto-list or open workflow routing."))
	return box


func _transit_section() -> VBoxContainer:
	var box := VBoxContainer.new()
	if WorldState.in_transit.is_empty():
		box.add_child(_muted("No shipments in flight."))
		return box
	for ship in WorldState.in_transit:
		if not (ship is Dictionary):
			continue
		var s: Dictionary = ship
		var lbl := Label.new()
		lbl.text = "%s × %d → %s (arrives %s)" % [
			s.get("material", "?"),
			int(s.get("qty", 0)),
			s.get("dest_plot_id", "?"),
			WorldState.format_ticks_as_gametime(
				maxi(0, int(s.get("arrive_tick", 0)) - WorldState.current_tick)
			),
		]
		box.add_child(lbl)
	return box


func _supply_section() -> VBoxContainer:
	var box := VBoxContainer.new()
	var n := 0
	for c in WorldState.active_contracts:
		if not (c is Dictionary):
			continue
		if str((c as Dictionary).get("kind", "")) != "supply_contract":
			continue
		var party := WorldState.party_id
		if str((c as Dictionary).get("supplier", "")) != party and str((c as Dictionary).get("buyer", "")) != party:
			continue
		n += 1
		var lbl := Label.new()
		var d: Dictionary = c
		lbl.text = "%s × %d — %s" % [d.get("material", "?"), int(d.get("qty_per_cycle", 0)), d.get("status", "")]
		box.add_child(lbl)
	if n == 0:
		box.add_child(_muted("No supply contracts — propose in Pacts → Supply."))
	var btn := Button.new()
	btn.text = "Open Pacts"
	PanelUI.style_btn(btn)
	btn.pressed.connect(_nav.bind("contracts"))
	box.add_child(btn)
	return box


func _muted(text: String) -> Label:
	var lbl := Label.new()
	lbl.text = text
	lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	lbl.add_theme_color_override("font_color", RealmColors.MUTED)
	return lbl


func _open_plot(plot_id: String) -> void:
	var host := get_tree().current_scene
	if host != null and host.has_method("_open_plot_detail"):
		host.call("_open_plot_detail", plot_id)


func _open_workflow_for_plot(plot_id: String) -> void:
	var ui := WorldState.get_plot_ui(plot_id)
	for b in ui.get("buildings", []):
		if not (b is Dictionary):
			continue
		var row: Dictionary = b
		if not WorldState.building_supports_production(row) and not WorldState.building_is_warehouse(row):
			continue
		_open_workflow_for_building(plot_id, row)
		return
	_open_plot(plot_id)


func _open_workflow_for_building(plot_id: String, building: Dictionary) -> void:
	var host := WorldState.find_game_shell()
	if host != null and host.has_method("open_production_workflow"):
		var pd: Dictionary = WorldState.get_plot_ui(plot_id)
		host.call("open_production_workflow", plot_id, building, pd)
