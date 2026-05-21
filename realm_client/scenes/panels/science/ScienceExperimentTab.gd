extends VBoxContainer

var _elements: Array = []
var _plot_sel: OptionButton
var _elem_a: OptionButton
var _elem_b: OptionButton


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var hint := Label.new()
	hint.text = "Requires an owned plot with a laboratory building."
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(hint)
	_plot_sel = OptionButton.new()
	add_child(_plot_sel)
	_elem_a = OptionButton.new()
	_elem_b = OptionButton.new()
	add_child(_elem_a)
	add_child(_elem_b)
	var cond := LineEdit.new()
	cond.text = "heat_1200c"
	cond.placeholder_text = "Conditions (comma-separated)"
	add_child(cond)
	var btn := Button.new()
	btn.text = "Run experiment"
	PanelUI.style_btn(btn, true)
	btn.pressed.connect(func() -> void:
		if _plot_sel.selected < 0 or _elem_a.selected < 0 or _elem_b.selected < 0:
			MainFeedback.toast("Pick plot and elements", true)
			return
		var conditions: Array = []
		for part in cond.text.split(","):
			var s := str(part).strip_edges()
			if not s.is_empty():
				conditions.append(s)
		API.post_science_experiment({
			"party": WorldState.party_id,
			"plot_id": str(_plot_sel.get_item_metadata(_plot_sel.selected)),
			"material_a": str(_elem_a.get_item_metadata(_elem_a.selected)),
			"material_b": str(_elem_b.get_item_metadata(_elem_b.selected)),
		}, func(r: Dictionary) -> void:
			if bool(r.get("ok", false)):
				MainFeedback.toast("Experiment queued")
			else:
				MainFeedback.toast(str(r.get("reason", "Failed")), true)
		)
	)
	add_child(btn)
	API.get_science_elements(_on_elements)
	WorldState.player_updated.connect(_fill_plots)
	_fill_plots()


func _on_elements(d: Dictionary) -> void:
	_elements.clear()
	for row in d.get("elements", []) as Array:
		_elements.append(row)
	_fill_element_opts()


func _fill_element_opts() -> void:
	for ob in [_elem_a, _elem_b]:
		ob.clear()
		for row in _elements:
			var eid := str(row)
			if row is Dictionary:
				eid = str((row as Dictionary).get("element_id", (row as Dictionary).get("id", eid)))
			ob.add_item(eid)
			ob.set_item_metadata(ob.item_count - 1, eid)


func _fill_plots() -> void:
	_plot_sel.clear()
	for pid in WorldState.owned_plot_ids_sorted():
		if _plot_has_lab(pid):
			_plot_sel.add_item(pid)
			_plot_sel.set_item_metadata(_plot_sel.item_count - 1, pid)


func _plot_has_lab(plot_id: String) -> bool:
	for b in WorldState.plot_buildings:
		if not (b is Dictionary):
			continue
		if str((b as Dictionary).get("plot_id", "")) != plot_id:
			continue
		if str((b as Dictionary).get("building_id", "")) == "laboratory":
			return true
	return false
