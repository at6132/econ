extends VBoxContainer
## Live bulk-shipping calculator — calls GET /shipping/estimate.

var _plots: Array = []


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	_build_form()
	_refresh_plot_options()
	WorldState.world_updated.connect(_on_world_updated)


func _on_world_updated() -> void:
	_refresh_plot_options()


func _build_form() -> void:
	var grid := GridContainer.new()
	grid.columns = 2
	add_child(grid)

	var from_lbl := Label.new()
	from_lbl.text = "From plot"
	grid.add_child(from_lbl)
	var from_sel := OptionButton.new()
	from_sel.name = "FromPlotSelect"
	from_sel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	from_sel.item_selected.connect(func(_i): _refresh_estimate())
	grid.add_child(from_sel)

	var to_lbl := Label.new()
	to_lbl.text = "To plot"
	grid.add_child(to_lbl)
	var to_in := LineEdit.new()
	to_in.name = "ToPlotInput"
	to_in.placeholder_text = "p-x-y"
	to_in.text_changed.connect(func(_t): _refresh_estimate())
	grid.add_child(to_in)

	var mat_lbl := Label.new()
	mat_lbl.text = "Material"
	grid.add_child(mat_lbl)
	var mat_sel := OptionButton.new()
	mat_sel.name = "MaterialSelect"
	for mid in ["grain", "coal", "timber", "stone", "brick", "lumber"]:
		mat_sel.add_item(mid, -1)
		mat_sel.set_item_metadata(mat_sel.item_count - 1, mid)
	mat_sel.item_selected.connect(func(_i): _refresh_estimate())
	grid.add_child(mat_sel)

	var qty_lbl := Label.new()
	qty_lbl.text = "Quantity"
	grid.add_child(qty_lbl)
	var qty_spin := SpinBox.new()
	qty_spin.name = "QtySpinBox"
	qty_spin.min_value = 1
	qty_spin.max_value = 9999
	qty_spin.value = 10
	qty_spin.value_changed.connect(func(_v): _refresh_estimate())
	grid.add_child(qty_spin)

	var err := Label.new()
	err.name = "ErrorLabel"
	err.add_theme_color_override("font_color", RealmColors.DANGER)
	add_child(err)

	var panel := PanelContainer.new()
	panel.name = "EstimatePanel"
	panel.visible = false
	var est_vbox := VBoxContainer.new()
	panel.add_child(est_vbox)
	for node_name in [
		"DistanceLabel",
		"TripCostLabel",
		"PerUnitLabel",
		"TotalFeeLabel",
		"BreakevenLabel",
		"WarningLabel",
		"ProfitLabel",
	]:
		var lbl := Label.new()
		lbl.name = node_name
		lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		est_vbox.add_child(lbl)
	add_child(panel)

	var ship_btn := Button.new()
	ship_btn.text = "Dispatch shipment"
	PanelUI.style_btn(ship_btn)
	ship_btn.pressed.connect(_on_dispatch_pressed)
	add_child(ship_btn)


func _refresh_plot_options() -> void:
	var sel: OptionButton = get_node_or_null("FromPlotSelect") as OptionButton
	if sel == null:
		return
	sel.clear()
	_plots = []
	var party := WorldState.party_id
	for pid in WorldState.plots.keys():
		var row: Dictionary = WorldState.plots[pid] as Dictionary
		if str(row.get("owner", "")) != party:
			continue
		_plots.append(str(pid))
		sel.add_item(str(pid), -1)
		sel.set_item_metadata(sel.item_count - 1, str(pid))
	if sel.item_count > 0:
		_refresh_estimate()


func _refresh_estimate() -> void:
	var from_sel: OptionButton = get_node_or_null("FromPlotSelect") as OptionButton
	var to_in: LineEdit = get_node_or_null("ToPlotInput") as LineEdit
	var qty_spin: SpinBox = get_node_or_null("QtySpinBox") as SpinBox
	var panel: PanelContainer = get_node_or_null("EstimatePanel") as PanelContainer
	var err_lbl: Label = get_node_or_null("ErrorLabel") as Label
	if from_sel == null or to_in == null or qty_spin == null:
		return
	if from_sel.item_count == 0:
		return
	var from_pid: String = str(from_sel.get_item_metadata(from_sel.selected))
	var to_pid: String = to_in.text.strip_edges()
	var qty: int = int(qty_spin.value)
	if from_pid.is_empty() or to_pid.is_empty() or qty <= 0:
		if panel:
			panel.hide()
		return
	API.get_shipping_estimate(from_pid, to_pid, qty, _on_estimate_received)


func _on_estimate_received(data: Dictionary) -> void:
	var panel: PanelContainer = get_node_or_null("EstimatePanel") as PanelContainer
	var err_lbl: Label = get_node_or_null("ErrorLabel") as Label
	if not bool(data.get("ok", false)):
		if panel:
			panel.hide()
		if err_lbl:
			err_lbl.text = str(data.get("reason", "Cannot estimate"))
		return
	if err_lbl:
		err_lbl.text = ""
	if panel:
		panel.show()
	var trip := int(data.get("trip_cost_cents", 0))
	var per_u := int(data.get("per_unit_cents", 0))
	var total := int(data.get("total_fee_cents", 0))
	var dist := int(data.get("distance_tiles", 0))
	var brkevn := int(data.get("breakeven_qty", 0))
	_set_lbl("DistanceLabel", "%d tiles" % dist)
	_set_lbl("TripCostLabel", "Trip cost: %s (fixed)" % WorldState.format_money(trip))
	_set_lbl("PerUnitLabel", "Per unit: %s" % WorldState.format_money(per_u))
	_set_lbl("TotalFeeLabel", "Total fee: %s" % WorldState.format_money(total))
	_set_lbl("BreakevenLabel", "Breakeven qty: %d units" % brkevn)
	var warn: Label = get_node_or_null("EstimatePanel/WarningLabel") as Label
	if warn:
		if data.get("is_uncharted"):
			warn.text = "⚠ Uncharted route — 2× cost. Register a route for 50% savings."
			warn.show()
		elif data.get("is_ocean"):
			warn.text = "🌊 Ocean route — 1.5× cost."
			warn.show()
		else:
			warn.hide()
	var mat_sel: OptionButton = get_node_or_null("MaterialSelect") as OptionButton
	var profit_lbl: Label = get_node_or_null("EstimatePanel/ProfitLabel") as Label
	if mat_sel and profit_lbl:
		var mat_id: String = str(mat_sel.get_item_metadata(mat_sel.selected))
		var market_price := _best_bid_cents(mat_id)
		if market_price > 0:
			var qty_spin: SpinBox = get_node_or_null("QtySpinBox") as SpinBox
			var q := int(qty_spin.value) if qty_spin else 1
			var profit_per_unit := market_price - per_u
			var profit_total := profit_per_unit * q
			profit_lbl.text = (
				"Profit: %s/unit = %s total"
				% [
					WorldState.format_money(profit_per_unit),
					WorldState.format_money(profit_total),
				]
			)
			profit_lbl.modulate = (
				Color(0.3, 1.0, 0.4) if profit_per_unit > 0 else Color(1.0, 0.4, 0.4)
			)
		else:
			profit_lbl.text = ""


func _best_bid_cents(material_id: String) -> int:
	var best := 0
	for row in WorldState.market_bids_rows:
		if not (row is Dictionary):
			continue
		var d: Dictionary = row as Dictionary
		if str(d.get("material", "")) != material_id:
			continue
		best = maxi(best, int(d.get("price_per_unit_cents", 0)))
	if best > 0:
		return best
	var cached: Variant = WorldState.market_bids.get(material_id)
	if cached is Array and not (cached as Array).is_empty():
		var first: Variant = (cached as Array)[0]
		if first is Dictionary:
			return int((first as Dictionary).get("price_per_unit_cents", 0))
	return 0


func _set_lbl(node_name: String, text: String) -> void:
	var lbl: Label = get_node_or_null("EstimatePanel/%s" % node_name) as Label
	if lbl:
		lbl.text = text


func _on_dispatch_pressed() -> void:
	var from_sel: OptionButton = get_node_or_null("FromPlotSelect") as OptionButton
	var to_in: LineEdit = get_node_or_null("ToPlotInput") as LineEdit
	var mat_sel: OptionButton = get_node_or_null("MaterialSelect") as OptionButton
	var qty_spin: SpinBox = get_node_or_null("QtySpinBox") as SpinBox
	if from_sel == null or to_in == null or mat_sel == null or qty_spin == null:
		return
	var from_pid: String = str(from_sel.get_item_metadata(from_sel.selected))
	var to_pid: String = to_in.text.strip_edges()
	var mat_id: String = str(mat_sel.get_item_metadata(mat_sel.selected))
	API.ship(from_pid, to_pid, mat_id, int(qty_spin.value), func(r: Dictionary) -> void:
		if bool(r.get("ok", false)):
			_refresh_estimate()
			API.get_world_player(func(_p: Dictionary) -> void: pass, WorldState.party_id)
		elif get_node_or_null("ErrorLabel"):
			(get_node_or_null("ErrorLabel") as Label).text = str(r.get("reason", r.get("detail", "Failed")))
	)


func refresh() -> void:
	_refresh_estimate()
