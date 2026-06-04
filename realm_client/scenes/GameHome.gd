extends Control
## Realm entry: main menu → Solo (New / Continue) → in-game ``Main``.

const MAIN_SCENE := "res://scenes/Main.tscn"
const CreationScreenScene := preload("res://scenes/WorldCreationScreen.tscn")

const DEFAULT_SCENARIO := "genesis"

const SCENARIOS: Array = [
	["genesis", "Genesis — full 320×240 continental map (default)"],
	["frontier", "Frontier — small solo slice"],
	["cartel", "Cartel"],
	["bootstrapper", "Bootstrapper"],
	["speculator", "Speculator"],
	["millrace", "Millrace"],
	["archive", "Archive"],
]

@onready var _left: VBoxContainer = $Margin/HBox/LeftColumn

var _panel_root: VBoxContainer
var _panel_solo: VBoxContainer
var _panel_new: VBoxContainer
var _panel_continue: VBoxContainer
var _panel_settings: VBoxContainer

var _scenario_opt: OptionButton
var _seed_spin: SpinBox
var _name_edit: LineEdit
var _footer: Label
var _worlds_scroll: ScrollContainer
var _worlds_vbox: VBoxContainer
var _saves_detail_heading: Label
var _saves_detail_scroll: ScrollContainer
var _saves_detail_vbox: VBoxContainer
var _selected_world_key: String = ""
var _grouped_slots: Dictionary = {}
var _world_row_buttons: Dictionary = {}
var _pending_new_world_name: String = ""
var _pending_new_world_id: String = ""
## Bumped on each Continue open so late ``persistence/list`` callbacks cannot
## repaint the menu with stale or disk-placeholder rows.
var _continue_list_seq: int = 0
var _persistence_list_done: Dictionary = {}  # seq -> bool

var _dialog: AcceptDialog
var _confirm_clear_saves: ConfirmationDialog
var _confirm_restart_engine: ConfirmationDialog

var _settings_about: Label
var _settings_status: Label
var _chk_start_paused: CheckButton
var _opt_default_speed: OptionButton
var _opt_default_overlay: OptionButton
var _edit_save_slot: LineEdit
var _settings_pause_btn: Button
var _settings_speed_btns: Array[Button] = []


func _ready() -> void:
	_dialog = AcceptDialog.new()
	_dialog.title = "Realm"
	add_child(_dialog)
	_confirm_clear_saves = ConfirmationDialog.new()
	_confirm_clear_saves.title = "Clear all saves?"
	_confirm_clear_saves.dialog_text = (
		"Delete every *.sqlite file in the saves/ folder.\n\n"
		+ "This cannot be undone. Your current in-memory world is not affected."
	)
	_confirm_clear_saves.ok_button_text = "Clear all saves"
	_confirm_clear_saves.cancel_button_text = "Cancel"
	_confirm_clear_saves.confirmed.connect(_on_clear_all_saves_confirmed)
	add_child(_confirm_clear_saves)
	_confirm_restart_engine = ConfirmationDialog.new()
	_confirm_restart_engine.title = "Restart solo engine?"
	_confirm_restart_engine.dialog_text = (
		"Stops and respawns the Python process (tries ports 9000–9003).\n\n"
		+ "Use this after engine code changes or if Continue/New world acts stale."
	)
	_confirm_restart_engine.ok_button_text = "Restart"
	_confirm_restart_engine.confirmed.connect(_on_restart_engine_confirmed)
	add_child(_confirm_restart_engine)
	WorldState.sim_clock_updated.connect(_on_world_sim_clock_updated)
	Transport.engine_ready.connect(_on_transport_engine_ready)
	Transport.engine_error.connect(_on_transport_engine_error)
	_build_panels()
	_show_panel("root")
	if RealmFonts:
		RealmFonts.apply_to_control(self)
	var cap: Label = $Margin/HBox/Hero/HeroCaption as Label
	cap.add_theme_color_override("font_color", RealmColors.MUTED)
	if RealmFonts.font_body:
		cap.add_theme_font_override("font", RealmFonts.font_body)
	cap.add_theme_font_size_override("font_size", 17)


func _build_panels() -> void:
	for c in _left.get_children():
		c.queue_free()

	var title := Label.new()
	title.name = "BrandTitle"
	title.text = "REALM"
	title.add_theme_color_override("font_color", RealmColors.ACCENT)
	if RealmFonts.font_display:
		title.add_theme_font_override("font", RealmFonts.font_display)
		title.add_theme_font_size_override("font_size", 14)

	var sub := Label.new()
	sub.text = "Player-run economy"
	sub.add_theme_color_override("font_color", RealmColors.MUTED)
	if RealmFonts.font_body:
		sub.add_theme_font_override("font", RealmFonts.font_body)
		sub.add_theme_font_size_override("font_size", 22)

	var spacer := Control.new()
	spacer.custom_minimum_size.y = 28

	_left.add_child(title)
	_left.add_child(sub)
	_left.add_child(spacer)

	var stack := MarginContainer.new()
	stack.add_theme_constant_override("margin_top", 8)
	stack.size_flags_vertical = Control.SIZE_EXPAND_FILL
	var inner := VBoxContainer.new()
	inner.add_theme_constant_override("separation", 14)
	stack.add_child(inner)
	_left.add_child(stack)

	_footer = Label.new()
	_footer.text = ""
	_footer.add_theme_color_override("font_color", RealmColors.MAGIC)
	if RealmFonts.font_body:
		_footer.add_theme_font_override("font", RealmFonts.font_body)
	_footer.add_theme_font_size_override("font_size", 17)
	_left.add_child(_footer)

	_panel_root = _make_root_menu()
	_panel_solo = _make_solo_menu()
	_panel_new = _make_new_world()
	_panel_continue = _make_continue()
	_panel_settings = _make_settings()
	for p in [_panel_root, _panel_solo, _panel_new, _panel_continue, _panel_settings]:
		p.visible = false
		inner.add_child(p)


func _make_root_menu() -> VBoxContainer:
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 12)
	v.add_child(_menu_heading("Main menu"))

	var b_settings := _menu_button("Settings", false)
	b_settings.pressed.connect(func(): _show_panel("settings"))

	var b_solo := _menu_button("Solo", false)
	b_solo.pressed.connect(_on_solo_pressed)

	var b_labs := _menu_button("Labs", false)
	b_labs.pressed.connect(_on_labs_pressed)

	var b_multi := _menu_button("Multiplayer", true)
	b_multi.pressed.connect(_on_coming_soon_pressed.bind("Multiplayer"))

	var b_quit := _menu_button("Quit game", false)
	b_quit.pressed.connect(_on_quit_game_pressed)

	v.add_child(b_solo)
	v.add_child(b_labs)
	v.add_child(b_multi)
	v.add_child(b_settings)
	v.add_child(b_quit)
	return v


func _on_labs_pressed() -> void:
	LabsSession.clear()
	get_tree().change_scene_to_file("res://scenes/labs/LabsHub.tscn")


func _on_quit_game_pressed() -> void:
	get_tree().quit()


func _make_solo_menu() -> VBoxContainer:
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 12)
	v.add_child(_menu_heading("Solo"))

	var b_new := _menu_button("New world", false)
	b_new.pressed.connect(func(): _show_panel("new"))

	var b_cont := _menu_button("Continue", false)
	b_cont.pressed.connect(_on_continue_pressed)

	var b_back := _menu_button("Back", false)
	b_back.pressed.connect(func(): _show_panel("root"))

	v.add_child(b_new)
	v.add_child(b_cont)
	v.add_child(b_back)
	return v


func _make_new_world() -> VBoxContainer:
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 14)
	v.add_child(_menu_heading("New world"))

	var row_name := HBoxContainer.new()
	row_name.add_theme_constant_override("separation", 12)
	var lname := Label.new()
	lname.text = "Name"
	lname.add_theme_color_override("font_color", RealmColors.DIM)
	lname.custom_minimum_size.x = 120
	if RealmFonts.font_body:
		lname.add_theme_font_override("font", RealmFonts.font_body)
		lname.add_theme_font_size_override("font_size", 20)
	_name_edit = LineEdit.new()
	_name_edit.placeholder_text = "My World"
	_name_edit.custom_minimum_size.x = 360
	_name_edit.max_length = 64
	_name_edit.add_theme_stylebox_override("normal", RealmColors.style_btn_normal())
	_name_edit.add_theme_color_override("font_color", RealmColors.TEXT)
	_name_edit.add_theme_color_override("font_placeholder_color", RealmColors.MUTED)
	if RealmFonts.font_body:
		_name_edit.add_theme_font_override("font", RealmFonts.font_body)
		_name_edit.add_theme_font_size_override("font_size", 20)
	row_name.add_child(lname)
	row_name.add_child(_name_edit)
	v.add_child(row_name)

	var row_sc := HBoxContainer.new()
	row_sc.add_theme_constant_override("separation", 12)
	var ls := Label.new()
	ls.text = "Scenario"
	ls.add_theme_color_override("font_color", RealmColors.DIM)
	ls.custom_minimum_size.x = 120
	if RealmFonts.font_body:
		ls.add_theme_font_override("font", RealmFonts.font_body)
		ls.add_theme_font_size_override("font_size", 20)
	_scenario_opt = OptionButton.new()
	_scenario_opt.custom_minimum_size.x = 360
	for row in SCENARIOS:
		var sid: String = str(row[0])
		var lab: String = str(row[1])
		_scenario_opt.add_item(lab)
		_scenario_opt.set_item_metadata(_scenario_opt.item_count - 1, sid)
	var default_idx := 0
	for i in range(SCENARIOS.size()):
		if str((SCENARIOS[i] as Array)[0]) == DEFAULT_SCENARIO:
			default_idx = i
			break
	_scenario_opt.select(default_idx)
	_style_primary_button(_scenario_opt)
	row_sc.add_child(ls)
	row_sc.add_child(_scenario_opt)
	v.add_child(row_sc)

	var row_seed := HBoxContainer.new()
	row_seed.add_theme_constant_override("separation", 12)
	var lseed := Label.new()
	lseed.text = "Seed"
	lseed.add_theme_color_override("font_color", RealmColors.DIM)
	lseed.custom_minimum_size.x = 120
	if RealmFonts.font_body:
		lseed.add_theme_font_override("font", RealmFonts.font_body)
		lseed.add_theme_font_size_override("font_size", 20)
	_seed_spin = SpinBox.new()
	_seed_spin.min_value = 0
	_seed_spin.max_value = 2_147_483_647
	_seed_spin.value = _roll_new_world_seed_spin()
	_seed_spin.step = 1
	_seed_spin.custom_minimum_size.x = 200
	_style_primary_button(_seed_spin)
	row_seed.add_child(lseed)
	row_seed.add_child(_seed_spin)
	v.add_child(row_seed)

	var hint := Label.new()
	hint.text = "Spawns the local Python engine (no uvicorn). First boot can take a minute for Genesis."
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hint.add_theme_color_override("font_color", RealmColors.MUTED)
	if RealmFonts.font_body:
		hint.add_theme_font_override("font", RealmFonts.font_body)
		hint.add_theme_font_size_override("font_size", 16)
	v.add_child(hint)

	var b_start := _menu_button("Start", false)
	b_start.pressed.connect(_on_start_new_world)
	v.add_child(b_start)

	var b_back := _menu_button("Back", false)
	b_back.pressed.connect(func(): _show_panel("solo"))
	v.add_child(b_back)
	return v


func _make_settings() -> VBoxContainer:
	var outer := VBoxContainer.new()
	outer.size_flags_vertical = Control.SIZE_EXPAND_FILL
	outer.add_theme_constant_override("separation", 10)
	outer.add_child(_menu_heading("Settings"))

	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.custom_minimum_size = Vector2(0, 420)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	var v := VBoxContainer.new()
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	v.add_theme_constant_override("separation", 14)
	scroll.add_child(v)
	outer.add_child(scroll)

	# ── About ──
	v.add_child(_menu_heading("About"))
	_settings_about = _settings_info_label("Loading engine info…")
	v.add_child(_settings_about)
	_settings_status = _settings_info_label("")
	v.add_child(_settings_status)

	var b_log := _menu_button("Open engine log", false)
	b_log.pressed.connect(_on_open_log_pressed)
	v.add_child(b_log)

	# ── Session defaults (user://) ──
	v.add_child(_menu_heading("Session defaults"))
	v.add_child(
		_settings_hint_label("Applied when you enter the world from New world or Continue.")
	)

	_chk_start_paused = CheckButton.new()
	_chk_start_paused.text = "Start paused"
	_style_check_button(_chk_start_paused)
	_chk_start_paused.toggled.connect(_on_start_paused_toggled)
	v.add_child(_chk_start_paused)

	var row_speed := HBoxContainer.new()
	row_speed.add_theme_constant_override("separation", 12)
	row_speed.add_child(_settings_field_label("Default speed"))
	_opt_default_speed = OptionButton.new()
	_opt_default_speed.custom_minimum_size.x = 200
	for mult in RealmSettings.SPEED_OPTIONS:
		_opt_default_speed.add_item("%dx" % int(mult))
	_style_primary_button(_opt_default_speed)
	_opt_default_speed.item_selected.connect(_on_default_speed_selected)
	row_speed.add_child(_opt_default_speed)
	v.add_child(row_speed)

	var row_ov := HBoxContainer.new()
	row_ov.add_theme_constant_override("separation", 12)
	row_ov.add_child(_settings_field_label("Map overlay"))
	_opt_default_overlay = OptionButton.new()
	_opt_default_overlay.custom_minimum_size.x = 280
	for row in RealmSettings.OVERLAY_MODES:
		_opt_default_overlay.add_item(str((row as Array)[1]))
	_style_primary_button(_opt_default_overlay)
	_opt_default_overlay.item_selected.connect(_on_default_overlay_selected)
	row_ov.add_child(_opt_default_overlay)
	v.add_child(row_ov)

	var row_slot := HBoxContainer.new()
	row_slot.add_theme_constant_override("separation", 12)
	row_slot.add_child(_settings_field_label("Save slot"))
	_edit_save_slot = LineEdit.new()
	_edit_save_slot.placeholder_text = "world id (default)"
	_edit_save_slot.custom_minimum_size.x = 200
	_edit_save_slot.max_length = 48
	_edit_save_slot.add_theme_stylebox_override("normal", RealmColors.style_btn_normal())
	_edit_save_slot.add_theme_color_override("font_color", RealmColors.TEXT)
	if RealmFonts.font_body:
		_edit_save_slot.add_theme_font_override("font", RealmFonts.font_body)
		_edit_save_slot.add_theme_font_size_override("font_size", 20)
	_edit_save_slot.text_submitted.connect(func(_t: String) -> void: _on_save_slot_committed())
	_edit_save_slot.focus_exited.connect(func() -> void: _on_save_slot_committed())
	row_slot.add_child(_edit_save_slot)
	v.add_child(row_slot)
	v.add_child(
		_settings_hint_label(
			"Blank = manual saves go to this world's id file (not shared «current»). "
			+ "Autosave is separate: <id>_autosave.sqlite."
		)
	)

	# ── Live sim (engine must be up) ──
	v.add_child(_menu_heading("Simulation"))
	v.add_child(_settings_hint_label("Controls the running solo engine (same as in-game top strip)."))
	var sim_row := HBoxContainer.new()
	sim_row.add_theme_constant_override("separation", 8)
	_settings_pause_btn = _menu_button("Pause", false)
	_settings_pause_btn.custom_minimum_size = Vector2(100, 40)
	_settings_pause_btn.pressed.connect(_on_settings_pause_pressed)
	sim_row.add_child(_settings_pause_btn)
	_settings_speed_btns.clear()
	for mult in [1.0, 2.0, 4.0]:
		var sb := _menu_button("%dx" % int(mult), false)
		sb.custom_minimum_size = Vector2(64, 40)
		sb.pressed.connect(_on_settings_speed_pressed.bind(mult))
		sim_row.add_child(sb)
		_settings_speed_btns.append(sb)
	v.add_child(sim_row)

	# ── Saves & engine ──
	v.add_child(_menu_heading("Saves & engine"))
	var b_folder := _menu_button("Open saves folder", false)
	b_folder.pressed.connect(_on_open_saves_folder_pressed)
	v.add_child(b_folder)

	v.add_child(
		_settings_hint_label("Removes every *.sqlite in saves/. In-memory play is not affected.")
	)
	var b_clear := _menu_button("Clear all save files", false)
	b_clear.add_theme_color_override("font_color", RealmColors.DANGER)
	b_clear.add_theme_color_override("font_hover_color", RealmColors.WARN)
	b_clear.pressed.connect(_on_clear_saves_pressed)
	v.add_child(b_clear)

	var b_restart := _menu_button("Restart solo engine", false)
	b_restart.pressed.connect(_on_restart_engine_pressed)
	v.add_child(b_restart)

	var b_back := _menu_button("Back", false)
	b_back.pressed.connect(func(): _show_panel("root"))
	v.add_child(b_back)

	_sync_settings_prefs_ui()
	return outer


func _make_continue() -> VBoxContainer:
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 12)
	v.add_child(_menu_heading("Continue"))

	var split := HBoxContainer.new()
	split.add_theme_constant_override("separation", 14)
	split.custom_minimum_size = Vector2(0, 320)
	split.size_flags_vertical = Control.SIZE_EXPAND_FILL

	var worlds_col := VBoxContainer.new()
	worlds_col.custom_minimum_size.x = 228
	worlds_col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	worlds_col.size_flags_stretch_ratio = 1.0
	worlds_col.add_child(_continue_side_heading("Worlds"))
	_worlds_scroll = ScrollContainer.new()
	_worlds_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_worlds_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_worlds_vbox = VBoxContainer.new()
	_worlds_vbox.add_theme_constant_override("separation", 8)
	_worlds_vbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_worlds_scroll.add_child(_worlds_vbox)
	worlds_col.add_child(_worlds_scroll)

	var saves_col := VBoxContainer.new()
	saves_col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	saves_col.size_flags_stretch_ratio = 1.15
	saves_col.add_child(_continue_side_heading("Saves"))
	_saves_detail_heading = Label.new()
	_saves_detail_heading.text = "Select a world on the left."
	_saves_detail_heading.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_saves_detail_heading.add_theme_color_override("font_color", RealmColors.MUTED)
	if RealmFonts.font_body:
		_saves_detail_heading.add_theme_font_override("font", RealmFonts.font_body)
		_saves_detail_heading.add_theme_font_size_override("font_size", 15)
	saves_col.add_child(_saves_detail_heading)
	_saves_detail_scroll = ScrollContainer.new()
	_saves_detail_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_saves_detail_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_saves_detail_vbox = VBoxContainer.new()
	_saves_detail_vbox.add_theme_constant_override("separation", 8)
	_saves_detail_vbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_saves_detail_scroll.add_child(_saves_detail_vbox)
	saves_col.add_child(_saves_detail_scroll)

	split.add_child(worlds_col)
	split.add_child(saves_col)
	v.add_child(split)

	var b_back := _menu_button("Back", false)
	b_back.pressed.connect(func(): _show_panel("solo"))
	v.add_child(b_back)

	var hint2 := Label.new()
	hint2.text = "Pick a world, then a save slot to load."
	hint2.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hint2.add_theme_color_override("font_color", RealmColors.MUTED)
	if RealmFonts.font_body:
		hint2.add_theme_font_override("font", RealmFonts.font_body)
		hint2.add_theme_font_size_override("font_size", 15)
	v.add_child(hint2)
	return v


func _continue_side_heading(txt: String) -> Label:
	var l := Label.new()
	l.text = txt
	l.add_theme_color_override("font_color", RealmColors.DIM)
	if RealmFonts.font_body:
		l.add_theme_font_override("font", RealmFonts.font_body)
		l.add_theme_font_size_override("font_size", 16)
	return l


func _menu_heading(txt: String) -> Label:
	var l := Label.new()
	l.name = "GroupKicker"
	l.text = txt.to_upper()
	l.add_theme_color_override("font_color", RealmColors.MUTED)
	if RealmFonts.font_display:
		l.add_theme_font_override("font", RealmFonts.font_display)
		l.add_theme_font_size_override("font_size", 9)
	return l


func _menu_button(text: String, dimmed: bool) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = Vector2(0, 48)
	b.alignment = HORIZONTAL_ALIGNMENT_LEFT
	b.add_theme_stylebox_override("normal", RealmColors.style_btn_normal())
	b.add_theme_stylebox_override("hover", RealmColors.style_btn_hover())
	b.add_theme_stylebox_override("pressed", RealmColors.style_btn_normal())
	b.add_theme_color_override("font_color", RealmColors.TEXT)
	b.add_theme_color_override("font_hover_color", RealmColors.ACCENT)
	if dimmed:
		b.modulate = Color(1.0, 1.0, 1.0, 0.48)
	if RealmFonts.font_body:
		b.add_theme_font_override("font", RealmFonts.font_body)
		b.add_theme_font_size_override("font_size", 22)
	return b


func _style_primary_button(ctrl: Control) -> void:
	if ctrl is OptionButton:
		var ob := ctrl as OptionButton
		ob.add_theme_stylebox_override("normal", RealmColors.style_btn_normal())
		ob.add_theme_stylebox_override("hover", RealmColors.style_btn_hover())
	if ctrl is SpinBox:
		var sb := ctrl as SpinBox
		sb.add_theme_stylebox_override("normal", RealmColors.style_btn_normal())


func _show_panel(which: String) -> void:
	_panel_root.visible = which == "root"
	_panel_solo.visible = which == "solo"
	_panel_new.visible = which == "new"
	_panel_continue.visible = which == "continue"
	_panel_settings.visible = which == "settings"
	if which == "settings":
		_sync_settings_prefs_ui()
		_refresh_settings_diagnostics()
	if which == "new":
		if is_instance_valid(_seed_spin):
			_seed_spin.value = _roll_new_world_seed_spin()
		if is_instance_valid(_name_edit):
			_name_edit.text = ""


func _roll_new_world_seed_spin() -> int:
	## Uniform in ``[0, INT32_MAX]`` — matches ``SpinBox`` limits; no engine/API change.
	var rng := RandomNumberGenerator.new()
	rng.randomize()
	return rng.randi_range(0, 2_147_483_647)


func _on_coming_soon_pressed(feature: String) -> void:
	_dialog.dialog_text = "%s — coming soon." % feature
	_dialog.popup_centered()


func _settings_info_label(text: String) -> Label:
	var l := Label.new()
	l.text = text
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.add_theme_color_override("font_color", RealmColors.DIM)
	if RealmFonts.font_body:
		l.add_theme_font_override("font", RealmFonts.font_body)
		l.add_theme_font_size_override("font_size", 16)
	return l


func _settings_hint_label(text: String) -> Label:
	var l := _settings_info_label(text)
	l.add_theme_color_override("font_color", RealmColors.MUTED)
	l.add_theme_font_size_override("font_size", 15)
	return l


func _settings_field_label(text: String) -> Label:
	var l := Label.new()
	l.text = text
	l.custom_minimum_size.x = 120
	l.add_theme_color_override("font_color", RealmColors.DIM)
	if RealmFonts.font_body:
		l.add_theme_font_override("font", RealmFonts.font_body)
		l.add_theme_font_size_override("font_size", 18)
	return l


func _style_check_button(cb: CheckButton) -> void:
	cb.add_theme_color_override("font_color", RealmColors.TEXT)
	cb.add_theme_color_override("font_hover_color", RealmColors.ACCENT)
	if RealmFonts.font_body:
		cb.add_theme_font_override("font", RealmFonts.font_body)
		cb.add_theme_font_size_override("font_size", 20)


func _sync_settings_prefs_ui() -> void:
	if not is_instance_valid(_chk_start_paused):
		return
	_chk_start_paused.set_block_signals(true)
	_chk_start_paused.button_pressed = RealmSettings.start_paused
	_chk_start_paused.set_block_signals(false)
	if is_instance_valid(_opt_default_speed):
		_opt_default_speed.select(RealmSettings.speed_index_from_value(RealmSettings.default_speed))
	if is_instance_valid(_opt_default_overlay):
		var oi := RealmSettings.overlay_index_from_id(RealmSettings.default_overlay)
		_opt_default_overlay.select(maxi(0, oi))
	if is_instance_valid(_edit_save_slot):
		_edit_save_slot.text = RealmSettings.default_save_slot
	if is_instance_valid(_settings_pause_btn):
		_settings_pause_btn.text = "Resume" if WorldState.sim_paused else "Pause"


func _refresh_settings_diagnostics() -> void:
	if not is_instance_valid(_settings_about):
		return
	var port := Transport.get_solo_port()
	var log_p := Transport.solo_log_path()
	var saves_p := Transport.repo_saves_dir()
	_settings_about.text = (
		"Solo engine: %s:%d\nLog: %s\nSaves: %s"
		% [Transport.SOLO_HOST, port, log_p, saves_p]
	)
	_settings_status.text = "Fetching version…"
	if Transport.mode == Transport.Mode.SOLO and not Transport.is_engine_ready():
		Transport.engine_ready.connect(_refresh_settings_diagnostics, CONNECT_ONE_SHOT)
		return
	API.get_version(
		func(ver: Dictionary) -> void:
			if not is_instance_valid(_settings_about):
				return
			var build := str(ver.get("build_id", "?"))
			var cash := WorldState.variant_to_int(ver.get("player_starting_cash_cents", 0), 0)
			var line := "Build: %s (client %s)" % [build, WorldState.REALM_BUILD_ID]
			if cash > 0:
				line += "  ·  starting cash %s" % WorldState.format_money(cash)
			if not bool(ver.get("ok", false)):
				line = "Engine on :%d is outdated (no /version)." % port
			_settings_about.text = (
				"%s\nSolo: %s:%d\nLog: %s\nSaves: %s" % [line, Transport.SOLO_HOST, port, log_p, saves_p]
			)
	)
	API.persistence_status(
		func(st: Dictionary) -> void:
			if not is_instance_valid(_settings_status):
				return
			if not bool(st.get("ok", false)):
				_settings_status.text = ""
				return
			var at := int(st.get("last_save_at", 0))
			var path := str(st.get("last_save_path", ""))
			var kind := str(st.get("last_save_kind", ""))
			if at <= 0:
				_settings_status.text = "Last save: none yet"
			else:
				var ago := maxi(0, int(Time.get_unix_time_from_system()) - at)
				var name := path.get_file() if not path.is_empty() else "?"
				_settings_status.text = "Last save: %s (%s, %d s ago)" % [name, kind, ago]
	)


func _on_start_paused_toggled(on: bool) -> void:
	RealmSettings.start_paused = on
	RealmSettings.persist()


func _on_default_speed_selected(idx: int) -> void:
	if idx >= 0 and idx < RealmSettings.SPEED_OPTIONS.size():
		RealmSettings.default_speed = float(RealmSettings.SPEED_OPTIONS[idx])
		RealmSettings.persist()


func _on_default_overlay_selected(idx: int) -> void:
	RealmSettings.default_overlay = RealmSettings.overlay_id_from_index(idx)
	RealmSettings.persist()


func _on_save_slot_committed() -> void:
	if not is_instance_valid(_edit_save_slot):
		return
	var slot := _edit_save_slot.text.strip_edges()
	RealmSettings.default_save_slot = "" if slot.is_empty() or slot == "current" else slot
	RealmSettings.persist()


func _on_settings_pause_pressed() -> void:
	await _ensure_engine_ready()
	API.sim_control({"paused": not WorldState.sim_paused}, _on_settings_sim_control_done)


func _on_settings_speed_pressed(mult: float) -> void:
	await _ensure_engine_ready()
	API.sim_control({"speed": float(mult), "paused": false}, _on_settings_sim_control_done)


func _on_settings_sim_control_done(data: Dictionary) -> void:
	if not data.is_empty():
		WorldState.apply_sim_status(data)
	_sync_settings_prefs_ui()


func _on_world_sim_clock_updated() -> void:
	if _panel_settings.visible:
		_sync_settings_prefs_ui()


func _on_open_saves_folder_pressed() -> void:
	var dir := Transport.repo_saves_dir()
	if not DirAccess.dir_exists_absolute(dir):
		DirAccess.make_dir_recursive_absolute(dir)
	var err := OS.shell_open(dir)
	if err != OK:
		_dialog.dialog_text = "Could not open folder:\n%s" % dir
		_dialog.popup_centered()


func _on_open_log_pressed() -> void:
	var path := Transport.solo_log_path()
	if FileAccess.file_exists(path):
		var err := OS.shell_open(path)
		if err != OK:
			_dialog.dialog_text = "Could not open log:\n%s" % path
			_dialog.popup_centered()
	else:
		_dialog.dialog_text = "Log not found yet:\n%s\n\nStart Solo once to create it." % path
		_dialog.popup_centered()


func _on_restart_engine_pressed() -> void:
	_confirm_restart_engine.popup_centered()


func _on_restart_engine_confirmed() -> void:
	_footer.text = "Restarting engine…"
	await Transport.restart_solo_engine()
	_footer.text = "Solo engine restarted."
	_refresh_settings_diagnostics()


func _on_clear_saves_pressed() -> void:
	_confirm_clear_saves.popup_centered()


func _on_clear_all_saves_confirmed() -> void:
	await _ensure_engine_ready()
	_footer.text = "Clearing saves…"
	API.persistence_clear_all(
		func(data: Dictionary) -> void:
			if bool(data.get("ok", false)):
				var n := int(data.get("count", 0))
				_footer.text = "Removed %d save file(s)." % n
				if _panel_continue.visible:
					_refresh_save_list()
			else:
				_footer.text = ""
				var reason := str(data.get("reason", data))
				_dialog.dialog_text = "Could not clear saves: %s" % reason
				_dialog.popup_centered()
	)


func _on_solo_pressed() -> void:
	_show_panel("solo")


func _on_continue_pressed() -> void:
	_show_panel("continue")
	_continue_load_list()


func _continue_load_list() -> void:
	_continue_list_seq += 1
	var seq := _continue_list_seq
	_set_continue_loading_status("Starting solo engine…")
	var start_err := await _wait_for_solo_socket(seq, 45.0)
	if not is_instance_valid(self) or not _panel_continue.visible or seq != _continue_list_seq:
		return
	if not start_err.is_empty():
		var detail := Transport.last_engine_status.strip_edges()
		if not detail.is_empty():
			start_err = "%s\n\n%s" % [start_err, detail]
		_show_continue_list_message(
			"%s\n\nSettings → Restart solo engine, then open Continue again." % start_err,
			RealmColors.WARN,
		)
		return
	_set_continue_loading_status("Loading saves…")
	# Transport handshake already verified /version at connect.
	await _fetch_continue_slots_from_engine(seq)


func _on_transport_engine_ready() -> void:
	pass


func _on_transport_engine_error(msg: String) -> void:
	if not _panel_continue.visible:
		return
	_continue_list_seq += 1
	_show_continue_list_message(
		"Solo engine disconnected: %s\n\nSettings → Restart solo engine." % msg,
		RealmColors.WARN,
	)


func _set_continue_list_loading() -> void:
	_set_continue_loading_status("Loading saves…")


func _set_continue_loading_status(status: String) -> void:
	for c in _worlds_vbox.get_children():
		c.queue_free()
	for c in _saves_detail_vbox.get_children():
		c.queue_free()
	_world_row_buttons.clear()
	_grouped_slots.clear()
	_selected_world_key = ""
	if is_instance_valid(_saves_detail_heading):
		_saves_detail_heading.text = status
	var loading := Label.new()
	loading.text = status
	loading.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	loading.add_theme_color_override("font_color", RealmColors.DIM)
	_worlds_vbox.add_child(loading)


func _wait_for_solo_socket(seq: int, timeout_s: float) -> String:
	if seq != _continue_list_seq:
		return ""
	if Transport.mode != Transport.Mode.SOLO or Transport.is_engine_ready():
		return ""
	Transport.use_solo_mode()
	var tree := get_tree()
	var deadline_ms := Time.get_ticks_msec() + int(timeout_s * 1000.0)
	var error_msg := ""
	Transport.engine_error.connect(
		func(msg: String) -> void:
			error_msg = msg,
		CONNECT_ONE_SHOT,
	)
	while not Transport.is_engine_ready() and error_msg.is_empty():
		if seq != _continue_list_seq:
			return ""
		var status := Transport.last_engine_status.strip_edges()
		if not status.is_empty() and is_instance_valid(_saves_detail_heading):
			_saves_detail_heading.text = status
		if Time.get_ticks_msec() > deadline_ms:
			if status.is_empty():
				status = "no response from solo engine"
			return (
				"Solo engine did not start within %d s (%s).\nLog: %s"
				% [int(timeout_s), status, Transport.solo_log_path()]
			)
		await tree.process_frame
	if seq != _continue_list_seq:
		return ""
	if not error_msg.is_empty():
		return "Solo engine failed: %s\nLog: %s" % [error_msg, Transport.solo_log_path()]
	if not Transport.is_engine_ready():
		return (
			"Solo engine did not start (port %d).\nLog: %s"
			% [Transport.get_solo_port(), Transport.solo_log_path()]
		)
	return ""


func _ensure_engine_ready() -> void:
	if Transport.mode != Transport.Mode.SOLO or Transport.is_engine_ready():
		return
	await Transport.await_engine_ready(60.0)


func _solo_engine_verify_error() -> String:
	if Transport.mode != Transport.Mode.SOLO:
		return ""
	var start_err := await Transport.await_engine_ready(60.0)
	if not start_err.is_empty():
		return start_err
	var ver := Transport.get_handshake_version()
	if ver.is_empty():
		ver = await _await_api_get("/version", 8_000)
	return _stale_engine_message(ver)


func _await_version_with_retry(seq: int, total_timeout_ms: int) -> Dictionary:
	var tree := get_tree()
	var deadline_ms := Time.get_ticks_msec() + total_timeout_ms
	var attempt := 0
	while Time.get_ticks_msec() < deadline_ms:
		if seq != _continue_list_seq:
			return {"timed_out": true}
		attempt += 1
		var left_ms := deadline_ms - Time.get_ticks_msec()
		var slice_ms := mini(8000, maxi(2000, left_ms))
		var ver := await _await_api_get("/version", slice_ms)
		if not bool(ver.get("timed_out", false)) and bool(ver.get("ok", false)):
			return ver
		if not bool(ver.get("timed_out", false)) and not ver.is_empty():
			return ver
		if is_instance_valid(_saves_detail_heading):
			_saves_detail_heading.text = "Waiting for engine… (attempt %d)" % attempt
		if tree == null:
			return {"timed_out": true}
		await tree.create_timer(0.5).timeout
	return {"ok": false, "timed_out": true}


func _await_api_get(endpoint: String, timeout_ms: int = 15_000) -> Dictionary:
	var done := false
	var result: Dictionary = {}
	API.get_request(
		endpoint,
		func(data: Dictionary) -> void:
			result = data
			done = true
	)
	var tree := get_tree()
	var deadline_ms := Time.get_ticks_msec() + timeout_ms
	while not done:
		if tree == null:
			return {"ok": false, "reason": "scene exited", "timed_out": false}
		if Time.get_ticks_msec() > deadline_ms:
			return {"ok": false, "reason": "request timed out", "timed_out": true}
		await tree.process_frame
	return result


func _refresh_save_list() -> void:
	if Transport.mode == Transport.Mode.SOLO and not Transport.is_engine_ready():
		_continue_load_list()
		return
	_continue_list_seq += 1
	await _fetch_continue_slots_from_engine(_continue_list_seq)


func _fetch_continue_slots_from_engine(seq: int) -> void:
	if not is_instance_valid(_worlds_vbox):
		return
	for c in _worlds_vbox.get_children():
		c.queue_free()
	for c in _saves_detail_vbox.get_children():
		c.queue_free()
	_world_row_buttons.clear()
	_grouped_slots.clear()
	_selected_world_key = ""
	if is_instance_valid(_saves_detail_heading):
		_saves_detail_heading.text = "Loading saves…"
	var loading := Label.new()
	loading.text = "Loading saves…"
	loading.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	loading.add_theme_color_override("font_color", RealmColors.DIM)
	_worlds_vbox.add_child(loading)
	var list_cb := func(data: Dictionary) -> void:
		_on_persistence_list_loaded(data, seq)
	API.persistence_list(list_cb)
	var list_wait := await _await_persistence_list_done(list_cb, seq, 30_000)
	if seq != _continue_list_seq:
		return
	if list_wait == "timeout":
		_show_continue_list_message(
			"Loading saves timed out (engine on port %d).\n\n"
			% Transport.get_solo_port()
			+ "Settings → Restart solo engine, then try Continue again.\n\n"
			+ "Log: %s" % Transport.solo_log_path(),
			RealmColors.WARN,
		)
	elif list_wait == "cancelled":
		pass


func _await_persistence_list_done(_list_cb: Callable, seq: int, timeout_ms: int) -> String:
	_persistence_list_done[seq] = false
	var tree := get_tree()
	var deadline_ms := Time.get_ticks_msec() + timeout_ms
	while not bool(_persistence_list_done.get(seq, false)):
		if tree == null:
			return "exited"
		if Time.get_ticks_msec() > deadline_ms:
			_persistence_list_done.erase(seq)
			return "timeout"
		if seq != _continue_list_seq:
			_persistence_list_done.erase(seq)
			return "cancelled"
		await tree.process_frame
	_persistence_list_done.erase(seq)
	return "ok"


func _world_group_key(slot: Dictionary) -> String:
	var wid := str(slot.get("world_id", "")).strip_edges()
	if not wid.is_empty():
		return "id:%s" % wid
	# Pre–world_id saves: one row per file until re-saved with metadata.
	var path := str(slot.get("path", "")).strip_edges()
	if not path.is_empty():
		return "path:%s" % path
	var name := str(slot.get("name", "")).strip_edges()
	if not name.is_empty():
		return "name:%s" % name
	var wn := str(slot.get("world_name", "")).strip_edges()
	var scenario := str(slot.get("scenario_id", "")).strip_edges()
	var seed := int(slot.get("seed", 0))
	if not wn.is_empty():
		return "legacy:%s|%s|%d" % [wn, scenario, seed]
	return "legacy:%s|%d" % [scenario, seed]


func _world_title_from_slot(slot: Dictionary) -> String:
	var wn := str(slot.get("world_name", "")).strip_edges()
	if not wn.is_empty():
		return wn
	var file_name := str(slot.get("name", "")).strip_edges()
	if not file_name.is_empty() and file_name not in ["current", "autosave"]:
		return file_name.replace("_", " ")
	var scenario := str(slot.get("scenario_id", "")).strip_edges()
	if scenario.is_empty():
		if not file_name.is_empty():
			return file_name.replace("_", " ")
		scenario = "unknown"
	return "Unnamed · %s" % scenario.replace("_", " ").capitalize()


func _world_subtitle_from_slots(slots: Array) -> String:
	if slots.is_empty():
		return ""
	var first: Dictionary = slots[0] as Dictionary
	var scenario := str(first.get("scenario_id", "")).strip_edges()
	var seed := int(first.get("seed", 0))
	var wid := str(first.get("world_id", "")).strip_edges()
	var parts: PackedStringArray = PackedStringArray()
	if not scenario.is_empty():
		parts.append(scenario.replace("_", " ").capitalize())
	if seed != 0:
		parts.append("seed %d" % seed)
	if not wid.is_empty():
		parts.append(wid)
	parts.append("%d save%s" % [slots.size(), "" if slots.size() == 1 else "s"])
	return " · ".join(parts)


func _format_save_label(slot: Dictionary) -> String:
	var file_name := str(slot.get("name", ""))
	if file_name.is_empty():
		file_name = str(slot.get("path", "")).get_file().get_basename()
	var tick := int(slot.get("tick", -1))
	var tick_s := "?" if tick < 0 else str(tick)
	var saved_at := int(slot.get("saved_at", 0))
	var when := ""
	if saved_at > 0:
		var ago := maxi(0, int(Time.get_unix_time_from_system()) - saved_at)
		if ago < 120:
			when = "%d s ago" % ago
		elif ago < 7200:
			when = "%d min ago" % int(ago / 60)
		elif ago < 172800:
			when = "%d h ago" % int(ago / 3600)
		else:
			when = "%d d ago" % int(ago / 86400)
	if when.is_empty():
		return "%s  ·  tick %s" % [file_name, tick_s]
	return "%s  ·  tick %s  ·  %s" % [file_name, tick_s, when]


func _on_persistence_list_loaded(data: Dictionary, seq: int) -> void:
	_persistence_list_done[seq] = true
	if seq != _continue_list_seq or not is_instance_valid(_worlds_vbox):
		return
	if not _panel_continue.visible:
		return
	var slots: Array = []
	if bool(data.get("ok", false)):
		var raw: Variant = data.get("slots", [])
		if raw is Array:
			slots = raw as Array
	else:
		var reason := str(data.get("reason", "")).strip_edges()
		if reason.is_empty():
			reason = "solo engine on port %d did not answer" % Transport.get_solo_port()
		var st := Transport.last_engine_status.strip_edges()
		if not st.is_empty():
			reason = "%s\n%s" % [reason, st]
		_show_continue_list_message(
			"Could not list saves: %s.\n\nFolder: %s\n\nRestart solo engine in Settings."
			% [reason, Transport.repo_saves_dir()],
			RealmColors.WARN,
		)
		return
	if slots.is_empty():
		_show_continue_list_message(
			"No .sqlite files in:\n%s\n\nPlay a New world (autosaves on quit) or Save in-game."
			% Transport.repo_saves_dir(),
			RealmColors.DIM,
		)
		return
	_populate_continue_from_slots(slots)


func _show_continue_list_message(text: String, color: Color) -> void:
	for c in _worlds_vbox.get_children():
		c.queue_free()
	var msg := Label.new()
	msg.text = text
	msg.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	msg.add_theme_color_override("font_color", color)
	_worlds_vbox.add_child(msg)


func _populate_continue_from_slots(slots: Array) -> void:
	for c in _worlds_vbox.get_children():
		c.queue_free()
	_grouped_slots.clear()
	_world_row_buttons.clear()
	for row in slots:
		if not (row is Dictionary):
			continue
		var d: Dictionary = row as Dictionary
		var key := _world_group_key(d)
		if not _grouped_slots.has(key):
			_grouped_slots[key] = []
		(_grouped_slots[key] as Array).append(d)

	var world_keys: Array = _grouped_slots.keys()
	world_keys.sort_custom(
		func(a: String, b: String) -> bool:
			return _world_group_latest_mtime(a) > _world_group_latest_mtime(b)
	)

	for key in world_keys:
		var group: Array = _grouped_slots[key] as Array
		group.sort_custom(
			func(a: Dictionary, b: Dictionary) -> bool:
				return int(a.get("saved_at", 0)) > int(b.get("saved_at", 0))
		)
		var sample: Dictionary = group[0] as Dictionary
		var title := _world_title_from_slot(sample)
		var subtitle := _world_subtitle_from_slots(group)
		var btn := _menu_button("%s\n%s" % [title, subtitle], false)
		btn.pressed.connect(_on_world_selected.bind(key))
		_worlds_vbox.add_child(btn)
		_world_row_buttons[key] = btn

	if not world_keys.is_empty():
		_on_world_selected(world_keys[0] as String)


func _world_group_latest_mtime(world_key: String) -> int:
	var group: Variant = _grouped_slots.get(world_key, [])
	if not (group is Array):
		return 0
	var best := 0
	for row in group as Array:
		if row is Dictionary:
			best = maxi(best, int((row as Dictionary).get("saved_at", 0)))
			best = maxi(best, int((row as Dictionary).get("mtime", 0)))
	return best


func _on_world_selected(world_key: String) -> void:
	_selected_world_key = world_key
	_style_world_rows()
	var group: Variant = _grouped_slots.get(world_key, [])
	if not (group is Array) or (group as Array).is_empty():
		_populate_saves_for_world([])
		return
	var sample: Dictionary = (group as Array)[0] as Dictionary
	if is_instance_valid(_saves_detail_heading):
		_saves_detail_heading.text = _world_title_from_slot(sample)
	_populate_saves_for_world(group as Array)


func _style_world_rows() -> void:
	for key in _world_row_buttons.keys():
		var btn: Button = _world_row_buttons[key] as Button
		var selected := str(key) == _selected_world_key
		if selected:
			btn.add_theme_stylebox_override("normal", _world_row_stylebox_selected())
			btn.add_theme_color_override("font_color", RealmColors.ACCENT)
		else:
			btn.add_theme_stylebox_override("normal", RealmColors.style_btn_normal())
			btn.add_theme_color_override("font_color", RealmColors.TEXT)


func _world_row_stylebox_selected() -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.14, 0.13, 0.10)
	sb.set_border_width_all(2)
	sb.border_color = RealmColors.ACCENT
	sb.set_corner_radius_all(4)
	return sb


func _populate_saves_for_world(slots: Array) -> void:
	for c in _saves_detail_vbox.get_children():
		c.queue_free()
	if slots.is_empty():
		var empty := Label.new()
		empty.text = "No saves for this world."
		empty.add_theme_color_override("font_color", RealmColors.DIM)
		_saves_detail_vbox.add_child(empty)
		return
	for row in slots:
		if not (row is Dictionary):
			continue
		var d: Dictionary = row as Dictionary
		var path := str(d.get("path", ""))
		if path.is_empty():
			continue
		var btn := _menu_button(_format_save_label(d), false)
		btn.pressed.connect(_on_pick_save.bind(path))
		_saves_detail_vbox.add_child(btn)


func _on_pick_save(relative_path: String) -> void:
	var err := await _solo_engine_verify_error()
	if not err.is_empty():
		_dialog.dialog_text = err
		_dialog.popup_centered()
		return
	_footer.text = ""
	if is_instance_valid(_creation_screen):
		_creation_screen.queue_free()
		_creation_screen = null

	_creation_screen = CreationScreenScene.instantiate()
	add_child(_creation_screen)
	var display_name := relative_path.get_file().get_basename()
	_creation_screen.open_load(display_name)
	_creation_screen.creation_finished.connect(_on_creation_screen_done, CONNECT_ONE_SHOT)

	API.persistence_load_path(
		relative_path,
		func(data: Dictionary) -> void:
			if not is_instance_valid(self):
				return
			if bool(data.get("ok", false)):
				var loaded_tick := int(data.get("tick", -1))
				if loaded_tick < 0:
					push_warning("GameHome: load ok but no tick in response for %s" % relative_path)
				var wid := str(data.get("world_id", "")).strip_edges()
				if not wid.is_empty():
					WorldState.world_id = wid
				var cash := int(data.get("player_cash_cents", 0))
				if cash > 0:
					WorldState.player_cash_cents = cash
					WorldState.summary_updated.emit()
				var expected := int(data.get("player_starting_cash_cents", 0))
				if expected > 0:
					WorldState.player_starting_cash_cents = expected
				if is_instance_valid(_creation_screen):
					_creation_screen.mark_done()
				else:
					get_tree().call_deferred("change_scene_to_file", MAIN_SCENE)
			else:
				if is_instance_valid(_creation_screen):
					_creation_screen.visible = false
					_creation_screen.queue_free()
					_creation_screen = null
				var reason := str(data.get("reason", data))
				if reason.is_empty():
					reason = "unknown error (check engine/logs/realm_solo.log)"
				_dialog.dialog_text = (
					"Load failed: %s\n\nTry Settings → Restart solo engine, then Continue again."
					% reason
				)
				_dialog.popup_centered()
	)


var _creation_screen: Control = null


func _on_start_new_world() -> void:
	if is_instance_valid(_creation_screen):
		return
	var scenario: String = str(_scenario_opt.get_item_metadata(_scenario_opt.selected))
	var seed_val := int(_seed_spin.value)
	var wname: String = _name_edit.text.strip_edges() if is_instance_valid(_name_edit) else ""
	_footer.text = ""

	# Loading overlay first — engine verify and reset can take a minute on Genesis.
	_creation_screen = CreationScreenScene.instantiate()
	add_child(_creation_screen)
	_creation_screen.open(scenario)
	_creation_screen.creation_finished.connect(_on_creation_screen_done, CONNECT_ONE_SHOT)
	_creation_screen.engine_wait_timed_out.connect(
		func() -> void:
			_abort_creation_screen(
				"World creation timed out. Quit Godot, reopen, and try again "
				+ "(check engine/logs/realm_solo.log)."
			),
		CONNECT_ONE_SHOT,
	)

	var reset_timeout_s := 180.0 if scenario == "genesis" else 90.0
	_creation_screen.begin_waiting_for_engine(reset_timeout_s)

	var err := await _solo_engine_verify_error()
	if not err.is_empty():
		_abort_creation_screen(err)
		return

	# Hit /version FIRST so we fail fast if a stale realm_solo.py is on :9000.
	API.get_version(
		func(version_resp: Dictionary) -> void:
			var stale_msg := _stale_engine_message(version_resp)
			if not stale_msg.is_empty():
				_abort_creation_screen(stale_msg)
				return
			API.get_request(
				"/health",
				func(health_resp: Dictionary) -> void:
					if str(health_resp.get("status", "")) != "ok":
						_abort_creation_screen(
							"Solo engine not responding on port 9000. Quit Godot, reopen, try again."
						)
						return
					_send_dev_reset(seed_val, scenario, wname),
			),
	)


func _stale_engine_message(version_resp: Dictionary) -> String:
	var port := Transport.get_solo_port()
	if bool(version_resp.get("timed_out", false)):
		return (
			"Solo engine on port %d did not answer /version in time.\n\n"
			% port
			+ "Settings → Restart solo engine, or quit Godot, end any python.exe in Task Manager, then reopen."
		)
	if not bool(version_resp.get("ok", false)):
		var detail := str(version_resp.get("reason", "")).strip_edges()
		if detail.is_empty():
			detail = "no /version endpoint (stale listener?)"
		return (
			"Solo engine on port %d: %s.\n\n"
			% [port, detail]
			+ "An orphaned realm_solo.py from a previous run may be bound to this port. "
			+ "Quit Godot, end any python.exe processes in Task Manager, then reopen."
		)
	var engine_build := str(version_resp.get("build_id", "")).strip_edges()
	if not engine_build.is_empty() and engine_build != WorldState.REALM_BUILD_ID:
		return (
			"Solo engine build %s does not match this client (%s).\n\n"
			% [engine_build, WorldState.REALM_BUILD_ID]
			+ "Restart the solo engine (Settings) so it loads the current realm_solo.py."
		)
	var engine_starting := WorldState.variant_to_int(
		version_resp.get("player_starting_cash_cents", 0), 0
	)
	if engine_starting != WorldState.PLAYER_STARTING_CASH_CENTS:
		return (
			"Solo engine reports starting cash %s but this build expects %s.\n\n"
			% [
				WorldState.format_money(engine_starting),
				WorldState.format_money(WorldState.PLAYER_STARTING_CASH_CENTS),
			]
			+ "Stale realm_solo.py is bound to :%d. Quit Godot, end every python.exe in Task Manager, then reopen."
			% port
		)
	return ""


func _generate_world_id() -> String:
	var crypto := Crypto.new()
	return "w_%s" % crypto.generate_random_bytes(6).hex_encode()


func _sanitize_save_slot(raw: String) -> String:
	var s := raw.strip_edges()
	if s.is_empty():
		return ""
	var out := ""
	for i in s.length():
		var c := s[i]
		if (c >= "a" and c <= "z") or (c >= "A" and c <= "Z") or (c >= "0" and c <= "9") or c in "_-":
			out += c
		elif c == " ":
			out += "_"
	if out.is_empty():
		return ""
	return out.substr(0, 48)


func _snapshot_slot_for_new_world(wname: String, scenario: String, seed_val: int) -> String:
	var base := _sanitize_save_slot(wname)
	if base.is_empty():
		base = _sanitize_save_slot(scenario)
	if base.is_empty():
		base = "world"
	return "%s_%d" % [base, seed_val]


func _autosave_new_world_snapshot(data: Dictionary) -> void:
	var wid := str(data.get("world_id", _pending_new_world_id)).strip_edges()
	var slot := wid
	if slot.is_empty():
		var scenario := str(data.get("scenario_id", "")).strip_edges()
		var seed_val := int(data.get("seed", 0))
		slot = _snapshot_slot_for_new_world(_pending_new_world_name, scenario, seed_val)
	API.save_game(Callable(), slot)


func _send_dev_reset(seed_val: int, scenario: String, wname: String) -> void:
	_pending_new_world_name = wname.strip_edges()
	_pending_new_world_id = _generate_world_id()
	API.dev_reset(
		seed_val,
		scenario,
		func(data: Dictionary) -> void:
			if is_instance_valid(_creation_screen):
				_creation_screen.end_waiting_for_engine()
			if bool(data.get("ok", false)):
				var wid := str(data.get("world_id", _pending_new_world_id)).strip_edges()
				if not wid.is_empty():
					WorldState.world_id = wid
				var expected := WorldState.variant_to_int(
					data.get("player_starting_cash_cents", 0), 0
				)
				if expected > 0:
					WorldState.player_starting_cash_cents = expected
				var cash := WorldState.variant_to_int(data.get("player_cash_cents", 0), 0)
				# Older solo builds omit player_cash_cents; read the ledger before blocking.
				if cash <= 0:
					API.get_world_summary(
						WorldState.party_id,
						func(summary: Dictionary) -> void:
							var ledger_cash := WorldState.variant_to_int(summary.get("cash", 0), 0)
							_finish_dev_reset_cash_check(data, ledger_cash)
					)
					return
				_finish_dev_reset_cash_check(data, cash)
			else:
				_abort_creation_screen(
					"World creation failed: %s" % str(data.get("reason", data))
				),
		wname,
		_pending_new_world_id,
	)


func _finish_dev_reset_cash_check(data: Dictionary, cash_cents: int) -> void:
	var expected := WorldState.variant_to_int(data.get("player_starting_cash_cents", 0), 0)
	var mismatch := _starting_cash_mismatch_message(cash_cents, expected)
	if not mismatch.is_empty():
		_abort_creation_screen(mismatch)
		return
	if cash_cents > 0:
		WorldState.player_cash_cents = cash_cents
		WorldState.summary_updated.emit()
	_autosave_new_world_snapshot(data)
	if is_instance_valid(_creation_screen):
		_creation_screen.mark_done()
	else:
		get_tree().call_deferred("change_scene_to_file", MAIN_SCENE)


func _starting_cash_mismatch_message(actual_cents: int, expected_cents: int) -> String:
	var canon := expected_cents if expected_cents > 0 else WorldState.PLAYER_STARTING_CASH_CENTS
	if actual_cents == canon:
		return ""
	if actual_cents <= 0:
		return (
			"The solo engine did not report your starting cash after New world "
			+ "(often an outdated realm_solo.py still on port 9000).\n\n"
			+ "Quit Godot completely, end any Python processes, reopen, and try New world again."
		)
	return (
		"Solo engine started you at %s but this build expects %s.\n\n"
		% [WorldState.format_money(actual_cents), WorldState.format_money(canon)]
		+ "Quit Godot completely (close the window), reopen, and use New world — not Continue. "
		+ "Continue loads old saves that still have the previous balance."
	)


func _abort_creation_screen(message: String) -> void:
	if is_instance_valid(_creation_screen):
		_creation_screen.visible = false
		_creation_screen.queue_free()
		_creation_screen = null
	_dialog.dialog_text = message
	_dialog.popup_centered()


func _on_creation_screen_done() -> void:
	if is_instance_valid(_creation_screen):
		_creation_screen.queue_free()
		_creation_screen = null
	get_tree().call_deferred("change_scene_to_file", MAIN_SCENE)
