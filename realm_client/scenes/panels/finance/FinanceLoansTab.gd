extends VBoxContainer
## Bank loans — apply, view, repay.

var _loans_list: VBoxContainer
var _status: Label


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var form := GridContainer.new()
	form.columns = 2
	form.add_theme_constant_override("v_separation", 8)

	form.add_child(_lbl("Principal ($)"))
	var principal := SpinBox.new()
	principal.min_value = 100
	principal.max_value = 1_000_000
	principal.value = 5000
	principal.name = "PrincipalSpin"
	form.add_child(principal)

	form.add_child(_lbl("Term (cycles)"))
	var cycles := SpinBox.new()
	cycles.min_value = 1
	cycles.max_value = 120
	cycles.value = 12
	form.add_child(cycles)

	form.add_child(_lbl("Collateral plot"))
	var collat := LineEdit.new()
	collat.placeholder_text = "optional plot id"
	collat.name = "CollateralInput"
	form.add_child(collat)

	add_child(form)

	var apply_btn := Button.new()
	apply_btn.text = "Apply for loan"
	PanelUI.style_btn(apply_btn, true)
	apply_btn.pressed.connect(
		func() -> void:
			var cents := int(principal.value) * 100
			var plot_id := collat.text.strip_edges()
			API.apply_for_loan(
				cents,
				int(cycles.value),
				func(r: Dictionary) -> void:
					if bool(r.get("ok", false)):
						MainFeedback.toast("Loan application submitted")
						refresh()
						API.get_world_player(func(p): WorldState.apply_player(p), WorldState.party_id)
					else:
						_status.text = str(r.get("reason", r.get("detail", "Failed"))),
				WorldState.party_id,
				plot_id,
			)
	)
	add_child(apply_btn)

	var hdr := Label.new()
	hdr.text = "Active loans"
	hdr.add_theme_color_override("font_color", RealmColors.ACCENT)
	add_child(hdr)

	var sc := PanelUI.make_scroll_list()
	sc.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_loans_list = PanelUI.list_inner(sc)
	add_child(sc)

	_status = Label.new()
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(_status)

	WorldState.player_updated.connect(refresh)
	refresh()


func _lbl(t: String) -> Label:
	var l := Label.new()
	l.text = t
	return l


func refresh() -> void:
	PanelUI.clear_children(_loans_list)
	API.get_bank_loans(
		func(data: Dictionary) -> void:
			if not is_instance_valid(_loans_list):
				return
			var rows: Variant = data.get("loans", data.get("active_loans", []))
			if not (rows is Array) or (rows as Array).is_empty():
				_loans_list.add_child(_muted("No active bank loans."))
				return
			for row in rows as Array:
				if row is Dictionary:
					_loans_list.add_child(_loan_row(row as Dictionary)),
		WorldState.party_id,
	)


func _loan_row(loan: Dictionary) -> VBoxContainer:
	var box := VBoxContainer.new()
	var lid := str(loan.get("loan_id", loan.get("id", "")))
	var lbl := Label.new()
	lbl.text = "%s — principal %s · owed %s · %s cycles left" % [
		lid,
		WorldState.format_money(int(loan.get("principal_cents", 0))),
		WorldState.format_money(int(loan.get("balance_cents", loan.get("owed_cents", 0)))),
		str(loan.get("cycles_remaining", "?")),
	]
	box.add_child(lbl)
	var repay := Button.new()
	repay.text = "Repay in full"
	PanelUI.style_btn(repay, true)
	repay.pressed.connect(
		func() -> void:
			API.repay_bank_loan(
				lid,
				func(r: Dictionary) -> void:
					if bool(r.get("ok", false)):
						MainFeedback.toast("Loan repaid")
						refresh()
						API.get_world_player(func(p): WorldState.apply_player(p), WorldState.party_id)
					else:
						_status.text = str(r.get("reason", "Repay failed")),
			)
	)
	box.add_child(repay)
	return box


func _muted(t: String) -> Label:
	var l := Label.new()
	l.text = t
	l.add_theme_color_override("font_color", RealmColors.MUTED)
	return l
