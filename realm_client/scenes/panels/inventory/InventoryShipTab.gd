extends VBoxContainer
## Dispatch bulk from a plot stash to another owned site (Option B logistics).

var _from_sel: OptionButton
var _dest_sel: OptionButton
var _mat_sel: OptionButton
var _qty_spin: SpinBox
var _err_lbl: Label
var _estimate_panel: PanelContainer
var _ship_btn: Button


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	_build_form()
	WorldState.player_updated.connect(_on_data_changed)
	WorldState.world_updated.connect(_on_data_changed)
	_on_data_changed()


func _build_form() -> void:
	var hint := Label.new()
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hint.add_theme_color_override("font_color", RealmColors.MUTED)
	hint.text = (
		"Shipments move bulk goods from one plot stash to another. "
		+ "Personal carry (tools) is not shipped here — bulk stays on plots; grid power is not a commodity."
	)
	add_child(hint)

	var grid := GridContainer.new()
	grid.columns = 2
	grid.add_theme_constant_override("h_separation", 10)
	grid.add_theme_constant_override("v_separation", 8)

	grid.add_child(_label("Source plot (stock on site)"))
	_from_sel = OptionButton.new()
	_from_sel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_from_sel.item_selected.connect(func(_i: int) -> void: _on_origin_changed())
	grid.add_child(_from_sel)

	grid.add_child(_label("Destination"))
	_dest_sel = OptionButton.new()
	_dest_sel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_dest_sel.item_selected.connect(func(_i: int) -> void: _refresh_estimate())
	grid.add_child(_dest_sel)

	grid.add_child(_label("Material"))
	_mat_sel = OptionButton.new()
	_mat_sel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_mat_sel.item_selected.connect(func(_i: int) -> void: _refresh_estimate())
	grid.add_child(_mat_sel)

	grid.add_child(_label("Quantity"))
	_qty_spin = SpinBox.new()
	_qty_spin.min_value = 1
	_qty_spin.max_value = 99999
	_qty_spin.value = 10
	_qty_spin.value_changed.connect(func(_v: float) -> void: _refresh_estimate())
	grid.add_child(_qty_spin)

	add_child(grid)

	_err_lbl = Label.new()
	_err_lbl.add_theme_color_override("font_color", RealmColors.DANGER)
	add_child(_err_lbl)

	_estimate_panel = PanelContainer.new()
	_estimate_panel.visible = false
	var est_vbox := VBoxContainer.new()
	_estimate_panel.add_child(est_vbox)
	for node_name in [
		"DistanceLabel",
		"TripCostLabel",
		"PerUnitLabel",
		"TotalFeeLabel",
		"BreakevenLabel",
		"WarningLabel",
	]:
		var lbl := Label.new()
		lbl.name = node_name
		lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		est_vbox.add_child(lbl)
	add_child(_estimate_panel)

	_ship_btn = Button.new()
	_ship_btn.text = "Dispatch shipment"
	PanelUI.style_btn(_ship_btn, true)
	_ship_btn.pressed.connect(_on_dispatch_pressed)
	add_child(_ship_btn)


func _label(text: String) -> Label:
	var lbl := Label.new()
	lbl.text = text
	return lbl


func _on_data_changed() -> void:
	_refresh_plot_selectors()
	_refresh_materials()
	_refresh_estimate()


func refresh() -> void:
	_on_data_changed()


func prefill_from_row(row: Dictionary) -> void:
	var kind := str(row.get("kind", ""))
	if kind != "stash":
		_err_lbl.text = "Select a plot stash row to prefill dispatch."
		return
	var mid := str(row.get("material", ""))
	var qty: int = int(row.get("qty", 0))
	var plot_id := str(row.get("plot_id", ""))
	if mid.is_empty() or plot_id.is_empty():
		return
	_err_lbl.text = ""
	_select_origin_plot(plot_id)
	_select_material(mid)
	if qty > 0:
		_qty_spin.value = mini(qty, int(_qty_spin.max_value))
	_refresh_estimate()


func _select_material(material_id: String) -> void:
	for i in _mat_sel.item_count:
		if str(_mat_sel.get_item_metadata(i)) == material_id:
			_mat_sel.select(i)
			return


func _select_origin_plot(plot_id: String) -> void:
	for i in _from_sel.item_count:
		if str(_from_sel.get_item_metadata(i)) == plot_id:
			_from_sel.select(i)
			return


func _refresh_plot_selectors() -> void:
	var prev_origin := _origin_plot_id()
	_from_sel.clear()
	for pid in WorldState.owned_plot_ids_sorted():
		var total := 0
		var pd: Dictionary = WorldState.plots.get(pid, {})
		var stock: Variant = pd.get("output_stock", {})
		if stock is Dictionary:
			for v in (stock as Dictionary).values():
				total += WorldState.variant_to_int(v, 0)
		var suffix := "" if total <= 0 else " · %d u" % total
		_from_sel.add_item("%s%s" % [WorldState.plot_site_label(pid), suffix])
		_from_sel.set_item_metadata(_from_sel.item_count - 1, pid)
	if not prev_origin.is_empty():
		_select_origin_plot(prev_origin)
	elif _from_sel.item_count > 0:
		_from_sel.select(0)

	_dest_sel.clear()
	var last_group := ""
	for opt in WorldState.ship_destination_options():
		if not (opt is Dictionary):
			continue
		var g := str(opt.get("group", "other"))
		if g != last_group:
			last_group = g
			var sep_idx := _dest_sel.item_count
			var gtitle := str(opt.get("group_label", WorldState.logistics_site_group_label(g)))
			_dest_sel.add_item("── %s ──" % gtitle)
			_dest_sel.set_item_disabled(sep_idx, true)
			_dest_sel.set_item_metadata(sep_idx, "")
		var pid := str(opt.get("plot_id", ""))
		_dest_sel.add_item("  %s" % str(opt.get("label", pid)))
		_dest_sel.set_item_metadata(_dest_sel.item_count - 1, pid)
	if _dest_sel.item_count > 0:
		_select_first_real_destination()


func _select_first_real_destination() -> void:
	for i in _dest_sel.item_count:
		var meta := str(_dest_sel.get_item_metadata(i))
		if not meta.is_empty() and meta != _origin_plot_id():
			_dest_sel.select(i)
			return


func _on_origin_changed() -> void:
	_refresh_materials()
	_refresh_estimate()


func _refresh_materials() -> void:
	var prev := ""
	if _mat_sel.item_count > 0 and _mat_sel.selected >= 0:
		prev = str(_mat_sel.get_item_metadata(_mat_sel.selected))
	_mat_sel.clear()
	var origin := _origin_plot_id()
	if origin.is_empty():
		return
	var pd: Dictionary = WorldState.plots.get(origin, {})
	var stock: Variant = pd.get("output_stock", {})
	if not (stock is Dictionary):
		return
	var keys: Array = (stock as Dictionary).keys()
	keys.sort()
	for k in keys:
		var mid := str(k)
		if WorldState.is_carried_material(mid):
			continue
		var qty: int = WorldState.variant_to_int((stock as Dictionary)[k], 0)
		if qty <= 0:
			continue
		_mat_sel.add_item("%s (%d on site)" % [WorldState.material_display_name(mid), qty])
		_mat_sel.set_item_metadata(_mat_sel.item_count - 1, mid)
	if prev != "":
		_select_material(prev)
	elif _mat_sel.item_count > 0:
		_mat_sel.select(0)
	_refresh_qty_cap()


func _refresh_qty_cap() -> void:
	if _mat_sel.item_count == 0 or _mat_sel.selected < 0:
		return
	var mid := str(_mat_sel.get_item_metadata(_mat_sel.selected))
	var origin := _origin_plot_id()
	var have := WorldState.plot_output_stock_qty(origin, mid) if not origin.is_empty() else 0
	_qty_spin.max_value = maxi(1, have)
	if int(_qty_spin.value) > have:
		_qty_spin.value = maxi(1, have)


func _origin_plot_id() -> String:
	if _from_sel.item_count == 0 or _from_sel.selected < 0:
		return ""
	return str(_from_sel.get_item_metadata(_from_sel.selected))


func _dest_plot_id() -> String:
	if _dest_sel.item_count == 0 or _dest_sel.selected < 0:
		return ""
	return str(_dest_sel.get_item_metadata(_dest_sel.selected))


func _selected_material() -> String:
	if _mat_sel.item_count == 0 or _mat_sel.selected < 0:
		return ""
	return str(_mat_sel.get_item_metadata(_mat_sel.selected))


func _refresh_estimate() -> void:
	_refresh_qty_cap()
	var from_pid := _origin_plot_id()
	var to_pid := _dest_plot_id()
	var qty := int(_qty_spin.value)
	if from_pid.is_empty() or to_pid.is_empty() or from_pid == to_pid or qty <= 0:
		_estimate_panel.hide()
		return
	API.get_shipping_estimate(from_pid, to_pid, qty, _on_estimate_received)


func _on_estimate_received(data: Dictionary) -> void:
	if not bool(data.get("ok", false)):
		_estimate_panel.hide()
		_err_lbl.text = str(data.get("reason", "Cannot estimate"))
		return
	_err_lbl.text = ""
	_estimate_panel.show()
	_set_est_lbl("DistanceLabel", "%d tiles" % int(data.get("distance_tiles", 0)))
	_set_est_lbl("TripCostLabel", "Trip cost: %s (fixed)" % WorldState.format_money(int(data.get("trip_cost_cents", 0))))
	_set_est_lbl("PerUnitLabel", "Per unit: %s" % WorldState.format_money(int(data.get("per_unit_cents", 0))))
	_set_est_lbl("TotalFeeLabel", "Total fee: %s" % WorldState.format_money(int(data.get("total_fee_cents", 0))))
	_set_est_lbl("BreakevenLabel", "Breakeven qty: %d units" % int(data.get("breakeven_qty", 0)))
	var warn: Label = _estimate_panel.get_node_or_null("VBoxContainer/WarningLabel") as Label
	if warn:
		if data.get("is_uncharted"):
			warn.text = "Uncharted route — higher cost. Register a route to save."
			warn.show()
		elif data.get("is_ocean"):
			warn.text = "Ocean route — 1.5× cost."
			warn.show()
		else:
			warn.hide()


func _set_est_lbl(node_name: String, text: String) -> void:
	var lbl: Label = _estimate_panel.get_node_or_null("VBoxContainer/%s" % node_name) as Label
	if lbl:
		lbl.text = text


func _on_dispatch_pressed() -> void:
	var from_pid := _origin_plot_id()
	var to_pid := _dest_plot_id()
	var mat_id := _selected_material()
	var qty := int(_qty_spin.value)
	if from_pid.is_empty() or to_pid.is_empty() or mat_id.is_empty() or qty <= 0:
		_err_lbl.text = "Fill source plot, destination, material, and quantity."
		return
	if from_pid == to_pid:
		_err_lbl.text = "Source and destination must differ."
		return
	if WorldState.plot_output_stock_qty(from_pid, mat_id) < qty:
		_err_lbl.text = "Not enough %s on %s." % [mat_id, from_pid]
		return
	_ship_btn.disabled = true
	API.ship(
		from_pid,
		to_pid,
		mat_id,
		qty,
		func(r: Dictionary) -> void:
			_ship_btn.disabled = false
			if bool(r.get("ok", false)):
				_err_lbl.text = ""
				API.get_world(func(w: Dictionary) -> void: WorldState.apply_world(w))
				API.get_world_player(func(p): WorldState.apply_player(p), WorldState.party_id)
				_refresh_estimate()
				var host := get_tree().current_scene
				if host != null and host.has_method("show_feedback"):
					host.call("show_feedback", "Shipment dispatched")
			else:
				_err_lbl.text = str(r.get("reason", r.get("detail", "Dispatch failed"))),
	)
