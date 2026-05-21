extends VBoxContainer

const EVENTS := [
	"mine_collapse", "building_degraded", "epidemic", "storm", "drought",
	"seismic_event", "flood", "route_blocked",
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
		if c is Dictionary and str((c as Dictionary).get("kind", "")) == "insurance":
			list.add_child(_row(c as Dictionary))


func _row(d: Dictionary) -> Label:
	var l := Label.new()
	l.text = "%s → %s · %s · %s" % [
		d.get("insurer", d.get("seller", "?")),
		d.get("insured", d.get("buyer", "?")),
		d.get("status", "?"),
		d.get("covered_event_kind", ""),
	]
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	return l


func _form() -> VBoxContainer:
	var box := VBoxContainer.new()
	var title := Label.new()
	title.text = "Propose insurance"
	title.add_theme_color_override("font_color", RealmColors.ACCENT)
	box.add_child(title)
	var insured := LineEdit.new()
	insured.placeholder_text = "Insured party id"
	box.add_child(insured)
	var event := OptionButton.new()
	for e in EVENTS:
		event.add_item(e)
	box.add_child(event)
	var plot := LineEdit.new()
	plot.placeholder_text = "Covered plot id (optional)"
	box.add_child(plot)
	var payout := SpinBox.new()
	payout.prefix = "Payout ¢ "
	payout.min_value = 1
	payout.value = 10_000
	box.add_child(payout)
	var prem := SpinBox.new()
	prem.prefix = "Premium /7d ¢ "
	prem.min_value = 1
	prem.value = 500
	box.add_child(prem)
	var dur := SpinBox.new()
	dur.prefix = "Duration ticks "
	dur.min_value = 10080
	dur.value = 10080
	box.add_child(dur)
	var btn := Button.new()
	btn.text = "Propose (you are insurer)"
	PanelUI.style_btn(btn, true)
	btn.pressed.connect(func() -> void:
		API.propose_insurance({
			"insurer": WorldState.party_id,
			"insured": insured.text.strip_edges(),
			"covered_event_kind": EVENTS[event.selected],
			"covered_plot_id": plot.text.strip_edges(),
			"payout_cents": int(payout.value),
			"premium_per_7days_cents": int(prem.value),
			"duration_ticks": int(dur.value),
		}, func(r: Dictionary) -> void:
			if bool(r.get("ok", false)):
				MainFeedback.toast("Insurance proposed")
			else:
				MainFeedback.toast(str(r.get("reason", "Failed")), true)
		)
	)
	box.add_child(btn)
	return box
