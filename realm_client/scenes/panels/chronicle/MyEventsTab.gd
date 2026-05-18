extends VBoxContainer

var _filter: String = "All"
var _chip_row: HBoxContainer
var _scroll: ScrollContainer
var _list: VBoxContainer


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	_chip_row = HBoxContainer.new()
	add_child(_chip_row)
	_rebuild_chips()
	_scroll = PanelUI.make_scroll_list()
	_list = PanelUI.list_inner(_scroll)
	add_child(_scroll)
	WorldState.world_updated.connect(_refresh)
	call_deferred("_refresh")


func refresh() -> void:
	_refresh()


func _player_plot_ids() -> Dictionary:
	var out: Dictionary = {}
	for pid in WorldState.plots.keys():
		var pd: Dictionary = WorldState.plots[pid]
		if str(pd.get("owner", "")) == WorldState.party_id:
			out[str(pid)] = true
	return out


func _event_involves_player(d: Dictionary, owned: Dictionary) -> bool:
	if str(d.get("party", "")) == WorldState.party_id:
		return true
	var pid: String = str(d.get("plot_id", ""))
	if pid != "" and owned.has(pid):
		return true
	var msg: String = str(d.get("message", ""))
	if WorldState.party_id in msg:
		return true
	return false


func _rebuild_chips() -> void:
	PanelUI.clear_children(_chip_row)
	for cat in ChronicleFeedStyles.MY_EVENT_FILTERS:
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
	var owned := _player_plot_ids()
	var entries: Array = WorldState.event_log.duplicate()
	entries.reverse()
	var shown := 0
	for row in entries:
		if shown >= 200:
			break
		if not (row is Dictionary):
			continue
		var d: Dictionary = row as Dictionary
		if not _event_involves_player(d, owned):
			continue
		var kind: String = str(d.get("kind", ""))
		var bucket := ChronicleFeedStyles.my_event_bucket(kind)
		if _filter != "All" and bucket != _filter:
			continue
		_list.add_child(_make_row(d, kind, shown % 2 == 1))
		shown += 1
	if shown == 0:
		var lbl := Label.new()
		lbl.text = "No personal events yet."
		lbl.add_theme_color_override("font_color", RealmColors.MUTED)
		_list.add_child(lbl)


func _make_row(d: Dictionary, kind: String, alt: bool) -> PanelContainer:
	var style: Dictionary = ChronicleFeedStyles.style_for_kind(kind)
	var pc := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.1, 0.1, 0.12) if alt else Color(0.08, 0.08, 0.1)
	pc.add_theme_stylebox_override("panel", sb)
	var row := HBoxContainer.new()
	pc.add_child(row)
	var icon := Label.new()
	icon.text = str(style.get("icon", "•"))
	row.add_child(icon)
	var msg := Label.new()
	msg.text = str(d.get("message", ""))
	msg.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	msg.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	msg.add_theme_color_override("font_color", RealmColors.TEXT)
	row.add_child(msg)
	var tick: int = int(d.get("tick", 0))
	var ago_ticks: int = maxi(0, WorldState.current_tick - tick)
	var ago_lbl := Label.new()
	ago_lbl.text = "%s ago" % WorldState.format_ticks_as_gametime(ago_ticks)
	ago_lbl.add_theme_font_size_override("font_size", 11)
	ago_lbl.add_theme_color_override("font_color", RealmColors.MUTED)
	row.add_child(ago_lbl)
	return pc
