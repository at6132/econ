extends CanvasLayer
## Slides in from the right: plot summary, claim/survey/build, buildings, embedded production.

const PANEL_WIDTH := 420.0
const HUD_BAR_TOP := 96.0

const TERRAIN_LABELS := {
	"water_deep": "Deep ocean",
	"water_shallow": "Shallow water",
	"coastal": "Coastal",
	"plains": "Plains",
	"forest": "Forest",
	"temperate_forest": "Temperate forest",
	"tropical": "Tropical",
	"mountain": "Mountain",
	"hills": "Hills",
	"desert": "Desert",
	"tundra": "Tundra",
	"swamp": "Swamp",
	"valley": "Valley",
}

const MINERAL_ROWS := [
	["iron_ore_grade", "Iron ore"],
	["coal_grade", "Coal"],
	["copper_ore_grade", "Copper ore"],
	["tin_grade", "Tin"],
	["lead_grade", "Lead"],
	["sulfur_grade", "Sulfur"],
	["phosphate_grade", "Phosphate"],
	["clay_grade", "Clay"],
	["saltpeter_grade", "Saltpeter"],
	["silica_grade", "Silica"],
	["platinum_grade", "Platinum"],
	["oil_shale_grade", "Oil shale"],
	["rare_earth_grade", "Rare earth"],
]

@onready var panel: Panel = %Panel
@onready var title_label: Label = %TitleLabel
@onready var close_btn: Button = %CloseBtn
@onready var terrain_value: Label = %TerrainValue
@onready var coords_value: Label = %CoordsValue
@onready var landmass_value: Label = %LandmassValue
@onready var owner_value: Label = %OwnerValue
@onready var energy_value: Label = %EnergyValue
@onready var soil_row: HBoxContainer = %SoilRow
@onready var soil_value: Label = %SoilValue
@onready var claim_section: VBoxContainer = %ClaimSection
@onready var claim_info_label: Label = %ClaimInfoLabel
@onready var claim_cost_label: Label = %ClaimCostLabel
@onready var claim_btn: Button = %ClaimBtn
@onready var claim_confirm_bar: HBoxContainer = %ClaimConfirmBar
@onready var claim_confirm_label: Label = %ClaimConfirmLabel
@onready var claim_confirm_btn: Button = %ClaimConfirmBtn
@onready var claim_cancel_btn: Button = %ClaimCancelBtn
@onready var survey_section: VBoxContainer = %SurveySection
@onready var survey_btn: Button = %SurveyBtn
@onready var subsurface_section: VBoxContainer = %SubsurfaceSection
@onready var subsurface_grid: GridContainer = %SubsurfaceGrid
@onready var real_estate_section: VBoxContainer = %RealEstateSection
@onready var plot_value_label: Label = %PlotValueLabel
@onready var sale_status_label: Label = %SaleStatusLabel
@onready var list_for_sale_btn: Button = %ListForSaleBtn
@onready var build_btn: Button = %BuildBtn
@onready var buildings_list: VBoxContainer = %BuildingsList
@onready var production_section: VBoxContainer = %ProductionSection

var _plot_id: String = ""
var _plot_data: Dictionary = {}
var _production_control: Node = null

const ProductionControlScene := preload("res://scenes/panels/ProductionControl.tscn")


func _ready() -> void:
	_apply_theme()
	var vp := get_viewport().get_visible_rect().size
	panel.position = Vector2(vp.x, HUD_BAR_TOP)
	panel.size = Vector2(PANEL_WIDTH, vp.y - HUD_BAR_TOP)
	close_btn.mouse_filter = Control.MOUSE_FILTER_STOP
	close_btn.z_index = 10
	close_btn.pressed.connect(close)
	claim_btn.pressed.connect(_on_claim_btn)
	claim_confirm_btn.pressed.connect(_on_claim_confirm)
	claim_cancel_btn.pressed.connect(
		func() -> void:
			claim_confirm_bar.hide()
			claim_btn.show()
	)
	survey_btn.pressed.connect(_on_survey)
	build_btn.pressed.connect(_on_build_btn)
	list_for_sale_btn.pressed.connect(_on_list_for_sale)
	get_viewport().size_changed.connect(_on_viewport_resized)


func _on_viewport_resized() -> void:
	var vp := get_viewport().get_visible_rect().size
	panel.size = Vector2(PANEL_WIDTH, vp.y - HUD_BAR_TOP)
	if panel.position.x < vp.x - PANEL_WIDTH + 1.0:
		panel.position.x = vp.x - PANEL_WIDTH


func _apply_theme() -> void:
	var bg := StyleBoxFlat.new()
	bg.bg_color = Color(0.08, 0.08, 0.1)
	bg.set_border_width_all(1)
	bg.border_color = Color(0.85, 0.72, 0.2, 0.35)
	panel.add_theme_stylebox_override("panel", bg)
	_style_gold_button(close_btn)
	_style_gold_button(claim_btn)
	_style_gold_button(claim_confirm_btn)
	_style_gold_button(claim_cancel_btn)
	_style_gold_button(survey_btn)
	_style_gold_button(build_btn)
	_style_gold_button(list_for_sale_btn)
	for n in panel.find_children("*", "Label", true, false):
		(n as Label).add_theme_color_override("font_color", Color(0.9, 0.88, 0.82))


func _style_gold_button(btn: Button) -> void:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.12, 0.12, 0.14)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.55)
	btn.add_theme_stylebox_override("normal", sb)
	var sb_h := sb.duplicate()
	sb_h.border_color = Color(0.95, 0.82, 0.35)
	btn.add_theme_stylebox_override("hover", sb_h as StyleBoxFlat)
	btn.add_theme_color_override("font_color", Color(0.9, 0.88, 0.82))


func open(plot_id: String, plot_data: Dictionary) -> void:
	_plot_id = plot_id
	_plot_data = plot_data.duplicate(true)
	_populate(_plot_data)
	_slide_in()
	API.get_plot_energy(plot_id, _on_energy_response)
	API.get_plot_value(plot_id, _on_plot_value_response)
	_refresh_buildings()


func close() -> void:
	_slide_out()


func _slide_in() -> void:
	var vp := get_viewport().get_visible_rect().size
	var tw := create_tween().set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	tw.tween_property(panel, "position:x", vp.x - PANEL_WIDTH, 0.25)


func _slide_out() -> void:
	if not is_inside_tree():
		return
	var vp := get_viewport().get_visible_rect().size
	var tw := create_tween().set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_IN)
	tw.tween_property(panel, "position:x", vp.x, 0.2)
	tw.finished.connect(queue_free, CONNECT_ONE_SHOT)


func _plot_owner_str(p: Dictionary) -> String:
	var o: Variant = p.get("owner", null)
	if o == null:
		return ""
	return str(o)


func _populate(p: Dictionary) -> void:
	var terrain := str(p.get("terrain", "plains"))
	var x := int(p.get("x", 0))
	var y := int(p.get("y", 0))
	var owner_s := _plot_owner_str(p)
	var is_mine := owner_s == WorldState.party_id
	var is_unclaimed := owner_s.is_empty()
	var is_surveyed := bool(p.get("surveyed", false))
	var has_report := WorldState.player_has_survey_report_for_plot(_plot_id)

	title_label.text = "Plot %s · %s" % [_plot_id, TERRAIN_LABELS.get(terrain, terrain.capitalize())]
	terrain_value.text = TERRAIN_LABELS.get(terrain, terrain.capitalize())
	coords_value.text = "(%d, %d)" % [x, y]
	landmass_value.text = WorldState.scenario_id if WorldState.scenario_id != "" else "Genesis"
	if is_unclaimed:
		owner_value.text = "Unclaimed"
	elif is_mine:
		owner_value.text = "You"
	else:
		owner_value.text = str(WorldState.party_display_names.get(owner_s, owner_s))

	var ag_terrains: Array[String] = ["plains", "valley", "tropical", "temperate_forest", "forest"]
	if terrain in ag_terrains:
		var sub_src: Dictionary = WorldState.subsurface_for_plot_ui(_plot_id, p)
		var phosphate := float(sub_src.get("phosphate_grade", 0.0))
		soil_value.text = _grade_label(phosphate)
		soil_row.show()
	else:
		soil_row.hide()

	claim_section.visible = is_unclaimed
	claim_confirm_bar.hide()
	claim_btn.show()
	if is_unclaimed:
		claim_info_label.text = "This plot is unclaimed."
		var cost: int = int(p.get("claim_cost_cents", 500))
		claim_cost_label.text = "Cost: %s" % WorldState.format_money(cost)
		claim_confirm_label.text = "Claim for %s?" % WorldState.format_money(cost)

	survey_section.visible = is_mine and not is_surveyed
	var survey_cost := WorldState.format_money(WorldState.SURVEY_COST_CENTS)
	survey_btn.text = "Survey this plot (%s)" % survey_cost

	var show_sub := is_surveyed and (is_mine or has_report)
	subsurface_section.visible = show_sub
	if show_sub:
		_populate_subsurface(WorldState.subsurface_for_plot_ui(_plot_id, p))

	build_btn.visible = is_mine
	real_estate_section.visible = not is_unclaimed
	production_section.hide()
	if _production_control and is_instance_valid(_production_control):
		_production_control.queue_free()
		_production_control = null


func _on_energy_response(data: Dictionary) -> void:
	if not is_instance_valid(self) or not is_inside_tree():
		return
	if data.is_empty() or not bool(data.get("ok", true)):
		energy_value.text = "—"
		energy_value.modulate = Color(0.7, 0.7, 0.7)
		return
	if bool(data.get("powered", false)):
		var srcs: Variant = data.get("power_sources", [])
		if srcs is Array and not srcs.is_empty() and srcs[0] is Dictionary:
			var s: Dictionary = srcs[0]
			var dist: int = int(s.get("distance_tiles", 0))
			var bid: String = str(s.get("building_id", "?"))
			energy_value.text = "Powered (%s, %d tiles)" % [bid, dist]
			energy_value.modulate = Color(0.4, 1.0, 0.4)
			return
		energy_value.text = "Powered"
		energy_value.modulate = Color(0.4, 1.0, 0.4)
		return
	var near: Variant = data.get("nearest_power_source", null)
	if near is Dictionary:
		var d: int = int(near.get("distance_tiles", 0))
		var bid: String = str(near.get("building_id", "?"))
		energy_value.text = "No grid power (%s, %d tiles away)" % [bid, d]
	else:
		energy_value.text = "No power sources on this map yet"
	energy_value.modulate = Color(1.0, 0.5, 0.3)


func _populate_subsurface(sub: Dictionary) -> void:
	for child in subsurface_grid.get_children():
		child.queue_free()
	for pair in MINERAL_ROWS:
		var key: String = pair[0]
		var disp: String = pair[1]
		var grade: float = float(sub.get(key, 0.0))
		if grade < 0.05:
			continue
		var lbl := Label.new()
		lbl.text = disp
		lbl.add_theme_color_override("font_color", Color(0.9, 0.88, 0.82))
		var val := Label.new()
		val.text = _grade_label(grade)
		val.modulate = _grade_color(grade)
		subsurface_grid.add_child(lbl)
		subsurface_grid.add_child(val)


func _refresh_buildings() -> void:
	for child in buildings_list.get_children():
		child.queue_free()
	_production_control = null
	_plot_data = WorldState.get_plot_ui(_plot_id)
	var buildings: Array = _plot_data.get("buildings", [])
	for b in buildings:
		if b is Dictionary:
			buildings_list.add_child(_make_building_row(b as Dictionary))


func _building_operational(b: Dictionary) -> bool:
	var done_tick: int = int(b.get("completes_at_tick", 0))
	if done_tick <= 0:
		return true
	return WorldState.current_tick >= done_tick


func _make_building_row(b: Dictionary) -> PanelContainer:
	var pc := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.1, 0.1, 0.12)
	sb.set_content_margin_all(6)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.25)
	pc.add_theme_stylebox_override("panel", sb)
	var vbox := VBoxContainer.new()
	pc.add_child(vbox)

	var header := HBoxContainer.new()
	var name_lbl := Label.new()
	name_lbl.text = str(b.get("label", b.get("building_id", "?")))
	name_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	name_lbl.add_theme_color_override("font_color", Color(0.9, 0.88, 0.82))
	header.add_child(name_lbl)

	var eff: int = int(b.get("_efficiency_pct", 100))
	var missed_b: int = int(b.get("_missed_cycles", 0))
	var eff_lbl := Label.new()
	eff_lbl.text = "%d%%" % eff
	eff_lbl.modulate = _efficiency_color(eff)
	header.add_child(eff_lbl)
	vbox.add_child(header)

	var maint_lbl := Label.new()
	maint_lbl.add_theme_font_size_override("font_size", 11)
	maint_lbl.add_theme_color_override("font_color", Color(0.9, 0.88, 0.82))
	if not _building_operational(b):
		maint_lbl.text = "Under construction…"
		maint_lbl.modulate = Color(0.75, 0.8, 1.0)
	elif eff == 0:
		maint_lbl.text = "Stopped — maintenance required"
		maint_lbl.modulate = Color.WHITE
	else:
		var due_in: int = int(b.get("_due_in_ticks", 99_999))
		if missed_b > 0:
			maint_lbl.text = "Overdue — efficiency %d%%" % eff
			maint_lbl.modulate = Color(1, 0.3, 0.3)
		elif due_in < 2880:
			maint_lbl.text = "Due in %s" % WorldState.format_ticks_as_gametime(due_in)
			maint_lbl.modulate = Color(1, 0.85, 0.2)
		else:
			maint_lbl.text = "Healthy — due in %s" % WorldState.format_ticks_as_gametime(due_in)
			maint_lbl.modulate = Color(0.4, 1, 0.4)
	vbox.add_child(maint_lbl)

	var btns := HBoxContainer.new()
	if _building_operational(b) and (missed_b > 0 or eff < 100):
		var maintain_btn := Button.new()
		var needs: Dictionary = b.get("_maintenance_materials", {}) as Dictionary
		maintain_btn.text = "Maintain"
		_style_gold_button(maintain_btn)
		maintain_btn.pressed.connect(func() -> void: _on_maintain(b))
		if not needs.is_empty():
			var parts: PackedStringArray = []
			for mat in needs.keys():
				parts.append("%s×%d" % [str(mat), int(needs[mat])])
			maintain_btn.tooltip_text = "Consumes: %s" % ", ".join(parts)
		btns.add_child(maintain_btn)

	var prod_btn := Button.new()
	prod_btn.text = "Production"
	_style_gold_button(prod_btn)
	prod_btn.disabled = not _building_operational(b)
	if prod_btn.disabled:
		prod_btn.tooltip_text = "Available when construction finishes"
	prod_btn.pressed.connect(func() -> void: _show_production_for(b))
	btns.add_child(prod_btn)
	vbox.add_child(btns)

	return pc


func _show_production_for(b: Dictionary) -> void:
	if _production_control and is_instance_valid(_production_control):
		_production_control.queue_free()
	_production_control = ProductionControlScene.instantiate()
	production_section.add_child(_production_control)
	production_section.show()
	if _production_control.has_method("setup"):
		_production_control.call("setup", _plot_id, b, str(_plot_data.get("terrain", "plains")))


func _on_claim_btn() -> void:
	claim_btn.hide()
	claim_confirm_bar.show()


func _on_claim_confirm() -> void:
	claim_confirm_bar.hide()
	claim_btn.show()
	claim_btn.disabled = true
	claim_btn.text = "Claiming…"
	API.claim_plot(
		_plot_id,
		func(data: Dictionary) -> void:
			if bool(data.get("ok", false)):
				claim_section.hide()
				API.get_world_map(
					func(m: Dictionary) -> void:
						WorldState.apply_map(m)
						API.get_world_player(
							func(pdata: Dictionary) -> void:
								WorldState.apply_player(pdata)
								_plot_data = WorldState.get_plot_ui(_plot_id)
								_populate(WorldState.plots.get(_plot_id, _plot_data))
								_refresh_buildings(),
							WorldState.party_id,
						)
				)
				API.get_world_summary(WorldState.party_id, func(s): WorldState.apply_summary(s))
			else:
				claim_btn.disabled = false
				claim_btn.text = "Claim plot"
				_show_error(str(data.get("reason", "Claim failed")))
	)


func _on_survey() -> void:
	survey_btn.disabled = true
	survey_btn.text = "Surveying…"
	API.survey_plot(
		_plot_id,
		func(data: Dictionary) -> void:
			survey_btn.disabled = false
			var survey_cost := WorldState.format_money(WorldState.SURVEY_COST_CENTS)
			survey_btn.text = "Survey this plot (%s)" % survey_cost
			if bool(data.get("ok", false)):
				survey_section.hide()
				# Survey reveals subsurface — that data lives on /world/player.
				# Refresh the map so the surveyed flag flips, then player so
				# the subsurface grades land in the owned-plots entry.
				API.get_world_map(func(m): WorldState.apply_map(m))
				API.get_world_player(
					func(pdata: Dictionary) -> void:
						WorldState.apply_player(pdata)
						_plot_data = WorldState.get_plot_ui(_plot_id)
						var base: Dictionary = WorldState.plots.get(_plot_id, {})
						_populate(base)
						_populate_subsurface(WorldState.subsurface_for_plot_ui(_plot_id, base))
						subsurface_section.show(),
					WorldState.party_id,
				)
			else:
				_show_error(str(data.get("reason", "Survey failed")))
	)


func _on_plot_value_response(data: Dictionary) -> void:
	if not is_instance_valid(self) or not is_inside_tree():
		return
	if data.is_empty():
		return
	_plot_data["market"] = data
	var fair := int(data.get("fair_value_cents", 0))
	plot_value_label.text = "Fair value: %s" % WorldState.format_money(fair)
	var listed := bool(data.get("listed_for_sale", false))
	var owner_s := _plot_owner_str(_plot_data)
	var is_mine := owner_s == WorldState.party_id
	if listed:
		var ask := int(data.get("ask_price_cents", fair))
		sale_status_label.text = "Listed for %s" % WorldState.format_money(ask)
		list_for_sale_btn.text = "Update listing"
	elif is_mine:
		sale_status_label.text = "Not listed"
		list_for_sale_btn.text = "List for sale"
	else:
		var npc_bid := int(data.get("top_npc_bid_cents", 0))
		if npc_bid > 0:
			sale_status_label.text = "Top NPC interest: %s" % WorldState.format_money(npc_bid)
		else:
			sale_status_label.text = ""
		list_for_sale_btn.hide()
		return
	list_for_sale_btn.visible = is_mine


func _on_list_for_sale() -> void:
	list_for_sale_btn.disabled = true
	var fair := 0
	if _plot_data.has("market"):
		fair = int(_plot_data["market"].get("fair_value_cents", 0))
	API.list_plot_for_sale(
		_plot_id,
		fair if fair > 0 else 0,
		func(data: Dictionary) -> void:
			list_for_sale_btn.disabled = false
			if bool(data.get("ok", false)):
				API.get_plot_value(_plot_id, _on_plot_value_response)
				API.get_world_player(func(p): WorldState.apply_player(p), WorldState.party_id)
			else:
				_show_error(str(data.get("reason", "Listing failed"))),
	)


func _on_build_btn() -> void:
	var host: Node = get_tree().current_scene
	if host != null and host.has_method("open_build_panel"):
		host.call("open_build_panel", _plot_id, _plot_data)
		return
	if host != null and host.has_method("open_building_picker"):
		host.call("open_building_picker", _plot_id, str(_plot_data.get("terrain", "plains")))
		return
	push_warning("PlotDetail: Main.open_build_panel unavailable")


func _on_maintain(b: Dictionary) -> void:
	var instance_id: String = str(b.get("instance_id", ""))
	API.maintain_building(
		_plot_id,
		instance_id,
		func(data: Dictionary) -> void:
			if bool(data.get("ok", false)):
				API.get_world_player(
					func(pdata: Dictionary) -> void:
						WorldState.apply_player(pdata)
						_plot_data = WorldState.get_plot_ui(_plot_id)
						_refresh_buildings()
				)
			else:
				_show_error(str(data.get("reason", "Maintenance failed")))
	)


func _show_error(msg: String) -> void:
	var err := Label.new()
	err.text = "⚠ %s" % msg
	err.modulate = Color(1, 0.3, 0.3)
	err.add_theme_font_size_override("font_size", 11)
	%VBoxMain.add_child(err)
	await get_tree().create_timer(3.0).timeout
	if is_instance_valid(err):
		err.queue_free()


func _grade_label(grade: float) -> String:
	if grade >= 0.7:
		return "Rich (%.0f%%)" % (grade * 100.0)
	if grade >= 0.5:
		return "Good (%.0f%%)" % (grade * 100.0)
	if grade >= 0.3:
		return "Moderate (%.0f%%)" % (grade * 100.0)
	if grade >= 0.1:
		return "Poor (%.0f%%)" % (grade * 100.0)
	return "Trace"


func _grade_color(grade: float) -> Color:
	if grade >= 0.7:
		return Color(0.2, 1.0, 0.3)
	if grade >= 0.5:
		return Color(0.6, 1.0, 0.3)
	if grade >= 0.3:
		return Color(1.0, 0.85, 0.2)
	return Color(0.7, 0.7, 0.7)


func _efficiency_color(eff: int) -> Color:
	if eff >= 90:
		return Color(0.3, 1.0, 0.3)
	if eff >= 70:
		return Color(1.0, 0.85, 0.2)
	if eff > 0:
		return Color(1.0, 0.4, 0.2)
	return Color(0.5, 0.5, 0.5)
