extends VBoxContainer


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
		if c is Dictionary and str((c as Dictionary).get("kind", "")) == "land_lease":
			list.add_child(_row(c as Dictionary))


func _row(d: Dictionary) -> Label:
	var l := Label.new()
	l.text = "Plot %s · %s · rent %s /7d" % [
		d.get("plot_id", "?"),
		d.get("status", "?"),
		WorldState.format_money(int(d.get("rent_per_7days_cents", 0))),
	]
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	return l


func _form() -> VBoxContainer:
	var box := VBoxContainer.new()
	box.add_child(_lbl("Propose land lease (you are lessor)"))
	var lessee := LineEdit.new()
	lessee.placeholder_text = "Lessee party id"
	box.add_child(lessee)
	var plot := LineEdit.new()
	plot.placeholder_text = "Plot id"
	box.add_child(plot)
	var rent := SpinBox.new()
	rent.prefix = "Rent /7d ¢ "
	rent.min_value = 1
	rent.value = 1000
	box.add_child(rent)
	var dur := SpinBox.new()
	dur.prefix = "Duration ticks "
	dur.min_value = 10080
	dur.value = 20160
	box.add_child(dur)
	var btn := Button.new()
	btn.text = "Propose lease"
	PanelUI.style_btn(btn, true)
	btn.pressed.connect(func() -> void:
		API.propose_lease({
			"lessor": WorldState.party_id,
			"lessee": lessee.text.strip_edges(),
			"plot_id": plot.text.strip_edges(),
			"rent_per_7days_cents": int(rent.value),
			"duration_ticks": int(dur.value),
		}, func(r: Dictionary) -> void:
			if bool(r.get("ok", false)):
				MainFeedback.toast("Lease proposed")
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
