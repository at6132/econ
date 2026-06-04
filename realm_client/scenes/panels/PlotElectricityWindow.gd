extends CanvasLayer
## Full plot electricity UI — flow/routing + providers/contracts (web parity).

const PANEL_W := 920.0
const PANEL_H := 620.0

var _plot_id: String = ""
var _party: String = "player"
var _data: Dictionary = {}
var _busy: bool = false

var _status_lbl: Label
var _block_lbl: Label
var _msg_lbl: Label
var _flow_col: PanelContainer
var _providers_col: PanelContainer
var _contract_layer: CanvasLayer
var _contract_text: TextEdit
var _contract_agree: CheckBox
var _contract_provider: String = ""
var _contract_rate: int = 0
var _title_lbl: Label

signal closed


func _ready() -> void:
	layer = 48
	_build_main_ui()
	_build_contract_overlay()


func setup(plot_id: String, party: String = "player") -> void:
	_plot_id = plot_id
	_party = party if party != "" else "player"
	if _title_lbl:
		_title_lbl.text = "Electricity — %s" % _plot_id
	_reload()


func _build_main_ui() -> void:
	var dim := _make_dim(Callable(self, "_close"))
	add_child(dim)

	var panel := Panel.new()
	panel.name = "MainPanel"
	var vp := get_viewport().get_visible_rect().size
	panel.position = Vector2((vp.x - PANEL_W) * 0.5, maxf(48.0, (vp.y - PANEL_H) * 0.5))
	panel.size = Vector2(PANEL_W, minf(PANEL_H, vp.y - 64.0))
	PanelUI.style_panel(panel)
	add_child(panel)

	var root := VBoxContainer.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.offset_left = 14
	root.offset_top = 14
	root.offset_right = -14
	root.offset_bottom = -14
	root.add_theme_constant_override("separation", 8)
	panel.add_child(root)

	var head := HBoxContainer.new()
	_title_lbl = Label.new()
	_title_lbl.text = "Electricity"
	_title_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_title_lbl.add_theme_font_size_override("font_size", 16)
	_title_lbl.add_theme_color_override("font_color", RealmColors.ACCENT)
	head.add_child(_title_lbl)
	var close_btn := Button.new()
	close_btn.text = "✕"
	PanelUI.style_btn(close_btn)
	close_btn.pressed.connect(_close)
	head.add_child(close_btn)
	root.add_child(head)

	_status_lbl = Label.new()
	_status_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_status_lbl.add_theme_font_size_override("font_size", 11)
	_status_lbl.add_theme_color_override("font_color", RealmColors.MUTED)
	root.add_child(_status_lbl)

	var cols := HBoxContainer.new()
	cols.size_flags_vertical = Control.SIZE_EXPAND_FILL
	cols.add_theme_constant_override("separation", 10)
	root.add_child(cols)

	_flow_col = _make_column_panel("Flow & routing")
	cols.add_child(_flow_col)
	_providers_col = _make_column_panel("Providers & contracts")
	cols.add_child(_providers_col)

	_block_lbl = Label.new()
	_block_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_block_lbl.add_theme_font_size_override("font_size", 11)
	_block_lbl.add_theme_color_override("font_color", Color(0.79, 0.64, 0.15))
	root.add_child(_block_lbl)

	_msg_lbl = Label.new()
	_msg_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_msg_lbl.add_theme_font_size_override("font_size", 11)
	_msg_lbl.add_theme_color_override("font_color", RealmColors.DANGER)
	root.add_child(_msg_lbl)


func _make_column_panel(section_title: String) -> PanelContainer:
	var pc := PanelContainer.new()
	pc.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	pc.size_flags_stretch_ratio = 1.0
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.1, 0.1, 0.12)
	sb.set_content_margin_all(8)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.22)
	pc.add_theme_stylebox_override("panel", sb)
	var v := VBoxContainer.new()
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	v.add_theme_constant_override("separation", 6)
	pc.add_child(v)
	var hdr := Label.new()
	hdr.text = section_title
	hdr.add_theme_font_size_override("font_size", 13)
	hdr.add_theme_color_override("font_color", RealmColors.ACCENT)
	v.add_child(hdr)
	var sc := ScrollContainer.new()
	sc.size_flags_vertical = Control.SIZE_EXPAND_FILL
	sc.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	var inner := VBoxContainer.new()
	inner.name = "Inner"
	inner.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	inner.add_theme_constant_override("separation", 6)
	sc.add_child(inner)
	v.add_child(sc)
	return pc


func _col_inner(col: PanelContainer) -> VBoxContainer:
	return col.get_child(0).get_child(1).get_node("Inner") as VBoxContainer


func _build_contract_overlay() -> void:
	_contract_layer = CanvasLayer.new()
	_contract_layer.layer = 52
	_contract_layer.visible = false
	add_child(_contract_layer)

	var dim := _make_dim(Callable(self, "_close_contract"))
	_contract_layer.add_child(dim)

	var panel := Panel.new()
	panel.custom_minimum_size = Vector2(520, 460)
	var vp := get_viewport().get_visible_rect().size
	panel.position = Vector2((vp.x - 520.0) * 0.5, (vp.y - 460.0) * 0.5)
	panel.size = Vector2(520, 460)
	PanelUI.style_panel(panel)
	_contract_layer.add_child(panel)

	var root := VBoxContainer.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.offset_left = 14
	root.offset_top = 14
	root.offset_right = -14
	root.offset_bottom = -14
	root.add_theme_constant_override("separation", 8)
	panel.add_child(root)

	var head := HBoxContainer.new()
	var title := Label.new()
	title.text = "Utility contract"
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.add_theme_font_size_override("font_size", 15)
	title.add_theme_color_override("font_color", RealmColors.ACCENT)
	head.add_child(title)
	var x := Button.new()
	x.text = "✕"
	PanelUI.style_btn(x)
	x.pressed.connect(_close_contract)
	head.add_child(x)
	root.add_child(head)

	_contract_text = TextEdit.new()
	_contract_text.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_contract_text.editable = false
	_contract_text.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	root.add_child(_contract_text)

	_contract_agree = CheckBox.new()
	_contract_agree.text = "I have read and agree to the terms of this grid power supply agreement."
	root.add_child(_contract_agree)

	var actions := HBoxContainer.new()
	actions.add_theme_constant_override("separation", 8)
	var sign_btn := Button.new()
	sign_btn.text = "Sign contract"
	PanelUI.style_btn(sign_btn, true)
	sign_btn.pressed.connect(_on_sign_contract)
	actions.add_child(sign_btn)
	var cancel_btn := Button.new()
	cancel_btn.text = "Cancel"
	PanelUI.style_btn(cancel_btn)
	cancel_btn.pressed.connect(_close_contract)
	actions.add_child(cancel_btn)
	root.add_child(actions)


func _make_dim(on_click: Callable) -> ColorRect:
	var dim := ColorRect.new()
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	dim.color = Color(0, 0, 0, 0.58)
	dim.mouse_filter = Control.MOUSE_FILTER_STOP
	dim.gui_input.connect(
		func(ev: InputEvent) -> void:
			if ev is InputEventMouseButton and (ev as InputEventMouseButton).pressed:
				on_click.call()
	)
	return dim


func _close() -> void:
	if _contract_layer != null and _contract_layer.visible:
		_close_contract()
		return
	closed.emit()
	queue_free()


func _close_contract() -> void:
	_contract_layer.visible = false
	_contract_agree.button_pressed = false


func _reload() -> void:
	if _plot_id.is_empty():
		return
	API.get_plot_energy(
		_plot_id,
		func(data: Dictionary) -> void:
			if not is_instance_valid(self):
				return
			_data = data
			_render(),
		_party,
	)


func _power_dict() -> Dictionary:
	if _data.get("power") is Dictionary:
		return _data["power"] as Dictionary
	return _data


func _flow_dict() -> Dictionary:
	if _data.get("energy_flow") is Dictionary:
		return _data["energy_flow"] as Dictionary
	return {}


func _cfg_dict() -> Dictionary:
	if _data.get("utility_config") is Dictionary:
		return _data["utility_config"] as Dictionary
	var flow := _flow_dict()
	if flow.get("config") is Dictionary:
		return flow["config"] as Dictionary
	return {}


func _active_connections() -> Array:
	var out: Array = []
	for c in _data.get("connections", []) as Array:
		if c is Dictionary and str((c as Dictionary).get("status", "")) == "active":
			out.append(c)
	return out


func _access_status_label() -> String:
	var mode := str(_data.get("access_mode", ""))
	match mode:
		"own_generation":
			return "Self-supplied"
		"utility_contract":
			return "%d contract(s)" % _active_connections().size()
		"requires_contract":
			return "Needs contract"
		"unpowered":
			return "Off grid"
		_:
			if bool(_power_dict().get("powered", false)):
				return "On grid"
			return "Electricity"


func _render() -> void:
	_msg_lbl.text = ""
	var pw := _power_dict()
	var note := str(pw.get("status_note", "Grid"))
	var price := int(pw.get("clearing_price_cents", 0))
	var brownout := bool(pw.get("brownout", false))
	var may := bool(_data.get("may_draw_grid_energy", false))
	_status_lbl.text = (
		"%s · clearing %d¢/kWh%s · %s"
		% [
			note,
			price,
			" · brownout" if brownout else "",
			"authorized" if may else "not authorized",
		]
	)
	var block := str(_data.get("block_reason", ""))
	_block_lbl.text = block
	_block_lbl.visible = not block.is_empty()

	_render_flow_column()
	_render_providers_column()


func _render_flow_column() -> void:
	var inner := _col_inner(_flow_col)
	PanelUI.clear_children(inner)
	var flow := _flow_dict()
	var load_kwh := float(flow.get("load_wh_today", 0)) / 1000.0
	_add_help(inner, "Load today: %.1f kWh" % load_kwh)

	_add_subhead(inner, "Sources")
	var sources: Array = flow.get("sources", [])
	if sources.is_empty():
		_add_help(inner, "No on-plot generators.")
	else:
		for s in sources:
			if s is Dictionary:
				var row: Dictionary = s
				var own := " (yours)" if bool(row.get("own", false)) else ""
				_add_bullet(
					inner,
					"%s — %.1f kWh/day%s"
					% [row.get("label", "?"), float(row.get("capacity_wh_per_day", 0)) / 1000.0, own]
				)

	_add_subhead(inner, "Storage")
	var storage: Array = flow.get("storage", [])
	if storage.is_empty():
		_add_help(inner, "No battery banks on plot.")
	else:
		for b in storage:
			if b is Dictionary:
				var row: Dictionary = b
				_add_bullet(
					inner,
					"%s — %.1f / %.1f kWh"
					% [
						row.get("label", "?"),
						float(row.get("stored_wh", 0)) / 1000.0,
						float(row.get("capacity_wh", 0)) / 1000.0,
					]
				)

	_add_subhead(inner, "Consumers")
	var consumers: Array = flow.get("consumers", [])
	if consumers.is_empty():
		_add_help(inner, "No active consumers.")
	else:
		for c in consumers:
			if c is Dictionary:
				var row: Dictionary = c
				var extra := ""
				if int(row.get("draw_wh_per_batch", 0)) > 0:
					extra = " — %.1f kWh/batch" % (float(row.get("draw_wh_per_batch", 0)) / 1000.0)
				_add_bullet(inner, "%s%s" % [row.get("label", "?"), extra])

	var conns := _active_connections()
	if not conns.is_empty():
		_add_subhead(inner, "Supply routing")
		_render_routing_controls(inner, conns, storage)


func _render_routing_controls(parent: VBoxContainer, conns: Array, storage: Array) -> void:
	var cfg := _cfg_dict()
	var primary_id := str(cfg.get("primary_connection_id", ""))
	var backup_ids: Array = cfg.get("backup_connection_ids", [])
	var battery_ids: Array = cfg.get("battery_instance_ids", [])

	var prim_row := HBoxContainer.new()
	var prim_lbl := Label.new()
	prim_lbl.text = "Primary provider"
	prim_lbl.custom_minimum_size.x = 110
	prim_row.add_child(prim_lbl)
	var prim_opt := OptionButton.new()
	prim_opt.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	prim_opt.add_item("—", 0)
	prim_opt.set_item_metadata(0, "")
	var sel_idx := 0
	for i in conns.size():
		var c: Dictionary = conns[i]
		var cid := str(c.get("connection_id", ""))
		var item_label := "%s (%d¢/kWh)" % [c.get("provider_name", c.get("provider", "?")), int(c.get("rate_cents_per_kwh", 0))]
		prim_opt.add_item(item_label)
		prim_opt.set_item_metadata(i + 1, cid)
		if cid == primary_id:
			sel_idx = i + 1
	prim_opt.selected = sel_idx
	prim_opt.item_selected.connect(
		func(idx: int) -> void:
			if _busy:
				return
			_save_config({"primary_connection_id": str(prim_opt.get_item_metadata(idx))})
	)
	prim_row.add_child(prim_opt)
	parent.add_child(prim_row)

	_add_subhead(parent, "Backup providers (multi-select)")
	var backup_list := ItemList.new()
	backup_list.custom_minimum_size = Vector2(0, 72)
	backup_list.select_mode = ItemList.SELECT_MULTI
	for c in conns:
		var row: Dictionary = c as Dictionary
		var cid := str(row.get("connection_id", ""))
		var idx := backup_list.add_item(str(row.get("provider_name", row.get("provider", "?"))))
		backup_list.set_item_metadata(idx, cid)
		if cid in backup_ids:
			backup_list.select(idx)
	backup_list.item_selected.connect(func(_i: int) -> void: _on_backup_list_changed(backup_list))
	backup_list.multi_selected.connect(func(_i: int, _s: bool) -> void: _on_backup_list_changed(backup_list))
	parent.add_child(backup_list)

	if not storage.is_empty():
		_add_subhead(parent, "Battery backup banks")
		var bat_list := ItemList.new()
		bat_list.custom_minimum_size = Vector2(0, 60)
		bat_list.select_mode = ItemList.SELECT_MULTI
		for b in storage:
			if b is Dictionary:
				var row: Dictionary = b
				var iid := str(row.get("instance_id", ""))
				var idx := bat_list.add_item("%s (%s)" % [row.get("label", "?"), iid])
				bat_list.set_item_metadata(idx, iid)
				if iid in battery_ids:
					bat_list.select(idx)
		bat_list.item_selected.connect(func(_i: int) -> void: _on_battery_list_changed(bat_list))
		bat_list.multi_selected.connect(func(_i: int, _s: bool) -> void: _on_battery_list_changed(bat_list))
		parent.add_child(bat_list)


func _on_backup_list_changed(list: ItemList) -> void:
	if _busy:
		return
	var ids: Array = []
	for i in list.get_selected_items():
		ids.append(str(list.get_item_metadata(i)))
	_save_config({"backup_connection_ids": ids})


func _on_battery_list_changed(list: ItemList) -> void:
	if _busy:
		return
	var ids: Array = []
	for i in list.get_selected_items():
		ids.append(str(list.get_item_metadata(i)))
	_save_config({"battery_instance_ids": ids})


func _save_config(patch: Dictionary) -> void:
	if _busy:
		return
	_busy = true
	API.configure_grid_utility(
		_plot_id,
		patch,
		func(res: Dictionary) -> void:
			_busy = false
			if not is_instance_valid(self):
				return
			if bool(res.get("ok", false)):
				_reload()
				API.get_world_player(func(p: Dictionary) -> void: WorldState.apply_player(p), _party)
			else:
				_msg_lbl.text = str(res.get("reason", "Config failed")),
		_party,
	)


func _render_providers_column() -> void:
	var inner := _col_inner(_providers_col)
	PanelUI.clear_children(inner)

	_add_subhead(inner, "Available")
	var offers: Array = _data.get("provider_offers", [])
	if offers.is_empty():
		_add_help(inner, "No third-party grid providers in this region.")
	else:
		for o in offers:
			if o is Dictionary:
				inner.add_child(_make_provider_card(o as Dictionary, true))

	_add_subhead(inner, "Signed on this plot")
	var conns := _active_connections()
	if conns.is_empty():
		_add_help(inner, "No active contracts.")
	else:
		for c in conns:
			if c is Dictionary:
				inner.add_child(_make_provider_card(c as Dictionary, false))


func _make_provider_card(row: Dictionary, is_offer: bool) -> PanelContainer:
	var pc := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.09, 0.09, 0.11)
	sb.set_content_margin_all(8)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.18)
	pc.add_theme_stylebox_override("panel", sb)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 4)
	pc.add_child(v)

	var name_lbl := Label.new()
	if is_offer:
		name_lbl.text = str(row.get("display_name", row.get("provider_party", "?")))
	else:
		name_lbl.text = str(row.get("provider_name", row.get("provider", "?")))
	name_lbl.add_theme_color_override("font_color", RealmColors.TEXT)
	v.add_child(name_lbl)

	var detail := Label.new()
	detail.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	detail.add_theme_font_size_override("font_size", 11)
	detail.add_theme_color_override("font_color", RealmColors.MUTED)
	if is_offer:
		detail.text = (
			"%d¢/kWh · cap %.1f kWh/day\nContract band: %.1f–%.1f kWh/day"
			% [
				int(row.get("rate_cents_per_kwh", 0)),
				float(row.get("capacity_kwh_per_day", 0)),
				float(row.get("min_kwh_per_day", 0)),
				float(row.get("max_kwh_per_day", 0)),
			]
		)
	else:
		detail.text = (
			"%d¢/kWh · role %s\n%.1f–%.1f kWh/day"
			% [
				int(row.get("rate_cents_per_kwh", 0)),
				row.get("role", "standby"),
				float(row.get("min_wh_per_day", 0)) / 1000.0,
				float(row.get("max_wh_per_day", 0)) / 1000.0,
			]
		)
	v.add_child(detail)

	var btn_row := HBoxContainer.new()
	if is_offer:
		var provider := str(row.get("provider_party", ""))
		var btn := Button.new()
		btn.text = "Connected" if bool(row.get("already_connected", false)) else "Select"
		btn.disabled = _busy or bool(row.get("already_connected", false))
		PanelUI.style_btn(btn, not btn.disabled)
		btn.pressed.connect(func() -> void: _open_contract(provider))
		btn_row.add_child(btn)
	else:
		var cid := str(row.get("connection_id", ""))
		var btn := Button.new()
		btn.text = "Cancel"
		btn.disabled = _busy
		PanelUI.style_btn(btn)
		btn.pressed.connect(func() -> void: _disconnect(cid))
		btn_row.add_child(btn)
	v.add_child(btn_row)
	return pc


func _add_subhead(parent: Node, text: String) -> void:
	var lbl := Label.new()
	lbl.text = text
	lbl.add_theme_font_size_override("font_size", 12)
	lbl.add_theme_color_override("font_color", Color(0.82, 0.78, 0.65))
	parent.add_child(lbl)


func _add_help(parent: Node, text: String) -> void:
	var lbl := Label.new()
	lbl.text = text
	lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	lbl.add_theme_font_size_override("font_size", 11)
	lbl.add_theme_color_override("font_color", RealmColors.MUTED)
	parent.add_child(lbl)


func _add_bullet(parent: Node, text: String) -> void:
	var lbl := Label.new()
	lbl.text = "• " + text
	lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	lbl.add_theme_font_size_override("font_size", 11)
	lbl.add_theme_color_override("font_color", RealmColors.TEXT)
	parent.add_child(lbl)


func _open_contract(provider: String) -> void:
	if _busy or provider.is_empty():
		return
	_busy = true
	API.get_grid_utility_contract_preview(
		_plot_id,
		provider,
		func(res: Dictionary) -> void:
			_busy = false
			if not is_instance_valid(self):
				return
			if not bool(res.get("ok", false)):
				_msg_lbl.text = str(res.get("reason", "Preview failed"))
				return
			_contract_provider = provider
			_contract_rate = int(res.get("rate_cents_per_kwh", 0))
			_contract_text.text = str(res.get("contract_text", ""))
			_contract_agree.button_pressed = false
			_contract_layer.visible = true,
		_party,
	)


func _on_sign_contract() -> void:
	if _busy or _contract_provider.is_empty() or not _contract_agree.button_pressed:
		return
	_busy = true
	_close_contract()
	API.connect_grid_utility(
		_plot_id,
		_contract_provider,
		_contract_rate,
		func(res: Dictionary) -> void:
			_busy = false
			if not is_instance_valid(self):
				return
			if bool(res.get("ok", false)):
				_msg_lbl.text = "Signed contract %s" % str(res.get("connection_id", ""))
				_reload()
				API.get_world_player(func(p: Dictionary) -> void: WorldState.apply_player(p), _party)
			else:
				_msg_lbl.text = str(res.get("reason", "Connect failed")),
		_party,
	)


func _disconnect(connection_id: String) -> void:
	if _busy or connection_id.is_empty():
		return
	_busy = true
	API.disconnect_grid_utility(
		connection_id,
		func(res: Dictionary) -> void:
			_busy = false
			if not is_instance_valid(self):
				return
			if bool(res.get("ok", false)):
				MainFeedback.toast("Contract cancelled")
				_reload()
				API.get_world_player(func(p: Dictionary) -> void: WorldState.apply_player(p), _party)
			else:
				_msg_lbl.text = str(res.get("reason", "Disconnect failed")),
		_party,
	)
