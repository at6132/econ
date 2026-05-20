extends VBoxContainer
## Laborer list with food/fuel need levels.

var fetch_callable: Callable = Callable()
var title: String = ""


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var hdr := Label.new()
	hdr.text = title
	hdr.add_theme_color_override("font_color", RealmColors.ACCENT)
	add_child(hdr)
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
	_render(list, data)


func _render(list: VBoxContainer, data: Dictionary) -> void:
	if not bool(data.get("ok", true)) and data.has("reason"):
		var err := Label.new()
		err.text = str(data.get("reason", "Error"))
		err.add_theme_color_override("font_color", RealmColors.DANGER)
		list.add_child(err)
		return
	var rows: Variant = data.get("laborers", [])
	if rows is Array:
		for item in rows as Array:
			if item is Dictionary:
				list.add_child(_laborer_row(item as Dictionary))


func _laborer_row(laborer: Dictionary) -> VBoxContainer:
	var box := VBoxContainer.new()
	var name_lbl := Label.new()
	name_lbl.text = str(laborer.get("display_name", laborer.get("laborer_id", "?")))
	name_lbl.add_theme_color_override("font_color", RealmColors.TEXT)
	box.add_child(name_lbl)

	var health := float(laborer.get("health", 1.0))
	var dots := ""
	for i in range(5):
		dots += "●" if health >= (i + 1) * 0.2 else "○"
	var health_lbl := Label.new()
	health_lbl.text = dots
	health_lbl.add_theme_font_size_override("font_size", 10)
	health_lbl.modulate = Color(0.4, 0.9, 0.5) if health >= 0.6 else Color(0.9, 0.5, 0.3)
	box.add_child(health_lbl)

	var needs: Dictionary = laborer.get("needs", {}) as Dictionary
	var food_pct := int(float(needs.get("food", 1.0)) * 100.0)
	var fuel_pct := int(float(needs.get("fuel", 1.0)) * 100.0)
	var needs_lbl := Label.new()
	needs_lbl.text = "Food: %d%%  Fuel: %d%%" % [food_pct, fuel_pct]
	needs_lbl.add_theme_font_size_override("font_size", 9)
	needs_lbl.modulate = Color(1.0, 0.5, 0.3) if food_pct < 50 else Color(0.6, 0.6, 0.6)
	box.add_child(needs_lbl)

	var meta := Label.new()
	meta.text = "skill %d · %s" % [
		int(laborer.get("skill_level", 0)),
		"employed" if bool(laborer.get("employed", false)) else "open",
	]
	meta.add_theme_font_size_override("font_size", 9)
	meta.add_theme_color_override("font_color", RealmColors.MUTED)
	box.add_child(meta)
	return box
