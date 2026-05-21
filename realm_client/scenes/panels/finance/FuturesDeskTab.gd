extends VBoxContainer


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var sc := PanelUI.make_scroll_list()
	var list := PanelUI.list_inner(sc)
	add_child(sc)
	add_child(_form(list))
	_refresh(list)


func _refresh(list: VBoxContainer) -> void:
	API.get_futures_mine(WorldState.party_id, func(d: Dictionary) -> void:
		PanelUI.clear_children(list)
		for o in d.get("orders", []) as Array:
			if o is Dictionary:
				list.add_child(_row(o as Dictionary, list))
	)


func _row(o: Dictionary, list: VBoxContainer) -> HBoxContainer:
	var row := HBoxContainer.new()
	var lbl := Label.new()
	lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	lbl.text = "%s %d %s @ %s · deliver %s · %s" % [
		o.get("side", "?"),
		int(o.get("qty", 0)),
		o.get("material", "?"),
		WorldState.format_money(int(o.get("price_per_unit_cents", 0))),
		str(o.get("delivery_tick", "?")),
		o.get("status", "open"),
	]
	row.add_child(lbl)
	var oid := str(o.get("order_id", o.get("id", "")))
	if oid != "" and str(o.get("status", "open")) == "open":
		var rm := Button.new()
		rm.text = "Cancel"
		rm.pressed.connect(func() -> void:
			API.delete_futures_order(oid, WorldState.party_id, func(r: Dictionary) -> void:
				if bool(r.get("ok", false)):
					_refresh(list)
			)
		)
		row.add_child(rm)
	return row


func _form(list: VBoxContainer) -> VBoxContainer:
	var box := VBoxContainer.new()
	var title := Label.new()
	title.text = "Place futures order"
	title.add_theme_color_override("font_color", RealmColors.ACCENT)
	box.add_child(title)
	var side := OptionButton.new()
	side.add_item("buy")
	side.add_item("sell")
	box.add_child(side)
	var mat := OptionButton.new()
	for m in BazaarMaterials.ALL_MATERIALS:
		mat.add_item(str(m))
		mat.set_item_metadata(mat.item_count - 1, str(m))
	box.add_child(mat)
	var qty := SpinBox.new()
	qty.min_value = 1
	qty.value = 100
	box.add_child(qty)
	var price := SpinBox.new()
	price.prefix = "¢/unit "
	price.min_value = 1
	price.value = 50
	box.add_child(price)
	var deliv := SpinBox.new()
	deliv.prefix = "Delivery tick "
	deliv.min_value = WorldState.current_tick + 1440
	deliv.value = WorldState.current_tick + 2880
	box.add_child(deliv)
	var btn := Button.new()
	btn.text = "Submit"
	PanelUI.style_btn(btn, true)
	btn.pressed.connect(func() -> void:
		API.post_futures_order({
			"party": WorldState.party_id,
			"side": "buy" if side.selected == 0 else "sell",
			"material": str(mat.get_item_metadata(mat.selected)),
			"qty": int(qty.value),
			"price_per_unit_cents": int(price.value),
			"delivery_tick": int(deliv.value),
		}, func(r: Dictionary) -> void:
			if bool(r.get("ok", false)):
				MainFeedback.toast("Futures order placed")
				_refresh(list)
			else:
				MainFeedback.toast(str(r.get("reason", "Failed")), true)
		)
	)
	box.add_child(btn)
	return box
