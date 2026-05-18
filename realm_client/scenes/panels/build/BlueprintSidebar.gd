extends VBoxContainer

signal blueprint_selected(blueprint_id: String, bp_data: Dictionary)
signal plot_layout_changed()

@onready var search_box: LineEdit = %SearchBox
@onready var blueprint_list: VBoxContainer = %BlueprintList
@onready var create_btn: Button = %CreateBlueprintBtn
@onready var subdivide_btn: Button = %SubdivideBtn

const CATEGORY_ICONS := {
	"extraction": "M",
	"processing": "F",
	"infrastructure": "E",
	"commerce": "S",
	"population": "H",
	"research": "R",
	"custom": "*",
}

var _all_blueprints: Array = []
var _terrain: String = "plains"
var _selected_id: String = ""
var _plot_id: String = ""

const CreateBlueprintDialogScene := preload("res://scenes/panels/build/CreateBlueprintDialog.tscn")
const SubdivideDialogScene := preload("res://scenes/panels/build/SubdivideDialog.tscn")


func _ready() -> void:
	search_box.text_changed.connect(_filter)
	create_btn.pressed.connect(_on_create_blueprint)
	subdivide_btn.pressed.connect(_on_subdivide)


func set_plot_id(plot_id: String) -> void:
	_plot_id = plot_id


func load_blueprints(terrain: String) -> void:
	_terrain = terrain
	API.get_request("/blueprints?party=%s" % WorldState.party_id.uri_encode(), func(data: Dictionary) -> void:
		_all_blueprints = data.get("blueprints", [])
		if _all_blueprints is not Array:
			_all_blueprints = []
		_filter(search_box.text)
	)


func _filter(text: String) -> void:
	for c in blueprint_list.get_children():
		c.queue_free()
	var f := text.strip_edges().to_lower()
	var seeded: Array = []
	var mine: Array = []
	var others: Array = []
	for bp in _all_blueprints:
		if not (bp is Dictionary):
			continue
		if bool(bp.get("is_seeded", false)):
			seeded.append(bp)
		elif str(bp.get("creator_party", "")) == WorldState.party_id:
			mine.append(bp)
		elif bool(bp.get("is_public", false)):
			others.append(bp)
	if not seeded.is_empty():
		_add_section_header("Built-in Blueprints")
		for bp in seeded:
			if _passes_filter(bp, f):
				blueprint_list.add_child(_make_blueprint_card(bp))
	if not mine.is_empty():
		_add_section_header("Your Blueprints")
		for bp in mine:
			if _passes_filter(bp, f):
				blueprint_list.add_child(_make_blueprint_card(bp))
	if not others.is_empty():
		_add_section_header("Public Blueprints")
		for bp in others:
			if _passes_filter(bp, f):
				blueprint_list.add_child(_make_blueprint_card(bp))


func _passes_filter(bp: Dictionary, f: String) -> bool:
	if f != "" and f not in str(bp.get("name", "")).to_lower():
		return false
	return _terrain_ok(bp)


func _add_section_header(text: String) -> void:
	var lbl := Label.new()
	lbl.text = text
	lbl.add_theme_font_size_override("font_size", 10)
	lbl.modulate = Color(0.6, 0.6, 0.6)
	blueprint_list.add_child(lbl)


func _make_blueprint_card(bp: Dictionary) -> PanelContainer:
	var pc := PanelContainer.new()
	pc.custom_minimum_size = Vector2(260, 0)
	pc.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var vbox := VBoxContainer.new()
	vbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	pc.add_child(vbox)
	var bid: String = str(bp.get("blueprint_id", ""))
	if bid == _selected_id:
		pc.add_theme_stylebox_override("panel", _make_selected_stylebox())
	var header := HBoxContainer.new()
	var cat_icon: String = CATEGORY_ICONS.get(str(bp.get("category", "custom")), "*")
	var name_lbl := Label.new()
	name_lbl.text = "%s %s" % [cat_icon, str(bp.get("name", bid))]
	name_lbl.add_theme_font_size_override("font_size", 13)
	name_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	name_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	header.add_child(name_lbl)
	var fp_lbl := Label.new()
	fp_lbl.text = "%d×%d" % [int(bp.get("footprint_w", 1)), int(bp.get("footprint_h", 1))]
	fp_lbl.add_theme_font_size_override("font_size", 10)
	fp_lbl.modulate = Color(0.7, 0.85, 1.0)
	header.add_child(fp_lbl)
	vbox.add_child(header)
	if not _terrain_ok(bp):
		var block_lbl := Label.new()
		block_lbl.text = "Wrong terrain"
		block_lbl.add_theme_font_size_override("font_size", 9)
		block_lbl.modulate = Color(1.0, 0.4, 0.4)
		vbox.add_child(block_lbl)
		pc.modulate.a = 0.5
	else:
		var cost_lbl := Label.new()
		cost_lbl.text = WorldState.format_money(int(bp.get("construction_labor_cents", 0)))
		cost_lbl.add_theme_font_size_override("font_size", 10)
		cost_lbl.modulate = Color(0.85, 0.72, 0.20)
		vbox.add_child(cost_lbl)
		var fee: int = int(bp.get("license_fee_cents", 0))
		if fee > 0 and not bool(bp.get("is_seeded", true)):
			var fee_lbl := Label.new()
			fee_lbl.text = "License: %s" % WorldState.format_money(fee)
			fee_lbl.add_theme_font_size_override("font_size", 9)
			fee_lbl.modulate = Color(0.9, 0.6, 0.2)
			vbox.add_child(fee_lbl)
	pc.gui_input.connect(
		func(ev: InputEvent) -> void:
			if (
				ev is InputEventMouseButton
				and ev.pressed
				and ev.button_index == MOUSE_BUTTON_LEFT
				and _terrain_ok(bp)
			):
				_selected_id = bid
				_filter(search_box.text)
				blueprint_selected.emit(bid, bp)
	)
	return pc


func _terrain_ok(bp: Dictionary) -> bool:
	if _terrain.begins_with("water"):
		return false
	if bool(bp.get("requires_coastal", false)):
		return _terrain == "coastal"
	var req: Variant = bp.get("terrain_requirements", [])
	if req is Array and not req.is_empty():
		return _terrain in req
	return true


func _make_selected_stylebox() -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.15, 0.15, 0.20)
	sb.border_color = RealmColors.ACCENT
	sb.set_border_width_all(2)
	return sb


func _on_create_blueprint() -> void:
	var dialog: Node = CreateBlueprintDialogScene.instantiate()
	get_tree().root.add_child(dialog)
	if dialog.has_signal("blueprint_created"):
		dialog.blueprint_created.connect(
			func(bid: String, bp_data: Dictionary) -> void:
				_all_blueprints.append(bp_data)
				_filter(search_box.text)
				blueprint_selected.emit(bid, bp_data)
		)


func _on_subdivide() -> void:
	if _plot_id.is_empty():
		return
	var dialog: Node = SubdivideDialogScene.instantiate()
	get_tree().root.add_child(dialog)
	if dialog.has_method("setup"):
		dialog.call("setup", _plot_id)
	if dialog.has_signal("subdivided"):
		dialog.subdivided.connect(func(_ids: Array) -> void: plot_layout_changed.emit())
