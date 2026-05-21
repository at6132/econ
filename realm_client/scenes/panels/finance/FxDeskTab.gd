extends VBoxContainer

var _rates_lbl: Label
var _orders_list: VBoxContainer


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	_rates_lbl = Label.new()
	_rates_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(_rates_lbl)
	var sc := PanelUI.make_scroll_list()
	_orders_list = PanelUI.list_inner(sc)
	add_child(sc)
	add_child(_order_form())
	_refresh()
	API.get_fx_rates(func(_d): _refresh())
	API.get_fx_mine(WorldState.party_id, func(_d): _refresh())


func _refresh() -> void:
	API.get_fx_mine(WorldState.party_id, func(mine: Dictionary) -> void:
		PanelUI.clear_children(_orders_list)
		for o in mine.get("orders", []) as Array:
			if o is Dictionary:
				_orders_list.add_child(_order_row(o as Dictionary))
	)
	API.get_fx_rates(func(d: Dictionary) -> void:
		var lines: PackedStringArray = []
		for row in d.get("rates", d.get("pairs", [])) as Array:
			lines.append(str(row))
		_rates_lbl.text = "Market: " + ("\n".join(lines) if lines.size() else str(d))
	)


func _order_row(o: Dictionary) -> HBoxContainer:
	var row := HBoxContainer.new()
	var lbl := Label.new()
	lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	lbl.text = "Sell %d %s → %s (min %d) · %s" % [
		int(o.get("sell_qty", 0)),
		o.get("sell_material", "?"),
		o.get("buy_material", "?"),
		int(o.get("buy_qty_min", 0)),
		o.get("status", "open"),
	]
	row.add_child(lbl)
	var oid := str(o.get("order_id", o.get("id", "")))
	if oid != "" and str(o.get("status", "open")) == "open":
		var rm := Button.new()
		rm.text = "Cancel"
		rm.pressed.connect(func() -> void:
			API.delete_fx_order(oid, WorldState.party_id, func(r: Dictionary) -> void:
				if bool(r.get("ok", false)):
					_refresh()
			)
		)
		row.add_child(rm)
	return row


func _order_form() -> VBoxContainer:
	var box := VBoxContainer.new()
	var title := Label.new()
	title.text = "Place FX order"
	title.add_theme_color_override("font_color", RealmColors.ACCENT)
	box.add_child(title)
	var sell_m := OptionButton.new()
	var buy_m := OptionButton.new()
	for m in BazaarMaterials.ALL_MATERIALS:
		sell_m.add_item(str(m))
		sell_m.set_item_metadata(sell_m.item_count - 1, str(m))
		buy_m.add_item(str(m))
		buy_m.set_item_metadata(buy_m.item_count - 1, str(m))
	if sell_m.item_count > 1:
		buy_m.select(1)
	box.add_child(sell_m)
	var sell_q := SpinBox.new()
	sell_q.min_value = 1
	sell_q.value = 10
	box.add_child(sell_q)
	box.add_child(buy_m)
	var buy_q := SpinBox.new()
	buy_q.min_value = 1
	buy_q.value = 8
	box.add_child(buy_q)
	var btn := Button.new()
	btn.text = "Submit order"
	PanelUI.style_btn(btn, true)
	btn.pressed.connect(func() -> void:
		API.post_fx_order(
			str(sell_m.get_item_metadata(sell_m.selected)),
			int(sell_q.value),
			str(buy_m.get_item_metadata(buy_m.selected)),
			int(buy_q.value),
			func(r: Dictionary) -> void:
				if bool(r.get("ok", false)):
					MainFeedback.toast("FX order placed")
				else:
					MainFeedback.toast(str(r.get("reason", "Failed")), true)
		)
	)
	box.add_child(btn)
	return box
