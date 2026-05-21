extends VBoxContainer


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var sc := PanelUI.make_scroll_list()
	var list := PanelUI.list_inner(sc)
	add_child(sc)
	var jobs_lbl := Label.new()
	jobs_lbl.name = "Jobs"
	add_child(jobs_lbl)
	_refresh(list, jobs_lbl)


func _refresh(list: VBoxContainer, jobs_lbl: Label) -> void:
	API.get_assay_book(func(book: Dictionary) -> void:
		PanelUI.clear_children(list)
		for row in book.get("minerals", book.get("progress", [])) as Array:
			if row is Dictionary:
				var l := Label.new()
				l.text = str(row)
				l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
				list.add_child(l)
		for rid in book.get("discovered_recipe_ids", book.get("recipes", [])) as Array:
			var l2 := Label.new()
			l2.text = "Recipe: %s" % str(rid)
			l2.add_theme_color_override("font_color", RealmColors.ACCENT)
			list.add_child(l2)
	)
	API.get_assay_status(func(st: Dictionary) -> void:
		var jobs: Array = st.get("jobs", [])
		if jobs.is_empty():
			jobs_lbl.text = "No active assays"
		else:
			jobs_lbl.text = "Active: %s" % str(jobs)
	)
