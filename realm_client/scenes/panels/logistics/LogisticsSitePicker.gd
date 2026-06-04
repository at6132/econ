extends CanvasLayer
## Map + list picker for owned plot sites — labels come from buildings on the deed (open-ended).

signal site_confirmed(route_id: String, plot_id: String, summary: String)
signal picker_closed

class SiteMapControl extends Control:
	signal plot_pressed(plot_id: String)

	var entries: Array = []
	var selected_plot_id: String = ""
	var origin_plot_id: String = ""
	var hovered_plot_id: String = ""

	func _ready() -> void:
		mouse_filter = Control.MOUSE_FILTER_STOP
		tooltip_text = "Click a site. Scroll the list or map to choose where goods flow."

	func _draw() -> void:
		var rect := get_rect()
		draw_rect(rect, Color(0.05, 0.05, 0.08, 1.0))
		if entries.is_empty():
			draw_string(
				ThemeDB.fallback_font,
				rect.position + Vector2(12, 24),
				"No other owned sites.",
				HORIZONTAL_ALIGNMENT_LEFT,
				-1,
				14,
				Color(0.55, 0.52, 0.45),
			)
			return
		var min_x := 1_000_000
		var min_y := 1_000_000
		var max_x := -1_000_000
		var max_y := -1_000_000
		for row in entries:
			if not (row is Dictionary):
				continue
			var e: Dictionary = row
			min_x = mini(min_x, int(e.get("x", 0)))
			min_y = mini(min_y, int(e.get("y", 0)))
			max_x = maxi(max_x, int(e.get("x", 0)))
			max_y = maxi(max_y, int(e.get("y", 0)))
		if origin_plot_id != "":
			var oxy := WorldState.plot_world_xy(origin_plot_id)
			min_x = mini(min_x, oxy.x)
			min_y = mini(min_y, oxy.y)
			max_x = maxi(max_x, oxy.x)
			max_y = maxi(max_y, oxy.y)
		var span_x := maxi(1, max_x - min_x + 1)
		var span_y := maxi(1, max_y - min_y + 1)
		var pad := 28.0
		var inner := rect.size - Vector2(pad * 2.0, pad * 2.0)
		var scale := minf(inner.x / float(span_x), inner.y / float(span_y))
		var cell := clampf(scale * 0.85, 10.0, 48.0)

		if origin_plot_id != "":
			var or_xy := WorldState.plot_world_xy(origin_plot_id)
			var or_pos := Vector2(
				pad + (float(or_xy.x - min_x) + 0.5) * cell,
				pad + (float(or_xy.y - min_y) + 0.5) * cell,
			)
			draw_circle(or_pos, cell * 0.35, Color(0.95, 0.82, 0.35, 0.25))
			draw_arc(or_pos, cell * 0.38, 0.0, TAU, 24, Color(0.95, 0.82, 0.35, 0.7), 1.5)

		for row in entries:
			if not (row is Dictionary):
				continue
			var e: Dictionary = row
			var pid := str(e.get("plot_id", ""))
			var px := int(e.get("x", 0))
			var py := int(e.get("y", 0))
			var terrain := str(e.get("terrain", "unknown"))
			var col := RealmColors.terrain_color(terrain)
			var center := Vector2(
				pad + (float(px - min_x) + 0.5) * cell,
				pad + (float(py - min_y) + 0.5) * cell,
			)
			var half := cell * 0.42
			var site_rect := Rect2(center - Vector2(half, half), Vector2(half, half) * 2.0)
			var fill := col.darkened(0.15)
			if pid == selected_plot_id:
				fill = col.lightened(0.12)
			elif pid == hovered_plot_id:
				fill = col.lightened(0.05)
			draw_rect(site_rect, fill)
			var border := Color(0.12, 0.11, 0.10, 0.9)
			if pid == selected_plot_id:
				border = RealmColors.ACCENT
			elif pid == hovered_plot_id:
				border = RealmColors.ACCENT_DIM
			draw_rect(site_rect, border, false, 2.0)

	func _plot_at_local(pos: Vector2) -> String:
		if entries.is_empty():
			return ""
		var rect := get_rect()
		var min_x := 1_000_000
		var min_y := 1_000_000
		var max_x := -1_000_000
		var max_y := -1_000_000
		for row in entries:
			if not (row is Dictionary):
				continue
			var e: Dictionary = row
			min_x = mini(min_x, int(e.get("x", 0)))
			min_y = mini(min_y, int(e.get("y", 0)))
			max_x = maxi(max_x, int(e.get("x", 0)))
			max_y = maxi(max_y, int(e.get("y", 0)))
		var span_x := maxi(1, max_x - min_x + 1)
		var span_y := maxi(1, max_y - min_y + 1)
		var pad := 28.0
		var inner := rect.size - Vector2(pad * 2.0, pad * 2.0)
		var scale := minf(inner.x / float(span_x), inner.y / float(span_y))
		var cell := clampf(scale * 0.85, 10.0, 48.0)
		var best := ""
		var best_d := 1e12
		for row in entries:
			if not (row is Dictionary):
				continue
			var e: Dictionary = row
			var pid := str(e.get("plot_id", ""))
			var center := Vector2(
				pad + (float(int(e.get("x", 0)) - min_x) + 0.5) * cell,
				pad + (float(int(e.get("y", 0)) - min_y) + 0.5) * cell,
			)
			var d := pos.distance_squared_to(center)
			var hit_r := cell * 0.55
			if d <= hit_r * hit_r and d < best_d:
				best_d = d
				best = pid
		return best

	func _gui_input(event: InputEvent) -> void:
		if event is InputEventMouseMotion:
			var pid := _plot_at_local((event as InputEventMouseMotion).position)
			if pid != hovered_plot_id:
				hovered_plot_id = pid
				if is_inside_tree():
					queue_redraw()
		elif event is InputEventMouseButton:
			var mb := event as InputEventMouseButton
			if mb.button_index == MOUSE_BUTTON_LEFT and mb.pressed:
				var pid := _plot_at_local(mb.position)
				if not pid.is_empty():
					selected_plot_id = pid
					queue_redraw()
					plot_pressed.emit(pid)


@onready var _dim: ColorRect = $Dim
@onready var _panel: PanelContainer = $Center/Panel
@onready var _title: Label = $Center/Panel/Margin/VBox/Title
@onready var _hint: Label = $Center/Panel/Margin/VBox/Hint
var _map: SiteMapControl
@onready var _site_list: ItemList = $Center/Panel/Margin/VBox/Body/ListCol/SiteList
@onready var _detail: Label = $Center/Panel/Margin/VBox/Body/ListCol/Detail
@onready var _route_kind: OptionButton = $Center/Panel/Margin/VBox/Footer/RouteKind
@onready var _confirm_btn: Button = $Center/Panel/Margin/VBox/Footer/ConfirmBtn
@onready var _cancel_btn: Button = $Center/Panel/Margin/VBox/Footer/CancelBtn

var _mode: String = "input"  # input | output | supply
var _exclude_plot_id: String = ""
var _origin_plot_id: String = ""
var _entries: Array = []
var _list_plot_ids: PackedStringArray = PackedStringArray()
var _selected_plot_id: String = ""
var _on_confirm: Callable = Callable()


func _ready() -> void:
	visible = false
	process_mode = Node.PROCESS_MODE_DISABLED
	var map_slot: Node = $Center/Panel/Margin/VBox/Body/Map
	var body: Node = map_slot.get_parent()
	var map_idx := map_slot.get_index()
	body.remove_child(map_slot)
	map_slot.queue_free()
	_map = SiteMapControl.new()
	_map.name = "Map"
	_map.custom_minimum_size = Vector2(480, 360)
	_map.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_map.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_map.plot_pressed.connect(_select_plot)
	body.add_child(_map)
	body.move_child(_map, map_idx)
	_dim.gui_input.connect(_on_dim_clicked)
	_confirm_btn.pressed.connect(_on_confirm_pressed)
	_cancel_btn.pressed.connect(_on_cancel_pressed)
	_site_list.item_selected.connect(_on_list_selected)
	_site_list.item_activated.connect(_on_list_activated)
	_route_kind.item_selected.connect(_on_route_kind_changed)
	PanelUI.style_btn(_confirm_btn, true)
	PanelUI.style_btn(_cancel_btn)
	_apply_panel_theme()


func _apply_panel_theme() -> void:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.07, 0.07, 0.09, 0.98)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.45)
	sb.set_corner_radius_all(8)
	sb.set_content_margin_all(12)
	_panel.add_theme_stylebox_override("panel", sb)
	_title.add_theme_font_size_override("font_size", 18)
	_title.add_theme_color_override("font_color", RealmColors.TEXT)
	_hint.add_theme_color_override("font_color", RealmColors.MUTED)


func open_for(config: Dictionary) -> void:
	_mode = str(config.get("mode", "input"))
	_exclude_plot_id = str(config.get("exclude_plot_id", ""))
	_origin_plot_id = str(config.get("origin_plot_id", _exclude_plot_id))
	var current := str(config.get("current_route_id", ""))
	_on_confirm = config.get("on_confirm", Callable()) as Callable
	if _mode == "supply":
		_entries = WorldState.logistics_site_entries("")
	else:
		_entries = WorldState.logistics_site_entries(_exclude_plot_id)
	_map.entries = _entries
	_map.origin_plot_id = _origin_plot_id
	_selected_plot_id = ""
	if current.begins_with("stash_plot:"):
		_selected_plot_id = current.substr(11)
	elif current.begins_with("ship_to:"):
		_selected_plot_id = current.substr(8)
	_map.selected_plot_id = _selected_plot_id
	_map.queue_redraw()
	_build_list()
	_configure_route_kind(current)
	_refresh_detail()
	if _mode == "supply":
		_title.text = "Choose supply / stash site"
		_hint.text = (
			"Pick a deed to configure replenishment. Each site has a finite stash cap (yard vs "
			+ "warehouse); stock spoils and cannot sit forever. Labels show what you built on the deed."
		)
		_confirm_btn.text = "Configure this site"
	else:
		_title.text = "Choose site on map"
		_hint.text = (
			"Route bulk between deeds you own — dock, store, yard, warehouse, etc. Each deed has "
			+ "limited stash space; perishables spoil. Labels show buildings on the deed."
		)
		if _mode == "input":
			_hint.text += " Inputs pull from the site stash when production starts."
		else:
			_hint.text += " Outputs can land in stash or go out as a shipment leg."
		_confirm_btn.text = "Use this site"
	visible = true
	process_mode = Node.PROCESS_MODE_INHERIT
	_confirm_btn.grab_focus()


func close_picker() -> void:
	visible = false
	process_mode = Node.PROCESS_MODE_DISABLED
	picker_closed.emit()


func _build_list() -> void:
	_site_list.clear()
	_list_plot_ids = PackedStringArray()
	var last_group := ""
	for row in _entries:
		if not (row is Dictionary):
			continue
		var e: Dictionary = row
		var g := str(e.get("group", "other"))
		if g != last_group:
			last_group = g
			var sep := _site_list.item_count
			_site_list.add_item("── %s ──" % str(e.get("group_label", WorldState.logistics_site_group_label(g))))
			_site_list.set_item_disabled(sep, true)
			_site_list.set_item_metadata(sep, "")
		var pid := str(e.get("plot_id", ""))
		var stash: int = int(e.get("stash_units", 0))
		var suffix := "" if stash <= 0 else " · %d u in stash" % stash
		_site_list.add_item("  %s%s" % [str(e.get("summary", pid)), suffix])
		_site_list.set_item_metadata(_site_list.item_count - 1, pid)
		_list_plot_ids.append(pid)
	if not _selected_plot_id.is_empty():
		_select_plot(_selected_plot_id, false)


func _configure_route_kind(current_route: String) -> void:
	_route_kind.clear()
	if _mode == "supply":
		_route_kind.visible = false
		return
	if _mode == "input":
		_route_kind.add_item("Pull from site stash")
		_route_kind.set_item_metadata(0, "stash_plot")
		_route_kind.visible = false
		return
	_route_kind.visible = true
	_route_kind.add_item("Deliver to site stash (ship when batch completes)")
	_route_kind.set_item_metadata(0, "stash_plot")
	_route_kind.add_item("Dispatch active shipment to site")
	_route_kind.set_item_metadata(1, "ship_to")
	var pick := 0
	if current_route.begins_with("ship_to:"):
		pick = 1
	_route_kind.select(pick)


func _on_route_kind_changed(_i: int = 0) -> void:
	pass


func _route_prefix() -> String:
	if _mode == "supply" or _mode == "input":
		return "stash_plot"
	var meta := str(_route_kind.get_item_metadata(_route_kind.selected))
	return meta if not meta.is_empty() else "stash_plot"


func _select_plot(plot_id: String, focus_list: bool = true) -> void:
	_selected_plot_id = plot_id
	_map.selected_plot_id = plot_id
	_map.queue_redraw()
	if focus_list:
		for i in _site_list.item_count:
			if str(_site_list.get_item_metadata(i)) == plot_id:
				_site_list.select(i)
				_site_list.ensure_current_is_visible()
				break
	_refresh_detail()


func _refresh_detail() -> void:
	if _selected_plot_id.is_empty():
		_detail.text = "Select a site on the map or in the list."
		_confirm_btn.disabled = true
		return
	_confirm_btn.disabled = false
	for row in _entries:
		if not (row is Dictionary):
			continue
		if str((row as Dictionary).get("plot_id", "")) != _selected_plot_id:
			continue
		var e: Dictionary = row
		var labels: Variant = e.get("buildings", PackedStringArray())
		var btxt := ""
		if labels is PackedStringArray and (labels as PackedStringArray).size() > 0:
			btxt = "\nBuildings: %s" % ", ".join(labels)
		elif labels is Array and not (labels as Array).is_empty():
			btxt = "\nBuildings: %s" % ", ".join(labels)
		var terrain := str(e.get("terrain", "unknown")).replace("_", " ")
		_detail.text = (
			"%s\nTerrain: %s · Stash: %d units total%s"
			% [str(e.get("summary", _selected_plot_id)), terrain, int(e.get("stash_units", 0)), btxt]
		)
		return
	_detail.text = WorldState.plot_site_summary(_selected_plot_id)


func _on_list_selected(index: int) -> void:
	var pid := str(_site_list.get_item_metadata(index))
	if pid.is_empty():
		return
	_select_plot(pid, false)


func _on_list_activated(index: int) -> void:
	_on_list_selected(index)
	_on_confirm_pressed()


func _on_confirm_pressed() -> void:
	if _selected_plot_id.is_empty():
		return
	var prefix := _route_prefix()
	var route_id := "%s:%s" % [prefix, _selected_plot_id]
	var summary := WorldState.plot_site_summary(_selected_plot_id)
	site_confirmed.emit(route_id, _selected_plot_id, summary)
	if _on_confirm.is_valid():
		_on_confirm.call(route_id, _selected_plot_id, summary)
	close_picker()


func _on_cancel_pressed() -> void:
	close_picker()


func _on_dim_clicked(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.button_index == MOUSE_BUTTON_LEFT and mb.pressed:
			close_picker()


func _unhandled_input(event: InputEvent) -> void:
	if not visible:
		return
	if event.is_action_pressed("ui_cancel"):
		close_picker()
		get_viewport().set_input_as_handled()
