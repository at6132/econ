extends VBoxContainer
## First Bank rate tiers + CPI adjustment note.

var fetch_callable: Callable = Callable()
var title: String = ""


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var hdr := Label.new()
	hdr.text = title
	hdr.add_theme_color_override("font_color", RealmColors.ACCENT)
	add_child(hdr)
	var cpi_note := Label.new()
	cpi_note.name = "CPIRateNote"
	cpi_note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	cpi_note.add_theme_font_size_override("font_size", 11)
	cpi_note.add_theme_color_override("font_color", RealmColors.MUTED)
	add_child(cpi_note)
	var sc := PanelUI.make_scroll_list()
	sc.name = "Scroll"
	add_child(sc)
	if fetch_callable.is_valid():
		refresh()


func refresh() -> void:
	if not is_inside_tree():
		return
	var sc: ScrollContainer = get_node_or_null("Scroll") as ScrollContainer
	if sc == null:
		return
	var list := PanelUI.list_inner(sc)
	PanelUI.clear_children(list)
	if not fetch_callable.is_valid():
		return
	fetch_callable.call(func(data: Dictionary) -> void: _deliver(list, data))


func _deliver(list: VBoxContainer, data: Dictionary) -> void:
	if not is_instance_valid(self) or not is_instance_valid(list):
		return
	_update_cpi_note(data)
	_render(list, data)


func _update_cpi_note(data: Dictionary) -> void:
	var note: Label = get_node_or_null("CPIRateNote") as Label
	if note == null:
		return
	var cpi := float(data.get("cpi_current", WorldState.cpi_current))
	if cpi > 102.0:
		note.text = "⬆ Rates elevated due to inflation (CPI %.1f)" % cpi
	elif cpi < 98.0:
		note.text = "⬇ Rates discounted due to deflation (CPI %.1f)" % cpi
	else:
		note.text = "Rates stable (CPI %.1f)" % cpi


func _render(list: VBoxContainer, data: Dictionary) -> void:
	if not bool(data.get("ok", true)) and data.has("reason"):
		var err := Label.new()
		err.text = str(data.get("reason", "Error"))
		err.add_theme_color_override("font_color", RealmColors.DANGER)
		list.add_child(err)
		return
	var tiers: Variant = data.get("tiers", [])
	if tiers is Array:
		for item in tiers as Array:
			if item is Dictionary:
				list.add_child(_tier_label(item as Dictionary))


func _tier_label(tier: Dictionary) -> Control:
	var lbl := Label.new()
	lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	var base := int(tier.get("rate_bps_per_cycle", 0))
	var eff := int(tier.get("effective_rate_bps_per_cycle", base))
	var parts: PackedStringArray = [
		"%s tier" % str(tier.get("tier", "?")),
		"base %d bps/cycle" % base,
	]
	if eff != base:
		parts.append("effective %d bps/cycle" % eff)
	parts.append("max $%s" % WorldState.format_money(int(tier.get("max_principal_cents", 0))))
	if bool(tier.get("current_for_party", false)):
		parts.append("(your tier)")
	lbl.text = " · ".join(parts)
	lbl.add_theme_color_override("font_color", RealmColors.TEXT)
	return lbl
