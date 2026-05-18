class_name PactsTabs
extends RefCounted


static func make_supply_tab() -> Control:
	var root := VBoxContainer.new()
	root.size_flags_vertical = Control.SIZE_EXPAND_FILL
	var list_sc := PanelUI.make_scroll_list()
	var list := PanelUI.list_inner(list_sc)
	root.add_child(list_sc)
	root.set_meta("list", list)
	var form := _supply_form(root)
	root.add_child(form)
	root.set_script(preload("res://scenes/panels/pacts/SupplyTabLogic.gd"))
	return root


static func _supply_form(root: VBoxContainer) -> Control:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 6)
	var title := Label.new()
	title.text = "Propose supply contract"
	title.add_theme_color_override("font_color", RealmColors.ACCENT)
	box.add_child(title)
	var cp := LineEdit.new()
	cp.placeholder_text = "Counterparty party ID"
	cp.name = "Counterparty"
	box.add_child(cp)
	var mat := OptionButton.new()
	for i in range(BazaarMaterials.ALL_MATERIALS.size()):
		var m := str(BazaarMaterials.ALL_MATERIALS[i])
		mat.add_item(m)
		mat.set_item_metadata(i, m)
	mat.name = "Material"
	box.add_child(mat)
	var qty := SpinBox.new()
	qty.name = "Qty"
	qty.min_value = 1
	qty.value = 10
	box.add_child(qty)
	var price := SpinBox.new()
	price.name = "Price"
	price.min_value = 1
	price.value = 100
	box.add_child(price)
	var btn := Button.new()
	btn.text = "Propose Contract"
	PanelUI.style_btn(btn, true)
	btn.pressed.connect(func() -> void:
		var material: String = str(mat.get_item_metadata(mat.selected))
		API.propose_supply_contract(
			{
				"supplier": WorldState.party_id,
				"buyer": cp.text.strip_edges(),
				"material": material,
				"qty": int(qty.value),
				"total_price_cents": int(price.value),
				"due_in_ticks": 1440,
			},
			func(d: Dictionary) -> void:
				if bool(d.get("ok", false)):
					MainFeedback.toast("Supply contract proposed")
					root.refresh()
				else:
					MainFeedback.toast(str(d.get("reason", "Failed")), true)
		)
	)
	box.add_child(btn)
	return box


static func make_contract_list_tab(filter_kinds: Array, title: String) -> Control:
	var root := VBoxContainer.new()
	root.size_flags_vertical = Control.SIZE_EXPAND_FILL
	var sc := PanelUI.make_scroll_list()
	var list := PanelUI.list_inner(sc)
	root.add_child(sc)
	root.set_meta("filter_kinds", filter_kinds)
	root.set_meta("list", list)
	root.set_meta("title", title)
	root.set_script(preload("res://scenes/panels/pacts/ContractListTabLogic.gd"))
	return root


static func make_p2p_strip() -> PanelContainer:
	var pc := PanelContainer.new()
	var v := VBoxContainer.new()
	pc.add_child(v)
	var hdr := Label.new()
	hdr.text = "▼ Direct Trade (P2P)"
	hdr.add_theme_color_override("font_color", RealmColors.ACCENT)
	v.add_child(hdr)
	var row := HBoxContainer.new()
	var give_mat := OptionButton.new()
	var get_mat := OptionButton.new()
	for i in range(BazaarMaterials.ALL_MATERIALS.size()):
		var m := str(BazaarMaterials.ALL_MATERIALS[i])
		give_mat.add_item(m)
		give_mat.set_item_metadata(i, m)
		get_mat.add_item(m)
		get_mat.set_item_metadata(i, m)
	var give_qty := SpinBox.new()
	give_qty.min_value = 1
	give_qty.value = 1
	var cash := SpinBox.new()
	cash.name = "CashCents"
	var cp := LineEdit.new()
	cp.placeholder_text = "Counterparty"
	var btn := Button.new()
	btn.text = "Propose trade"
	btn.pressed.connect(func() -> void:
		API.p2p_trade(
			{
				"party": WorldState.party_id,
				"counterparty": cp.text.strip_edges(),
				"give_material": str(give_mat.get_item_metadata(give_mat.selected)),
				"give_qty": int(give_qty.value),
				"want_material": str(get_mat.get_item_metadata(get_mat.selected)),
				"want_qty": 0,
				"want_cents": int(cash.value),
			},
			func(d: Dictionary) -> void:
				if bool(d.get("ok", false)):
					MainFeedback.toast("P2P trade proposed")
				else:
					MainFeedback.toast(str(d.get("reason", "Failed")), true)
		)
	)
	row.add_child(give_mat)
	row.add_child(give_qty)
	row.add_child(get_mat)
	row.add_child(cash)
	row.add_child(cp)
	row.add_child(btn)
	v.add_child(row)
	return pc
