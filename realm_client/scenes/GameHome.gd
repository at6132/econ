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
var _saves_scroll: ScrollContainer
var _saves_vbox: VBoxContainer

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
		"Stops and respawns the Python process on port 9000.\n\n"
		+ "Use this after engine code changes or if Continue/New world acts stale."
	)
	_confirm_restart_engine.ok_button_text = "Restart"
	_confirm_restart_engine.confirmed.connect(_on_restart_engine_confirmed)
	add_child(_confirm_restart_engine)
	WorldState.sim_clock_updated.connect(_on_world_sim_clock_updated)
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

	var b_multi := _menu_button("Multiplayer", true)
	b_multi.pressed.connect(_on_coming_soon_pressed.bind("Multiplayer"))

	v.add_child(b_settings)
	v.add_child(b_solo)
	v.add_child(b_multi)
	return v


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
	_edit_save_slot.placeholder_text = "current"
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

	_saves_scroll = ScrollContainer.new()
	_saves_scroll.custom_minimum_size = Vector2(0, 280)
	_saves_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_saves_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_saves_vbox = VBoxContainer.new()
	_saves_vbox.add_theme_constant_override("separation", 8)
	_saves_vbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_saves_scroll.add_child(_saves_vbox)
	v.add_child(_saves_scroll)

	var b_back := _menu_button("Back", false)
	b_back.pressed.connect(func(): _show_panel("solo"))
	v.add_child(b_back)

	var hint2 := Label.new()
	hint2.text = "Lists *.sqlite under the repo saves/ folder."
	hint2.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hint2.add_theme_color_override("font_color", RealmColors.MUTED)
	if RealmFonts.font_body:
		hint2.add_theme_font_override("font", RealmFonts.font_body)
		hint2.add_theme_font_size_override("font_size", 15)
	v.add_child(hint2)
	return v


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
	var port := Transport.SOLO_PORT
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
			var line := "Build: %s" % build
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
	RealmSettings.default_save_slot = "current" if slot.is_empty() else slot
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
	await _ensure_engine_ready()
	_refresh_save_list()


func _ensure_engine_ready() -> void:
	if Transport.mode == Transport.Mode.SOLO and not Transport.is_engine_ready():
		await Transport.engine_ready


func _refresh_save_list() -> void:
	for c in _saves_vbox.get_children():
		c.queue_free()
	API.persistence_list(
		func(data: Dictionary) -> void:
			if not bool(data.get("ok", false)):
				var err := Label.new()
				var reason := str(data.get("reason", "")).strip_edges()
				if reason.is_empty():
					err.text = "Could not list saves (solo engine on port 9000 not reachable)."
				else:
					err.text = "Could not list saves: %s" % reason
				err.add_theme_color_override("font_color", RealmColors.WARN)
				_saves_vbox.add_child(err)
				return
			var slots: Variant = data.get("slots", [])
			if not (slots is Array) or (slots as Array).is_empty():
				var empty := Label.new()
				empty.text = "No saves yet. Use in-game save to write saves/*.sqlite."
				empty.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
				empty.add_theme_color_override("font_color", RealmColors.DIM)
				_saves_vbox.add_child(empty)
				return
			for row in slots as Array:
				if not (row is Dictionary):
					continue
				var d: Dictionary = row
				var path: String = str(d.get("path", ""))
				var wname: String = str(d.get("world_name", ""))
				var scenario: String = str(d.get("scenario_id", ""))
				var tick: int = int(d.get("tick", 0))
				var label: String
				if not wname.is_empty():
					label = wname
					if not scenario.is_empty():
						label += "  ·  %s" % scenario
					label += "  ·  tick %d" % tick
				else:
					label = "%s  ·  %s  ·  tick %d" % [d.get("name", path), scenario, tick]
				var btn := _menu_button(label, false)
				btn.pressed.connect(_on_pick_save.bind(path))
				_saves_vbox.add_child(btn)
	)


func _on_pick_save(relative_path: String) -> void:
	await _ensure_engine_ready()
	_footer.text = ""

	# Show loading screen overlay
	_creation_screen = CreationScreenScene.instantiate()
	add_child(_creation_screen)
	var display_name := relative_path.get_file().get_basename()
	_creation_screen.open_load(display_name)
	_creation_screen.creation_finished.connect(_on_creation_screen_done)

	API.persistence_load_path(
		relative_path,
		func(data: Dictionary) -> void:
			if bool(data.get("ok", false)):
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
				_dialog.dialog_text = "Load failed: %s" % str(data)
				_dialog.popup_centered()
	)


var _creation_screen: Control = null


func _on_start_new_world() -> void:
	await _ensure_engine_ready()
	var scenario: String = str(_scenario_opt.get_item_metadata(_scenario_opt.selected))
	var seed_val := int(_seed_spin.value)
	var wname: String = _name_edit.text.strip_edges() if is_instance_valid(_name_edit) else ""
	_footer.text = ""

	# Show creation screen overlay
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
	if not bool(version_resp.get("ok", false)):
		return (
			"Solo engine on port 9000 is too old (no /version endpoint).\n\n"
			+ "An orphaned realm_solo.py from a previous run is winning the bind. "
			+ "Quit Godot, end any python.exe processes in Task Manager, then reopen."
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
			+ "Stale realm_solo.py is bound to :9000. Quit Godot, end every python.exe in Task Manager, then reopen."
		)
	return ""


func _send_dev_reset(seed_val: int, scenario: String, wname: String) -> void:
	API.dev_reset(
		seed_val,
		scenario,
		func(data: Dictionary) -> void:
			if is_instance_valid(_creation_screen):
				_creation_screen.end_waiting_for_engine()
			if bool(data.get("ok", false)):
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
