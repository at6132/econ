extends VBoxContainer
## Turnkey construction quotes and order tracking.

var _orders_list: VBoxContainer
var _status: Label


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var hint := Label.new()
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hint.add_theme_color_override("font_color", RealmColors.MUTED)
	hint.text = "Request NPC contractor quotes, accept one to place a construction order, track progress below."
	add_child(hint)

	var form := GridContainer.new()
	form.columns = 2
	form.add_theme_constant_override("v_separation", 6)
	form.add_child(_lbl("Plot"))
	var plot_in := LineEdit.new()
	plot_in.name = "PlotInput"
	plot_in.placeholder_text = "p-0-0"
	form.add_child(plot_in)
	form.add_child(_lbl("Building"))
	var bld := OptionButton.new()
	bld.name = "BuildingSelect"
	for bid in ["warehouse", "store", "power_shed", "dock", "assay_lab", "lumber_mill", "brickworks"]:
		bld.add_item(bid)
		bld.set_item_metadata(bld.item_count - 1, bid)
	form.add_child(bld)
	add_child(form)

	var quote_btn := Button.new()
	quote_btn.text = "Request quotes"
	PanelUI.style_btn(quote_btn, true)
	quote_btn.pressed.connect(_on_request_quotes.bind(plot_in, bld))
	add_child(quote_btn)

	_quotes_box = VBoxContainer.new()
	_quotes_box.name = "QuotesBox"
	add_child(_quotes_box)

	var sep := HSeparator.new()
	add_child(sep)

	var hdr := Label.new()
	hdr.text = "Your construction orders"
	hdr.add_theme_color_override("font_color", RealmColors.ACCENT)
	add_child(hdr)

	var sc := PanelUI.make_scroll_list()
	sc.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_orders_list = PanelUI.list_inner(sc)
	add_child(sc)

	_status = Label.new()
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(_status)

	WorldState.player_updated.connect(refresh)
	WorldState.world_updated.connect(refresh)
	refresh()


var _quotes_box: VBoxContainer


func _lbl(t: String) -> Label:
	var l := Label.new()
	l.text = t
	return l


func refresh() -> void:
	PanelUI.clear_children(_orders_list)
	API.get_construction_orders(
		WorldState.party_id,
		func(data: Dictionary) -> void:
			if not is_instance_valid(_orders_list):
				return
			for row in data.get("orders", []) as Array:
				if row is Dictionary:
					_orders_list.add_child(_order_row(row as Dictionary)),
	)


func _order_row(order: Dictionary) -> Label:
	var lbl := Label.new()
	lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	lbl.text = "%s on %s — %s (%s)" % [
		order.get("building_id", "?"),
		order.get("plot_id", "?"),
		order.get("status", "?"),
		order.get("contractor_party", order.get("contractor", "?")),
	]
	return lbl


func _on_request_quotes(plot_in: LineEdit, bld: OptionButton) -> void:
	var pid := plot_in.text.strip_edges()
	var building_id := str(bld.get_item_metadata(bld.selected))
	if pid.is_empty():
		_status.text = "Enter a plot id."
		return
	PanelUI.clear_children(_quotes_box)
	_status.text = "Requesting quotes…"
	API.post_construction_quotes(
		{
			"party": WorldState.party_id,
			"plot_id": pid,
			"building_id": building_id,
			"material_responsibility": "contractor",
		},
		func(data: Dictionary) -> void:
			if not bool(data.get("ok", false)):
				_status.text = str(data.get("reason", data.get("detail", "Failed")))
				return
			_status.text = ""
			for q in data.get("quotes", []) as Array:
				if q is Dictionary:
					var qd: Dictionary = q as Dictionary
					qd["building_id"] = building_id
					_quotes_box.add_child(_quote_row(qd, pid)),
	)


func _quote_row(quote: Dictionary, plot_id: String) -> HBoxContainer:
	var row := HBoxContainer.new()
	var lbl := Label.new()
	lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	lbl.text = "%s — %s · %s labor-days" % [
		quote.get("firm_party", "?"),
		WorldState.format_money(int(quote.get("quoted_price_cents", 0))),
		str(quote.get("labor_days", "?")),
	]
	row.add_child(lbl)
	var btn := Button.new()
	btn.text = "Accept"
	PanelUI.style_btn(btn, true)
	var building_id := str(quote.get("building_id", ""))
	btn.pressed.connect(
		func() -> void:
			API.accept_construction_quote(
				{
					"client": WorldState.party_id,
					"contractor": str(quote.get("firm_party", "")),
					"plot_id": plot_id,
					"building_id": building_id,
					"quoted_price_cents": int(quote.get("quoted_price_cents", 0)),
					"material_responsibility": str(quote.get("material_responsibility", "contractor")),
				},
				func(r: Dictionary) -> void:
					if bool(r.get("ok", false)):
						MainFeedback.toast("Construction order placed")
						refresh()
						API.get_world_player(func(p): WorldState.apply_player(p), WorldState.party_id)
						API.get_world(func(d): WorldState.apply_world(d))
					else:
						_status.text = str(r.get("reason", r.get("detail", "Accept failed"))),
			)
	)
	row.add_child(btn)
	return row
