extends VBoxContainer

const SERVICES := [
	"analytics_data", "route_access", "survey_reports", "market_intel",
	"recipe_license", "construction_priority", "labor_supply", "power_supply", "storage",
]


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var sc := PanelUI.make_scroll_list()
	var list := PanelUI.list_inner(sc)
	add_child(sc)
	add_child(_form())
	WorldState.player_updated.connect(_refresh.bind(list))
	_refresh(list)


func _refresh(list: VBoxContainer) -> void:
	PanelUI.clear_children(list)
	for c in WorldState.active_contracts:
		var k := str((c as Dictionary).get("kind", "")) if c is Dictionary else ""
		if k in ["service_subscription", "service"]:
			list.add_child(_row(c as Dictionary))


func _row(d: Dictionary) -> Label:
	var l := Label.new()
	l.text = "%s · fee %s · %s ticks · %s" % [
		d.get("service_id", "?"),
		WorldState.format_money(int(d.get("fee_cents", 0))),
		str(d.get("duration_ticks", "?")),
		d.get("status", "?"),
	]
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	return l


func _form() -> VBoxContainer:
	var box := VBoxContainer.new()
	box.add_child(_lbl("Propose service subscription (you are provider)"))
	var sub := LineEdit.new()
	sub.placeholder_text = "Subscriber party id"
	box.add_child(sub)
	var svc := OptionButton.new()
	for s in SERVICES:
		svc.add_item(s)
	box.add_child(svc)
	var fee := SpinBox.new()
	fee.prefix = "Fee ¢ "
	fee.min_value = 1
	fee.value = 500
	box.add_child(fee)
	var dur := SpinBox.new()
	dur.prefix = "Duration ticks "
	dur.min_value = 1440
	dur.value = 10080
	box.add_child(dur)
	var btn := Button.new()
	btn.text = "Propose service"
	PanelUI.style_btn(btn, true)
	btn.pressed.connect(func() -> void:
		API.propose_service_contract({
			"provider": WorldState.party_id,
			"subscriber": sub.text.strip_edges(),
			"service_id": SERVICES[svc.selected],
			"fee_cents": int(fee.value),
			"duration_ticks": int(dur.value),
		}, func(r: Dictionary) -> void:
			if bool(r.get("ok", false)):
				MainFeedback.toast("Service proposed")
			else:
				MainFeedback.toast(str(r.get("reason", "Failed")), true)
		)
	)
	box.add_child(btn)
	return box


func _lbl(t: String) -> Label:
	var l := Label.new()
	l.text = t
	l.add_theme_color_override("font_color", RealmColors.ACCENT)
	return l
