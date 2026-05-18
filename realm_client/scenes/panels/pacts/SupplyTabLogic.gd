extends VBoxContainer


func _ready() -> void:
	WorldState.world_updated.connect(refresh)
	call_deferred("refresh")


func refresh() -> void:
	var list: VBoxContainer = get_meta("list") as VBoxContainer
	PanelUI.clear_children(list)
	var party := WorldState.party_id
	for c in WorldState.active_contracts:
		if not (c is Dictionary):
			continue
		if str((c as Dictionary).get("kind", "")) != "supply_contract":
			continue
		var d: Dictionary = c as Dictionary
		if str(d.get("supplier", "")) != party and str(d.get("buyer", "")) != party:
			continue
		list.add_child(_row(d))


func _row(d: Dictionary) -> PanelContainer:
	var pc := PanelContainer.new()
	var v := VBoxContainer.new()
	pc.add_child(v)
	var mat: String = str(d.get("material", "?"))
	var qty: int = int(d.get("qty_per_cycle", d.get("qty", 0)))
	var status: String = str(d.get("status", "active"))
	var line := Label.new()
	line.text = "%s × %d/day — %s" % [mat, qty, status]
	v.add_child(line)
	var sub := Label.new()
	sub.text = "Supplier: %s → Buyer: %s" % [
		WorldState.party_label(str(d.get("supplier", ""))),
		WorldState.party_label(str(d.get("buyer", ""))),
	]
	sub.add_theme_font_size_override("font_size", 11)
	sub.add_theme_color_override("font_color", RealmColors.MUTED)
	v.add_child(sub)
	var cid: String = str(d.get("contract_id", d.get("id", "")))
	if str(d.get("supplier", "")) == WorldState.party_id and status in ["active", "due"]:
		var btn := Button.new()
		btn.text = "Fulfill"
		btn.pressed.connect(func() -> void:
			API.fulfill_supply_contract(cid, func(r: Dictionary) -> void:
				if bool(r.get("ok", false)):
					MainFeedback.toast("Fulfilled")
					refresh()
				else:
					MainFeedback.toast(str(r.get("reason", "Failed")), true)
			)
		)
		v.add_child(btn)
	if status == "proposed" and str(d.get("buyer", "")) == WorldState.party_id:
		var acc := Button.new()
		acc.text = "Accept"
		acc.pressed.connect(func() -> void:
			API.accept_supply_contract(cid, func(r: Dictionary) -> void:
				if bool(r.get("ok", false)):
					MainFeedback.toast("Accepted")
					refresh()
			)
		)
		v.add_child(acc)
	return pc
