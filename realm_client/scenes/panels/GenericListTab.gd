extends VBoxContainer
## Fetches API data and renders JSON-ish rows.

var endpoint: String = ""
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
	var sc: ScrollContainer = get_node("Scroll") as ScrollContainer
	var list := PanelUI.list_inner(sc)
	PanelUI.clear_children(list)
	if not fetch_callable.is_valid():
		return
	fetch_callable.call(func(data: Dictionary) -> void: _render(list, data))


func _render(list: VBoxContainer, data: Dictionary) -> void:
	if not bool(data.get("ok", true)) and data.has("reason"):
		var err := Label.new()
		err.text = str(data.get("reason", "Error"))
		err.add_theme_color_override("font_color", RealmColors.DANGER)
		list.add_child(err)
		return
	for key in data.keys():
		if key == "ok":
			continue
		var val: Variant = data[key]
		if val is Array:
			for item in val as Array:
				list.add_child(_item_label(item))
		elif val is Dictionary and not (val as Dictionary).is_empty():
			list.add_child(_item_label(val))


func _item_label(item: Variant) -> Control:
	var lbl := Label.new()
	lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	if item is Dictionary:
		lbl.text = _format_dict(item as Dictionary)
	else:
		lbl.text = str(item)
	lbl.add_theme_color_override("font_color", RealmColors.TEXT)
	return lbl


func _format_dict(d: Dictionary) -> String:
	var parts: PackedStringArray = []
	for k in d.keys():
		parts.append("%s: %s" % [str(k), str(d[k])])
	return " · ".join(parts)
