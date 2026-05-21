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
			if not current_blueprint.is_empty():
				_reset_hint()
	)
	mode_self.toggled.connect(func(on: bool) -> void:
		if on:
			build_mode = "self"
			build_mode_changed.emit(build_mode)
			if not current_blueprint.is_empty():
				_reset_hint()
	)
	_apply_theme()


func _apply_theme() -> void:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.08, 0.08, 0.1)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.25)
	add_theme_stylebox_override("panel", sb)


func show_blueprint(bp: Dictionary) -> void:
	if str(bp.get("blueprint_id", "")) == "road_segment":
		show_roads_context({})
		return
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
	var turnkey_est := int(bp.get("turnkey_estimate_cents", 0))
	var mat_est := int(bp.get("turnkey_materials_cents", 0))
	if build_mode == "turnkey" and turnkey_est > 0:
		cost_label.text = "Turnkey total: %s" % WorldState.format_money(turnkey_est)
		var pricing := str(bp.get("turnkey_pricing", "market"))
		var price_note := "market asks" if pricing == "market" else "fair-value estimate (no asks)"
		cost_label.text += "\nLabor %s · Materials ~%s (%s)" % [
			WorldState.format_money(labor),
			WorldState.format_money(mat_est),
			price_note,
		]
	else:
		cost_label.text = "Labor: %s" % WorldState.format_money(labor)
	var mats: Dictionary = bp.get("construction_materials", {}) as Dictionary
	var mat_lines: Dictionary = bp.get("turnkey_material_lines_cents", {}) as Dictionary
	if mats.is_empty():
		materials_label.text = "Materials: none (labor only)"
	else:
		var parts: PackedStringArray = []
		for mat in mats.keys():
			var line := "%s × %d" % [str(mat), int(mats[mat])]
			if build_mode == "turnkey" and mat_lines.has(mat):
				line += " (~%s)" % WorldState.format_money(int(mat_lines[mat]))
			parts.append(line)
		materials_label.text = (
			"Materials (self-build): %s"
			if build_mode != "turnkey"
			else "Materials (turnkey): %s"
		) % ", ".join(parts)
	if build_mode == "turnkey":
		materials_label.text += "\nTurnkey buys from the market when listed; otherwise fair-value."
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
	_reset_hint()


func show_placement_error(msg: String) -> void:
	var reason := msg.strip_edges()
	if reason.is_empty():
		reason = "Placement failed"
	hint_label.text = "Cannot place: %s" % reason
	hint_label.add_theme_color_override("font_color", Color(1.0, 0.38, 0.32))
	hint_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART


func _reset_hint() -> void:
	hint_label.remove_theme_color_override("font_color")
	hint_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	if build_mode == "turnkey":
		hint_label.text = (
			"Click the grid to place. Y or Enter to confirm, N or Esc to cancel. "
			+ "Turnkey charges labor plus market materials."
		)
	else:
		hint_label.text = (
			"Click the grid to place. Y or Enter to confirm, N or Esc to cancel. "
			+ "You must stock construction materials in inventory for self-build."
		)


func show_roads_context(grid: Dictionary) -> void:
	current_blueprint = {}
	mode_row.visible = true
	name_label.text = "Roads"
	meta_label.text = "Site grid (10m cells) · world edges (plot-to-plot)"
	var linked := bool(grid.get("site_roads_link_world", false))
	var workshops := bool(grid.get("site_roads_connect_workshops", false))
	var world_ok := bool(grid.get("road_accessible", false))
	var status_parts: PackedStringArray = []
	if world_ok:
		status_parts.append("World network: connected")
	elif linked:
		status_parts.append("World network: site road reaches neighbor highway")
	else:
		status_parts.append("World network: not linked")
	if workshops:
		status_parts.append("Workshops: site roads OK")
	else:
		status_parts.append("Workshops: need road beside each building")
	desc_label.text = "\n".join(status_parts)
	cost_label.text = "Site road: turnkey per cell (road_segment)"
	materials_label.text = "World road: lumber×2 + stone×2 + $120 on adjacent plot edge"
	recipes_label.hide()
	license_label.hide()
	hint_label.text = (
		"Drag on the grid to paint site roads. Click cyan edge ports to build a "
		+ "world road to the neighboring plot ($120 + materials)."
	)
	hint_label.remove_theme_color_override("font_color")


func set_market_context(fair_value_cents: int, free_cells: int) -> void:
	market_label.text = "Plot value: %s  ·  %d free cells" % [
		WorldState.format_money(fair_value_cents),
		free_cells,
	]


func set_cluster_context(plot_data: Dictionary) -> void:
	var cluster_bonus := float(plot_data.get("cluster_bonus", 0.0))
	var nearby := int(plot_data.get("nearby_buildings_same_owner", 0))
	if cluster_bonus > 0.0:
		market_label.text += "\n🏭 %d buildings nearby — +10%% cluster bonus active!" % nearby
	elif nearby > 0:
		var need := maxi(0, 4 - nearby)
		market_label.text += "\nBuild %d more buildings within 5 tiles for cluster bonus" % need
