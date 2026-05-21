extends VBoxContainer
## Register businesses from templates; view entities and linked plots.

var _mine_list: VBoxContainer
var _templates_list: VBoxContainer
var _template_sel: OptionButton
var _status: Label


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var hint := Label.new()
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hint.add_theme_color_override("font_color", RealmColors.MUTED)
	hint.text = "Register a legal entity to unlock banking tiers, tenders, and structured operations across plots."
	add_child(hint)

	var reg := _register_form()
	add_child(reg)

	var sep := HSeparator.new()
	add_child(sep)

	var mine_hdr := Label.new()
	mine_hdr.text = "My businesses"
	mine_hdr.add_theme_color_override("font_color", RealmColors.ACCENT)
	add_child(mine_hdr)
	var sc1 := PanelUI.make_scroll_list()
	sc1.custom_minimum_size = Vector2(0, 140)
	_mine_list = PanelUI.list_inner(sc1)
	add_child(sc1)

	var tpl_hdr := Label.new()
	tpl_hdr.text = "Templates"
	tpl_hdr.add_theme_color_override("font_color", RealmColors.ACCENT)
	add_child(tpl_hdr)
	var sc2 := PanelUI.make_scroll_list()
	sc2.custom_minimum_size = Vector2(0, 120)
	_templates_list = PanelUI.list_inner(sc2)
	add_child(sc2)

	_status = Label.new()
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(_status)

	refresh()


func refresh() -> void:
	if not is_inside_tree():
		return
	_fetch_mine()
	_fetch_templates()


func _register_form() -> VBoxContainer:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 6)
	var title := Label.new()
	title.text = "Register new entity"
	title.add_theme_color_override("font_color", RealmColors.ACCENT)
	box.add_child(title)
	var name_in := LineEdit.new()
	name_in.placeholder_text = "Business name"
	name_in.name = "NameInput"
	box.add_child(name_in)
	var desc_in := LineEdit.new()
	desc_in.placeholder_text = "Description (optional)"
	box.add_child(desc_in)
	var tpl := OptionButton.new()
	_template_sel = OptionButton.new()
	_template_sel.add_item("(No template)", -1)
	_template_sel.set_item_metadata(0, "")
	box.add_child(_template_sel)
	var plot_in := LineEdit.new()
	plot_in.placeholder_text = "Registered plot ids (comma-separated)"
	plot_in.name = "PlotsInput"
	box.add_child(plot_in)
	var btn := Button.new()
	btn.text = "Register ($10 fee)"
	PanelUI.style_btn(btn, true)
	btn.pressed.connect(
		func() -> void:
			var body := {
				"party": WorldState.party_id,
				"name": name_in.text.strip_edges(),
				"description": desc_in.text.strip_edges(),
			}
			var tid := ""
			if _template_sel.selected >= 0:
				tid = str(_template_sel.get_item_metadata(_template_sel.selected))
			if not tid.is_empty():
				body["template_id"] = tid
				var plots: Array = []
				for part in plot_in.text.split(","):
					var p := str(part).strip_edges()
					if not p.is_empty():
						plots.append(p)
				body["registered_plot_ids"] = plots
			API.register_business(
				body,
				func(r: Dictionary) -> void:
					if bool(r.get("ok", false)):
						MainFeedback.toast("Business registered")
						_status.text = "ID: %s" % str(r.get("business_id", ""))
						refresh()
						API.get_world(func(d): WorldState.apply_world(d))
					else:
						_status.text = str(r.get("reason", r.get("detail", "Failed"))),
			)
	)
	box.add_child(btn)
	return box


func _fetch_mine() -> void:
	PanelUI.clear_children(_mine_list)
	API.get_businesses_mine(
		WorldState.party_id,
		func(data: Dictionary) -> void:
			if not is_instance_valid(_mine_list):
				return
			for row in data.get("businesses", data.get("entities", [])) as Array:
				if row is Dictionary:
					_mine_list.add_child(_business_card(row as Dictionary)),
	)


func _fetch_templates() -> void:
	PanelUI.clear_children(_templates_list)
	API.get_business_templates(
		func(data: Dictionary) -> void:
			if not is_instance_valid(_templates_list):
				return
			if _template_sel != null:
				while _template_sel.item_count > 1:
					_template_sel.remove_item(1)
			for row in data.get("templates", []) as Array:
				if not (row is Dictionary):
					continue
				var d: Dictionary = row
				var lbl := Label.new()
				lbl.text = "%s — %s (%s)" % [d.get("label", "?"), d.get("template_id", ""), d.get("kind", "")]
				_templates_list.add_child(lbl)
				if _template_sel != null:
					var tid := str(d.get("template_id", ""))
					_template_sel.add_item(str(d.get("label", tid)))
					_template_sel.set_item_metadata(_template_sel.item_count - 1, tid),
	)


func _business_card(b: Dictionary) -> PanelContainer:
	var pc := PanelContainer.new()
	var v := VBoxContainer.new()
	pc.add_child(v)
	var title := Label.new()
	title.text = str(b.get("name", b.get("business_name", "?")))
	title.add_theme_color_override("font_color", RealmColors.TEXT)
	v.add_child(title)
	var sub := Label.new()
	sub.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	sub.add_theme_color_override("font_color", RealmColors.MUTED)
	sub.text = "ID %s · %s · plots: %s" % [
		b.get("business_id", b.get("id", "")),
		b.get("template_id", b.get("type_tag", "")),
		str(b.get("registered_plot_ids", b.get("plot_ids", []))),
	]
	v.add_child(sub)
	return pc
