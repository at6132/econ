extends CanvasLayer
## Modal building catalog (data from ``WorldState.building_catalog``).

signal building_chosen(building_id: String, mode: String)

const FOREST_TERRAINS: Array[String] = ["forest", "temperate_forest"]
const WATER_TERRAINS: Array[String] = ["water_deep", "water_shallow"]

@onready var search_box: LineEdit = %SearchBox
@onready var building_grid: GridContainer = %BuildingGrid
@onready var confirm_bar: HBoxContainer = %ConfirmBar
@onready var confirm_label: Label = %ConfirmLabel
@onready var turnkey_btn: Button = %BuildTurnkeyBtn
@onready var self_btn: Button = %BuildSelfBtn
@onready var cancel_confirm_btn: Button = %CancelConfirmBtn
@onready var close_btn: Button = %CloseBtn
@onready var center_panel: Panel = %CenterPanel

var _terrain: String = "plains"
var _selected_id: String = ""
var _selected_entry: Dictionary = {}
var _cb_turnkey := Callable()
var _cb_self := Callable()
var _cb_simple := Callable()


func _ready() -> void:
	_cb_turnkey = Callable(self, "_emit_build").bind("turnkey")
	_cb_self = Callable(self, "_emit_build").bind("self_contract")
	_cb_simple = Callable(self, "_emit_build").bind("")
	_apply_theme()
	search_box.text_changed.connect(_filter_buildings)
	cancel_confirm_btn.pressed.connect(func() -> void: confirm_bar.hide())
	close_btn.mouse_filter = Control.MOUSE_FILTER_STOP
	close_btn.z_index = 10
	close_btn.pressed.connect(queue_free)
	center_panel.scale = Vector2(0.88, 0.88)
	center_panel.modulate.a = 0.0
	var tw := create_tween()
	tw.set_parallel(true)
	tw.tween_property(center_panel, "scale", Vector2.ONE, 0.15)
	tw.tween_property(center_panel, "modulate:a", 1.0, 0.15)


func _apply_theme() -> void:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.08, 0.08, 0.1)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.45)
	center_panel.add_theme_stylebox_override("panel", sb)


func open(terrain: String) -> void:
	_terrain = terrain
	_populate_grid(search_box.text)


func _filter_buildings(t: String) -> void:
	_populate_grid(t)


func _populate_grid(filter: String) -> void:
	for c in building_grid.get_children():
		c.queue_free()
	confirm_bar.hide()
	var f := filter.strip_edges().to_lower()
	for entry in WorldState.building_catalog:
		if not (entry is Dictionary):
			continue
		var row: Dictionary = entry
		var bid := str(row.get("id", ""))
		var label := str(row.get("label", bid))
		if f != "" and not f in label.to_lower():
			continue
		building_grid.add_child(_make_card(bid, row))


func _make_card(bid: String, entry: Dictionary) -> PanelContainer:
	var blocked := _is_blocked(bid, entry)
	var pc := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.1, 0.1, 0.12)
	sb.set_content_margin_all(8)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.22 if not blocked else 0.08)
	pc.add_theme_stylebox_override("panel", sb)
	pc.modulate.a = 0.45 if blocked else 1.0
	var vbox := VBoxContainer.new()
	pc.add_child(vbox)

	var name_lbl := Label.new()
	name_lbl.text = str(entry.get("label", bid))
	name_lbl.add_theme_font_size_override("font_size", 13)
	name_lbl.add_theme_color_override("font_color", Color(0.9, 0.88, 0.82))
	vbox.add_child(name_lbl)

	var kind := str(entry.get("kind", "simple"))
	var cost_lbl := Label.new()
	cost_lbl.add_theme_font_size_override("font_size", 11)
	cost_lbl.add_theme_color_override("font_color", Color(0.85, 0.82, 0.75))
	if kind == "simple":
		cost_lbl.text = "Cost: %s" % WorldState.format_money(int(entry.get("cost_cents", 0)))
	else:
		cost_lbl.text = "Turnkey: %s" % WorldState.format_money(int(entry.get("turnkey_total_cents", 0)))
	vbox.add_child(cost_lbl)

	var mats: Dictionary = {}
	var raw_mats: Variant = entry.get("self_materials", {})
	if raw_mats is Dictionary:
		mats = raw_mats
	if not mats.is_empty():
		var parts: PackedStringArray = []
		for k in mats.keys():
			parts.append("%s×%d" % [str(k), int(mats[k])])
		var ml := Label.new()
		ml.text = "Self materials: %s" % ", ".join(parts)
		ml.add_theme_font_size_override("font_size", 10)
		ml.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		ml.add_theme_color_override("font_color", Color(0.72, 0.74, 0.8))
		vbox.add_child(ml)

	if blocked:
		var why := Label.new()
		why.text = _block_reason(bid, entry)
		why.add_theme_font_size_override("font_size", 10)
		why.add_theme_color_override("font_color", Color(1.0, 0.45, 0.35))
		vbox.add_child(why)
	else:
		var select_btn := Button.new()
		select_btn.text = "Select"
		_style_btn(select_btn)
		select_btn.pressed.connect(func() -> void: _select_building(bid, entry))
		vbox.add_child(select_btn)

	return pc


func _style_btn(btn: Button) -> void:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.14, 0.14, 0.16)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.55)
	btn.add_theme_stylebox_override("normal", sb)
	btn.add_theme_color_override("font_color", Color(0.9, 0.88, 0.82))


func _select_building(bid: String, entry: Dictionary) -> void:
	_selected_id = bid
	_selected_entry = entry.duplicate(true)
	confirm_bar.show()
	var kind := str(entry.get("kind", "simple"))
	var label := str(entry.get("label", bid))
	confirm_label.text = "Build %s?" % label
	if kind == "simple":
		turnkey_btn.visible = true
		self_btn.visible = false
		var cents := int(entry.get("cost_cents", 0))
		turnkey_btn.text = "Build %s" % WorldState.format_money(cents)
		_connect_confirm_simple()
	else:
		turnkey_btn.visible = true
		self_btn.visible = true
		var turnkey := int(entry.get("turnkey_total_cents", 0))
		var shell := int(entry.get("self_shell_cents", 0))
		var fee := int(entry.get("self_contractor_fee_cents", 0))
		turnkey_btn.text = "Turnkey %s" % WorldState.format_money(turnkey)
		self_btn.text = "Self-build %s" % WorldState.format_money(shell + fee)
		_connect_confirm_contracted()


func _emit_build(mode: String) -> void:
	building_chosen.emit(_selected_id, mode)


func _clear_confirm_connections() -> void:
	if turnkey_btn.pressed.is_connected(_cb_turnkey):
		turnkey_btn.pressed.disconnect(_cb_turnkey)
	if turnkey_btn.pressed.is_connected(_cb_simple):
		turnkey_btn.pressed.disconnect(_cb_simple)
	if self_btn.pressed.is_connected(_cb_self):
		self_btn.pressed.disconnect(_cb_self)


func _connect_confirm_simple() -> void:
	_clear_confirm_connections()
	turnkey_btn.pressed.connect(_cb_simple)


func _connect_confirm_contracted() -> void:
	_clear_confirm_connections()
	turnkey_btn.pressed.connect(_cb_turnkey)
	self_btn.pressed.connect(_cb_self)


func _is_blocked(bid: String, entry: Dictionary) -> bool:
	if _terrain in WATER_TERRAINS:
		return true
	var tr: Variant = entry.get("terrain_required", [])
	var reqs: Array = tr if tr is Array else []
	if reqs.has("coastal") and _terrain != "coastal":
		return true
	if bid == "timber_yard" and not (_terrain in FOREST_TERRAINS):
		return true
	return false


func _block_reason(bid: String, _entry: Dictionary) -> String:
	if _terrain in WATER_TERRAINS:
		return "Not buildable on water"
	if bid == "timber_yard":
		return "Requires forest terrain"
	return "Terrain requirement not met"
