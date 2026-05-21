extends VBoxContainer
## Forward contract list + propose form.


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var list_sc := PanelUI.make_scroll_list()
	var list := PanelUI.list_inner(list_sc)
	add_child(list_sc)
	add_child(_forward_form())
	WorldState.world_updated.connect(refresh)
	WorldState.player_updated.connect(refresh)
	set_meta("list", list)
	refresh()


func refresh() -> void:
	var list: VBoxContainer = get_meta("list") as VBoxContainer
	if list == null:
		return
	PanelUI.clear_children(list)
	var party := WorldState.party_id
	for c in WorldState.active_contracts:
		if not (c is Dictionary):
			continue
		if str((c as Dictionary).get("kind", "")) != "forward_contract":
			continue
		var d: Dictionary = c
		if str(d.get("seller", "")) != party and str(d.get("buyer", "")) != party:
			continue
		list.add_child(_contract_row(d))


func _contract_row(d: Dictionary) -> VBoxContainer:
	var box := VBoxContainer.new()
	var line := Label.new()
	line.text = "%s × %d @ %s/unit — %s (deliver tick %s)" % [
		d.get("material", "?"),
		int(d.get("qty", 0)),
		WorldState.format_money(int(d.get("price_per_unit_cents", 0))),
		d.get("status", "?"),
		str(d.get("delivery_tick", "?")),
	]
	box.add_child(line)
	var cid := str(d.get("contract_id", d.get("id", "")))
	if d.get("status") == "proposed" and str(d.get("buyer", "")) == WorldState.party_id:
		var acc := Button.new()
		acc.text = "Accept"
		acc.pressed.connect(
			func() -> void:
				API.accept_forward(cid, WorldState.party_id, func(r: Dictionary) -> void:
					if bool(r.get("ok", false)):
						MainFeedback.toast("Forward accepted")
						refresh()
				)
		)
		box.add_child(acc)
	if d.get("status") == "active" and str(d.get("seller", "")) == WorldState.party_id:
		var deliv := Button.new()
		deliv.text = "Deliver"
		deliv.pressed.connect(
			func() -> void:
				API.deliver_forward(cid, WorldState.party_id, func(r: Dictionary) -> void:
					if bool(r.get("ok", false)):
						MainFeedback.toast("Delivered")
						refresh()
				)
		)
		box.add_child(deliv)
	return box


func _forward_form() -> VBoxContainer:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 6)
	var title := Label.new()
	title.text = "Propose forward (hedge delivery)"
	title.add_theme_color_override("font_color", RealmColors.ACCENT)
	box.add_child(title)
	var buyer := LineEdit.new()
	buyer.placeholder_text = "Buyer party id"
	box.add_child(buyer)
	var mat := OptionButton.new()
	for i in range(BazaarMaterials.ALL_MATERIALS.size()):
		var m := str(BazaarMaterials.ALL_MATERIALS[i])
		mat.add_item(m)
		mat.set_item_metadata(i, m)
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
	var delivery := SpinBox.new()
	delivery.prefix = "Deliver at tick "
	delivery.min_value = WorldState.current_tick + 1
	delivery.max_value = WorldState.current_tick + 999_999
	delivery.value = WorldState.current_tick + 1440
	box.add_child(delivery)
	var btn := Button.new()
	btn.text = "Propose forward"
	PanelUI.style_btn(btn, true)
	btn.pressed.connect(
		func() -> void:
			API.propose_forward(
				{
					"seller": WorldState.party_id,
					"buyer": buyer.text.strip_edges(),
					"material": str(mat.get_item_metadata(mat.selected)),
					"qty": int(qty.value),
					"price_per_unit_cents": int(price.value),
					"delivery_tick": int(delivery.value),
				},
				func(d: Dictionary) -> void:
					if bool(d.get("ok", false)):
						MainFeedback.toast("Forward proposed")
						API.get_world(func(w): WorldState.apply_world(w))
						refresh()
					else:
						MainFeedback.toast(str(d.get("reason", "Failed")), true),
			)
	)
	box.add_child(btn)
	return box
