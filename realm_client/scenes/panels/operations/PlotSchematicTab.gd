extends VBoxContainer
## Linear recipe-chain planner with engine validation (parity with web schematic).

const STORAGE_PREFIX := "plot_schematic_"

var _plot_sel: OptionButton
var _chain_list: ItemList
var _recipe_sel: OptionButton
var _status: Label
var _chain: Array = []


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var hint := Label.new()
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hint.add_theme_color_override("font_color", RealmColors.MUTED)
	hint.text = (
		"Plan multi-step production on a surveyed plot. Order matters — outputs of step N "
		+ "feed step N+1. Validate against engine recipes and your carried inventory."
	)
	add_child(hint)

	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	_plot_sel = OptionButton.new()
	_plot_sel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_plot_sel.item_selected.connect(_on_plot_changed)
	row.add_child(_plot_sel)
	add_child(row)

	_chain_list = ItemList.new()
	_chain_list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_chain_list.custom_minimum_size = Vector2(0, 160)
	add_child(_chain_list)

	var add_row := HBoxContainer.new()
	_recipe_sel = OptionButton.new()
	_recipe_sel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	add_row.add_child(_recipe_sel)
	var add_btn := Button.new()
	add_btn.text = "Add step"
	PanelUI.style_btn(add_btn)
	add_btn.pressed.connect(_on_add_step)
	add_row.add_child(add_btn)
	var up_btn := Button.new()
	up_btn.text = "↑"
	PanelUI.style_btn(up_btn)
	up_btn.pressed.connect(_on_move_up)
	add_row.add_child(up_btn)
	var down_btn := Button.new()
	down_btn.text = "↓"
	PanelUI.style_btn(down_btn)
	down_btn.pressed.connect(_on_move_down)
	add_row.add_child(down_btn)
	var rm_btn := Button.new()
	rm_btn.text = "Remove"
	PanelUI.style_btn(rm_btn)
	rm_btn.pressed.connect(_on_remove_step)
	add_row.add_child(rm_btn)
	add_child(add_row)

	var action_row := HBoxContainer.new()
	var val_btn := Button.new()
	val_btn.text = "Validate chain (engine)"
	PanelUI.style_btn(val_btn, true)
	val_btn.pressed.connect(_on_validate)
	action_row.add_child(val_btn)
	var clr_btn := Button.new()
	clr_btn.text = "Clear"
	PanelUI.style_btn(clr_btn)
	clr_btn.pressed.connect(_on_clear)
	action_row.add_child(clr_btn)
	add_child(action_row)

	_status = Label.new()
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(_status)

	WorldState.player_updated.connect(_refresh_plots)
	WorldState.world_updated.connect(_refresh_plots)
	_refresh_plots()
	_populate_recipe_picker()


func refresh() -> void:
	_refresh_plots()


func _refresh_plots() -> void:
	var prev := _selected_plot_id()
	_plot_sel.clear()
	for pid in WorldState.owned_plot_ids_sorted():
		var pd: Dictionary = WorldState.plots[pid] as Dictionary
		if not bool(pd.get("surveyed", false)):
			continue
		_plot_sel.add_item(WorldState.plot_site_label(pid))
		_plot_sel.set_item_metadata(_plot_sel.item_count - 1, pid)
	if prev != "":
		for i in _plot_sel.item_count:
			if str(_plot_sel.get_item_metadata(i)) == prev:
				_plot_sel.select(i)
				break
	elif _plot_sel.item_count > 0:
		_plot_sel.select(0)
	_on_plot_changed(_plot_sel.selected)


func _populate_recipe_picker() -> void:
	_recipe_sel.clear()
	for r in WorldState.recipes:
		if not (r is Dictionary):
			continue
		var row: Dictionary = r
		var rid := str(row.get("id", ""))
		_recipe_sel.add_item(str(row.get("display_name", rid)))
		_recipe_sel.set_item_metadata(_recipe_sel.item_count - 1, rid)


func _selected_plot_id() -> String:
	if _plot_sel.item_count == 0 or _plot_sel.selected < 0:
		return ""
	return str(_plot_sel.get_item_metadata(_plot_sel.selected))


func _on_plot_changed(_i: int) -> void:
	_load_chain_from_disk()
	_sync_chain_list()


func _storage_key() -> String:
	var pid := _selected_plot_id()
	if pid.is_empty():
		return ""
	return STORAGE_PREFIX + pid


func _load_chain_from_disk() -> void:
	_chain.clear()
	var key := _storage_key()
	if key.is_empty():
		return
	var cfg := ConfigFile.new()
	if cfg.load("user://%s.cfg" % key) == OK:
		var raw: Variant = cfg.get_value("chain", "recipe_ids", [])
		if raw is Array:
			for rid in raw:
				_chain.append(str(rid))


func _save_chain_to_disk() -> void:
	var key := _storage_key()
	if key.is_empty():
		return
	var cfg := ConfigFile.new()
	cfg.set_value("chain", "recipe_ids", _chain.duplicate())
	cfg.save("user://%s.cfg" % key)


func _sync_chain_list() -> void:
	_chain_list.clear()
	for i in _chain.size():
		var rid := str(_chain[i])
		var row := WorldState.recipe_by_id(rid)
		_chain_list.add_item("%d. %s" % [i + 1, row.get("display_name", rid)])


func _on_add_step() -> void:
	if _recipe_sel.selected < 0:
		return
	var rid := str(_recipe_sel.get_item_metadata(_recipe_sel.selected))
	if rid.is_empty():
		return
	_chain.append(rid)
	_save_chain_to_disk()
	_sync_chain_list()


func _on_remove_step() -> void:
	var idx := _chain_list.get_selected_items()
	if idx.is_empty():
		return
	_chain.remove_at(idx[0])
	_save_chain_to_disk()
	_sync_chain_list()


func _on_move_up() -> void:
	var idx := _chain_list.get_selected_items()
	if idx.is_empty() or idx[0] <= 0:
		return
	var i := idx[0]
	var tmp = _chain[i]
	_chain[i] = _chain[i - 1]
	_chain[i - 1] = tmp
	_save_chain_to_disk()
	_sync_chain_list()
	_chain_list.select(i - 1)


func _on_move_down() -> void:
	var idx := _chain_list.get_selected_items()
	if idx.is_empty() or idx[0] >= _chain.size() - 1:
		return
	var i := idx[0]
	var tmp = _chain[i]
	_chain[i] = _chain[i + 1]
	_chain[i + 1] = tmp
	_save_chain_to_disk()
	_sync_chain_list()
	_chain_list.select(i + 1)


func _on_clear() -> void:
	_chain.clear()
	_save_chain_to_disk()
	_sync_chain_list()
	_status.text = ""


func _on_validate() -> void:
	var pid := _selected_plot_id()
	if pid.is_empty():
		_status.text = "Select a surveyed plot."
		_status.add_theme_color_override("font_color", RealmColors.DANGER)
		return
	if _chain.is_empty():
		_status.text = "Add at least one recipe step."
		_status.add_theme_color_override("font_color", RealmColors.DANGER)
		return
	_status.text = "Validating…"
	API.validate_plot_schematic(
		pid,
		_chain,
		func(data: Dictionary) -> void:
			if bool(data.get("ok", false)):
				_status.text = "Engine confirmed: chain is feasible with current rules."
				_status.add_theme_color_override("font_color", Color(0.4, 1.0, 0.5))
				MainFeedback.toast("Schematic validated")
			else:
				var errs: Variant = data.get("errors", data.get("detail", "Rejected"))
				if errs is Array:
					_status.text = "\n".join(errs)
				else:
					_status.text = str(errs)
				_status.add_theme_color_override("font_color", RealmColors.DANGER),
	)
