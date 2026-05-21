extends VBoxContainer


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var sc := PanelUI.make_scroll_list()
	var list := PanelUI.list_inner(sc)
	add_child(sc)
	add_child(_list_form())
	refresh_list(list)


func refresh_list(list: VBoxContainer) -> void:
	API.get_loans_market(func(d: Dictionary) -> void:
		PanelUI.clear_children(list)
		for row in d.get("listings", d.get("loans", [])) as Array:
			if row is Dictionary:
				list.add_child(_listing_row(row as Dictionary))
	)


func _listing_row(d: Dictionary) -> VBoxContainer:
	var box := VBoxContainer.new()
	var cid := str(d.get("contract_id", d.get("loan_id", "")))
	var lbl := Label.new()
	lbl.text = "%s · ask %s · principal %s" % [
		cid,
		WorldState.format_money(int(d.get("ask_cents", d.get("ask_price_cents", 0)))),
		WorldState.format_money(int(d.get("principal_cents", 0))),
	]
	lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(lbl)
	var buy := Button.new()
	buy.text = "Buy note"
	buy.pressed.connect(func() -> void:
		API.buy_loan_on_market(cid, func(r: Dictionary) -> void:
			if bool(r.get("ok", false)):
				MainFeedback.toast("Loan purchased")
			else:
				MainFeedback.toast(str(r.get("reason", "Failed")), true)
		)
	)
	box.add_child(buy)
	return box


func _list_form() -> VBoxContainer:
	var box := VBoxContainer.new()
	var title := Label.new()
	title.text = "List your loan on secondary market"
	title.add_theme_color_override("font_color", RealmColors.ACCENT)
	box.add_child(title)
	var cid := LineEdit.new()
	cid.placeholder_text = "Loan / contract id"
	box.add_child(cid)
	var ask := SpinBox.new()
	ask.prefix = "Ask ¢ "
	ask.min_value = 1
	ask.value = 1000
	box.add_child(ask)
	var btn := Button.new()
	btn.text = "List"
	PanelUI.style_btn(btn, true)
	btn.pressed.connect(func() -> void:
		API.list_loan_for_sale(cid.text.strip_edges(), int(ask.value), func(r: Dictionary) -> void:
			if bool(r.get("ok", false)):
				MainFeedback.toast("Listed")
			else:
				MainFeedback.toast(str(r.get("reason", "Failed")), true)
		)
	)
	box.add_child(btn)
	return box
