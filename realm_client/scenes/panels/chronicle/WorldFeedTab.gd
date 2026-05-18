extends VBoxContainer
## World feed log with category filter chips.

var _filter: String = "All"
var _chip_row: HBoxContainer
var _scroll: ScrollContainer
var _list: VBoxContainer


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	_chip_row = HBoxContainer.new()
	_chip_row.add_theme_constant_override("separation", 6)
	add_child(_chip_row)
	_rebuild_chips()
	_scroll = PanelUI.make_scroll_list()
	_list = PanelUI.list_inner(_scroll)
	add_child(_scroll)
	WorldState.feed_updated.connect(_refresh)
	WorldState.world_updated.connect(_refresh)
	call_deferred("_refresh")


func refresh() -> void:
	_refresh()


func _rebuild_chips() -> void:
	PanelUI.clear_children(_chip_row)
	for cat in ChronicleFeedStyles.FILTER_CATEGORIES:
		var btn := Button.new()
		btn.text = cat
		btn.toggle_mode = true
		btn.button_pressed = cat == _filter
		PanelUI.style_btn(btn, cat == _filter)
		btn.pressed.connect(_on_chip.bind(cat))
		_chip_row.add_child(btn)


func _on_chip(cat: String) -> void:
	_filter = cat
	_rebuild_chips()
	_refresh()


func _refresh() -> void:
	PanelUI.clear_children(_list)
	var entries: Array = WorldState.world_feed_log.duplicate()
	entries.reverse()
	var shown := 0
	for row in entries:
		if shown >= 200:
			break
		if not (row is Dictionary):
			continue
		var d: Dictionary = row as Dictionary
		var kind: String = str(d.get("kind", d.get("feed_source", "world_feed")))
		if _filter != "All" and ChronicleFeedStyles.category_for_kind(kind) != _filter:
			continue
		_list.add_child(_make_row(d, kind, shown % 2 == 1))
		shown += 1
	if shown == 0:
		var lbl := Label.new()
		lbl.text = "No feed entries yet. Advance ticks to see world events."
		lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		lbl.add_theme_color_override("font_color", RealmColors.MUTED)
		_list.add_child(lbl)


func _make_row(d: Dictionary, kind: String, alt: bool) -> PanelContainer:
	var style: Dictionary = ChronicleFeedStyles.style_for_kind(kind)
	var is_digest := kind == "weekly_digest" or "weekly_digest" in kind
	var pc := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.1, 0.1, 0.12) if alt else Color(0.08, 0.08, 0.1)
	if is_digest:
		sb.border_width_top = 2
		sb.border_width_bottom = 2
		sb.border_color = RealmColors.ACCENT
	pc.add_theme_stylebox_override("panel", sb)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	pc.add_child(row)
	var icon := Label.new()
	icon.text = str(style.get("icon", "•"))
	icon.custom_minimum_size.x = 28
	row.add_child(icon)
	var msg := Label.new()
	msg.text = str(d.get("message", ""))
	msg.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	msg.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	msg.add_theme_color_override("font_color", RealmColors.TEXT)
	if is_digest:
		msg.add_theme_font_size_override("font_size", 15)
	row.add_child(msg)
	var tick: int = int(d.get("tick", 0))
	var day: int = (tick / maxi(1, WorldState.ticks_per_game_day)) + 1
	var day_lbl := Label.new()
	day_lbl.text = "Day %d" % day
	day_lbl.add_theme_font_size_override("font_size", 11)
	day_lbl.add_theme_color_override("font_color", RealmColors.MUTED)
	row.add_child(day_lbl)
	return pc
