extends Control
## Configure lab parameters and POST /labs/start.

const LABS_HUB := "res://scenes/labs/LabsHub.tscn"
const MAIN_SCENE := "res://scenes/Main.tscn"
const CreationScreenScene := preload("res://scenes/WorldCreationScreen.tscn")

var _preset: Dictionary = {}
var _schema: Dictionary = {}

var _seed_spin: SpinBox
var _map_slider: HSlider
var _cash_slider: HSlider
var _settler_slider: HSlider
var _speed_opt: OptionButton
var _map_val: Label
var _cash_val: Label
var _settler_row: Control
var _footer: Label
var _creation_screen: Control = null


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	_build_chrome()
	if RealmFonts:
		RealmFonts.apply_to_control(self)
	var pid := LabsSession.selected_preset_id
	if pid.is_empty():
		_footer.text = "No preset selected."
		return
	_load_preset(pid)


func _build_chrome() -> void:
	var bg := ColorRect.new()
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	bg.color = RealmColors.BG
	add_child(bg)

	var margin := MarginContainer.new()
	margin.set_anchors_preset(Control.PRESET_FULL_RECT)
	margin.add_theme_constant_override("margin_left", 40)
	margin.add_theme_constant_override("margin_right", 40)
	margin.add_theme_constant_override("margin_top", 28)
	margin.add_theme_constant_override("margin_bottom", 24)
	add_child(margin)

	var root := HBoxContainer.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_theme_constant_override("separation", 24)
	margin.add_child(root)

	# Left — specimen sheet
	var left := PanelContainer.new()
	left.custom_minimum_size.x = 520
	left.size_flags_vertical = Control.SIZE_EXPAND_FILL
	left.add_theme_stylebox_override("panel", LabsUi.style_data_panel())
	root.add_child(left)

	var lv := VBoxContainer.new()
	lv.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	lv.add_theme_constant_override("margin_left", 16)
	lv.add_theme_constant_override("margin_right", 16)
	lv.add_theme_constant_override("margin_top", 14)
	lv.add_theme_constant_override("margin_bottom", 14)
	lv.add_theme_constant_override("separation", 10)
	left.add_child(lv)
	lv.add_child(LabsUi.kicker_label("Specimen"))
	lv.add_child(LabsUi.title_label("PRESET", 18))
	var _meta_box := VBoxContainer.new()
	_meta_box.name = "MetaBox"
	lv.add_child(_meta_box)

	# Right — parameters
	var right := VBoxContainer.new()
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	right.add_theme_constant_override("separation", 12)
	root.add_child(right)

	var nav := HBoxContainer.new()
	var back := Button.new()
	back.text = "← Catalog"
	LabsUi.style_menu_button(back, false)
	back.pressed.connect(func(): get_tree().change_scene_to_file(LABS_HUB))
	nav.add_child(back)
	right.add_child(nav)

	right.add_child(LabsUi.kicker_label("Run configuration"))
	right.add_child(LabsUi.title_label("PARAMETERS", 18))
	right.add_child(LabsUi.body_label(
		"Adjust experimental variables before bootstrap. All runs are deterministic for a given seed.",
		RealmColors.MUTED,
	))

	var form := PanelContainer.new()
	form.size_flags_vertical = Control.SIZE_EXPAND_FILL
	form.add_theme_stylebox_override("panel", LabsUi.style_data_panel())
	right.add_child(form)

	var fv := VBoxContainer.new()
	fv.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	fv.add_theme_constant_override("margin_left", 18)
	fv.add_theme_constant_override("margin_right", 18)
	fv.add_theme_constant_override("margin_top", 16)
	fv.add_theme_constant_override("margin_bottom", 16)
	fv.add_theme_constant_override("separation", 16)
	form.add_child(fv)

	fv.add_child(_param_row_seed())
	_map_val = LabsUi.body_label("100%", RealmColors.MAGIC)
	_map_slider = _make_slider(50, 150, 100, _map_val, "%")
	fv.add_child(_wrap_slider_block("Map scale", _map_slider, _map_val))
	_cash_val = LabsUi.body_label("100%", RealmColors.MAGIC)
	_cash_slider = _make_slider(25, 400, 100, _cash_val, "%")
	fv.add_child(_wrap_slider_block("Starting cash", _cash_slider, _cash_val))
	_settler_row = _param_row_settlers()
	fv.add_child(_settler_row)
	fv.add_child(_param_row_speed())

	var start := Button.new()
	start.text = "▶ INITIATE LAB RUN"
	start.custom_minimum_size.y = 52
	PanelUI.style_btn(start, true)
	if RealmFonts.font_body:
		start.add_theme_font_override("font", RealmFonts.font_body)
		start.add_theme_font_size_override("font_size", 22)
	start.pressed.connect(_on_start_pressed)
	fv.add_child(start)

	_footer = LabsUi.body_label("", RealmColors.MAGIC)
	right.add_child(_footer)


func _param_row_seed() -> HBoxContainer:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 12)
	row.add_child(_field_label("Seed"))
	_seed_spin = SpinBox.new()
	_seed_spin.min_value = 1
	_seed_spin.max_value = 999999
	_seed_spin.value = 42
	_seed_spin.custom_minimum_size.x = 200
	_seed_spin.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(_seed_spin)
	return row


func _wrap_slider_block(label: String, slider: HSlider, value_lbl: Label) -> VBoxContainer:
	var row := VBoxContainer.new()
	row.add_theme_constant_override("separation", 4)
	var head := HBoxContainer.new()
	head.add_child(_field_label(label))
	value_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(value_lbl)
	row.add_child(head)
	row.add_child(slider)
	return row


func _param_row_settlers() -> VBoxContainer:
	var row := VBoxContainer.new()
	row.add_theme_constant_override("separation", 4)
	var head := HBoxContainer.new()
	head.add_child(_field_label("Settler count"))
	var val := LabsUi.body_label("—", RealmColors.MAGIC)
	head.add_child(val)
	row.add_child(head)
	_settler_slider = HSlider.new()
	_settler_slider.min_value = 0
	_settler_slider.max_value = 80
	_settler_slider.step = 1
	_settler_slider.value_changed.connect(func(v: float) -> void: val.text = str(int(v)))
	row.add_child(_settler_slider)
	row.visible = false
	return row


func _param_row_speed() -> HBoxContainer:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 12)
	row.add_child(_field_label("Sim speed"))
	_speed_opt = OptionButton.new()
	_speed_opt.add_item("Slow (0.5×)")
	_speed_opt.add_item("Normal (1×)")
	_speed_opt.add_item("Fast (2×)")
	_speed_opt.selected = 2
	_speed_opt.custom_minimum_size.x = 220
	row.add_child(_speed_opt)
	return row


func _make_slider(mn: int, mx: int, def: int, val_lbl: Label, suffix: String) -> HSlider:
	var s := HSlider.new()
	s.min_value = mn
	s.max_value = mx
	s.step = 10 if suffix == "%" else 1
	s.value = def
	s.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	s.value_changed.connect(func(v: float) -> void: val_lbl.text = "%d%s" % [int(v), suffix])
	val_lbl.text = "%d%s" % [def, suffix]
	return s


func _field_label(text: String) -> Label:
	var l := Label.new()
	l.text = text
	l.custom_minimum_size.x = 140
	l.add_theme_color_override("font_color", RealmColors.DIM)
	if RealmFonts.font_body:
		l.add_theme_font_override("font", RealmFonts.font_body)
	l.add_theme_font_size_override("font_size", 18)
	return l


func _load_preset(preset_id: String) -> void:
	_footer.text = "Loading preset definition…"
	API.labs_get_preset(
		preset_id,
		func(data: Dictionary) -> void:
			if not bool(data.get("ok", false)):
				_footer.text = str(data.get("detail", data))
				return
			_preset = data.get("preset", {})
			_schema = _preset.get("override_schema", {})
			_seed_spin.value = int(_preset.get("default_seed", 42))
			_speed_opt.selected = clampi(int(_preset.get("default_sim_speed", 2)), 0, 2)
			if _schema.has("map_scale_pct"):
				var d: Dictionary = _schema.map_scale_pct
				_map_slider.min_value = int(d.get("min", 50))
				_map_slider.max_value = int(d.get("max", 150))
				_map_slider.value = int(d.get("default", 100))
			if _schema.has("cash_scale_pct"):
				var d2: Dictionary = _schema.cash_scale_pct
				_cash_slider.min_value = int(d2.get("min", 25))
				_cash_slider.max_value = int(d2.get("max", 400))
				_cash_slider.value = int(d2.get("default", 100))
			if _schema.has("settler_count"):
				var d3: Dictionary = _schema.settler_count
				_settler_row.visible = true
				_settler_slider.min_value = int(d3.get("min", 0))
				_settler_slider.max_value = int(d3.get("max", 80))
				_settler_slider.value = int(d3.get("default", 0))
			_populate_meta()
			_footer.text = "Ready to bootstrap isolated world."
	)


func _populate_meta() -> void:
	var box: VBoxContainer = find_child("MetaBox", true, false) as VBoxContainer
	if box == null:
		return
	PanelUI.clear_children(box)
	var rows: Array = [
		["ID", str(_preset.get("id", ""))],
		["Class", str(_preset.get("category", ""))],
		["Base engine", str(_preset.get("base", ""))],
		["Grid", str(_preset.get("grid_label", ""))],
		["Tags", ", ".join(_preset.get("tags", []))],
	]
	for r in rows:
		box.add_child(_meta_kv(str(r[0]), str(r[1])))
	var desc := LabsUi.body_label(str(_preset.get("description", "")), RealmColors.DIM)
	box.add_child(desc)


func _meta_kv(key: String, val: String) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.add_child(_field_label(key))
	var v := LabsUi.data_cell(val, true)
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(v)
	return row


func _on_start_pressed() -> void:
	await _ensure_engine()
	var overrides := {
		"map_scale_pct": int(_map_slider.value),
		"cash_scale_pct": int(_cash_slider.value),
		"sim_speed": _speed_opt.selected,
	}
	if _settler_row.visible:
		overrides["settler_count"] = int(_settler_slider.value)

	_creation_screen = CreationScreenScene.instantiate()
	add_child(_creation_screen)
	var title := str(_preset.get("title", LabsSession.selected_preset_id))
	_creation_screen.open_lab(title)
	_creation_screen.creation_finished.connect(_on_creation_done, CONNECT_ONE_SHOT)
	_creation_screen.begin_waiting_for_engine(120.0)

	API.labs_start(
		LabsSession.selected_preset_id,
		int(_seed_spin.value),
		overrides,
		func(data: Dictionary) -> void:
			if is_instance_valid(_creation_screen):
				_creation_screen.end_waiting_for_engine()
			if not bool(data.get("ok", false)):
				_abort(str(data.get("detail", data)))
				return
			LabsSession.last_start_response = data
			WorldState.lab_mode = true
			WorldState.lab_preset_id = str(data.get("lab_preset_id", ""))
			WorldState.lab_title = str(data.get("lab_title", title))
			WorldState.lab_category = str(data.get("lab_category", ""))
			var wid := str(data.get("world_id", "")).strip_edges()
			if not wid.is_empty():
				WorldState.world_id = wid
			var cash := int(data.get("player_cash_cents", 0))
			if cash > 0:
				WorldState.player_cash_cents = cash
			var spd_idx := int(overrides.get("sim_speed", 2))
			var speeds := [0.5, 1.0, 2.0]
			API.sim_control({"speed": speeds[clampi(spd_idx, 0, 2)]}, Callable())
			if is_instance_valid(_creation_screen):
				_creation_screen.mark_done()
	)


func _ensure_engine() -> void:
	if Transport.is_engine_ready():
		return
	_footer.text = "Starting solo engine…"
	await Transport.engine_ready


func _abort(msg: String) -> void:
	if is_instance_valid(_creation_screen):
		_creation_screen.queue_free()
		_creation_screen = null
	_footer.text = msg


func _on_creation_done() -> void:
	if is_instance_valid(_creation_screen):
		_creation_screen.queue_free()
	get_tree().change_scene_to_file(MAIN_SCENE)


func _on_creation_screen_done() -> void:
	pass
