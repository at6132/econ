extends VBoxContainer
## Register a regional shipping route from an owned plot.


func _ready() -> void:
	var title := Label.new()
	title.text = "Register route"
	title.add_theme_color_override("font_color", RealmColors.ACCENT)
	add_child(title)
	var plot := OptionButton.new()
	plot.name = "PlotSelect"
	add_child(plot)
	var from_r := LineEdit.new()
	from_r.placeholder_text = "From region id"
	add_child(from_r)
	var to_r := LineEdit.new()
	to_r.placeholder_text = "To region id"
	add_child(to_r)
	var fee := SpinBox.new()
	fee.prefix = "Fee ¢/tile "
	fee.min_value = 0
	fee.value = 5
	add_child(fee)
	var btn := Button.new()
	btn.text = "Register"
	PanelUI.style_btn(btn, true)
	btn.pressed.connect(func() -> void:
		if plot.selected < 0:
			return
		API.register_route(
			from_r.text.strip_edges(),
			to_r.text.strip_edges(),
			int(fee.value),
			str(plot.get_item_metadata(plot.selected)),
			func(r: Dictionary) -> void:
				if bool(r.get("ok", false)):
					MainFeedback.toast("Route registered")
				else:
					MainFeedback.toast(str(r.get("reason", "Failed")), true)
		)
	)
	add_child(btn)
	WorldState.player_updated.connect(_fill_plots)
	_fill_plots()


func _fill_plots() -> void:
	var sel: OptionButton = get_node("PlotSelect") as OptionButton
	var prev := ""
	if sel.item_count > 0 and sel.selected >= 0:
		prev = str(sel.get_item_metadata(sel.selected))
	sel.clear()
	for pid in WorldState.owned_plot_ids_sorted():
		sel.add_item(pid)
		sel.set_item_metadata(sel.item_count - 1, pid)
	if prev != "":
		for i in sel.item_count:
			if str(sel.get_item_metadata(i)) == prev:
				sel.select(i)
				break
