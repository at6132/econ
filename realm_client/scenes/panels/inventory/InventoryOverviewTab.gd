extends VBoxContainer
## Unified stock ledger — carried, plot stashes, in-transit.

signal ship_requested(row: Dictionary)
signal harvest_requested(plot_id: String, material: String, qty: int)

const FILTER_ALL := "All"
const FILTER_CARRIED := "Carried"
const FILTER_STASH := "Plot stash"
const FILTER_TRANSIT := "In transit"

const COL_MAT_W := 128.0
const COL_QTY_W := 52.0
const COL_LOC_W := 160.0
const COL_STATUS_W := 120.0
const COL_ACTION_W := 72.0

var _filter: String = FILTER_ALL
var _summary: Label
var _scroll: ScrollContainer
var _list: VBoxContainer
var _filter_row: HBoxContainer
var _header_row: HBoxContainer
var _empty_panel: PanelContainer


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	_build_chrome()
	WorldState.player_updated.connect(refresh)
	WorldState.world_updated.connect(refresh)
	refresh()


func _build_chrome() -> void:
	_summary = Label.new()
	_summary.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_summary.add_theme_color_override("font_color", RealmColors.MUTED)
	add_child(_summary)

	_filter_row = HBoxContainer.new()
	_filter_row.add_theme_constant_override("separation", 6)
	add_child(_filter_row)
	# Short button labels so nothing truncates in a narrow panel.
	var btn_labels: Dictionary = {
		FILTER_ALL: "All",
		FILTER_CARRIED: "Carried",
		FILTER_STASH: "Stash",
		FILTER_TRANSIT: "In transit",
	}
	for key in [FILTER_ALL, FILTER_CARRIED, FILTER_STASH, FILTER_TRANSIT]:
		var btn := Button.new()
		btn.text = str(btn_labels.get(key, key))
		btn.toggle_mode = true
		btn.button_pressed = key == _filter
		PanelUI.style_btn(btn, key == _filter)
		btn.pressed.connect(_on_filter_pressed.bind(key, btn))
		_filter_row.add_child(btn)

	_header_row = _make_header_row()
	add_child(_header_row)

	var sep := HSeparator.new()
	add_child(sep)

	_scroll = ScrollContainer.new()
	_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_scroll.custom_minimum_size = Vector2(0, 200)
	_list = VBoxContainer.new()
	_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_list.add_theme_constant_override("separation", 0)
	_scroll.add_child(_list)
	add_child(_scroll)


func _on_filter_pressed(label: String, btn: Button) -> void:
	_filter = label
	for c in _filter_row.get_children():
		if c is Button:
			var b := c as Button
			var on: bool = b == btn
			b.button_pressed = on
			PanelUI.style_btn(b, on)
	refresh()


func refresh() -> void:
	PanelUI.clear_children(_list)
	var all_rows: Array = WorldState.inventory_ledger_rows()
	var shown: Array = []
	for row in all_rows:
		if not (row is Dictionary):
			continue
		var kind: String = str(row.get("kind", ""))
		if _filter == FILTER_CARRIED and kind != "carried":
			continue
		if _filter == FILTER_STASH and kind != "stash":
			continue
		if _filter == FILTER_TRANSIT and kind != "transit":
			continue
		shown.append(row)

	var carried_n := 0
	var stash_n := 0
	var transit_n := 0
	var carried_qty := 0
	var stash_qty := 0
	var transit_qty := 0
	for row in all_rows:
		if not (row is Dictionary):
			continue
		var q: int = int(row.get("qty", 0))
		match str(row.get("kind", "")):
			"carried":
				carried_n += 1
				carried_qty += q
			"stash":
				stash_n += 1
				stash_qty += q
			"transit":
				transit_n += 1
				transit_qty += q

	_summary.text = (
		"%d lines · carried %d (%d units) · stash %d (%d) · in transit %d (%d) · est. %s"
		% [
			shown.size(),
			carried_n,
			carried_qty,
			stash_n,
			stash_qty,
			transit_n,
			transit_qty,
			WorldState.format_money(WorldState.player_inventory_value_cents),
		]
	)

	_header_row.visible = not shown.is_empty()

	if shown.is_empty():
		_list.add_child(_make_empty_state(all_rows.is_empty()))
		return

	for i in shown.size():
		_add_row(shown[i] as Dictionary)
		if i < shown.size() - 1:
			_list.add_child(_thin_sep())


func _make_empty_state(world_is_empty: bool) -> Control:
	var wrap := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.06, 0.05, 0.08, 0.9)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.2)
	sb.set_corner_radius_all(6)
	sb.set_content_margin_all(16)
	wrap.add_theme_stylebox_override("panel", sb)

	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 8)
	wrap.add_child(v)

	var title := Label.new()
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_color_override("font_color", RealmColors.ACCENT)
	title.add_theme_font_size_override("font_size", 14)

	var body := Label.new()
	body.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	body.add_theme_color_override("font_color", RealmColors.MUTED)

	if world_is_empty:
		title.text = "No inventory yet"
		body.text = (
			"Carried stock, plot stashes, and in-transit shipments all read as zero.\n"
			+ "Buy materials at the Bazaar, claim plots, or start production to populate this ledger."
		)
	else:
		match _filter:
			FILTER_CARRIED:
				title.text = "No carried stock"
				body.text = "Party inventory is empty for this filter. Other locations may still hold materials."
			FILTER_STASH:
				title.text = "No plot stashes"
				body.text = "Nothing waiting on plot output stock. Harvest or route production outputs here."
			FILTER_TRANSIT:
				title.text = "Nothing in transit"
				body.text = "No active shipments. Use Dispatch to send materials between sites."
			_:
				title.text = "No matching stock"
				body.text = "Try another filter or refresh after a trade or production run."

	v.add_child(title)
	v.add_child(body)
	return wrap


func _make_header_row() -> HBoxContainer:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	row.add_child(_col_label("Material", COL_MAT_W, false))
	row.add_child(_col_label("Qty", COL_QTY_W, true))
	row.add_child(_col_label("Location", COL_LOC_W, false))
	row.add_child(_col_label("Status", COL_STATUS_W, false))
	var act := Label.new()
	act.text = ""
	act.custom_minimum_size.x = COL_ACTION_W
	row.add_child(act)
	return row


func _add_row(row: Dictionary) -> void:
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 8)

	var mat := _col_label(
		WorldState.material_display_name(str(row.get("material", ""))),
		COL_MAT_W,
		false,
	)
	h.add_child(mat)

	var qty := _col_label(str(int(row.get("qty", 0))), COL_QTY_W, true)
	h.add_child(qty)

	var loc := _col_label(str(row.get("location", "")), COL_LOC_W, false)
	loc.clip_text = true
	loc.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	h.add_child(loc)

	var status_txt := str(row.get("status", ""))
	var status := _col_label(status_txt, COL_STATUS_W, false)
	status.clip_text = true
	status.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	status.add_theme_color_override(
		"font_color",
		Color(0.45, 0.95, 0.55) if str(row.get("kind", "")) == "transit" else Color(0.82, 0.78, 0.72),
	)
	h.add_child(status)

	var act_box := HBoxContainer.new()
	act_box.custom_minimum_size.x = COL_ACTION_W
	act_box.alignment = BoxContainer.ALIGNMENT_END
	if bool(row.get("can_ship", false)):
		var ship_btn := Button.new()
		ship_btn.text = "Ship"
		ship_btn.custom_minimum_size = Vector2(64, 28)
		PanelUI.style_btn(ship_btn, true)
		ship_btn.pressed.connect(func() -> void: ship_requested.emit(row.duplicate(true)))
		act_box.add_child(ship_btn)
	elif bool(row.get("can_harvest", false)):
		var harv_btn := Button.new()
		harv_btn.text = "Take"
		harv_btn.custom_minimum_size = Vector2(64, 28)
		PanelUI.style_btn(harv_btn)
		harv_btn.pressed.connect(
			func() -> void:
				harvest_requested.emit(
					str(row.get("plot_id", "")),
					str(row.get("material", "")),
					int(row.get("qty", 0)),
				)
		)
		act_box.add_child(harv_btn)
	else:
		act_box.add_child(_col_label("—", COL_ACTION_W, true))
	h.add_child(act_box)
	_list.add_child(h)


func _col_label(text: String, min_w: float, right: bool) -> Label:
	var l := Label.new()
	l.text = text
	l.custom_minimum_size.x = min_w
	l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	if right:
		l.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	l.add_theme_font_size_override("font_size", 12)
	return l


func _thin_sep() -> HSeparator:
	var s := HSeparator.new()
	s.add_theme_constant_override("separation", 0)
	return s
