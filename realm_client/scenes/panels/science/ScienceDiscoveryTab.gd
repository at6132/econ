extends VBoxContainer

## Capabilities, patents, custom authorship, and research progress (open-ended progression).


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var sc := PanelUI.make_scroll_list()
	var list := PanelUI.list_inner(sc)
	add_child(sc)
	var hint := Label.new()
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hint.text = "Loading discovery…"
	add_child(hint)
	_refresh(list, hint)


func _refresh(list: VBoxContainer, hint: Label) -> void:
	API.get_discovery_digest(func(digest: Dictionary) -> void:
		PanelUI.clear_children(list)
		var caps: Array = digest.get("capabilities", [])
		var cap_title := Label.new()
		cap_title.text = "Capabilities"
		cap_title.add_theme_color_override("font_color", RealmColors.ACCENT)
		list.add_child(cap_title)
		for row in caps:
			if row is not Dictionary:
				continue
			var l := Label.new()
			var unlocked: bool = bool(row.get("unlocked", false))
			l.text = "%s %s" % ["✓" if unlocked else "○", str(row.get("label", row.get("id", "")))]
			if not unlocked:
				l.add_theme_color_override("font_color", Color(0.55, 0.55, 0.58))
			l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			list.add_child(l)
		var patents: Array = digest.get("patents", [])
		if not patents.is_empty():
			var pt := Label.new()
			pt.text = "Patents: %s" % ", ".join(patents.map(func(p): return str(p)))
			pt.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			list.add_child(pt)
		var research: Dictionary = digest.get("research", {})
		var completed: Array = research.get("completed", [])
		if not completed.is_empty():
			var rt := Label.new()
			rt.text = "Research completed: %s" % ", ".join(completed.map(func(n): return str(n)))
			rt.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			list.add_child(rt)
		var active: Variant = research.get("active")
		if active is Dictionary and not active.is_empty():
			var al := Label.new()
			al.text = "In progress: %s (%s days)" % [str(active.get("node_id", "")), str(active.get("progress_days", 0))]
			list.add_child(al)
		var customs: Array = digest.get("custom_recipes", [])
		if not customs.is_empty():
			var cr := Label.new()
			cr.text = "Your custom recipes: %d" % customs.size()
			list.add_child(cr)
		var bps: Array = digest.get("blueprints_authored", [])
		if not bps.is_empty():
			var bl := Label.new()
			bl.text = "Your blueprints: %d" % bps.size()
			list.add_child(bl)
		var buildable_n := (digest.get("buildable_recipe_ids", []) as Array).size()
		hint.text = "Max custom facility size: %d cells · Buildable recipes: %d" % [int(digest.get("max_blueprint_cells", 0)), buildable_n]
	)
