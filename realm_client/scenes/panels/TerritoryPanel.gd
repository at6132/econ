extends CanvasLayer
## Owned plots list — opens from HUD Territory; slides in from the right (same as other overlays).

signal plot_selected(plot_id: String, plot_data: Dictionary)
signal plot_locate_requested(plot_id: String)

const PANEL_WIDTH := 400.0
const HUD_TOP := 96.0

@onready var panel: Panel = %Panel
@onready var close_btn: Button = %CloseBtn
@onready var plot_scroll: ScrollContainer = %ScrollContainer
@onready var plot_list: VBoxContainer = %PlotList
@onready var all_btn: Button = %AllBtn
@onready var producing_btn: Button = %ProducingBtn
@onready var idle_btn: Button = %IdleBtn
@onready var maint_btn: Button = %MaintBtn
@onready var sort_plot_btn: Button = %SortPlotBtn
@onready var sort_eff_btn: Button = %SortEffBtn

var _filter: String = "all"
var _sort_mode: String = "plot" # plot | eff


func _ready() -> void:
	_apply_theme()
	_layout_panel()
	close_btn.pressed.connect(close)
	all_btn.pressed.connect(func() -> void: _set_filter("all"))
	producing_btn.pressed.connect(func() -> void: _set_filter("producing"))
	idle_btn.pressed.connect(func() -> void: _set_filter("idle"))
	maint_btn.pressed.connect(func() -> void: _set_filter("maint"))
	sort_plot_btn.pressed.connect(func() -> void: _set_sort("plot"))
	sort_eff_btn.pressed.connect(func() -> void: _set_sort("eff"))
	plot_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	plot_scroll.resized.connect(_sync_plot_list_width)
	WorldState.world_updated.connect(_refresh_list)
	# Owned-plot ownership/inventory updates land on the realtime tick.
	WorldState.player_updated.connect(_refresh_list)
	get_viewport().size_changed.connect(_on_viewport_resized)
	call_deferred("_sync_plot_list_width")
	SlidePanelAnim.slide_in(self, panel, _width_pct(), true)
	# Initial fetch: cheap player payload; legacy /world keeps the map +
	# market caches warm for other tabs that haven't been migrated yet.
	API.get_world_player(func(p): WorldState.apply_player(p), WorldState.party_id)
	_refresh_list()


func _apply_theme() -> void:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.08, 0.08, 0.1)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.35)
	panel.add_theme_stylebox_override("panel", sb)
	_style_btn(close_btn)
	_style_btn(all_btn)
	_style_btn(producing_btn)
	_style_btn(idle_btn)
	_style_btn(maint_btn)
	_style_btn(sort_plot_btn)
	_style_btn(sort_eff_btn)


func _style_btn(btn: Button) -> void:
	var s := StyleBoxFlat.new()
	s.bg_color = Color(0.12, 0.12, 0.14)
	s.set_border_width_all(1)
	s.border_color = Color(0.85, 0.72, 0.2, 0.55)
	btn.add_theme_stylebox_override("normal", s)
	btn.add_theme_color_override("font_color", Color(0.9, 0.88, 0.82))


func _width_pct() -> float:
	var vp_w := get_viewport().get_visible_rect().size.x
	if vp_w <= 1.0:
		return 0.22
	return clampf(PANEL_WIDTH / vp_w, 0.15, 0.4)


func _layout_panel() -> void:
	SlidePanelAnim.layout_panel(panel, _width_pct(), HUD_TOP)


func _on_viewport_resized() -> void:
	_layout_panel()
	var vp := get_viewport().get_visible_rect().size
	var w := SlidePanelAnim.panel_width(panel, _width_pct())
	if panel.position.x < vp.x - w + 1.0:
		panel.position.x = vp.x - w
	_sync_plot_list_width()


func _sync_plot_list_width() -> void:
	var w := plot_scroll.size.x
	if w > 4.0:
		plot_list.custom_minimum_size.x = w


func close() -> void:
	if not is_inside_tree():
		return
	SlidePanelAnim.slide_out(self, panel, _width_pct(), queue_free, true)


func _set_filter(f: String) -> void:
	_filter = f
	_refresh_list()


func _set_sort(mode: String) -> void:
	_sort_mode = mode
	_refresh_list()


func _plot_has_running_production(pid: String) -> bool:
	for r in WorldState.active_production:
		if not (r is Dictionary):
			continue
		if str((r as Dictionary).get("plot_id", "")) != pid:
			continue
		if int((r as Dictionary).get("ticks_remaining", 0)) > 0:
			return true
	return false


func _passes_filter(ui: Dictionary) -> bool:
	if _filter == "all":
		return true
	var buildings: Array = ui.get("buildings", [])
	if _filter == "producing":
		return _plot_has_running_production(str(ui.get("id", "")))
	if _filter == "idle":
		return not _plot_has_running_production(str(ui.get("id", "")))
	if _filter == "maint":
		for b in buildings:
			if b is Dictionary and int((b as Dictionary).get("_efficiency_pct", 100)) < 100:
				return true
		return false
	return true


func _min_efficiency(ui: Dictionary) -> int:
	var buildings: Array = ui.get("buildings", [])
	var m := 100
	for b in buildings:
		if b is Dictionary:
			m = mini(m, int((b as Dictionary).get("_efficiency_pct", 100)))
	return m


func _refresh_list() -> void:
	for c in plot_list.get_children():
		c.queue_free()
	call_deferred("_sync_plot_list_width")
	var rows: Array = []
	for pid in WorldState.plots.keys():
		var p: Dictionary = WorldState.plots[pid]
		var own: Variant = p.get("owner", null)
		if own == null or str(own) != WorldState.party_id:
			continue
		var ui := WorldState.get_plot_ui(str(pid))
		ui["id"] = str(pid)
		if not _passes_filter(ui):
			continue
		rows.append(ui)
	if _sort_mode == "eff":
		rows.sort_custom(
			func(a: Dictionary, b: Dictionary) -> bool: return _min_efficiency(a) < _min_efficiency(b)
		)
	else:
		rows.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return str(a["id"]) < str(b["id"]))
	for ui in rows:
		if ui is Dictionary:
			plot_list.add_child(_make_plot_row(ui as Dictionary))


func _make_plot_row(ui: Dictionary) -> PanelContainer:
	var pid := str(ui.get("id", ""))
	var pc := PanelContainer.new()
	pc.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	pc.add_theme_stylebox_override("panel", _plot_card_stylebox())

	var root := VBoxContainer.new()
	root.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	root.add_theme_constant_override("separation", 6)
	pc.add_child(root)

	var header := HBoxContainer.new()
	header.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var title := Label.new()
	title.text = "Plot %s" % pid
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.add_theme_font_size_override("font_size", 13)
	title.add_theme_color_override("font_color", RealmColors.TEXT)
	header.add_child(title)
	var cell_n := _plot_cell_count(pid, ui)
	var size_badge := Label.new()
	size_badge.text = "%d cell%s" % [cell_n, "" if cell_n == 1 else "s"]
	size_badge.add_theme_font_size_override("font_size", 10)
	size_badge.add_theme_color_override("font_color", RealmColors.MAGIC)
	header.add_child(size_badge)
	root.add_child(header)

	var terrain: String = str(ui.get("terrain", "?"))
	var tags: PackedStringArray = PackedStringArray([terrain.replace("_", " ").capitalize()])
	if bool(ui.get("surveyed", false)):
		tags.append("Surveyed")
	if bool(ui.get("deep_surveyed", false)):
		tags.append("Deep survey")
	if ui.get("powered", true) == false:
		tags.append("Off-grid")
	var tag_lbl := Label.new()
	tag_lbl.text = " · ".join(tags)
	tag_lbl.add_theme_font_size_override("font_size", 11)
	tag_lbl.add_theme_color_override("font_color", RealmColors.DIM)
	tag_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	root.add_child(tag_lbl)

	var loc_lbl := Label.new()
	loc_lbl.text = "Location: %s" % _plot_location_summary(pid, ui)
	loc_lbl.add_theme_font_size_override("font_size", 11)
	loc_lbl.add_theme_color_override("font_color", RealmColors.DIM)
	root.add_child(loc_lbl)

	var fair_lbl := Label.new()
	fair_lbl.text = "Fair value: …"
	fair_lbl.add_theme_font_size_override("font_size", 12)
	fair_lbl.add_theme_color_override("font_color", RealmColors.ACCENT)
	root.add_child(fair_lbl)
	_fetch_plot_fair_value(pid, fair_lbl)

	var status := _plot_status_line(ui)
	if not status.is_empty():
		var status_lbl := Label.new()
		status_lbl.text = status
		status_lbl.add_theme_font_size_override("font_size", 11)
		status_lbl.add_theme_color_override("font_color", RealmColors.MUTED)
		status_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		root.add_child(status_lbl)

	var btn_row := HBoxContainer.new()
	btn_row.add_theme_constant_override("separation", 8)
	btn_row.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var locate_btn := Button.new()
	locate_btn.text = "Show on map"
	locate_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_style_btn(locate_btn)
	locate_btn.pressed.connect(func() -> void: plot_locate_requested.emit(pid))
	btn_row.add_child(locate_btn)
	var open_btn := Button.new()
	open_btn.text = "Open →"
	open_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_style_btn(open_btn)
	open_btn.pressed.connect(func() -> void: plot_selected.emit(pid, ui))
	btn_row.add_child(open_btn)
	root.add_child(btn_row)
	return pc


func _plot_card_stylebox() -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = RealmColors.PANEL_DEEP
	sb.set_content_margin_all(10)
	sb.set_border_width_all(2)
	sb.border_color = RealmColors.BORDER
	sb.corner_radius_top_left = 4
	sb.corner_radius_top_right = 4
	sb.corner_radius_bottom_left = 4
	sb.corner_radius_bottom_right = 4
	sb.shadow_color = Color(0, 0, 0, 0.35)
	sb.shadow_size = 2
	sb.shadow_offset = Vector2(2, 2)
	return sb


func _plot_cell_count(plot_id: String, ui: Dictionary) -> int:
	var p: Dictionary = WorldState.plots.get(plot_id, ui)
	var cells_v: Variant = p.get("world_cells", [])
	if cells_v is Array and not (cells_v as Array).is_empty():
		return (cells_v as Array).size()
	var n := 0
	if not WorldState.world_cell_to_plot.is_empty():
		for key in WorldState.world_cell_to_plot.keys():
			if str(WorldState.world_cell_to_plot[key]) == plot_id:
				n += 1
	return maxi(n, 1)


func _plot_location_summary(plot_id: String, ui: Dictionary) -> String:
	var p: Dictionary = WorldState.plots.get(plot_id, ui)
	var min_x := 1_000_000
	var min_y := 1_000_000
	var max_x := -1
	var max_y := -1
	var n := 0
	var cells_v: Variant = p.get("world_cells", [])
	if cells_v is Array and not (cells_v as Array).is_empty():
		for c in cells_v as Array:
			if not (c is Dictionary):
				continue
			var gx := WorldState.variant_to_int((c as Dictionary).get("x", 0), 0)
			var gy := WorldState.variant_to_int((c as Dictionary).get("y", 0), 0)
			min_x = mini(min_x, gx)
			min_y = mini(min_y, gy)
			max_x = maxi(max_x, gx)
			max_y = maxi(max_y, gy)
			n += 1
	if n == 0 and not WorldState.world_cell_to_plot.is_empty():
		for key in WorldState.world_cell_to_plot.keys():
			if str(WorldState.world_cell_to_plot[key]) != plot_id:
				continue
			var parts: PackedStringArray = str(key).split(",")
			if parts.size() != 2:
				continue
			var gx := int(parts[0])
			var gy := int(parts[1])
			min_x = mini(min_x, gx)
			min_y = mini(min_y, gy)
			max_x = maxi(max_x, gx)
			max_y = maxi(max_y, gy)
			n += 1
	if n == 0:
		return "Grid (%d, %d)" % [
			WorldState.variant_to_int(p.get("x", 0), 0),
			WorldState.variant_to_int(p.get("y", 0), 0),
		]
	if min_x == max_x and min_y == max_y:
		return "(%d, %d)" % [min_x, min_y]
	return "(%d, %d) – (%d, %d)" % [min_x, min_y, max_x, max_y]


func _plot_status_line(ui: Dictionary) -> String:
	var parts: PackedStringArray = PackedStringArray()
	var n_bld: int = int(ui.get("buildings", []).size())
	parts.append("%d building%s" % [n_bld, "" if n_bld == 1 else "s"])
	var pid := str(ui.get("id", ""))
	if _plot_has_running_production(pid):
		parts.append("Producing")
	else:
		parts.append("Idle")
	var me := _min_efficiency(ui)
	if n_bld > 0:
		parts.append("Eff %d%%" % me)
	var dens := float(WorldState.population_density_map.get(pid, 0.0))
	if dens > 0.01:
		parts.append("Pop %.0f%%" % (dens * 100.0))
	return " · ".join(parts)


func _fetch_plot_fair_value(plot_id: String, fair_lbl: Label) -> void:
	API.get_plot_value(
		plot_id,
		func(data: Dictionary) -> void:
			if not is_instance_valid(fair_lbl):
				return
			if WorldState.is_api_error_payload(data):
				fair_lbl.text = "Fair value: —"
				fair_lbl.add_theme_color_override("font_color", RealmColors.MUTED)
				return
			fair_lbl.text = "Fair value: %s" % WorldState.format_money(
				int(data.get("fair_value_cents", 0))
			),
	)


func _eff_color(eff: int) -> Color:
	if eff >= 90:
		return Color(0.3, 1.0, 0.3)
	if eff >= 70:
		return Color(1.0, 0.85, 0.2)
	if eff > 0:
		return Color(1.0, 0.4, 0.2)
	return Color(0.5, 0.5, 0.5)
