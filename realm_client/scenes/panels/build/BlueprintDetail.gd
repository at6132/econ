extends PanelContainer
## Right column — selected blueprint stats and build mode.

@onready var name_label: Label = %NameLabel
@onready var meta_label: Label = %MetaLabel
@onready var desc_label: Label = %DescLabel
@onready var cost_label: Label = %CostLabel
@onready var materials_label: Label = %MaterialsLabel
@onready var recipes_label: Label = %RecipesLabel
@onready var license_label: Label = %LicenseLabel
@onready var hint_label: Label = %HintLabel
@onready var mode_row: HBoxContainer = %ModeRow
@onready var mode_turnkey: Button = %ModeTurnkey
@onready var mode_self: Button = %ModeSelf
@onready var market_label: Label = %MarketLabel

var current_blueprint: Dictionary = {}
var build_mode: String = "turnkey"

signal build_mode_changed(mode: String)


func _ready() -> void:
	mode_turnkey.toggled.connect(func(on: bool) -> void:
		if on:
			build_mode = "turnkey"
			build_mode_changed.emit(build_mode)
	)
	mode_self.toggled.connect(func(on: bool) -> void:
		if on:
			build_mode = "self"
			build_mode_changed.emit(build_mode)
	)
	_apply_theme()


func _apply_theme() -> void:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.08, 0.08, 0.1)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.25)
	add_theme_stylebox_override("panel", sb)


func show_blueprint(bp: Dictionary) -> void:
	current_blueprint = bp.duplicate(true)
	var bid := str(bp.get("blueprint_id", ""))
	name_label.text = str(bp.get("name", bid))
	meta_label.text = "%s  ·  %d×%d cells  ·  %dm×%dm" % [
		str(bp.get("category", "custom")).capitalize(),
		int(bp.get("footprint_w", 1)),
		int(bp.get("footprint_h", 1)),
		int(bp.get("footprint_w", 1)) * 10,
		int(bp.get("footprint_h", 1)) * 10,
	]
	desc_label.text = str(bp.get("description", ""))
	var labor := int(bp.get("construction_labor_cents", 0))
	cost_label.text = "Labor: %s" % WorldState.format_money(labor)
	var mats: Dictionary = bp.get("construction_materials", {}) as Dictionary
	if mats.is_empty():
		materials_label.text = "Materials: none (labor only)"
	else:
		var parts: PackedStringArray = []
		for mat in mats.keys():
			parts.append("%s × %d" % [str(mat), int(mats[mat])])
		materials_label.text = "Materials (self-build): %s" % ", ".join(parts)
	if build_mode == "turnkey":
		materials_label.text += "\nTurnkey: buys materials from market when available."
	materials_label.show()
	var recipes: Array = bp.get("enabled_recipe_ids", [])
	if recipes is Array and not recipes.is_empty():
		recipes_label.text = "Recipes: %s" % ", ".join(recipes.map(func(r): return str(r)))
		recipes_label.show()
	else:
		recipes_label.hide()
	var fee := int(bp.get("license_fee_cents", 0))
	if fee > 0 and not bool(bp.get("is_seeded", true)):
		license_label.text = "License fee: %s per build" % WorldState.format_money(fee)
		license_label.show()
	else:
		license_label.hide()
	var creator := str(bp.get("creator_party", ""))
	if creator != "" and creator != "null":
		desc_label.text += "\nCreator: %s" % WorldState.party_label(creator)
	hint_label.text = "Click the grid to place footprint. Y/Enter to confirm. Stock materials for self-build."


func set_market_context(fair_value_cents: int, free_cells: int) -> void:
	market_label.text = "Plot value: %s  ·  %d free cells" % [
		WorldState.format_money(fair_value_cents),
		free_cells,
	]
