extends VBoxContainer


func _ready() -> void:
	WorldState.world_updated.connect(refresh)
	call_deferred("refresh")


func refresh() -> void:
	var list: VBoxContainer = get_meta("list") as VBoxContainer
	var kinds: Array = get_meta("filter_kinds") as Array
	PanelUI.clear_children(list)
	for c in WorldState.active_contracts:
		if not (c is Dictionary):
			continue
		var d: Dictionary = c as Dictionary
		var kind: String = str(d.get("kind", ""))
		if not kinds.is_empty() and kind not in kinds:
			continue
		list.add_child(_generic_row(d))


func _generic_row(d: Dictionary) -> Label:
	var lbl := Label.new()
	lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	lbl.text = "[%s] %s" % [str(d.get("kind", "?")), str(d.get("summary", d.get("message", JSON.stringify(d))))]
	lbl.add_theme_color_override("font_color", RealmColors.TEXT)
	return lbl
