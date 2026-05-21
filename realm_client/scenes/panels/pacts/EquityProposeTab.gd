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
		var k := str((c as Dictionary).get("kind", "")) if c is Dictionary else ""
		if k in ["equity_stake", "equity"]:
			list.add_child(_row(c as Dictionary))


func _row(d: Dictionary) -> Label:
	var l := Label.new()
	l.text = "%s · %s%% · invest %s · %s" % [
		d.get("business_id", "?"),
		float(int(d.get("ownership_pct_bps", 0))) / 100.0,
		WorldState.format_money(int(d.get("investment_cents", 0))),
		d.get("status", "?"),
	]
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	return l


func _form() -> VBoxContainer:
	var box := VBoxContainer.new()
	box.add_child(_lbl("Propose equity stake (you are issuer)"))
	var investor := LineEdit.new()
	investor.placeholder_text = "Investor party id"
	box.add_child(investor)
	var biz := LineEdit.new()
	biz.placeholder_text = "Business id"
	box.add_child(biz)
	var pct := SpinBox.new()
	pct.prefix = "Ownership bps "
	pct.min_value = 1
	pct.max_value = 9999
	pct.value = 1000
	box.add_child(pct)
	var invest := SpinBox.new()
	invest.prefix = "Investment ¢ "
	invest.min_value = 1
	invest.value = 50_000
	box.add_child(invest)
	var btn := Button.new()
	btn.text = "Propose stake"
	PanelUI.style_btn(btn, true)
	btn.pressed.connect(func() -> void:
		API.propose_equity_stake({
			"issuer": WorldState.party_id,
			"investor": investor.text.strip_edges(),
			"business_id": biz.text.strip_edges(),
			"ownership_pct_bps": int(pct.value),
			"investment_cents": int(invest.value),
		}, func(r: Dictionary) -> void:
			if bool(r.get("ok", false)):
				MainFeedback.toast("Equity proposed")
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
