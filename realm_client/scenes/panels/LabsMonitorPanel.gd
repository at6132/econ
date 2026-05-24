extends VBoxContainer
## In-run lab observatory — experiment metadata and live telemetry.

var _meta_box: VBoxContainer
var _telemetry_box: VBoxContainer


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	add_theme_constant_override("separation", 12)
	add_child(LabsUi.kicker_label("Observatory"))
	add_child(LabsUi.title_label("LAB RUN", 16))
	add_child(LabsUi.body_label(
		"Isolated sandbox — metrics refresh when the engine pushes ticks.",
		RealmColors.MUTED,
	))
	_meta_box = VBoxContainer.new()
	_meta_box.add_theme_constant_override("separation", 6)
	add_child(_meta_box)
	var sep := HSeparator.new()
	add_child(sep)
	add_child(LabsUi.kicker_label("Telemetry"))
	_telemetry_box = VBoxContainer.new()
	_telemetry_box.add_theme_constant_override("separation", 4)
	add_child(_telemetry_box)
	var exit := Button.new()
	exit.text = "Exit lab → main menu"
	PanelUI.style_btn(exit)
	exit.pressed.connect(_exit_lab)
	add_child(exit)
	WorldState.summary_updated.connect(_refresh)
	_refresh()


func _refresh() -> void:
	PanelUI.clear_children(_meta_box)
	PanelUI.clear_children(_telemetry_box)
	if not WorldState.lab_mode:
		_meta_box.add_child(LabsUi.body_label("Not in a lab session.", RealmColors.WARN))
		return
	_add_kv(_meta_box, "Preset", WorldState.lab_preset_id)
	_add_kv(_meta_box, "Title", WorldState.lab_title)
	_add_kv(_meta_box, "Class", WorldState.lab_category)
	_add_kv(_meta_box, "Seed", str(WorldState.lab_seed if WorldState.lab_seed > 0 else WorldState.world_seed))
	_add_kv(_meta_box, "Scenario", WorldState.scenario_id)
	_add_kv(_meta_box, "World id", WorldState.world_id)

	_add_kv(_telemetry_box, "Tick", str(WorldState.current_tick))
	_add_kv(_telemetry_box, "Game day", str(WorldState.game_day))
	_add_kv(_telemetry_box, "Cash", WorldState.format_money(WorldState.player_cash_cents))
	_add_kv(_telemetry_box, "Net worth", WorldState.format_money(WorldState.player_net_worth_cents))
	_add_kv(_telemetry_box, "Active production", str(WorldState.active_production_count))
	_add_kv(_telemetry_box, "Plots", str(WorldState.plots.size()))
	_add_kv(_telemetry_box, "Open orders", "see bazaar")
	var hist_n := WorldState.market_history_rows.size()
	_add_kv(_telemetry_box, "Market snapshots", str(hist_n))


func _add_kv(parent: VBoxContainer, key: String, val: String) -> void:
	var row := HBoxContainer.new()
	var k := Label.new()
	k.text = key
	k.custom_minimum_size.x = 120
	k.add_theme_color_override("font_color", RealmColors.MUTED)
	if RealmFonts.font_body:
		k.add_theme_font_override("font", RealmFonts.font_body)
	var v := LabsUi.data_cell(val, true)
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(k)
	row.add_child(v)
	parent.add_child(row)


func _exit_lab() -> void:
	API.labs_exit(
		"frontier",
		42,
		func(_data: Dictionary) -> void:
			WorldState.lab_mode = false
			WorldState.lab_preset_id = ""
			WorldState.lab_title = ""
			LabsSession.clear()
			get_tree().change_scene_to_file("res://scenes/GameHome.tscn"),
	)
