extends VBoxContainer

var _alerts_list: VBoxContainer
var _mat_select: OptionButton
var _cond_above: Button
var _cond_below: Button
var _threshold: SpinBox
var _condition: String = "above"


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var title := Label.new()
	title.text = "Active alerts"
	title.add_theme_color_override("font_color", RealmColors.ACCENT)
	add_child(title)
	_alerts_list = VBoxContainer.new()
	add_child(_alerts_list)
	var sep := HSeparator.new()
	add_child(sep)
	var form_title := Label.new()
	form_title.text = "Add alert"
	form_title.add_theme_color_override("font_color", RealmColors.ACCENT)
	add_child(form_title)
	var form := HBoxContainer.new()
	form.add_theme_constant_override("separation", 8)
	add_child(form)
	_mat_select = OptionButton.new()
	_mat_select.custom_minimum_size.x = 160
	for i in range(BazaarMaterials.ALL_MATERIALS.size()):
		var m := str(BazaarMaterials.ALL_MATERIALS[i])
		_mat_select.add_item(m.replace("_", " ").capitalize())
		_mat_select.set_item_metadata(i, m)
	form.add_child(_mat_select)
	_cond_above = Button.new()
	_cond_above.text = "above ▲"
	_cond_above.toggle_mode = true
	_cond_above.button_pressed = true
	_cond_above.pressed.connect(func() -> void: _set_condition("above"))
	form.add_child(_cond_above)
	_cond_below = Button.new()
	_cond_below.text = "below ▼"
	_cond_below.toggle_mode = true
	_cond_below.pressed.connect(func() -> void: _set_condition("below"))
	form.add_child(_cond_below)
	_threshold = SpinBox.new()
	_threshold.min_value = 1
	_threshold.max_value = 999_999
	_threshold.value = 100
	_threshold.prefix = ""
	_threshold.suffix = "¢"
	form.add_child(_threshold)
	var add_btn := Button.new()
	add_btn.text = "+ Add Alert"
	PanelUI.style_btn(add_btn, true)
	add_btn.pressed.connect(_on_add)
	form.add_child(add_btn)
	var helper := Label.new()
	helper.text = "Alerts appear in the World Feed when triggered — no interruptions."
	helper.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	helper.add_theme_color_override("font_color", RealmColors.MUTED)
	helper.add_theme_font_size_override("font_size", 12)
	add_child(helper)
	_load_alerts()


func refresh() -> void:
	_load_alerts()


func _set_condition(c: String) -> void:
	_condition = c
	_cond_above.button_pressed = c == "above"
	_cond_below.button_pressed = c == "below"


func _load_alerts() -> void:
	PanelUI.clear_children(_alerts_list)
	API.get_price_alerts(_on_alerts_loaded, WorldState.party_id)


func _on_alerts_loaded(data: Dictionary) -> void:
	var alerts: Variant = data.get("alerts", WorldState.player_price_alerts)
	if not (alerts is Array) or (alerts as Array).is_empty():
		var lbl := Label.new()
		lbl.text = "No price alerts configured."
		lbl.add_theme_color_override("font_color", RealmColors.MUTED)
		_alerts_list.add_child(lbl)
		return
	for a in alerts as Array:
		if a is Dictionary:
			_alerts_list.add_child(_make_row(a as Dictionary))


func _make_row(alert: Dictionary) -> HBoxContainer:
	var row := HBoxContainer.new()
	var mat: String = str(alert.get("material", "?"))
	var cond: String = str(alert.get("condition", "?"))
	var thresh: int = int(alert.get("threshold_cents", 0))
	var triggered: bool = bool(alert.get("triggered", alert.get("is_triggered", false)))
	var lbl := Label.new()
	var arrow := "▲" if cond == "above" else "▼"
	lbl.text = "%s %s %d¢" % [mat.replace("_", " ").capitalize(), arrow, thresh]
	lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	lbl.add_theme_color_override("font_color", RealmColors.ACCENT if triggered else RealmColors.TEXT)
	row.add_child(lbl)
	var del_btn := Button.new()
	del_btn.text = "✕"
	var alert_id: String = str(alert.get("alert_id", ""))
	del_btn.pressed.connect(func() -> void:
		API.delete_price_alert(alert_id, func(_d: Dictionary) -> void: _load_alerts())
	)
	row.add_child(del_btn)
	return row


func _on_add() -> void:
	var idx := _mat_select.selected
	if idx < 0:
		return
	var mat: String = str(_mat_select.get_item_metadata(idx))
	var thresh: int = int(_threshold.value)
	API.post_price_alert(
		mat,
		_condition,
		thresh,
		func(d: Dictionary) -> void:
			if bool(d.get("ok", false)):
				_load_alerts()
				MainFeedback.toast("Price alert added")
			else:
				MainFeedback.toast(str(d.get("reason", "Alert failed")), true)
		,
		WorldState.party_id,
	)
