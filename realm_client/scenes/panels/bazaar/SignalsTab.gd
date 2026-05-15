extends VBoxContainer
## Public market signals + configurable price alerts.

@onready var signals_list: VBoxContainer = %SignalsList
@onready var flows_list: VBoxContainer = %FlowsList
@onready var alerts_list: VBoxContainer = %AlertsList
@onready var alert_mat_select: OptionButton = %MaterialSelect
@onready var alert_condition: OptionButton = %ConditionSelect
@onready var alert_threshold: SpinBox = %ThresholdSpinBox
@onready var add_alert_btn: Button = %AddAlertBtn
@onready var refresh_btn: Button = %RefreshBtn


func _ready() -> void:
	_style_btn(refresh_btn)
	_style_btn(add_alert_btn)
	alert_condition.add_item("above")
	alert_condition.add_item("below")
	_populate_material_select()
	alert_condition.select(0)
	add_alert_btn.pressed.connect(_on_add_alert)
	refresh_btn.pressed.connect(_refresh)
	_refresh()


func _style_btn(btn: Button) -> void:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.12, 0.12, 0.14)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.55)
	btn.add_theme_stylebox_override("normal", sb)
	btn.add_theme_color_override("font_color", Color(0.9, 0.88, 0.82))


func _populate_material_select() -> void:
	alert_mat_select.clear()
	for i in range(BazaarMaterials.ALL_MATERIALS.size()):
		var m := str(BazaarMaterials.ALL_MATERIALS[i])
		alert_mat_select.add_item(m.replace("_", " ").capitalize())
		alert_mat_select.set_item_metadata(i, m)


func _refresh() -> void:
	_load_signals()
	_load_alerts()


func _load_signals() -> void:
	for c in signals_list.get_children():
		c.queue_free()
	for c in flows_list.get_children():
		c.queue_free()
	API.get_market_signals(_on_market_signals_loaded)


func _on_market_signals_loaded(data: Dictionary) -> void:
	var activity: Variant = data.get("region_activity", [])
	if activity is Array and not (activity as Array).is_empty():
		for item in activity as Array:
			if item is Dictionary:
				signals_list.add_child(_make_activity_row(item as Dictionary))
	else:
		var lbl := Label.new()
		lbl.text = "No regional supply concentration to show (empty book)."
		lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		lbl.add_theme_color_override("font_color", Color(0.65, 0.65, 0.68))
		signals_list.add_child(lbl)
	var flows: Variant = data.get("trade_flows", [])
	if flows is Array and not (flows as Array).is_empty():
		var ft := Label.new()
		ft.text = "Trade flows (recent route traffic)"
		ft.add_theme_font_size_override("font_size", 12)
		ft.add_theme_color_override("font_color", Color(0.88, 0.86, 0.78))
		flows_list.add_child(ft)
		for frow in flows as Array:
			if frow is Dictionary:
				flows_list.add_child(_make_flow_row(frow as Dictionary))


func _make_activity_row(info: Dictionary) -> PanelContainer:
	var pc := PanelContainer.new()
	var v := VBoxContainer.new()
	pc.add_child(v)
	var mat := str(info.get("material", "?"))
	var pr := str(info.get("primary_region", "—"))
	var line := Label.new()
	line.text = "%s — primary region %s" % [mat.replace("_", " ").capitalize(), pr]
	line.add_theme_color_override("font_color", Color(0.92, 0.88, 0.72))
	v.add_child(line)
	var by: Variant = info.get("by_region", {})
	if by is Dictionary and not (by as Dictionary).is_empty():
		var parts: PackedStringArray = []
		for rk in (by as Dictionary).keys():
			parts.append("%s: %d" % [str(rk), int((by as Dictionary)[rk])])
		var line2 := Label.new()
		line2.text = ", ".join(parts)
		line2.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		line2.add_theme_font_size_override("font_size", 10)
		line2.add_theme_color_override("font_color", Color(0.75, 0.78, 0.9))
		v.add_child(line2)
	return pc


func _make_flow_row(d: Dictionary) -> Label:
	var lbl := Label.new()
	lbl.text = "%s → %s · %d shipments" % [
		str(d.get("from_region", "?")),
		str(d.get("to_region", "?")),
		int(d.get("shipments", 0)),
	]
	lbl.add_theme_font_size_override("font_size", 10)
	lbl.add_theme_color_override("font_color", Color(0.82, 0.9, 0.82))
	return lbl


func _load_alerts() -> void:
	for c in alerts_list.get_children():
		c.queue_free()
	API.get_price_alerts(_on_price_alerts_loaded)


func _on_price_alerts_loaded(data: Dictionary) -> void:
	var alerts: Variant = data.get("alerts", [])
	if not (alerts is Array) or (alerts as Array).is_empty():
		var lbl := Label.new()
		lbl.text = "No price alerts configured."
		lbl.modulate = Color(0.55, 0.55, 0.58)
		lbl.add_theme_color_override("font_color", Color(0.85, 0.83, 0.78))
		alerts_list.add_child(lbl)
		return
	for a in alerts as Array:
		if a is Dictionary:
			alerts_list.add_child(_make_alert_row(a as Dictionary))


func _make_alert_row(alert: Dictionary) -> HBoxContainer:
	var row := HBoxContainer.new()
	var mat: String = str(alert.get("material", "?"))
	var cond: String = str(alert.get("condition", "?"))
	var thresh: int = int(alert.get("threshold_cents", 0))
	var lbl := Label.new()
	lbl.text = "%s %s %d¢" % [mat.replace("_", " ").capitalize(), cond, thresh]
	lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	lbl.add_theme_color_override("font_color", Color(0.9, 0.88, 0.82))
	row.add_child(lbl)
	var del_btn := Button.new()
	del_btn.text = "✕"
	del_btn.custom_minimum_size.x = 36
	var alert_id: String = str(alert.get("alert_id", ""))
	del_btn.pressed.connect(_on_delete_alert_pressed.bind(alert_id))
	row.add_child(del_btn)
	return row


func _on_add_alert() -> void:
	var idx := alert_mat_select.selected
	if idx < 0:
		return
	var mat: String = str(alert_mat_select.get_item_metadata(idx))
	var cond: String = "above" if alert_condition.selected == 0 else "below"
	var thresh: int = int(alert_threshold.value)
	if thresh <= 0:
		return
	API.post_price_alert(mat, cond, thresh, _on_price_alert_posted, WorldState.party_id)


func _on_delete_alert_pressed(alert_id: String) -> void:
	API.delete_price_alert(alert_id, _on_price_alert_deleted)


func _on_price_alert_deleted(_data: Dictionary) -> void:
	_load_alerts()


func _on_price_alert_posted(data: Dictionary) -> void:
	if bool(data.get("ok", false)):
		_load_alerts()
