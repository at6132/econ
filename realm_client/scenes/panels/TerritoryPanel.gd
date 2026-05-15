extends CanvasLayer
## Owned plots list — opens from HUD Territory; slides in from the left.

signal plot_selected(plot_id: String, plot_data: Dictionary)

const PANEL_WIDTH := 380.0
const HUD_BAR_TOP := 56.0

@onready var panel: Panel = %Panel
@onready var close_btn: Button = %CloseBtn
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
	var vp := get_viewport().get_visible_rect().size
	panel.position = Vector2(-PANEL_WIDTH, HUD_BAR_TOP)
	panel.size = Vector2(PANEL_WIDTH, vp.y - HUD_BAR_TOP)
	close_btn.pressed.connect(close)
	all_btn.pressed.connect(func() -> void: _set_filter("all"))
	producing_btn.pressed.connect(func() -> void: _set_filter("producing"))
	idle_btn.pressed.connect(func() -> void: _set_filter("idle"))
	maint_btn.pressed.connect(func() -> void: _set_filter("maint"))
	sort_plot_btn.pressed.connect(func() -> void: _set_sort("plot"))
	sort_eff_btn.pressed.connect(func() -> void: _set_sort("eff"))
	WorldState.world_updated.connect(_refresh_list)
	get_viewport().size_changed.connect(_on_viewport_resized)
	_slide_in()
	API.get_world(func(d): WorldState.apply_world(d))
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


func _on_viewport_resized() -> void:
	var vp := get_viewport().get_visible_rect().size
	panel.size = Vector2(PANEL_WIDTH, vp.y - HUD_BAR_TOP)


func _slide_in() -> void:
	var tw := create_tween().set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	tw.tween_property(panel, "position:x", 0.0, 0.25)


func close() -> void:
	var tw := create_tween().set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_IN)
	tw.tween_property(panel, "position:x", -PANEL_WIDTH, 0.2)
	await tw.finished
	queue_free()


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
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.1, 0.1, 0.12)
	sb.set_content_margin_all(8)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.2)
	pc.add_theme_stylebox_override("panel", sb)
	var hbox := HBoxContainer.new()
	pc.add_child(hbox)

	var info := VBoxContainer.new()
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var row1 := Label.new()
	var terrain: String = str(ui.get("terrain", "?"))
	var n: int = int(ui.get("buildings", []).size())
	row1.text = "Plot %s · %s · %d building%s" % [pid, terrain.capitalize(), n, "s" if n != 1 else ""]
	row1.add_theme_color_override("font_color", Color(0.9, 0.88, 0.82))
	info.add_child(row1)
	var buildings: Array = ui.get("buildings", [])
	if not buildings.is_empty():
		var me := _min_efficiency(ui)
		var eff_lbl := Label.new()
		eff_lbl.text = "Min efficiency: %d%%" % me
		eff_lbl.modulate = _eff_color(me)
		eff_lbl.add_theme_font_size_override("font_size", 11)
		info.add_child(eff_lbl)

	hbox.add_child(info)

	var open_btn := Button.new()
	open_btn.text = "Open →"
	_style_btn(open_btn)
	open_btn.pressed.connect(func() -> void: plot_selected.emit(pid, ui))
	hbox.add_child(open_btn)
	return pc


func _eff_color(eff: int) -> Color:
	if eff >= 90:
		return Color(0.3, 1.0, 0.3)
	if eff >= 70:
		return Color(1.0, 0.85, 0.2)
	if eff > 0:
		return Color(1.0, 0.4, 0.2)
	return Color(0.5, 0.5, 0.5)
