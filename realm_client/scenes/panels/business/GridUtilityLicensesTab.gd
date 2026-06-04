extends VBoxContainer
## Grid utility operator franchises — Registry tab (web Market parity).

var _status: Label
var _error: Label
var _mine_list: VBoxContainer
var _plot_opt: OptionButton
var _rate_spin: SpinBox
var _min_spin: SpinBox
var _max_spin: SpinBox
var _register_btn: Button
var _busy: bool = false
var _registry: Dictionary = {}


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	add_theme_constant_override("separation", 8)

	var hint := Label.new()
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hint.add_theme_color_override("font_color", RealmColors.MUTED)
	hint.text = (
		"Register as a regional grid operator to sell power to other players. "
		+ "Requires a registered business, a road-accessible plot with an active power shed, "
		+ "and a franchise fee. Published rates appear on consumer plots in your region."
	)
	add_child(hint)

	var mine_hdr := Label.new()
	mine_hdr.text = "My grid franchises"
	mine_hdr.add_theme_color_override("font_color", RealmColors.ACCENT)
	add_child(mine_hdr)

	var sc := PanelUI.make_scroll_list()
	sc.custom_minimum_size = Vector2(0, 160)
	_mine_list = PanelUI.list_inner(sc)
	add_child(sc)

	var form_hdr := Label.new()
	form_hdr.text = "Register franchise"
	form_hdr.add_theme_color_override("font_color", RealmColors.ACCENT)
	add_child(form_hdr)

	var form := GridContainer.new()
	form.columns = 2
	form.add_theme_constant_override("h_separation", 8)
	form.add_theme_constant_override("v_separation", 6)
	add_child(form)

	_add_form_label(form, "Plot (power shed)")
	_plot_opt = OptionButton.new()
	_plot_opt.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	form.add_child(_plot_opt)

	_add_form_label(form, "Rate (¢/kWh)")
	_rate_spin = SpinBox.new()
	_rate_spin.min_value = 1
	_rate_spin.max_value = 999
	_rate_spin.value = 12
	form.add_child(_rate_spin)

	_add_form_label(form, "Min kWh/day")
	_min_spin = SpinBox.new()
	_min_spin.min_value = 0
	_min_spin.max_value = 9999
	_min_spin.step = 0.1
	form.add_child(_min_spin)

	_add_form_label(form, "Max kWh/day (0 = auto)")
	_max_spin = SpinBox.new()
	_max_spin.min_value = 0
	_max_spin.max_value = 99999
	_max_spin.step = 0.1
	form.add_child(_max_spin)

	_register_btn = Button.new()
	_register_btn.text = "Register franchise"
	PanelUI.style_btn(_register_btn, true)
	_register_btn.pressed.connect(_on_register)
	add_child(_register_btn)

	_status = Label.new()
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_status.add_theme_color_override("font_color", RealmColors.MUTED)
	add_child(_status)

	_error = Label.new()
	_error.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_error.add_theme_color_override("font_color", RealmColors.DANGER)
	add_child(_error)

	refresh()


func refresh() -> void:
	if not is_inside_tree():
		return
	_error.text = ""
	API.get_grid_operators_registry(func(d: Dictionary) -> void: _on_registry(d), WorldState.party_id)


func _on_registry(data: Dictionary) -> void:
	if not is_instance_valid(_mine_list):
		return
	_registry = data
	PanelUI.clear_children(_mine_list)
	var fee := int(data.get("franchise_fee_cents", 2500))
	_register_btn.text = "Register franchise (%s)" % WorldState.format_money(fee)
	var has_biz := bool(data.get("has_business", false))
	if not has_biz:
		_status.text = "Register a business on the Desk tab before applying for a grid franchise."
		_register_btn.disabled = true
	else:
		_status.text = ""
		_register_btn.disabled = false

	for op in data.get("player_operators", []) as Array:
		if op is Dictionary:
			_mine_list.add_child(_operator_row(op as Dictionary))

	if _mine_list.get_child_count() == 0:
		var empty := Label.new()
		empty.text = "No grid franchises registered yet."
		empty.add_theme_color_override("font_color", RealmColors.MUTED)
		_mine_list.add_child(empty)

	_plot_opt.clear()
	var eligible: Array = []
	for p in data.get("eligible_plots", []) as Array:
		if p is Dictionary and not bool((p as Dictionary).get("already_registered", false)):
			eligible.append(p)
	var has_eligible := not eligible.is_empty()
	_register_btn.disabled = _register_btn.disabled or not has_eligible
	if not has_eligible and has_biz:
		_status.text = "Build and maintain a power shed on a road-connected plot to register."
	for p in eligible:
		var row: Dictionary = p
		var label := "%s · %s · %.1f kWh/day cap" % [
			row.get("plot_id", ""),
			row.get("region_id", ""),
			float(row.get("capacity_kwh_per_day", 0)),
		]
		_plot_opt.add_item(label)
		_plot_opt.set_item_metadata(_plot_opt.item_count - 1, str(row.get("plot_id", "")))


func _operator_row(op: Dictionary) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	var info := Label.new()
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	info.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	var status := str(op.get("status", ""))
	var suspend := str(op.get("suspend_reason", ""))
	if not suspend.is_empty():
		status += " — %s" % suspend
	info.text = "%s · %s · %d¢/kWh · %s" % [
		op.get("operator_plot", ""),
		op.get("region_id", ""),
		int(op.get("rate_cents_per_kwh", 0)),
		status,
	]
	row.add_child(info)
	if str(op.get("status", "")) == "active":
		var plot_id := str(op.get("operator_plot", ""))
		var btn := Button.new()
		btn.text = "Cancel"
		PanelUI.style_btn(btn)
		btn.pressed.connect(func() -> void: _on_cancel(plot_id))
		row.add_child(btn)
	return row


func _on_register() -> void:
	if _busy or _plot_opt.item_count == 0:
		return
	var plot_id := str(_plot_opt.get_item_metadata(_plot_opt.selected))
	if plot_id.is_empty():
		return
	_busy = true
	_error.text = ""
	var max_wh := int(_max_spin.value * 1000.0)
	API.register_grid_operator(
		plot_id,
		int(_rate_spin.value),
		int(_min_spin.value * 1000.0),
		max_wh if max_wh > 0 else -1,
		func(res: Dictionary) -> void:
			_busy = false
			if bool(res.get("ok", false)):
				MainFeedback.toast("Grid franchise registered")
				API.get_world_player(func(p: Dictionary) -> void: WorldState.apply_player(p), WorldState.party_id)
				refresh()
			else:
				_error.text = str(res.get("reason", res.get("detail", "Registration failed"))),
		WorldState.party_id,
	)


func _on_cancel(plot_id: String) -> void:
	if _busy or plot_id.is_empty():
		return
	_busy = true
	API.unregister_grid_operator(
		plot_id,
		func(res: Dictionary) -> void:
			_busy = false
			if bool(res.get("ok", false)):
				MainFeedback.toast("Franchise cancelled")
				refresh()
			else:
				_error.text = str(res.get("reason", "Cancel failed")),
		WorldState.party_id,
	)


func _add_form_label(grid: GridContainer, text: String) -> void:
	var lbl := Label.new()
	lbl.text = text
	lbl.add_theme_color_override("font_color", RealmColors.MUTED)
	grid.add_child(lbl)
