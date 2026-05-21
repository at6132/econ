extends VBoxContainer
## Post job openings on owned plots; manage listings.

var _list: VBoxContainer
var _status: Label


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var form := GridContainer.new()
	form.columns = 2
	form.add_theme_constant_override("v_separation", 6)
	form.add_child(_lbl("Plot"))
	var plot_sel := OptionButton.new()
	plot_sel.name = "PlotSelect"
	plot_sel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	form.add_child(plot_sel)
	form.add_child(_lbl("Min skill"))
	var skill := SpinBox.new()
	skill.min_value = 0
	skill.max_value = 10
	form.add_child(skill)
	form.add_child(_lbl("Wage ¢/day"))
	var wage := SpinBox.new()
	wage.min_value = 100
	wage.max_value = 500_000
	wage.value = 2000
	form.add_child(wage)
	add_child(form)

	var post_btn := Button.new()
	post_btn.text = "Post opening"
	PanelUI.style_btn(post_btn, true)
	post_btn.pressed.connect(
		func() -> void:
			if plot_sel.item_count == 0:
				_status.text = "No owned plots."
				return
			var pid := str(plot_sel.get_item_metadata(plot_sel.selected))
			API.post_job_opening(
				pid,
				int(skill.value),
				int(wage.value),
				func(r: Dictionary) -> void:
					if bool(r.get("ok", false)):
						MainFeedback.toast("Job opening posted")
						refresh()
					else:
						_status.text = str(r.get("reason", r.get("detail", "Failed"))),
			)
	)
	add_child(post_btn)

	var hdr := Label.new()
	hdr.text = "Your openings"
	hdr.add_theme_color_override("font_color", RealmColors.ACCENT)
	add_child(hdr)

	var sc := PanelUI.make_scroll_list()
	sc.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_list = PanelUI.list_inner(sc)
	add_child(sc)

	_status = Label.new()
	add_child(_status)

	WorldState.player_updated.connect(_refresh_plots.bind(plot_sel))
	WorldState.world_updated.connect(_refresh_plots.bind(plot_sel))
	_refresh_plots(plot_sel)
	refresh()


func _lbl(t: String) -> Label:
	var l := Label.new()
	l.text = t
	return l


func _refresh_plots(plot_sel: OptionButton) -> void:
	if not is_instance_valid(plot_sel):
		return
	var prev := ""
	if plot_sel.item_count > 0 and plot_sel.selected >= 0:
		prev = str(plot_sel.get_item_metadata(plot_sel.selected))
	plot_sel.clear()
	for pid in WorldState.owned_plot_ids_sorted():
		plot_sel.add_item(WorldState.plot_site_label(pid))
		plot_sel.set_item_metadata(plot_sel.item_count - 1, pid)
	if prev != "":
		for i in plot_sel.item_count:
			if str(plot_sel.get_item_metadata(i)) == prev:
				plot_sel.select(i)
				break
	elif plot_sel.item_count > 0:
		plot_sel.select(0)


func refresh() -> void:
	PanelUI.clear_children(_list)
	API.get_job_openings(
		WorldState.party_id,
		func(data: Dictionary) -> void:
			if not is_instance_valid(_list):
				return
			for row in data.get("openings", []) as Array:
				if row is Dictionary:
					_list.add_child(_opening_row(row as Dictionary)),
	)


func _opening_row(op: Dictionary) -> HBoxContainer:
	var row := HBoxContainer.new()
	var lbl := Label.new()
	lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	lbl.text = "%s · skill≥%d · %s/day" % [
		op.get("plot_id", "?"),
		int(op.get("skill_min", 0)),
		WorldState.format_money(int(op.get("wage_per_day_cents", 0))),
	]
	row.add_child(lbl)
	var del_btn := Button.new()
	del_btn.text = "Remove"
	PanelUI.style_btn(del_btn)
	var oid := str(op.get("opening_id", op.get("id", "")))
	del_btn.pressed.connect(
		func() -> void:
			API.delete_job_opening(
				oid,
				WorldState.party_id,
				func(r: Dictionary) -> void:
					if bool(r.get("ok", true)):
						refresh()
			)
	)
	row.add_child(del_btn)
	return row
