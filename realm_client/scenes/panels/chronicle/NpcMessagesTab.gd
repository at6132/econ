extends VBoxContainer

var _scroll: ScrollContainer
var _list: VBoxContainer


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	_scroll = PanelUI.make_scroll_list()
	_list = PanelUI.list_inner(_scroll)
	add_child(_scroll)
	WorldState.world_updated.connect(_refresh)
	call_deferred("_refresh")


func refresh() -> void:
	_refresh()


func _refresh() -> void:
	PanelUI.clear_children(_list)
	var msgs: Array = WorldState.npc_messages.duplicate()
	msgs.reverse()
	if msgs.is_empty():
		var lbl := Label.new()
		lbl.text = "Margaux hasn't reached out yet. Keep playing — she's watching."
		lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		lbl.add_theme_color_override("font_color", RealmColors.MUTED)
		_list.add_child(lbl)
		return
	for row in msgs:
		if row is Dictionary:
			_list.add_child(_make_message_card(row as Dictionary))


func _make_message_card(d: Dictionary) -> PanelContainer:
	var from_party: String = str(d.get("from_party", d.get("from", "")))
	var is_margaux := "margaux" in from_party.to_lower() or from_party == "llm_margaux"
	var pc := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.09, 0.09, 0.11)
	sb.border_width_left = 3
	if is_margaux:
		sb.border_color = RealmColors.ACCENT
	else:
		var accent: Color = Color(0.5, 0.7, 0.9)
		if d.has("owner_accent_color"):
			accent = Color(str(d.get("owner_accent_color", "#6ee7ff")))
		sb.border_color = accent
	pc.add_theme_stylebox_override("panel", sb)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 4)
	pc.add_child(v)
	var hdr := HBoxContainer.new()
	var name_lbl := Label.new()
	if is_margaux:
		name_lbl.text = "Margaux"
		name_lbl.add_theme_color_override("font_color", RealmColors.ACCENT)
	else:
		name_lbl.text = WorldState.party_label(from_party)
		name_lbl.add_theme_color_override("font_color", RealmColors.TEXT)
	name_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	hdr.add_child(name_lbl)
	var tick: int = int(d.get("tick", 0))
	var day: int = (tick / maxi(1, WorldState.ticks_per_game_day)) + 1
	var day_lbl := Label.new()
	day_lbl.text = "Day %d" % day
	day_lbl.add_theme_font_size_override("font_size", 11)
	day_lbl.add_theme_color_override("font_color", RealmColors.MUTED)
	hdr.add_child(day_lbl)
	v.add_child(hdr)
	var body := Label.new()
	body.text = str(d.get("text", d.get("message", "")))
	body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	body.add_theme_color_override("font_color", RealmColors.TEXT)
	if is_margaux:
		body.add_theme_font_override("font", null) # italic via modulate trick
		body.modulate = Color(1, 1, 1, 0.95)
	v.add_child(body)
	return pc
