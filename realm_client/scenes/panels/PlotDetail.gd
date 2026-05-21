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

const BUILDING_FOOTPRINTS := {
	"road_segment": Vector2i(1, 1),
	"power_shed": Vector2i(2, 2),
	"foundry": Vector2i(4, 4),
	"strip_mine": Vector2i(6, 4),
	"timber_yard": Vector2i(5, 3),
	"grain_row": Vector2i(8, 4),
	"warehouse": Vector2i(4, 4),
	"wood_shop": Vector2i(3, 3),
	"watch_hut": Vector2i(2, 2),
}

const BUILDING_CATEGORIES := {
	"strip_mine": "Extraction",
	"timber_yard": "Extraction",
	"grain_row": "Extraction",
	"drill_rig": "Extraction",
	"foundry": "Processing",
	"wood_shop": "Processing",
	"stone_works": "Processing",
	"gristmill": "Processing",
	"power_shed": "Infrastructure",
	"road_segment": "Infrastructure",
	"warehouse": "Infrastructure",
	"dock": "Infrastructure",
	"store": "Commerce",
	"bank_building": "Commerce",
	"residence": "Population",
	"assay_lab": "Research",
	"laboratory": "Research",
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
@onready var scroll: ScrollContainer = %Scroll
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
@onready var buildings_section: VBoxContainer = %BuildingsSection
@onready var buildings_list: VBoxContainer = %BuildingsList
@onready var roads_section: VBoxContainer = %RoadsSection
@onready var roads_summary: Label = %RoadsSummary
@onready var roads_list: VBoxContainer = %RoadsList
@onready var production_section: VBoxContainer = %ProductionSection
@onready var _sep_after_header: HSeparator = %SepAfterHeader
@onready var _sep_after_info: HSeparator = %SepAfterInfo
@onready var _sep_after_claim: HSeparator = %SepAfterClaim
@onready var _sep_after_survey: HSeparator = %SepAfterSurvey
@onready var _sep_after_subsurface: HSeparator = %SepAfterSubsurface
@onready var _sep_before_buildings: HSeparator = %SepBeforeBuildings
@onready var _sep_before_roads: HSeparator = %SepBeforeRoads
@onready var _sep_before_production: HSeparator = %SepBeforeProduction

const ROAD_BLUEPRINT_ID := "road_segment"

var _plot_id: String = ""
var _plot_data: Dictionary = {}
var _production_control: Node = null
var _geology_section: VBoxContainer
var _geology_jobs: Label
var _buy_plot_btn: Button

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
	_setup_geology_and_buy()
	get_viewport().size_changed.connect(_on_viewport_resized)
	WorldState.player_updated.connect(_on_world_state_player_updated)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	var vbox := %VBoxMain
	vbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	vbox.custom_minimum_size = Vector2.ZERO


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
		var lbl := n as Label
		lbl.add_theme_color_override("font_color", Color(0.9, 0.88, 0.82))
		if lbl.autowrap_mode != TextServer.AUTOWRAP_OFF:
			lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	title_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	title_label.clip_text = true
	energy_value.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	energy_value.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	if roads_summary:
		roads_summary.add_theme_color_override("font_color", Color(0.75, 0.73, 0.68))
	for lbl in [
		terrain_value,
		coords_value,
		landmass_value,
		owner_value,
		soil_value,
		plot_value_label,
		sale_status_label,
		claim_info_label,
		claim_cost_label,
	]:
		if lbl == null:
			continue
		lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		if lbl.autowrap_mode == TextServer.AUTOWRAP_OFF:
			lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART


func _setup_geology_and_buy() -> void:
	_buy_plot_btn = Button.new()
	_buy_plot_btn.text = "Buy listed plot"
	_buy_plot_btn.visible = false
	_buy_plot_btn.pressed.connect(_on_buy_plot)
	real_estate_section.add_child(_buy_plot_btn)
	_geology_section = VBoxContainer.new()
	_geology_section.name = "GeologySection"
	var gtitle := Label.new()
	gtitle.text = "Geology & assays"
	gtitle.add_theme_color_override("font_color", RealmColors.ACCENT)
	_geology_section.add_child(gtitle)
	_geology_jobs = Label.new()
	_geology_jobs.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_geology_section.add_child(_geology_jobs)
	var deep_btn := Button.new()
	deep_btn.text = "Deep survey (drill rig + bit)"
	deep_btn.pressed.connect(_on_deep_survey)
	_geology_section.add_child(deep_btn)
	var assay_row := HBoxContainer.new()
	var mineral_opt := OptionButton.new()
	for row in MINERAL_ROWS:
		mineral_opt.add_item(row[1])
		mineral_opt.set_item_metadata(mineral_opt.item_count - 1, row[0])
	assay_row.add_child(mineral_opt)
	var assay_btn := Button.new()
	assay_btn.text = "Assay"
	assay_btn.pressed.connect(func() -> void:
		if mineral_opt.selected < 0:
			return
		_on_assay(str(mineral_opt.get_item_metadata(mineral_opt.selected)))
	)
	assay_row.add_child(assay_btn)
	_geology_section.add_child(assay_row)
	_style_gold_button(deep_btn)
	_style_gold_button(assay_btn)
	_style_gold_button(_buy_plot_btn)
	var vbox := %VBoxMain
	var idx := subsurface_section.get_index() + 1
	vbox.add_child(_geology_section)
	vbox.move_child(_geology_section, idx)


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
	if WorldState.player_updated.is_connected(_on_world_state_player_updated):
		WorldState.player_updated.disconnect(_on_world_state_player_updated)
	_slide_out()


func _on_world_state_player_updated() -> void:
	if _plot_id.is_empty() or not is_inside_tree():
		return
	# Tick-level player payloads only need building rows refreshed — full
	# _populate() retriggers layout and was paired with scroll width syncing
	# that drifted content left over time.
	_refresh_buildings()
	_refresh_plot_energy()


func _refresh_plot_panel_from_state() -> void:
	if _plot_id.is_empty() or not is_inside_tree():
		return
	_plot_data = WorldState.get_plot_ui(_plot_id)
	_populate(_plot_data)
	_refresh_buildings()


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
		# claim_cost_cents is fetched lazily via /plots/{id}/value when
		# this panel opens (used to ride on /world for every plot, but
		# that forced a 9 s build for 76800-plot Genesis). The button
		# starts with a "…" placeholder until the value lands.
		var cost: int = int(p.get("claim_cost_cents", -1))
		if cost >= 0:
			claim_cost_label.text = "Cost: %s" % WorldState.format_money(cost)
			claim_confirm_label.text = "Claim for %s?" % WorldState.format_money(cost)
		else:
			claim_cost_label.text = "Cost: …"
			claim_confirm_label.text = "Claim?"

	survey_section.visible = is_mine and not is_surveyed
	var survey_cost := WorldState.format_money(WorldState.SURVEY_COST_CENTS)
	survey_btn.text = "Survey this plot (%s)" % survey_cost

	var show_sub := is_surveyed and (is_mine or has_report)
	subsurface_section.visible = show_sub
	if show_sub:
		_populate_subsurface(WorldState.subsurface_for_plot_ui(_plot_id, p))

	build_btn.visible = is_mine
	buildings_section.visible = is_mine
	roads_section.visible = is_mine
	real_estate_section.visible = not is_unclaimed
	if _geology_section:
		_geology_section.visible = is_mine and is_surveyed
		if _geology_section.visible:
			_refresh_geology_status()
	production_section.hide()
	if _production_control and is_instance_valid(_production_control):
		_production_control.queue_free()
		_production_control = null
	_sync_section_visibility()


func _refresh_plot_energy() -> void:
	if _plot_id.is_empty():
		return
	API.get_plot_energy(_plot_id, _on_energy_response)


func _format_power_generators(generators: Array) -> String:
	if generators.is_empty():
		return ""
	var parts: PackedStringArray = []
	for g in generators:
		if not (g is Dictionary):
			continue
		var row: Dictionary = g as Dictionary
		var lbl := str(row.get("label", row.get("building_id", "?")))
		if bool(row.get("active", false)):
			var cap := int(row.get("capacity_per_day", 0))
			parts.append("%s (%d/day)" % [lbl, cap])
		else:
			parts.append("%s (offline)" % lbl)
	return ", ".join(parts)


func _on_energy_response(data: Dictionary) -> void:
	if not is_instance_valid(self) or not is_inside_tree():
		return
	if data.is_empty() or not bool(data.get("ok", true)):
		energy_value.text = "—"
		energy_value.modulate = Color(0.7, 0.7, 0.7)
		return

	var lines: PackedStringArray = []
	if bool(data.get("powered", false)):
		var note := str(data.get("status_note", "Grid power available"))
		lines.append(note)
		var cap := int(data.get("capacity_per_day", 0))
		var load := int(data.get("load_per_day", 0))
		var price := int(data.get("clearing_price_cents", 0))
		lines.append(
			"Capacity %d/day · load %d/day · price %s/unit"
			% [cap, load, WorldState.format_money(price)]
		)
		var lf := float(data.get("load_factor", 0.0))
		if bool(data.get("brownout", false)):
			lines.append("Brownout — demand exceeds ~95%% of capacity (%.0f%% load)" % (lf * 100.0))
		elif lf >= 0.95:
			lines.append("Near capacity (%.0f%% load)" % (lf * 100.0))
		var gen_txt := _format_power_generators(data.get("generators", []))
		if not gen_txt.is_empty():
			lines.append("Generators: %s" % gen_txt)
		lines.append("Run coal_generator in a power_shed for electricity stock")
		energy_value.text = "\n".join(lines)
		energy_value.modulate = Color(0.45, 1.0, 0.45) if not bool(data.get("brownout")) else Color(1.0, 0.85, 0.35)
		return

	var reason := str(data.get("reason", ""))
	if reason.is_empty():
		reason = "No grid power"
	lines.append(reason)
	var gen_txt := _format_power_generators(data.get("generators", []))
	if not gen_txt.is_empty():
		lines.append("On region: %s" % gen_txt)
	if not bool(data.get("grid_connected", true)):
		lines.append(
			"Tip: cyan ports in Build → Roads link to neighbors for a shared grid"
		)
	energy_value.text = "\n".join(lines)
	energy_value.modulate = Color(1.0, 0.5, 0.3)


func _sync_section_visibility() -> void:
	_sep_after_header.visible = true
	_sep_after_info.visible = (
		claim_section.visible
		or survey_section.visible
		or subsurface_section.visible
		or real_estate_section.visible
		or buildings_section.visible
		or roads_section.visible
		or production_section.visible
	)
	_sep_after_claim.visible = claim_section.visible
	_sep_after_survey.visible = (
		survey_section.visible
		or subsurface_section.visible
		or real_estate_section.visible
		or buildings_section.visible
		or roads_section.visible
		or production_section.visible
	)
	_sep_after_subsurface.visible = (
		subsurface_section.visible
		or (_geology_section != null and _geology_section.visible)
		or real_estate_section.visible
	)
	_sep_before_buildings.visible = (
		buildings_section.visible or roads_section.visible or production_section.visible
	)
	_sep_before_roads.visible = roads_section.visible or production_section.visible
	_sep_before_production.visible = production_section.visible


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
		lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		lbl.add_theme_color_override("font_color", Color(0.9, 0.88, 0.82))
		var val := Label.new()
		val.text = _grade_label(grade)
		val.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		val.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		val.modulate = _grade_color(grade)
		subsurface_grid.add_child(lbl)
		subsurface_grid.add_child(val)


func _refresh_buildings() -> void:
	for child in buildings_list.get_children():
		child.queue_free()
	for child in roads_list.get_children():
		child.queue_free()
	_production_control = null
	_plot_data = WorldState.get_plot_ui(_plot_id)
	var all_buildings: Array = _plot_data.get("buildings", [])
	var workshops: Array = []
	var roads: Array = []
	for b in all_buildings:
		if not (b is Dictionary):
			continue
		if _is_road_building(b as Dictionary):
			roads.append(b)
		else:
			workshops.append(b)
	for b in workshops:
		buildings_list.add_child(_make_building_row(b as Dictionary))
	_refresh_roads_list(roads)
	_refresh_plot_energy()


func _is_road_building(b: Dictionary) -> bool:
	return _building_id(b) == ROAD_BLUEPRINT_ID


func _refresh_roads_list(roads: Array) -> void:
	roads_summary.text = ""
	if not is_instance_valid(roads_section):
		return
	if roads.is_empty():
		roads_summary.text = "No road segments on this plot."
		var empty_lbl := Label.new()
		empty_lbl.text = "Lay roads in Build → Roads."
		empty_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		empty_lbl.add_theme_font_size_override("font_size", 11)
		empty_lbl.add_theme_color_override("font_color", Color(0.65, 0.63, 0.58))
		roads_list.add_child(empty_lbl)
		return
	var need_attn := 0
	for b in roads:
		if b is Dictionary and _road_needs_attention(b as Dictionary):
			need_attn += 1
	roads_summary.text = "%d segment%s" % [roads.size(), "" if roads.size() == 1 else "s"]
	if need_attn > 0:
		roads_summary.text += " · %d need maintenance" % need_attn
	roads_summary.modulate = (
		Color(1.0, 0.55, 0.25) if need_attn > 0 else Color(0.75, 0.73, 0.68)
	)
	for b in roads:
		if b is Dictionary:
			roads_list.add_child(_make_road_row(b as Dictionary))


func _road_needs_attention(b: Dictionary) -> bool:
	if not _building_operational(b):
		return false
	var eff := int(b.get("_efficiency_pct", 100))
	var missed := int(b.get("_missed_cycles", 0))
	var cond := int(b.get("condition_bps", 10_000))
	return missed > 0 or eff < 100 or cond < 8_000


func _building_operational(b: Dictionary) -> bool:
	var done_tick: int = int(b.get("completes_at_tick", 0))
	if done_tick <= 0:
		return true
	return WorldState.current_tick >= done_tick


func _building_id(b: Dictionary) -> String:
	return str(b.get("building_id", b.get("blueprint_id", "")))


func _building_category_label(building_id: String) -> String:
	return BUILDING_CATEGORIES.get(building_id, "Structure")


func _building_footprint_label(building_id: String) -> String:
	var fp: Variant = BUILDING_FOOTPRINTS.get(building_id, null)
	if fp is Vector2i:
		var v := fp as Vector2i
		return "%d×%d cells" % [v.x, v.y]
	return "—"


func _format_material_list(mats: Dictionary) -> String:
	if mats.is_empty():
		return "—"
	var parts: PackedStringArray = []
	for mat in mats.keys():
		parts.append("%s×%d" % [str(mat), int(mats[mat])])
	return ", ".join(parts)


func _building_subtitle(b: Dictionary, catalog: Dictionary, building_id: String) -> String:
	var cat_lbl := str(catalog.get("label", ""))
	if cat_lbl != "" and cat_lbl != str(b.get("label", "")):
		return cat_lbl
	return ""


func _building_status_line(b: Dictionary) -> String:
	if not _building_operational(b):
		var completes := int(b.get("completes_at_tick", 0))
		if completes > WorldState.current_tick:
			var left := completes - WorldState.current_tick
			return "Under construction — ready in %s" % WorldState.format_ticks_as_gametime(left)
		return "Under construction"
	var eff := int(b.get("_efficiency_pct", 100))
	var missed_b := int(b.get("_missed_cycles", 0))
	if eff == 0:
		return "Stopped — maintenance required"
	var due_in := int(b.get("_due_in_ticks", 99_999))
	if missed_b > 0:
		return "Overdue maintenance — running at %d%% efficiency" % eff
	if due_in < 2880:
		return "Maintenance due in %s" % WorldState.format_ticks_as_gametime(due_in)
	return "Operational — next maintenance in %s" % WorldState.format_ticks_as_gametime(due_in)


func _building_detail_rows(b: Dictionary) -> Array:
	var building_id := _building_id(b)
	var catalog := WorldState.building_catalog_entry(building_id)
	var rows: Array = []
	rows.append(["Category", _building_category_label(building_id)])
	rows.append(["Blueprint", building_id if building_id != "" else "—"])
	var gx := int(b.get("grid_x", -1))
	var gy := int(b.get("grid_y", -1))
	if gx >= 0 and gy >= 0:
		rows.append(["Grid cell", "(%d, %d) · %s" % [gx, gy, _building_footprint_label(building_id)]])
	var sub_plot := str(b.get("sub_plot_id", ""))
	if sub_plot != "":
		rows.append(["Sub-plot", sub_plot.split(":")[-1]])
	var build_mode := str(b.get("build_mode", ""))
	if build_mode != "":
		rows.append(["Built", build_mode.replace("_", " ")])
	var cond_bps := int(b.get("condition_bps", 10_000))
	if cond_bps < 10_000:
		rows.append(["Condition", "%d%%" % int(cond_bps / 100)])
	var book_val := int(b.get("book_value_cents", 0))
	var orig_val := int(b.get("original_cost_cents", 0))
	if orig_val > 0:
		var dep_pct := int((1.0 - float(book_val) / float(orig_val)) * 100.0)
		rows.append(
			[
				"Book value",
				"%s (%d%% depreciated)" % [WorldState.format_money(book_val), dep_pct],
			]
		)
	elif book_val > 0:
		rows.append(["Book value", WorldState.format_money(book_val)])
	var maint: Variant = b.get("maintenance", {})
	if maint is Dictionary:
		var md: Dictionary = maint as Dictionary
		if md.get("schedule") != null:
			var interval := int(md.get("interval_ticks", 0))
			if interval > 0:
				rows.append(
					["Maintenance cycle", "Every %s" % WorldState.format_ticks_as_gametime(interval)]
				)
			var mats: Variant = md.get("materials", {})
			if mats is Dictionary and not (mats as Dictionary).is_empty():
				rows.append(["Upkeep needs", _format_material_list(mats as Dictionary)])
	elif not (b.get("_maintenance_materials", {}) as Dictionary).is_empty():
		rows.append(
			[
				"Upkeep needs",
				_format_material_list(b.get("_maintenance_materials", {}) as Dictionary),
			]
		)
	if catalog.has("capacity"):
		rows.append(["Capacity", str(catalog.get("capacity", "—"))])
	var terr: Variant = catalog.get("terrain_required", [])
	if terr is Array and not (terr as Array).is_empty():
		var names: PackedStringArray = []
		for t in terr as Array:
			names.append(TERRAIN_LABELS.get(str(t), str(t).capitalize()))
		rows.append(["Terrain", ", ".join(names)])
	var recipe_rows := WorldState.recipes_for_workshop_building(b)
	if not recipe_rows.is_empty():
		var names: PackedStringArray = []
		for r in recipe_rows:
			if r is Dictionary:
				names.append(str((r as Dictionary).get("display_name", (r as Dictionary).get("id", "?"))))
		var shown := ", ".join(names.slice(0, 4))
		if names.size() > 4:
			shown += " +%d more" % (names.size() - 4)
		rows.append(["Recipes", shown])
	var run := WorldState.active_production_run_for_building(_plot_id, b)
	if not run.is_empty():
		var rid := str(run.get("recipe_id", ""))
		var rname := str(WorldState.recipe_by_id(rid).get("display_name", rid))
		var ticks_left := int(run.get("ticks_remaining", 0))
		rows.append(
			[
				"Active run",
				"%s — %s remaining" % [rname, WorldState.format_ticks_as_gametime(ticks_left)],
			]
		)
	return rows


func _add_detail_row(grid: GridContainer, key: String, value: String) -> void:
	var key_lbl := Label.new()
	key_lbl.text = key
	key_lbl.add_theme_font_size_override("font_size", 10)
	key_lbl.add_theme_color_override("font_color", Color(0.62, 0.60, 0.55))
	var val_lbl := Label.new()
	val_lbl.text = value
	val_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	val_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	val_lbl.add_theme_font_size_override("font_size", 11)
	val_lbl.add_theme_color_override("font_color", Color(0.9, 0.88, 0.82))
	grid.add_child(key_lbl)
	grid.add_child(val_lbl)


func _make_road_row(b: Dictionary) -> PanelContainer:
	var pc := PanelContainer.new()
	pc.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.09, 0.10, 0.11)
	sb.set_content_margin_all(6)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.45, 0.48, 0.52, 0.45)
	pc.add_theme_stylebox_override("panel", sb)
	var vbox := VBoxContainer.new()
	vbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	vbox.add_theme_constant_override("separation", 4)
	pc.add_child(vbox)

	var gx := int(b.get("grid_x", -1))
	var gy := int(b.get("grid_y", -1))
	var pos_lbl := "Road segment"
	if gx >= 0 and gy >= 0:
		pos_lbl = "Cell (%d, %d)" % [gx, gy]

	var header := HBoxContainer.new()
	header.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var name_lbl := Label.new()
	name_lbl.text = pos_lbl
	name_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	name_lbl.add_theme_font_size_override("font_size", 12)
	name_lbl.add_theme_color_override("font_color", Color(0.82, 0.84, 0.88))
	header.add_child(name_lbl)

	var eff := int(b.get("_efficiency_pct", 100))
	var eff_lbl := Label.new()
	eff_lbl.text = "%d%%" % eff
	eff_lbl.modulate = _efficiency_color(eff)
	header.add_child(eff_lbl)
	vbox.add_child(header)

	var status_lbl := Label.new()
	status_lbl.text = _road_status_line(b)
	status_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status_lbl.add_theme_font_size_override("font_size", 11)
	if _road_needs_attention(b):
		status_lbl.modulate = Color(1.0, 0.55, 0.25)
	else:
		status_lbl.modulate = Color(0.55, 0.58, 0.62)
	vbox.add_child(status_lbl)

	var cond_bps := int(b.get("condition_bps", 10_000))
	if cond_bps < 10_000:
		var cond_lbl := Label.new()
		cond_lbl.text = "Surface condition %d%%" % int(cond_bps / 100)
		cond_lbl.add_theme_font_size_override("font_size", 10)
		cond_lbl.modulate = Color(0.7, 0.7, 0.75)
		vbox.add_child(cond_lbl)

	if _building_operational(b) and _road_needs_attention(b):
		var needs: Dictionary = b.get("_maintenance_materials", {}) as Dictionary
		if needs.is_empty():
			var maint: Variant = b.get("maintenance", {})
			if maint is Dictionary:
				var mm: Variant = (maint as Dictionary).get("materials", {})
				if mm is Dictionary:
					needs = mm as Dictionary
		var maintain_btn := Button.new()
		maintain_btn.text = "Maintain"
		_style_gold_button(maintain_btn)
		maintain_btn.pressed.connect(func() -> void: _on_maintain(b))
		if not needs.is_empty():
			maintain_btn.tooltip_text = "Consumes: %s" % _format_material_list(needs)
		vbox.add_child(maintain_btn)

	return pc


func _road_status_line(b: Dictionary) -> String:
	if not _building_operational(b):
		return "Under construction"
	var eff := int(b.get("_efficiency_pct", 100))
	if eff == 0:
		return "Unserviceable — maintenance required"
	var missed := int(b.get("_missed_cycles", 0))
	if missed > 0:
		return "Overdue maintenance"
	var due_in := int(b.get("_due_in_ticks", 99_999))
	if due_in < 2880:
		return "Maintenance due in %s" % WorldState.format_ticks_as_gametime(due_in)
	return "In good repair"


func _make_building_row(b: Dictionary) -> PanelContainer:
	if _is_road_building(b):
		return _make_road_row(b)
	var building_id := _building_id(b)
	var catalog := WorldState.building_catalog_entry(building_id)
	var pc := PanelContainer.new()
	pc.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.1, 0.1, 0.12)
	sb.set_content_margin_all(8)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.25)
	pc.add_theme_stylebox_override("panel", sb)
	var vbox := VBoxContainer.new()
	vbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	vbox.add_theme_constant_override("separation", 6)
	pc.add_child(vbox)

	var header := HBoxContainer.new()
	header.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var name_lbl := Label.new()
	name_lbl.text = str(b.get("label", catalog.get("label", building_id if building_id != "" else "?")))
	name_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	name_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	name_lbl.add_theme_font_size_override("font_size", 13)
	name_lbl.add_theme_color_override("font_color", Color(0.95, 0.92, 0.85))
	header.add_child(name_lbl)

	var eff: int = int(b.get("_efficiency_pct", 100))
	var eff_lbl := Label.new()
	eff_lbl.text = "%d%%" % eff
	eff_lbl.size_flags_horizontal = Control.SIZE_SHRINK_END
	eff_lbl.modulate = _efficiency_color(eff)
	header.add_child(eff_lbl)
	vbox.add_child(header)

	var subtitle := _building_subtitle(b, catalog, building_id)
	if not subtitle.is_empty():
		var desc_lbl := Label.new()
		desc_lbl.text = subtitle
		desc_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		desc_lbl.add_theme_font_size_override("font_size", 11)
		desc_lbl.add_theme_color_override("font_color", Color(0.72, 0.70, 0.65))
		vbox.add_child(desc_lbl)

	var status_lbl := Label.new()
	status_lbl.text = _building_status_line(b)
	status_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status_lbl.add_theme_font_size_override("font_size", 11)
	if not _building_operational(b):
		status_lbl.modulate = Color(0.75, 0.8, 1.0)
	elif eff == 0:
		status_lbl.modulate = Color(1.0, 0.45, 0.35)
	elif int(b.get("_missed_cycles", 0)) > 0:
		status_lbl.modulate = Color(1.0, 0.55, 0.25)
	else:
		status_lbl.modulate = Color(0.55, 0.9, 0.55)
	vbox.add_child(status_lbl)

	var details := GridContainer.new()
	details.columns = 2
	details.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	details.add_theme_constant_override("h_separation", 10)
	details.add_theme_constant_override("v_separation", 3)
	for row in _building_detail_rows(b):
		if row is Array and (row as Array).size() >= 2:
			_add_detail_row(details, str(row[0]), str(row[1]))
	if details.get_child_count() > 0:
		vbox.add_child(details)

	var book_val := int(b.get("book_value_cents", 0))
	var missed_b: int = int(b.get("_missed_cycles", 0))

	var btns := HBoxContainer.new()
	btns.size_flags_horizontal = Control.SIZE_EXPAND_FILL
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

	var supports_prod := WorldState.building_supports_production(b)
	var is_wh := WorldState.building_is_warehouse(b)
	if supports_prod or is_wh:
		var prod_btn := Button.new()
		prod_btn.text = "Warehouse" if is_wh else "Production"
		_style_gold_button(prod_btn)
		prod_btn.disabled = not _building_operational(b)
		if prod_btn.disabled:
			prod_btn.tooltip_text = "Available when construction finishes"
		elif is_wh:
			prod_btn.tooltip_text = "Replenish rules and stash for this warehouse"
		else:
			var n := WorldState.recipes_for_workshop_building(b).size()
			prod_btn.tooltip_text = "%d recipe(s) on this blueprint" % n
		prod_btn.pressed.connect(func() -> void: _show_production_for(b))
		btns.add_child(prod_btn)
	if WorldState.recipes_for_workshop_building(b).size() > 0:
		var chain_btn := Button.new()
		chain_btn.text = "Chain"
		_style_gold_button(chain_btn)
		chain_btn.tooltip_text = "Recipe chain planner (Operations)"
		chain_btn.pressed.connect(_open_operations_chains)
		btns.add_child(chain_btn)
	if _building_operational(b) and str(b.get("instance_id", "")) != "":
		var demolish_btn := Button.new()
		demolish_btn.text = "🔨 Demolish (salvage %s)" % WorldState.format_money(book_val / 2)
		demolish_btn.modulate = Color(1.0, 0.4, 0.4)
		demolish_btn.pressed.connect(
			func() -> void: _confirm_demolish(str(b.get("instance_id", "")), book_val / 2)
		)
		btns.add_child(demolish_btn)
	vbox.add_child(btns)

	return pc


func _confirm_demolish(instance_id: String, salvage_cents: int) -> void:
	if instance_id == "":
		return
	API.demolish_building(
		instance_id,
		func(res: Dictionary) -> void:
			if bool(res.get("ok", false)):
				_refresh_buildings()
				API.get_world_player(
					func(p: Dictionary) -> void: WorldState.apply_player(p),
					WorldState.party_id,
				)
				API.get_world_summary(
					WorldState.party_id,
					func(s: Dictionary) -> void: WorldState.apply_summary(s),
				)
			else:
				push_warning("Demolish failed: %s" % str(res.get("reason", "?"))),
		WorldState.party_id,
	)


func _show_production_for(b: Dictionary) -> void:
	var host: Node = get_tree().current_scene
	if host != null and host.has_method("open_production_workflow"):
		host.call("open_production_workflow", _plot_id, b, _plot_data)
		return
	push_warning("PlotDetail: Main.open_production_workflow unavailable")


func _open_operations_chains() -> void:
	var host: Node = get_tree().current_scene
	if host != null and host.has_method("_on_nav_pressed"):
		host.call("_on_nav_pressed", "operations")


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
				var owner := str(data.get("owner", WorldState.party_id))
				if owner.is_empty():
					owner = WorldState.party_id
				_apply_claimed_ui(owner)
				MainFeedback.toast("Plot %s claimed" % _plot_id)
				API.get_world_summary(WorldState.party_id, func(s): WorldState.apply_summary(s))
				API.get_world_player(
					func(pdata: Dictionary) -> void:
						WorldState.apply_player(pdata)
						_refresh_plot_panel_from_state(),
					WorldState.party_id,
				)
				API.get_world_map(func(m: Dictionary) -> void: WorldState.apply_map(m))
			else:
				claim_btn.disabled = false
				claim_btn.text = "Claim plot"
				_show_error(str(data.get("reason", "Claim failed")))
	)


func _apply_claimed_ui(owner: String) -> void:
	WorldState.set_plot_owner(_plot_id, owner)
	_refresh_plot_panel_from_state()


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
				WorldState.set_plot_surveyed(_plot_id, true)
				# Map flips surveyed; player payload carries owned survey reports.
				API.get_world_map(
					func(m: Dictionary) -> void:
						WorldState.apply_map(m)
						API.get_world_player(
							func(pdata: Dictionary) -> void:
								WorldState.apply_player(pdata)
								if is_instance_valid(self) and is_inside_tree():
									_refresh_plot_panel_from_state(),
							WorldState.party_id,
						),
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
	# Lazy claim-cost fetch (see _populate above for why it's not on the
	# /world/map payload anymore). Update the button label as soon as
	# this response lands.
	var cc: Variant = data.get("claim_cost_cents", null)
	if cc != null:
		_plot_data["claim_cost_cents"] = int(cc)
		var owner_v: Variant = _plot_data.get("owner", null)
		if owner_v == null:
			claim_cost_label.text = "Cost: %s" % WorldState.format_money(int(cc))
			claim_confirm_label.text = "Claim for %s?" % WorldState.format_money(int(cc))
	var fair := int(data.get("fair_value_cents", 0))
	plot_value_label.text = "Fair value: %s" % WorldState.format_money(fair)
	var listed := bool(data.get("listed_for_sale", false))
	var owner_s := _plot_owner_str(_plot_data)
	var is_mine := owner_s == WorldState.party_id
	if listed:
		var ask := int(data.get("ask_price_cents", fair))
		sale_status_label.text = "Listed for %s" % WorldState.format_money(ask)
		list_for_sale_btn.text = "Update listing"
		if _buy_plot_btn:
			_buy_plot_btn.visible = not is_mine
	elif is_mine:
		sale_status_label.text = "Not listed"
		list_for_sale_btn.text = "List for sale"
		if _buy_plot_btn:
			_buy_plot_btn.visible = false
	else:
		var npc_bid := int(data.get("top_npc_bid_cents", 0))
		if npc_bid > 0:
			sale_status_label.text = "Top NPC interest: %s" % WorldState.format_money(npc_bid)
		else:
			sale_status_label.text = ""
		list_for_sale_btn.hide()
		if _buy_plot_btn:
			_buy_plot_btn.visible = false
		return
	list_for_sale_btn.visible = is_mine


func _on_buy_plot() -> void:
	if _plot_id.is_empty():
		return
	_buy_plot_btn.disabled = true
	API.buy_plot(
		_plot_id,
		func(data: Dictionary) -> void:
			_buy_plot_btn.disabled = false
			if bool(data.get("ok", false)):
				MainFeedback.toast("Plot purchased")
				API.get_world_map(func(m): WorldState.apply_map(m))
				API.get_world_player(func(p): WorldState.apply_player(p), WorldState.party_id)
				API.get_plot_value(_plot_id, _on_plot_value_response)
				_plot_data = WorldState.get_plot_ui(_plot_id)
				_populate(_plot_data)
			else:
				_show_error(str(data.get("reason", "Purchase failed"))),
	)


func _refresh_geology_status() -> void:
	if _geology_jobs == null:
		return
	_geology_jobs.text = "Loading jobs…"
	API.get_assay_status(func(st: Dictionary) -> void:
		var parts: PackedStringArray = []
		for j in st.get("jobs", []) as Array:
			if j is Dictionary and str((j as Dictionary).get("plot_id", "")) == _plot_id:
				parts.append("Assay: %s" % str(j))
		API.get_deep_survey_status(func(ds: Dictionary) -> void:
			for j in ds.get("jobs", []) as Array:
				if j is Dictionary and str((j as Dictionary).get("plot_id", "")) == _plot_id:
					parts.append("Deep survey: %s" % str(j))
			_geology_jobs.text = "\n".join(parts) if parts.size() else "No active geology jobs on this plot"
		)
	)


func _on_deep_survey() -> void:
	API.deep_survey_plot(
		_plot_id,
		func(data: Dictionary) -> void:
			if bool(data.get("ok", false)):
				MainFeedback.toast("Deep survey started")
				_refresh_geology_status()
			else:
				_show_error(str(data.get("reason", "Deep survey failed"))),
	)


func _on_assay(mineral_id: String) -> void:
	API.assay_mineral(
		_plot_id,
		mineral_id,
		func(data: Dictionary) -> void:
			if bool(data.get("ok", false)):
				MainFeedback.toast("Assay submitted")
				_refresh_geology_status()
			else:
				_show_error(str(data.get("reason", "Assay failed"))),
	)


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
