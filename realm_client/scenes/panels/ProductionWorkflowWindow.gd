extends CanvasLayer
## Building hub — centered ops console: overview, run, logistics, supply, automation.

signal closed

const ProductionControlScene := preload("res://scenes/panels/ProductionControl.tscn")
const LogisticsSitePickerScene := preload("res://scenes/panels/logistics/LogisticsSitePicker.tscn")

@onready var _title: Label = %TitleLabel
@onready var _close_btn: Button = %CloseBtn
@onready var _subtitle: Label = %SubtitleLabel
@onready var _context_strip_host: VBoxContainer = %ContextStripHost
@onready var _tab_overview: Button = %TabOverviewBtn
@onready var _tab_run: Button = %TabRunBtn
@onready var _tab_routing: Button = %TabRoutingBtn
@onready var _tab_warehouse: Button = %TabWarehouseBtn
@onready var _tab_automation: Button = %TabAutomationBtn
@onready var _overview_page: ScrollContainer = %OverviewPage
@onready var _overview_inner: VBoxContainer = %OverviewInner
@onready var _run_page: VBoxContainer = %RunPage
@onready var _routing_page: ScrollContainer = %RoutingPage
@onready var _routing_inner: VBoxContainer = %RoutingInner
@onready var _warehouse_page: HBoxContainer = %WarehousePage
@onready var _warehouse_list: ItemList = %WarehouseList
@onready var _warehouse_rules_inner: VBoxContainer = %WarehouseRulesInner
@onready var _automation_page: ScrollContainer = %AutomationPage
@onready var _automation_inner: VBoxContainer = %AutomationInner
@onready var _center_panel: PanelContainer = %CenterPanel

var _plot_id: String = ""
var _building: Dictionary = {}
var _plot_data: Dictionary = {}
var _workshop_id: String = ""
var _profile_mode: String = "production"  # production | warehouse
var _production_control: Node = null
var _tab_group: ButtonGroup = null
var _warehouse_plot_ids: PackedStringArray = PackedStringArray()
var _selected_warehouse_plot: String = ""
var _routing_selectors: Array = []
var _site_picker: CanvasLayer = null
var _picker_io_ctx: Dictionary = {}
var _overview_energy_lbl: Label
var _open_tab: String = "overview"
var _player_refresh_earliest_msec: int = 0
var _world_refresh_earliest_msec: int = 0
var _session_gen: int = 0
var _hub_alive: bool = false
var _hub_refresh_pending: bool = false
const PLAYER_REFRESH_MIN_MS := 1000
const WORLD_REFRESH_MIN_MS := 2000

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


func _tab_buttons() -> Array:
	return [_tab_overview, _tab_run, _tab_routing, _tab_warehouse, _tab_automation]


func _ready() -> void:
	set_process_unhandled_input(true)
	_tab_group = ButtonGroup.new()
	_tab_group.allow_unpress = false
	for btn in _tab_buttons():
		btn.button_group = _tab_group
		btn.pressed.connect(_on_tab_pressed.bind(btn))
	_close_btn.pressed.connect(close)
	var dim := get_node_or_null("DimBackground")
	if dim is ColorRect:
		(dim as ColorRect).gui_input.connect(_on_dim_clicked)
	_apply_panel_theme()
	_show_tab("overview")


func _is_hub_live(gen: int = -1) -> bool:
	if not _hub_alive or not is_instance_valid(self) or not is_inside_tree():
		return false
	return gen < 0 or gen == _session_gen


func _connect_hub_signals() -> void:
	if not WorldState.world_updated.is_connected(_on_world_map_updated):
		WorldState.world_updated.connect(_on_world_map_updated)
	if not WorldState.player_updated.is_connected(_on_player_tick_updated):
		WorldState.player_updated.connect(_on_player_tick_updated)
	if not WorldState.recipes_updated.is_connected(_on_recipes_catalog_ready):
		WorldState.recipes_updated.connect(_on_recipes_catalog_ready)
	if not WorldState.building_auto_list_changed.is_connected(_on_building_auto_list_changed):
		WorldState.building_auto_list_changed.connect(_on_building_auto_list_changed)
	if not WS.tick_event.is_connected(_on_tick_event):
		WS.tick_event.connect(_on_tick_event)


func _disconnect_hub_signals() -> void:
	if WorldState.world_updated.is_connected(_on_world_map_updated):
		WorldState.world_updated.disconnect(_on_world_map_updated)
	if WorldState.player_updated.is_connected(_on_player_tick_updated):
		WorldState.player_updated.disconnect(_on_player_tick_updated)
	if WorldState.recipes_updated.is_connected(_on_recipes_catalog_ready):
		WorldState.recipes_updated.disconnect(_on_recipes_catalog_ready)
	if WorldState.building_auto_list_changed.is_connected(_on_building_auto_list_changed):
		WorldState.building_auto_list_changed.disconnect(_on_building_auto_list_changed)
	if WS.tick_event.is_connected(_on_tick_event):
		WS.tick_event.disconnect(_on_tick_event)


func _teardown_hub() -> void:
	_hub_alive = false
	_session_gen += 1
	_hub_refresh_pending = false
	_disconnect_hub_signals()
	if is_instance_valid(_site_picker):
		_site_picker.queue_free()
		_site_picker = null


func _exit_tree() -> void:
	_teardown_hub()


func _apply_panel_theme() -> void:
	if _center_panel == null:
		return
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.07, 0.07, 0.09, 0.98)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.45)
	sb.set_corner_radius_all(8)
	sb.set_content_margin_all(4)
	_center_panel.add_theme_stylebox_override("panel", sb)
	PanelUI.style_btn(_close_btn)
	for btn in _tab_buttons():
		PanelUI.style_btn(btn, btn.button_pressed)
	_subtitle.add_theme_color_override("font_color", Color(0.65, 0.62, 0.55))
	_subtitle.max_lines_visible = 2
	_subtitle.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	_title.add_theme_font_size_override("font_size", 20)
	_title.add_theme_color_override("font_color", RealmColors.TEXT)


func open(plot_id: String, building: Dictionary, plot_data: Dictionary) -> void:
	_teardown_hub()
	_hub_alive = true
	var gen := _session_gen
	_player_refresh_earliest_msec = 0
	_world_refresh_earliest_msec = 0
	_connect_hub_signals()
	_plot_id = plot_id
	_building = building.duplicate(true)
	_plot_data = plot_data.duplicate(true)
	_workshop_id = WorldState.workshop_id_for_building(_building)
	_mount_production_control()
	_apply_building_profile()
	call_deferred("_refresh_hub_after_open", gen)


func _refresh_hub_after_open(gen: int) -> void:
	if not _is_hub_live(gen) or _plot_id.is_empty():
		return
	_refresh_context_strip()
	_refresh_visible_tab_content()
	_try_warehouse_replenish_all()
	_try_auto_maintain_building()


func _apply_building_profile() -> void:
	var bp := WorldState.blueprint_dict(_workshop_id)
	var cat := str(bp.get("category", "processing"))
	var recipe_on_blueprint := WorldState.recipes_for_workshop_building(_building).size()
	var recipe_on_plot := recipe_on_blueprint
	if _production_control != null and _production_control.has_method("count_plot_listable_recipes"):
		recipe_on_plot = int(_production_control.call("count_plot_listable_recipes"))
	var fw := int(bp.get("footprint_w", 0))
	var fh := int(bp.get("footprint_h", 0))
	var footprint := ""
	if fw > 0 and fh > 0:
		footprint = " · %d×%d cells" % [fw, fh]
	var terrain := str(_plot_data.get("terrain", "plains"))
	var bid := str(_building.get("building_id", _building.get("blueprint_id", "")))
	if bid == "road_segment":
		_profile_mode = "road"
		_title.text = "%s · Road" % _short_building_name(_building)
		_subtitle.text = "%s · %s%s" % [_terrain_label(terrain), _plot_coords_text(), footprint]
		_tab_overview.visible = true
		_tab_run.visible = false
		_tab_routing.visible = false
		_tab_warehouse.visible = false
		_tab_automation.visible = false
		_show_tab("overview")
		for b in _tab_buttons():
			PanelUI.style_btn(b, b == _tab_overview)
		return
	if WorldState.building_is_warehouse(_building):
		_profile_mode = "warehouse"
		_title.text = "%s · Warehouse" % _short_building_name(_building)
		_subtitle.text = "%s · %s%s · Supply & inbound routes" % [
			_terrain_label(terrain),
			_plot_coords_text(),
			footprint,
		]
		_tab_overview.visible = true
		_tab_run.visible = false
		_tab_routing.visible = false
		_tab_warehouse.visible = true
		_tab_automation.visible = true
		_tab_warehouse.text = "Supply"
		_selected_warehouse_plot = _plot_id
		_show_tab("overview")
		for b in _tab_buttons():
			PanelUI.style_btn(b, b == _tab_overview)
		return
	_profile_mode = "production"
	_title.text = "%s · %s" % [_short_building_name(_building), cat.capitalize()]
	var recipe_bit := "%d recipe%s on this deed" % [recipe_on_plot, "" if recipe_on_plot == 1 else "s"]
	if recipe_on_plot != recipe_on_blueprint:
		recipe_bit += " (%d on blueprint)" % recipe_on_blueprint
	_subtitle.text = "%s · %s · %s%s" % [_terrain_label(terrain), _plot_coords_text(), recipe_bit, footprint]
	var can_run := WorldState.building_supports_production(_building)
	_tab_overview.visible = true
	_tab_run.visible = can_run
	_tab_routing.visible = can_run
	_tab_warehouse.visible = true
	_tab_automation.visible = can_run
	_tab_run.text = "Run"
	_tab_routing.text = "Logistics"
	_tab_warehouse.text = "Supply"
	_show_tab("overview")
	for b in _tab_buttons():
		PanelUI.style_btn(b, b == _tab_overview)


func close() -> void:
	_teardown_hub()
	closed.emit()
	queue_free()


func _on_dim_clicked(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.pressed and mb.button_index == MOUSE_BUTTON_LEFT:
			close()


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		close()
		get_viewport().set_input_as_handled()


func _on_tab_pressed(btn: Button) -> void:
	for b in _tab_buttons():
		PanelUI.style_btn(b, b == btn)
	if btn == _tab_overview:
		_show_tab("overview")
	elif btn == _tab_run:
		_show_tab("run")
	elif btn == _tab_routing:
		_show_tab("routing")
	elif btn == _tab_warehouse:
		_show_tab("warehouse")
	else:
		_show_tab("automation")


func _show_tab(which: String) -> void:
	_open_tab = which
	_overview_page.visible = which == "overview"
	_run_page.visible = which == "run"
	_routing_page.visible = which == "routing"
	_warehouse_page.visible = which == "warehouse"
	_automation_page.visible = which == "automation"
	_refresh_context_strip()
	if which == "overview":
		_refresh_overview_tab()
	if which == "run":
		_refresh_run_knowledge()
	if which == "routing":
		_refresh_routing_tab()
	if which == "warehouse":
		_refresh_warehouse_rules_panel()
	if which == "automation":
		_refresh_automation_tab()


func _selected_recipe_id_or_empty() -> String:
	if _production_control != null and _production_control.has_method("selected_recipe_id"):
		return str(_production_control.call("selected_recipe_id"))
	return ""


func _refresh_context_strip() -> void:
	if not _is_hub_live() or _context_strip_host == null or not is_instance_valid(_context_strip_host):
		return
	PanelUI.clear_children(_context_strip_host)
	if _plot_id.is_empty():
		return
	var bar := HBoxContainer.new()
	bar.add_theme_constant_override("separation", 20)
	var used := WorldState.plot_stash_units_total(_plot_id)
	var cap := WorldState.plot_storage_cap_units(_plot_id)
	_add_status_chip(bar, "Stash", "%d / %d u" % [used, cap], used >= cap)
	_add_status_chip(bar, "Building", _building_status_blurb())
	var inst := _instance_id()
	if not inst.is_empty() and _profile_mode == "production":
		var edges := BuildingHubKnowledge.material_edges(inst, _plot_id, _selected_recipe_id_or_empty())
		var in_n: int = (edges["inputs"] as Array).size()
		var out_n: int = (edges["outputs"] as Array).size()
		_add_status_chip(bar, "Routes", "%d in · %d out" % [in_n, out_n])
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	bar.add_child(spacer)
	var map_btn := Button.new()
	map_btn.text = "Site map"
	PanelUI.style_btn(map_btn)
	map_btn.pressed.connect(_open_supply_site_picker)
	bar.add_child(map_btn)
	if _tab_routing.visible:
		var log_btn := Button.new()
		log_btn.text = "Logistics"
		PanelUI.style_btn(log_btn)
		log_btn.pressed.connect(func() -> void: _show_tab("routing"))
		bar.add_child(log_btn)
	_context_strip_host.add_child(bar)


func _append_knowledge_edges_block(parent: Node, title: String, recipe_id: String) -> void:
	var inst := _instance_id()
	if inst.is_empty():
		return
	if not title.is_empty():
		_add_section_title_to(parent, title)
	var edges := BuildingHubKnowledge.material_edges(inst, _plot_id, recipe_id)
	var inbound := BuildingHubKnowledge.inbound_edges_for_plot(_plot_id)
	for block in [
		{"label": "Inputs (from → this building)", "rows": edges["inputs"]},
		{"label": "Outputs (this building → to)", "rows": edges["outputs"]},
	]:
		var rows: Array = block["rows"]
		if rows.is_empty():
			continue
		var sub := Label.new()
		sub.text = str(block["label"])
		sub.add_theme_color_override("font_color", RealmColors.MUTED)
		parent.add_child(sub)
		for e in rows:
			if not (e is Dictionary):
				continue
			var row: Dictionary = e
			var line := Label.new()
			line.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			var mat := WorldState.material_display_name(str(row.get("material", "")))
			var qty: int = int(row.get("qty", 0))
			var qtxt := "" if qty <= 0 else " × %d" % qty
			line.text = "  %s%s → %s" % [mat, qtxt, str(row.get("route_label", ""))]
			if bool(row.get("is_remote", false)):
				line.add_theme_color_override("font_color", RealmColors.ACCENT_DIM)
			parent.add_child(line)
	if not inbound.is_empty():
		var sub_in := Label.new()
		sub_in.text = "Inbound (other buildings → this plot stash)"
		sub_in.add_theme_color_override("font_color", RealmColors.MUTED)
		parent.add_child(sub_in)
		for e in inbound:
			if not (e is Dictionary):
				continue
			var row: Dictionary = e
			var line := Label.new()
			line.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			line.text = (
				"  %s %s %s via %s"
				% [
					str(row.get("from_building", "?")),
					str(row.get("verb", "")),
					WorldState.material_display_name(str(row.get("material", ""))),
					str(row.get("route_label", "")),
				]
			)
			line.add_theme_color_override("font_color", RealmColors.MAGIC)
			parent.add_child(line)


func _append_stash_inventory_table(parent: Node) -> void:
	var snap := BuildingHubKnowledge.stash_snapshot(_plot_id, 16)
	if snap.is_empty():
		_add_muted_to(parent, "Empty.")
		return
	var grid := GridContainer.new()
	grid.columns = 2
	grid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	grid.add_theme_constant_override("h_separation", 24)
	grid.add_theme_constant_override("v_separation", 2)
	var hk := Label.new()
	hk.text = "Material"
	hk.add_theme_color_override("font_color", RealmColors.MUTED)
	var hq := Label.new()
	hq.text = "Qty"
	hq.add_theme_color_override("font_color", RealmColors.MUTED)
	grid.add_child(hk)
	grid.add_child(hq)
	for row in snap:
		if not (row is Dictionary):
			continue
		var mat_lbl := Label.new()
		mat_lbl.text = WorldState.material_display_name(str(row.get("material", "")))
		var qty_lbl := Label.new()
		qty_lbl.text = str(int(row.get("qty", 0)))
		qty_lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		grid.add_child(mat_lbl)
		grid.add_child(qty_lbl)
	parent.add_child(grid)


func _refresh_run_knowledge() -> void:
	var host := _run_page.get_node_or_null("RunKnowledgeHeader") as VBoxContainer
	if host == null:
		return
	PanelUI.clear_children(host)
	if _profile_mode != "production":
		return
	_add_section_title_to(host, "Routes for selected recipe")
	_append_knowledge_edges_block(host, "", _selected_recipe_id_or_empty())
	var go := Button.new()
	go.text = "Edit all routes on Logistics"
	PanelUI.style_btn(go)
	go.pressed.connect(func() -> void: _show_tab("routing"))
	host.add_child(go)


func _refresh_overview_tab() -> void:
	if not _is_hub_live():
		return
	PanelUI.clear_children(_overview_inner)
	var building_sec := _add_panel_section(_overview_inner, "This building")
	var bp := WorldState.blueprint_dict(_workshop_id)
	var b_rows: Array = [
		{"key": "Type", "value": str(bp.get("category", "—")).capitalize()},
		{"key": "Status", "value": _building_status_blurb()},
	]
	if _profile_mode == "production":
		var rc := WorldState.recipes_for_workshop_building(_building).size()
		b_rows.append({"key": "Recipes", "value": str(rc)})
	var fw := int(bp.get("footprint_w", 0))
	var fh := int(bp.get("footprint_h", 0))
	if fw > 0 and fh > 0:
		b_rows.append({"key": "Footprint", "value": "%d × %d cells" % [fw, fh]})
	_add_kv_grid(building_sec, b_rows)
	var deed_sec := _add_panel_section(_overview_inner, "Deed")
	var stash_kind := (
		"Warehouse cap"
		if WorldState.plot_has_operational_warehouse(_plot_id)
		else "Open yard cap"
	)
	_add_kv_grid(
		deed_sec,
		[
			{"key": "Terrain", "value": _terrain_label(str(_plot_data.get("terrain", "plains")))},
			{"key": "Tile", "value": _plot_coords_text()},
			{
				"key": "Stash",
				"value": WorldState.plot_stash_capacity_label(_plot_id),
				"warn": WorldState.plot_stash_units_total(_plot_id)
					>= WorldState.plot_storage_cap_units(_plot_id),
			},
			{"key": "Storage", "value": stash_kind},
		],
	)
	_add_section_title_to(deed_sec, "Structures here")
	_add_bullet_list(deed_sec, _deed_structure_labels())
	_add_muted_to(deed_sec, BuildingHubKnowledge.physical_storage_law_short())
	var stash_sec := _add_panel_section(_overview_inner, "Stash inventory")
	_append_stash_inventory_table(stash_sec)
	var log_sec := _add_panel_section(_overview_inner, "Logistics")
	if _profile_mode == "production" and not _instance_id().is_empty():
		var edges := BuildingHubKnowledge.material_edges(
			_instance_id(), _plot_id, _selected_recipe_id_or_empty()
		)
		var in_n: int = (edges["inputs"] as Array).size()
		var out_n: int = (edges["outputs"] as Array).size()
		var inbound_n: int = BuildingHubKnowledge.inbound_edges_for_plot(_plot_id).size()
		_add_kv_grid(
			log_sec,
			[
				{"key": "Input routes", "value": str(in_n)},
				{"key": "Output routes", "value": str(out_n)},
				{"key": "Inbound to stash", "value": str(inbound_n)},
			],
		)
		var go_log := Button.new()
		go_log.text = "Configure on Logistics tab →"
		PanelUI.style_btn(go_log)
		go_log.pressed.connect(func() -> void: _show_tab("routing"))
		log_sec.add_child(go_log)
	elif _profile_mode == "warehouse":
		var inbound := BuildingHubKnowledge.inbound_edges_for_plot(_plot_id)
		_add_kv_grid(log_sec, [{"key": "Inbound routes", "value": str(inbound.size())}])
		if inbound.is_empty():
			_add_muted_to(log_sec, "No inbound routes yet.")
		else:
			for e in inbound:
				if not (e is Dictionary):
					continue
				var row: Dictionary = e
				var lbl := Label.new()
				lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
				lbl.text = (
					"• %s — %s %s"
					% [
						_short_building_name_from_label(str(row.get("from_building", "?"))),
						str(row.get("verb", "")),
						WorldState.material_display_name(str(row.get("material", ""))),
					]
				)
				log_sec.add_child(lbl)
	else:
		_add_muted_to(log_sec, "Not applicable for this building type.")
	var power_sec := _add_panel_section(_overview_inner, "Power")
	_overview_energy_lbl = Label.new()
	_overview_energy_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_overview_energy_lbl.text = "Loading…"
	power_sec.add_child(_overview_energy_lbl)
	API.get_plot_energy(_plot_id, _on_overview_energy_loaded)
	var run := WorldState.active_production_run_for_building(_plot_id, _building)
	if not run.is_empty():
		var run_sec := _add_panel_section(_overview_inner, "Active production")
		var rid := str(run.get("recipe_id", ""))
		var rn := str(WorldState.recipe_by_id(rid).get("display_name", rid))
		_add_kv_grid(
			run_sec,
			[
				{"key": "Recipe", "value": rn},
				{
					"key": "Remaining",
					"value": WorldState.format_ticks_as_gametime(int(run.get("ticks_remaining", 0))),
				},
			],
		)
		var go_run := Button.new()
		go_run.text = "Open Run tab"
		PanelUI.style_btn(go_run)
		go_run.pressed.connect(func() -> void: _show_tab("run"))
		run_sec.add_child(go_run)
	var act_sec := _add_panel_section(_overview_inner, "Actions")
	var actions := HBoxContainer.new()
	actions.add_theme_constant_override("separation", 8)
	if _can_maintain_now():
		var maint := Button.new()
		maint.text = "Maintain"
		PanelUI.style_btn(maint, true)
		maint.pressed.connect(func() -> void: _maintain_building())
		actions.add_child(maint)
	if WorldState.building_supports_production(_building) and _building_operational():
		var run_btn := Button.new()
		run_btn.text = "Run production"
		PanelUI.style_btn(run_btn)
		run_btn.pressed.connect(func() -> void: _show_tab("run"))
		actions.add_child(run_btn)
	if WorldState.recipes_for_workshop_building(_building).size() > 0:
		var chain_btn := Button.new()
		chain_btn.text = "Recipe chains"
		PanelUI.style_btn(chain_btn)
		chain_btn.pressed.connect(_open_operations_chains)
		actions.add_child(chain_btn)
	if _building_operational() and _instance_id() != "":
		var book := int(_building.get("book_value_cents", 0))
		var demo := Button.new()
		demo.text = "Demolish (%s salvage)" % WorldState.format_money(book / 2)
		demo.modulate = Color(1.0, 0.45, 0.45)
		PanelUI.style_btn(demo)
		demo.pressed.connect(func() -> void: _confirm_demolish_building())
		actions.add_child(demo)
	if actions.get_child_count() > 0:
		act_sec.add_child(actions)
	else:
		_add_muted_to(act_sec, "No actions available.")


func _on_overview_energy_loaded(data: Dictionary) -> void:
	if not is_instance_valid(_overview_energy_lbl):
		return
	if data.is_empty() or not bool(data.get("ok", true)):
		_overview_energy_lbl.text = "Power data unavailable"
		return
	if bool(data.get("powered", false)):
		var lines: PackedStringArray = PackedStringArray([str(data.get("status_note", "Powered"))])
		lines.append(
			"Capacity %d/day · load %d/day · %s/unit"
			% [
				int(data.get("capacity_per_day", 0)),
				int(data.get("load_per_day", 0)),
				WorldState.format_money(int(data.get("clearing_price_cents", 0))),
			]
		)
		var gen := _format_generators_short(data.get("generators", []))
		if not gen.is_empty():
			lines.append("Generators: %s" % gen)
		_overview_energy_lbl.text = "\n".join(lines)
		_overview_energy_lbl.modulate = Color(0.45, 1.0, 0.45)
	else:
		_overview_energy_lbl.text = str(data.get("reason", "Not powered"))
		_overview_energy_lbl.modulate = Color(1.0, 0.5, 0.3)


func _format_generators_short(generators: Variant) -> String:
	if not (generators is Array):
		return ""
	var parts: PackedStringArray = []
	for g in generators as Array:
		if g is Dictionary:
			var row: Dictionary = g
			var lbl := str(row.get("label", row.get("building_id", "?")))
			if bool(row.get("active", false)):
				parts.append("%s (%d/day)" % [lbl, int(row.get("capacity_per_day", 0))])
			else:
				parts.append("%s (offline)" % lbl)
	return ", ".join(parts)


func _building_status_blurb() -> String:
	var eff := int(_building.get("_efficiency_pct", 100))
	var missed := int(_building.get("_missed_cycles", 0))
	var due := int(_building.get("_due_in_ticks", 99_999))
	var done_at := int(_building.get("completes_at_tick", 0))
	if done_at > WorldState.current_tick:
		return "Under construction — ready in %s" % WorldState.format_ticks_as_gametime(
			done_at - WorldState.current_tick
		)
	if eff <= 0:
		return "Stopped — run maintenance before production"
	if missed > 0:
		return "Overdue maintenance — efficiency %d%%" % eff
	return "Operational at %d%% · next upkeep in %s" % [
		eff,
		WorldState.format_ticks_as_gametime(due),
	]


func _building_operational() -> bool:
	return int(_building.get("completes_at_tick", 0)) <= WorldState.current_tick


func _can_maintain_now() -> bool:
	if not _building_operational():
		return false
	var eff := int(_building.get("_efficiency_pct", 100))
	var missed := int(_building.get("_missed_cycles", 0))
	return missed > 0 or eff < 100


func _maintain_building() -> void:
	var inst := _instance_id()
	if inst.is_empty():
		return
	API.maintain_building(
		_plot_id,
		inst,
		func(res: Dictionary) -> void:
			if bool(res.get("ok", false)):
				MainFeedback.toast("Maintenance complete", false)
				_sync_building_from_world()
				_refresh_overview_tab()
			else:
				MainFeedback.toast(str(res.get("reason", "Maintenance failed")), true),
		WorldState.party_id,
	)


func _confirm_demolish_building() -> void:
	var inst := _instance_id()
	if inst.is_empty():
		return
	API.demolish_building(
		inst,
		func(res: Dictionary) -> void:
			if bool(res.get("ok", false)):
				MainFeedback.toast("Building demolished", false)
				close()
			else:
				MainFeedback.toast(str(res.get("reason", "Demolish failed")), true),
		WorldState.party_id,
	)


func _open_operations_chains() -> void:
	var host := WorldState.find_game_shell()
	if host != null and host.has_method("_on_nav_pressed"):
		host.call("_on_nav_pressed", "operations")


func _refresh_automation_tab() -> void:
	PanelUI.clear_children(_automation_inner)
	var inst := _instance_id()
	if inst.is_empty():
		_add_muted_to(_automation_inner, "No building instance.")
		return
	_add_section_title_to(_automation_inner, "What automation will touch")
	var impact := BuildingHubKnowledge.automation_impact_lines(
		inst, _plot_id, _selected_recipe_id_or_empty()
	)
	if impact.is_empty():
		_add_muted_to(_automation_inner, "Enable options below to see impact lines.")
	else:
		for line in impact:
			var lbl := Label.new()
			lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			lbl.text = str(line)
			_automation_inner.add_child(lbl)
	_add_section_title_to(_automation_inner, "Engine-backed")
	var auto_list := CheckButton.new()
	auto_list.text = "Auto-list outputs on market when batches finish (engine)"
	auto_list.button_pressed = bool(_building.get("auto_list_output", false))
	auto_list.toggled.connect(
		func(on: bool) -> void: WorldState.set_building_auto_list_enabled(inst, on)
	)
	_automation_inner.add_child(auto_list)
	_add_section_title_to(_automation_inner, "Client automation (while game is open)")
	var auto_maint := CheckButton.new()
	auto_maint.text = "Auto-maintain when upkeep is due or overdue"
	auto_maint.button_pressed = RealmWorkflowSettings.get_auto_maintain(inst)
	auto_maint.toggled.connect(
		func(on: bool) -> void: RealmWorkflowSettings.set_auto_maintain(inst, on)
	)
	_automation_inner.add_child(auto_maint)
	var auto_buy := CheckButton.new()
	auto_buy.text = "Auto-buy missing recipe inputs from market before each start"
	auto_buy.button_pressed = RealmWorkflowSettings.get_auto_buy_inputs(inst)
	auto_buy.toggled.connect(
		func(on: bool) -> void: RealmWorkflowSettings.set_auto_buy_inputs(inst, on)
	)
	_automation_inner.add_child(auto_buy)
	var auto_wh := CheckButton.new()
	auto_wh.text = "Auto-replenish warehouse plots (stash rules on Supply tab)"
	auto_wh.button_pressed = RealmWorkflowSettings.get_auto_replenish_warehouses(inst)
	auto_wh.toggled.connect(
		func(on: bool) -> void: RealmWorkflowSettings.set_auto_replenish_warehouses(inst, on)
	)
	_automation_inner.add_child(auto_wh)
	_add_section_title_to(_automation_inner, "Tips")
	var tip := Label.new()
	tip.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	tip.add_theme_color_override("font_color", Color(0.55, 0.52, 0.45))
	tip.text = (
		"Set per-material routes on Logistics — use Map to pick any owned site (warehouse, dock, "
		+ "store, mill, stockpile, etc.). Output routing runs after each production_done event."
	)
	_automation_inner.add_child(tip)


func _terrain_label(terrain: String) -> String:
	return TERRAIN_LABELS.get(terrain, terrain.capitalize())


func _plot_coords_text() -> String:
	return "(%d, %d)" % [
		int(_plot_data.get("x", 0)),
		int(_plot_data.get("y", 0)),
	]


func _short_building_name(building: Dictionary) -> String:
	var full := WorldState.building_display_name(building)
	var p := full.find(" (")
	if p > 0:
		return full.substr(0, p)
	return full


func _short_building_name_from_label(label: String) -> String:
	var p := label.find(" (")
	if p > 0:
		return label.substr(0, p)
	return label


func _deed_structure_labels() -> PackedStringArray:
	var out := PackedStringArray()
	var seen: Dictionary = {}
	for b in _plot_data.get("buildings", []):
		if not (b is Dictionary):
			continue
		var row: Dictionary = b as Dictionary
		if str(row.get("building_id", "")) == "road_segment":
			continue
		var nm := _short_building_name(row)
		if seen.has(nm):
			continue
		seen[nm] = true
		out.append(nm)
	out.sort()
	return out


func _add_panel_section(parent: Node, title: String) -> VBoxContainer:
	var wrap := VBoxContainer.new()
	wrap.add_theme_constant_override("separation", 6)
	_add_section_title_to(wrap, title)
	parent.add_child(wrap)
	return wrap


func _add_kv_grid(parent: Node, rows: Array) -> void:
	var grid := GridContainer.new()
	grid.columns = 2
	grid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	grid.add_theme_constant_override("h_separation", 20)
	grid.add_theme_constant_override("v_separation", 4)
	const KEY_W := 132.0
	for row in rows:
		if not (row is Dictionary):
			continue
		var rd: Dictionary = row
		var k := Label.new()
		k.text = str(rd.get("key", ""))
		k.custom_minimum_size.x = KEY_W
		k.add_theme_color_override("font_color", RealmColors.MUTED)
		var v := Label.new()
		v.text = str(rd.get("value", ""))
		v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		v.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		if bool(rd.get("warn", false)):
			v.add_theme_color_override("font_color", RealmColors.WARN)
		grid.add_child(k)
		grid.add_child(v)
	parent.add_child(grid)


func _add_bullet_list(parent: Node, items: PackedStringArray) -> void:
	if items.is_empty():
		_add_muted_to(parent, "None on this deed.")
		return
	for item in items:
		var lbl := Label.new()
		lbl.text = "• %s" % item
		lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		parent.add_child(lbl)


func _add_status_chip(bar: HBoxContainer, label: String, value: String, warn: bool = false) -> void:
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 0)
	var k := Label.new()
	k.text = label
	k.add_theme_font_size_override("font_size", 10)
	k.add_theme_color_override("font_color", RealmColors.MUTED)
	var v := Label.new()
	v.text = value
	v.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	if warn:
		v.add_theme_color_override("font_color", RealmColors.WARN)
	col.add_child(k)
	col.add_child(v)
	bar.add_child(col)


func _add_section_title_to(parent: Node, text: String) -> void:
	var lbl := Label.new()
	lbl.text = text
	lbl.add_theme_color_override("font_color", RealmColors.ACCENT)
	parent.add_child(lbl)


func _add_muted_to(parent: Node, text: String) -> void:
	var lbl := Label.new()
	lbl.text = text
	lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	lbl.add_theme_color_override("font_color", Color(0.55, 0.52, 0.45))
	parent.add_child(lbl)


func _try_auto_maintain_building() -> void:
	var inst := _instance_id()
	if inst.is_empty() or not RealmWorkflowSettings.get_auto_maintain(inst):
		return
	if not _can_maintain_now():
		return
	_maintain_building()


func _ensure_run_knowledge_header() -> VBoxContainer:
	var h := _run_page.get_node_or_null("RunKnowledgeHeader") as VBoxContainer
	if h != null:
		return h
	h = VBoxContainer.new()
	h.name = "RunKnowledgeHeader"
	h.add_theme_constant_override("separation", 6)
	_run_page.add_child(h)
	_run_page.move_child(h, 0)
	return h


func _mount_production_control() -> void:
	_ensure_run_knowledge_header()
	if _production_control and is_instance_valid(_production_control):
		_production_control.queue_free()
	_production_control = ProductionControlScene.instantiate()
	_run_page.add_child(_production_control)
	if _production_control.has_method("setup"):
		_production_control.call(
			"setup",
			_plot_id,
			_building,
			str(_plot_data.get("terrain", "plains")),
		)
	var sel: OptionButton = _production_control.get_node_or_null("%RecipeSelector") as OptionButton
	if sel != null and not sel.item_selected.is_connected(_on_recipe_changed):
		sel.item_selected.connect(_on_recipe_changed)
	_refresh_run_knowledge()


func _on_recipe_changed(_i: int = 0) -> void:
	_refresh_context_strip()
	_refresh_routing_tab()
	if _run_page.visible:
		_refresh_run_knowledge()
	if _overview_page.visible:
		_refresh_overview_tab()
	if _automation_page.visible:
		_refresh_automation_tab()


func _instance_id() -> String:
	return str(_building.get("instance_id", ""))


func _selected_recipe_id() -> String:
	if _production_control != null and _production_control.has_method("selected_recipe_id"):
		return str(_production_control.call("selected_recipe_id"))
	return ""


func _recipe_row(rid: String) -> Dictionary:
	return WorldState.recipe_by_id(rid)


func _owned_plots() -> Array:
	var out: Array = []
	var party := WorldState.party_id
	for pid in WorldState.plots.keys():
		var row: Dictionary = WorldState.plots[pid] as Dictionary
		if str(row.get("owner", "")) == party:
			out.append({"id": str(pid), "data": row})
	out.sort_custom(func(a, b): return str(a["id"]) < str(b["id"]))
	return out


func _plot_has_warehouse(plot_id: String) -> bool:
	var ui := WorldState.get_plot_ui(plot_id)
	for b in ui.get("buildings", []):
		if b is Dictionary and str((b as Dictionary).get("building_id", "")) == "warehouse":
			return true
	return false


func _ensure_site_picker() -> void:
	if _site_picker != null:
		return
	_site_picker = LogisticsSitePickerScene.instantiate()
	add_child(_site_picker)
	if _site_picker.has_signal("site_confirmed"):
		_site_picker.site_confirmed.connect(_on_site_picker_confirmed)


func _stash_qty(plot_id: String, material: String) -> int:
	var pd: Dictionary = WorldState.plots.get(plot_id, {})
	var stock: Variant = pd.get("output_stock", {})
	if not (stock is Dictionary):
		return 0
	return int((stock as Dictionary).get(material, 0))


func _preset_source_options() -> Array:
	return [
		{"id": "stash_this", "label": "This plot stash"},
		{"id": "player_inv", "label": "Personal carry (portable only)"},
		{"id": "market_buy", "label": "Buy from market if short"},
		{"id": "__map__", "label": "Another owned site… (map)"},
	]


func _preset_dest_options() -> Array:
	return [
		{"id": "stash_this", "label": "This plot stash"},
		{"id": "harvest_player", "label": "To personal carry (portable only)"},
		{"id": "auto_list", "label": "Auto-list on market (building flag)"},
		{"id": "__map__", "label": "Another owned site… (map)"},
	]


func _is_plot_route(route_id: String) -> bool:
	return route_id.begins_with("stash_plot:") or route_id.begins_with("ship_to:")


func _open_site_picker_for_io(is_input: bool, material: String, instance_id: String, cur: String) -> void:
	_ensure_site_picker()
	_picker_io_ctx = {
		"is_input": is_input,
		"material": material,
		"instance_id": instance_id,
	}
	var mode := "input" if is_input else "output"
	if _site_picker.has_method("open_for"):
		_site_picker.call(
			"open_for",
			{
				"mode": mode,
				"exclude_plot_id": _plot_id,
				"origin_plot_id": _plot_id,
				"current_route_id": cur,
			},
		)


func _open_supply_site_picker() -> void:
	_ensure_site_picker()
	_picker_io_ctx = {"mode": "supply"}
	var cur := ""
	if not _selected_warehouse_plot.is_empty():
		cur = "stash_plot:%s" % _selected_warehouse_plot
	if _site_picker.has_method("open_for"):
		_site_picker.call(
			"open_for",
			{
				"mode": "supply",
				"exclude_plot_id": "",
				"origin_plot_id": _plot_id,
				"current_route_id": cur,
			},
		)


func _on_site_picker_confirmed(route_id: String, plot_id: String, _summary: String) -> void:
	var ctx := _picker_io_ctx
	_picker_io_ctx = {}
	if ctx.is_empty():
		return
	if str(ctx.get("mode", "")) == "supply":
		if plot_id.is_empty():
			plot_id = BuildingHubKnowledge.route_target_plot_id(route_id)
		if plot_id.is_empty():
			return
		_selected_warehouse_plot = plot_id
		_refresh_warehouse_list()
		_select_supply_plot_in_list(plot_id)
		return
	var is_input: bool = bool(ctx.get("is_input", true))
	var material: String = str(ctx.get("material", ""))
	var instance_id: String = str(ctx.get("instance_id", ""))
	if is_input:
		RealmWorkflowSettings.set_input_source(instance_id, material, route_id)
	else:
		RealmWorkflowSettings.set_output_dest(instance_id, material, route_id)
	_refresh_context_strip()
	_refresh_routing_tab()


func _fill_option(sel: OptionButton, options: Array, current_id: String) -> void:
	sel.clear()
	var pick := 0
	for i in options.size():
		var o: Dictionary = options[i]
		sel.add_item(str(o["label"]))
		sel.set_item_metadata(i, str(o["id"]))
		if str(o["id"]) == current_id:
			pick = i
	sel.select(pick)


func _refresh_routing_tab() -> void:
	if not _is_hub_live():
		return
	PanelUI.clear_children(_routing_inner)
	_routing_selectors.clear()
	_append_knowledge_edges_block(_routing_inner, "Route knowledge (this recipe)", _selected_recipe_id())
	var div := HSeparator.new()
	_routing_inner.add_child(div)
	var rid := _selected_recipe_id()
	if rid.is_empty():
		var hint := Label.new()
		hint.text = "Pick a recipe on the Run tab first."
		hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_routing_inner.add_child(hint)
		return
	var row := _recipe_row(rid)
	var inst := _instance_id()
	var inputs: Variant = row.get("inputs", {})
	var outputs: Variant = row.get("outputs", {})
	_add_section_title("Inputs — where materials come from")
	if inputs is Dictionary and not (inputs as Dictionary).is_empty():
		for mat in (inputs as Dictionary).keys():
			_add_io_row(true, str(mat), int((inputs as Dictionary)[mat]), inst)
	else:
		_add_muted("No recipe inputs.")
	_add_section_title("Outputs — what happens when a batch finishes")
	if outputs is Dictionary and not (outputs as Dictionary).is_empty():
		for mat in (outputs as Dictionary).keys():
			_add_io_row(false, str(mat), int((outputs as Dictionary)[mat]), inst)
	else:
		_add_muted("No recipe outputs.")
	var note := Label.new()
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	note.add_theme_color_override("font_color", Color(0.55, 0.52, 0.45))
	note.text = (
		"After each production_done event, outputs are harvested/shipped/auto-listed per these routes. "
		+ "Use Map to choose any owned site — label shows buildings on that deed (warehouse, dock, store, etc.). "
		+ "Market buy runs before start when an input route is set to buy-from-market."
	)
	_routing_inner.add_child(note)


func _add_section_title(text: String) -> void:
	var lbl := Label.new()
	lbl.text = text
	lbl.add_theme_color_override("font_color", RealmColors.ACCENT)
	_routing_inner.add_child(lbl)


func _add_muted(text: String) -> void:
	var lbl := Label.new()
	lbl.text = text
	lbl.add_theme_color_override("font_color", Color(0.55, 0.52, 0.45))
	_routing_inner.add_child(lbl)


func _mat_label(mat_id: String, qty: int) -> String:
	var name := mat_id.replace("_", " ")
	return "%s × %d" % [name, qty]


func _add_io_row(is_input: bool, material: String, qty: int, instance_id: String) -> void:
	var grid := GridContainer.new()
	grid.columns = 4
	grid.add_theme_constant_override("h_separation", 10)
	grid.add_theme_constant_override("v_separation", 6)
	var mat_lbl := Label.new()
	mat_lbl.text = _mat_label(material, qty)
	mat_lbl.custom_minimum_size.x = 120
	grid.add_child(mat_lbl)
	var stash_lbl := Label.new()
	if is_input:
		var here := _stash_qty(_plot_id, material)
		stash_lbl.text = "On plot: %d" % here
	else:
		stash_lbl.text = ""
	stash_lbl.custom_minimum_size.x = 72
	grid.add_child(stash_lbl)
	var cur := (
		RealmWorkflowSettings.get_input_source(instance_id, material, _plot_id)
		if is_input
		else RealmWorkflowSettings.get_output_dest(instance_id, material, _plot_id)
	)
	var route_lbl := Label.new()
	route_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	route_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	route_lbl.text = WorldState.workflow_route_label(cur)
	if _is_plot_route(cur):
		route_lbl.add_theme_color_override("font_color", RealmColors.ACCENT_DIM)
	grid.add_child(route_lbl)
	var ctrl := HBoxContainer.new()
	ctrl.add_theme_constant_override("separation", 6)
	ctrl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var sel := OptionButton.new()
	sel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var opts := _preset_source_options() if is_input else _preset_dest_options()
	var pick_meta := "__map__" if _is_plot_route(cur) else cur
	_fill_option(sel, opts, pick_meta)
	sel.item_selected.connect(
		func(_i: int) -> void:
			var picked := str(sel.get_item_metadata(sel.selected))
			if picked == "__map__":
				_open_site_picker_for_io(is_input, material, instance_id, cur)
				return
			if is_input:
				RealmWorkflowSettings.set_input_source(instance_id, material, picked)
			else:
				RealmWorkflowSettings.set_output_dest(instance_id, material, picked)
			route_lbl.text = WorldState.workflow_route_label(picked)
			route_lbl.remove_theme_color_override("font_color")
	)
	ctrl.add_child(sel)
	var map_btn := Button.new()
	map_btn.text = "Map"
	PanelUI.style_btn(map_btn)
	map_btn.pressed.connect(func() -> void: _open_site_picker_for_io(is_input, material, instance_id, cur))
	ctrl.add_child(map_btn)
	grid.add_child(ctrl)
	_routing_inner.add_child(grid)
	_routing_selectors.append(
		{"is_input": is_input, "material": material, "selector": sel, "route_label": route_lbl}
	)


func _select_supply_plot_in_list(plot_id: String) -> void:
	for i in _warehouse_list.item_count:
		if str(_warehouse_list.get_item_metadata(i)) == plot_id:
			_warehouse_list.select(i)
			_on_warehouse_selected(i)
			return


func _refresh_warehouse_list() -> void:
	_warehouse_list.clear()
	_warehouse_plot_ids = PackedStringArray()
	var last_group := ""
	for entry in BuildingHubKnowledge.supply_sites():
		if not (entry is Dictionary):
			continue
		var e: Dictionary = entry
		var pid := str(e.get("plot_id", ""))
		var g := str(e.get("group", "other"))
		if g != last_group:
			last_group = g
			var sep := _warehouse_list.item_count
			_warehouse_list.add_item("── %s ──" % str(e.get("group_label", "")))
			_warehouse_list.set_item_disabled(sep, true)
			_warehouse_list.set_item_metadata(sep, "")
		_warehouse_plot_ids.append(pid)
		var stash: int = int(e.get("stash_units", 0))
		var suffix := "" if stash <= 0 else " · %d u" % stash
		var tag := " (this deed)" if pid == _plot_id else ""
		_warehouse_list.add_item("  %s%s%s" % [str(e.get("summary", pid)), suffix, tag])
		_warehouse_list.set_item_metadata(_warehouse_list.item_count - 1, pid)
	if _profile_mode == "warehouse" and not _plot_id.is_empty():
		_selected_warehouse_plot = _plot_id
		_select_supply_plot_in_list(_plot_id)
		if _selected_warehouse_plot == _plot_id:
			return
	if _warehouse_plot_ids.is_empty():
		_warehouse_list.add_item("(Claim a plot to configure supply)")
		_selected_warehouse_plot = ""
		PanelUI.clear_children(_warehouse_rules_inner)
		var hint := Label.new()
		hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		hint.text = "Any owned deed with a plot stash can hold bulk — warehouse, dock, store, stockpile, or open land."
		_warehouse_rules_inner.add_child(hint)
		return
	if not _warehouse_list.item_selected.is_connected(_on_warehouse_selected):
		_warehouse_list.item_selected.connect(_on_warehouse_selected)
	if _selected_warehouse_plot.is_empty():
		for i in _warehouse_list.item_count:
			var pid := str(_warehouse_list.get_item_metadata(i))
			if not pid.is_empty():
				_warehouse_list.select(i)
				_on_warehouse_selected(i)
				break


func _on_warehouse_selected(index: int) -> void:
	if index < 0 or index >= _warehouse_list.item_count:
		return
	var pid := str(_warehouse_list.get_item_metadata(index))
	if pid.is_empty():
		return
	_selected_warehouse_plot = pid
	_refresh_warehouse_rules_panel()


func _refresh_warehouse_rules_panel() -> void:
	PanelUI.clear_children(_warehouse_rules_inner)
	if _selected_warehouse_plot.is_empty():
		return
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 8)
	var title := Label.new()
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	title.text = "Stash replenishment — %s" % WorldState.plot_site_summary(_selected_warehouse_plot)
	title.add_theme_color_override("font_color", RealmColors.ACCENT)
	head.add_child(title)
	var map_btn := Button.new()
	map_btn.text = "Map"
	PanelUI.style_btn(map_btn)
	map_btn.pressed.connect(_open_supply_site_picker)
	head.add_child(map_btn)
	_warehouse_rules_inner.add_child(head)
	var inbound := BuildingHubKnowledge.inbound_edges_for_plot(_selected_warehouse_plot)
	if not inbound.is_empty():
		_add_section_title_to(_warehouse_rules_inner, "Buildings routing here")
		for e in inbound:
			if not (e is Dictionary):
				continue
			var row: Dictionary = e
			var lbl := Label.new()
			lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			lbl.text = "  %s @ %s — %s %s" % [
				str(row.get("from_building", "?")),
				str(row.get("from_summary", "")),
				str(row.get("verb", "")),
				WorldState.material_display_name(str(row.get("material", ""))),
			]
			_warehouse_rules_inner.add_child(lbl)
	_add_section_title_to(_warehouse_rules_inner, "Market replenish rules")
	var materials := _common_materials()
	for mid in materials:
		_add_warehouse_rule_row(_selected_warehouse_plot, mid)
	var run_btn := Button.new()
	run_btn.text = "Run replenishment now"
	PanelUI.style_btn(run_btn, true)
	run_btn.pressed.connect(func() -> void: _replenish_warehouse_plot(_selected_warehouse_plot))
	_warehouse_rules_inner.add_child(run_btn)
	var ship_hint := Label.new()
	ship_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	ship_hint.add_theme_color_override("font_color", Color(0.55, 0.52, 0.45))
	ship_hint.text = (
		"Replenish targets must fit this deed's stash cap (%d / %d u). Market buy spends cash; "
		+ "goods still arrive as real inventory subject to spoilage and shipping. Build a warehouse "
		+ "on-plot (materials + construction ticks) to raise the bulk cap."
		% [
			WorldState.plot_stash_units_total(_selected_warehouse_plot),
			WorldState.plot_storage_cap_units(_selected_warehouse_plot),
		]
	)
	_warehouse_rules_inner.add_child(ship_hint)


func _common_materials() -> PackedStringArray:
	return PackedStringArray([
		"grain", "coal", "timber", "stone", "brick", "lumber", "iron_ore",
	])


func _add_warehouse_rule_row(plot_id: String, material: String) -> void:
	var rule := RealmWorkflowSettings.get_warehouse_rule(plot_id, material)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	var en := CheckButton.new()
	en.text = material
	en.button_pressed = bool(rule.get("enabled", false))
	var tgt := SpinBox.new()
	tgt.prefix = "Target"
	tgt.min_value = 0
	tgt.max_value = 99999
	tgt.value = int(rule.get("target_qty", 0))
	var price := SpinBox.new()
	price.prefix = "Max ¢/u"
	price.min_value = 0
	price.max_value = 999999
	price.value = int(rule.get("max_price_cents", 0))
	var save_rule := func() -> void:
		RealmWorkflowSettings.set_warehouse_rule(
			plot_id,
			material,
			{
				"enabled": en.button_pressed,
				"target_qty": int(tgt.value),
				"max_price_cents": int(price.value),
			},
		)
	en.toggled.connect(func(_on: bool) -> void: save_rule.call())
	tgt.value_changed.connect(func(_v: float) -> void: save_rule.call())
	price.value_changed.connect(func(_v: float) -> void: save_rule.call())
	row.add_child(en)
	row.add_child(tgt)
	row.add_child(price)
	_warehouse_rules_inner.add_child(row)


func _on_recipes_catalog_ready() -> void:
	if not _is_hub_live() or _plot_id.is_empty():
		return
	_mount_production_control()
	_apply_building_profile()
	_refresh_overview_tab()


func _on_world_map_updated() -> void:
	if not _is_hub_live():
		return
	var now := Time.get_ticks_msec()
	if now < _world_refresh_earliest_msec:
		_sync_building_from_world()
		return
	_world_refresh_earliest_msec = now + WORLD_REFRESH_MIN_MS
	_schedule_hub_refresh(true)


func _schedule_hub_refresh(full_tabs: bool) -> void:
	if not _is_hub_live() or _hub_refresh_pending:
		return
	_hub_refresh_pending = true
	call_deferred("_run_scheduled_hub_refresh", full_tabs, _session_gen)


func _run_scheduled_hub_refresh(full_tabs: bool, gen: int) -> void:
	_hub_refresh_pending = false
	if not _is_hub_live(gen):
		return
	_sync_building_from_world()
	_refresh_context_strip()
	if full_tabs:
		_refresh_visible_tab_content()


func _on_player_tick_updated() -> void:
	if not _is_hub_live():
		return
	var now := Time.get_ticks_msec()
	if now < _player_refresh_earliest_msec:
		_sync_building_from_world()
		return
	_player_refresh_earliest_msec = now + PLAYER_REFRESH_MIN_MS
	_sync_building_from_world()
	if _overview_page.visible:
		_refresh_overview_tab()
	if _run_page.visible and _production_control != null:
		if _production_control.has_method("_refresh_status"):
			_production_control.call("_refresh_status")
	if RealmWorkflowSettings.get_auto_replenish_warehouses(_instance_id()):
		_try_warehouse_replenish_all()
	_try_buy_inputs_before_start()
	_try_auto_maintain_building()


func _refresh_visible_tab_content() -> void:
	if not _is_hub_live():
		return
	if _overview_page.visible:
		_refresh_overview_tab()
	if _run_page.visible:
		_refresh_run_knowledge()
	if _routing_page.visible:
		_refresh_routing_tab()
	if _warehouse_page.visible:
		_refresh_warehouse_list()
	if _automation_page.visible:
		_refresh_automation_tab()


func _on_tick_event(event: Dictionary) -> void:
	if not _is_hub_live():
		return
	if str(event.get("kind", "")) == "production_done" and str(event.get("plot_id", "")) == _plot_id:
		_apply_output_routing()
	_sync_building_from_world()


func _on_building_auto_list_changed(instance_id: String, enabled: bool) -> void:
	if _instance_id() != instance_id:
		return
	_building["auto_list_output"] = enabled
	if _production_control != null:
		var toggle: CheckButton = _production_control.get_node_or_null("%AutoListToggle") as CheckButton
		if toggle != null:
			toggle.set_pressed_no_signal(enabled)


func _sync_building_from_world() -> void:
	var inst := _instance_id()
	if inst.is_empty():
		return
	var ui: Dictionary = WorldState.get_plot_ui(_plot_id)
	for b in ui.get("buildings", []):
		if b is Dictionary and str((b as Dictionary).get("instance_id", "")) == inst:
			_building = (b as Dictionary).duplicate(true)
			_workshop_id = WorldState.workshop_id_for_building(_building)
			break
	if _production_control != null and _production_control.has_method("setup"):
		_production_control.call(
			"setup",
			_plot_id,
			_building,
			str(_plot_data.get("terrain", "plains")),
		)


func _apply_output_routing() -> void:
	var inst := _instance_id()
	if inst.is_empty():
		return
	var rid := _selected_recipe_id()
	if rid.is_empty():
		return
	var row := _recipe_row(rid)
	var outputs: Variant = row.get("outputs", {})
	if not (outputs is Dictionary):
		return
	for mat in (outputs as Dictionary).keys():
		var mid := str(mat)
		var qty: int = int((outputs as Dictionary)[mat])
		if qty <= 0:
			continue
		var dest := RealmWorkflowSettings.get_output_dest(inst, mid, _plot_id)
		_execute_output_dest(dest, mid, qty)


func _execute_output_dest(dest_id: String, material: String, qty: int) -> void:
	if dest_id == "stash_this" or dest_id.is_empty():
		return
	if dest_id == "harvest_player":
		API.harvest_plot_output(_plot_id, material, qty, func(_d: Dictionary) -> void: pass)
		return
	if dest_id == "auto_list":
		var iid := _instance_id()
		if not bool(_building.get("auto_list_output", false)):
			WorldState.set_building_auto_list_enabled(iid, true)
		return
	if dest_id.begins_with("stash_plot:"):
		var to_pid := dest_id.substr(11)
		API.ship(_plot_id, to_pid, material, qty, func(_d: Dictionary) -> void: pass)
		return
	if dest_id.begins_with("ship_to:"):
		var to_pid := dest_id.substr(8)
		API.ship(_plot_id, to_pid, material, qty, func(_d: Dictionary) -> void: pass)


func _try_warehouse_replenish_all() -> void:
	if not RealmWorkflowSettings.get_auto_replenish_warehouses(_instance_id()):
		return
	for entry in BuildingHubKnowledge.supply_sites():
		if not (entry is Dictionary):
			continue
		var pid := str((entry as Dictionary).get("plot_id", ""))
		if pid.is_empty():
			continue
		if BuildingHubKnowledge.warehouse_rules_active(pid).is_empty():
			continue
		_replenish_warehouse_plot(pid)


func _replenish_warehouse_plot(plot_id: String) -> void:
	for mid in _common_materials():
		var rule := RealmWorkflowSettings.get_warehouse_rule(plot_id, mid)
		if not bool(rule.get("enabled", false)):
			continue
		var target: int = int(rule.get("target_qty", 0))
		if target <= 0:
			continue
		var have := _stash_qty(plot_id, mid)
		var need: int = target - have
		if need <= 0:
			continue
		var max_p: int = int(rule.get("max_price_cents", 0))
		API.market_buy(mid, need, 0, func(_d: Dictionary) -> void: pass, WorldState.party_id, max_p)


func _try_buy_inputs_before_start() -> void:
	var inst := _instance_id()
	if inst.is_empty() or not RealmWorkflowSettings.get_auto_buy_inputs(inst):
		return
	var rid := _selected_recipe_id()
	if rid.is_empty():
		return
	var row := _recipe_row(rid)
	var inputs: Variant = row.get("inputs", {})
	if not (inputs is Dictionary):
		return
	for mat in (inputs as Dictionary).keys():
		var mid := str(mat)
		if mid == "electricity":
			continue
		var src := RealmWorkflowSettings.get_input_source(inst, mid, _plot_id)
		if src != "market_buy":
			continue
		var need: int = int((inputs as Dictionary)[mat])
		if WorldState.player_has_material(mid, need):
			continue
		var shortfall: int = need - WorldState.player_material_qty(mid)
		if shortfall > 0:
			API.market_buy(mid, shortfall, 0, func(_d: Dictionary) -> void: pass)
