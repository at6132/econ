extends VBoxContainer
## Browse public / visible blueprints from GET /blueprints.


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var sc := PanelUI.make_scroll_list()
	var list := PanelUI.list_inner(sc)
	add_child(sc)
	var refresh_btn := Button.new()
	refresh_btn.text = "Refresh catalog"
	PanelUI.style_btn(refresh_btn)
	refresh_btn.pressed.connect(_load.bind(list))
	add_child(refresh_btn)
	_load(list)


func _load(list: VBoxContainer) -> void:
	API.get_blueprints(func(d: Dictionary) -> void:
		WorldState.merge_blueprints_list(d.get("blueprints", []))
		PanelUI.clear_children(list)
		for bp in d.get("blueprints", []) as Array:
			if bp is Dictionary:
				list.add_child(_bp_row(bp as Dictionary))
	)


func _bp_row(bp: Dictionary) -> VBoxContainer:
	var box := VBoxContainer.new()
	var bid := str(bp.get("blueprint_id", bp.get("id", "")))
	var title := Label.new()
	title.text = "%s — %s" % [bp.get("name", bid), bp.get("category", "")]
	title.add_theme_color_override("font_color", RealmColors.ACCENT)
	box.add_child(title)
	var desc := Label.new()
	desc.text = str(bp.get("description", "")).substr(0, 200)
	desc.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(desc)
	var meta := Label.new()
	meta.text = "%d×%d · license %s · by %s" % [
		int(bp.get("footprint_w", 0)),
		int(bp.get("footprint_h", 0)),
		WorldState.format_money(int(bp.get("license_fee_cents", 0))),
		bp.get("created_by", bp.get("owner", "?")),
	]
	box.add_child(meta)
	var use := Button.new()
	use.text = "Open in Build"
	use.pressed.connect(func() -> void:
		var host := get_tree().current_scene
		if host != null and host.has_method("open_build_panel"):
			host.call("open_build_panel", "", {})
			MainFeedback.toast("Select plot in Build — blueprint %s" % bid)
	)
	box.add_child(use)
	return box
