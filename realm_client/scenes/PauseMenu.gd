extends CanvasLayer
## In-game pause overlay — Escape toggles; pauses sim while open.

signal closed
signal quit_to_menu_requested
signal quit_game_requested

const GAME_HOME_SCENE := "res://scenes/GameHome.tscn"

var _sim_was_paused: bool = false
var _we_paused_sim: bool = false

var _dim: ColorRect
var _main_panel: PanelContainer
var _settings_panel: PanelContainer
var _world_name_edit: LineEdit
var _settings_status: Label


func _ready() -> void:
	layer = 64
	visible = false
	process_mode = Node.PROCESS_MODE_ALWAYS
	_build_ui()


func _build_ui() -> void:
	_dim = ColorRect.new()
	_dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	_dim.color = Color(0.02, 0.02, 0.04, 0.72)
	_dim.mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(_dim)

	var center := CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	_dim.add_child(center)

	_main_panel = _make_menu_panel()
	center.add_child(_main_panel)

	_settings_panel = _make_settings_panel()
	center.add_child(_settings_panel)
	_settings_panel.visible = false


func _make_menu_panel() -> PanelContainer:
	var pc := PanelContainer.new()
	pc.custom_minimum_size = Vector2(360, 0)
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.08, 0.08, 0.1, 0.98)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.45)
	sb.set_corner_radius_all(8)
	sb.set_content_margin_all(20)
	pc.add_theme_stylebox_override("panel", sb)

	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 12)
	pc.add_child(v)

	var title := Label.new()
	title.text = "Paused"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_color_override("font_color", RealmColors.ACCENT)
	if RealmFonts.font_display:
		title.add_theme_font_override("font", RealmFonts.font_display)
		title.add_theme_font_size_override("font_size", 28)
	v.add_child(title)

	var hint := Label.new()
	hint.text = "Press Esc to resume"
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	hint.add_theme_color_override("font_color", RealmColors.MUTED)
	if RealmFonts.font_body:
		hint.add_theme_font_override("font", RealmFonts.font_body)
		hint.add_theme_font_size_override("font_size", 14)
	v.add_child(hint)

	v.add_child(_menu_button("Resume", close_menu))
	v.add_child(_menu_button("Settings", _on_settings_pressed))
	v.add_child(_menu_button("Quit to menu", _on_quit_to_menu_pressed))
	v.add_child(_menu_button("Quit game", _on_quit_game_pressed))
	return pc


func _make_settings_panel() -> PanelContainer:
	var pc := PanelContainer.new()
	pc.custom_minimum_size = Vector2(400, 0)
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.08, 0.08, 0.1, 0.98)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.45)
	sb.set_corner_radius_all(8)
	sb.set_content_margin_all(20)
	pc.add_theme_stylebox_override("panel", sb)

	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 10)
	pc.add_child(v)

	var title := Label.new()
	title.text = "Settings"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_color_override("font_color", RealmColors.ACCENT)
	if RealmFonts.font_display:
		title.add_theme_font_override("font", RealmFonts.font_display)
		title.add_theme_font_size_override("font_size", 24)
	v.add_child(title)

	var name_lbl := Label.new()
	name_lbl.text = "World name"
	name_lbl.add_theme_color_override("font_color", RealmColors.TEXT)
	v.add_child(name_lbl)

	_world_name_edit = LineEdit.new()
	_world_name_edit.max_length = 64
	_world_name_edit.placeholder_text = "My realm"
	_world_name_edit.custom_minimum_size.y = 36
	_world_name_edit.add_theme_stylebox_override("normal", RealmColors.style_btn_normal())
	_world_name_edit.add_theme_color_override("font_color", RealmColors.TEXT)
	if RealmFonts.font_body:
		_world_name_edit.add_theme_font_override("font", RealmFonts.font_body)
		_world_name_edit.add_theme_font_size_override("font_size", 18)
	_world_name_edit.text_submitted.connect(func(_t: String) -> void: _save_world_name())
	v.add_child(_world_name_edit)

	_settings_status = Label.new()
	_settings_status.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_settings_status.add_theme_color_override("font_color", RealmColors.MUTED)
	if RealmFonts.font_body:
		_settings_status.add_theme_font_override("font", RealmFonts.font_body)
		_settings_status.add_theme_font_size_override("font_size", 13)
	v.add_child(_settings_status)

	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	row.alignment = BoxContainer.ALIGNMENT_CENTER
	var save_btn := _menu_button("Save", _save_world_name)
	save_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(save_btn)
	row.add_child(_menu_button("Back", _show_main))
	v.add_child(row)

	return pc


func _menu_button(text: String, cb: Callable) -> Button:
	var btn := Button.new()
	btn.text = text
	btn.custom_minimum_size.y = 44
	btn.focus_mode = Control.FOCUS_ALL
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.12, 0.12, 0.14)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.55)
	sb.set_corner_radius_all(4)
	btn.add_theme_stylebox_override("normal", sb)
	var sb_h := sb.duplicate() as StyleBoxFlat
	sb_h.border_color = Color(0.95, 0.82, 0.35)
	btn.add_theme_stylebox_override("hover", sb_h)
	btn.add_theme_color_override("font_color", Color(0.9, 0.88, 0.82))
	if RealmFonts.font_body:
		btn.add_theme_font_override("font", RealmFonts.font_body)
		btn.add_theme_font_size_override("font_size", 18)
	btn.pressed.connect(cb)
	return btn


func open_menu() -> void:
	_show_main()
	_refresh_world_name_field()
	_pause_sim_if_needed()
	visible = true


func close_menu() -> void:
	if not visible:
		return
	visible = false
	_restore_sim_pause()
	closed.emit()


func handle_escape() -> bool:
	if not visible:
		return false
	if _settings_panel.visible:
		_show_main()
		return true
	close_menu()
	return true


func _show_main() -> void:
	_settings_panel.visible = false
	_main_panel.visible = true
	_settings_status.text = ""


func _on_settings_pressed() -> void:
	_main_panel.visible = false
	_settings_panel.visible = true
	_refresh_world_name_field()
	_world_name_edit.grab_focus()


func _refresh_world_name_field() -> void:
	if not is_instance_valid(_world_name_edit):
		return
	_world_name_edit.text = WorldState.world_name


func _save_world_name() -> void:
	var name := _world_name_edit.text.strip_edges()
	_settings_status.text = "Saving…"
	_settings_status.modulate = RealmColors.MUTED
	API.set_world_name(
		name,
		func(res: Dictionary) -> void:
			if not is_instance_valid(self):
				return
			if bool(res.get("ok", false)):
				WorldState.world_name = str(res.get("world_name", name))
				WorldState.world_name_changed.emit()
				_settings_status.text = "Saved."
				_settings_status.modulate = RealmColors.OK
				API.get_world_summary(WorldState.party_id, func(s): WorldState.apply_summary(s))
			else:
				_settings_status.text = str(res.get("reason", "Could not save name"))
				_settings_status.modulate = Color(1.0, 0.35, 0.35),
	)


func _pause_sim_if_needed() -> void:
	_sim_was_paused = WorldState.sim_paused
	_we_paused_sim = false
	if not _sim_was_paused:
		_we_paused_sim = true
		API.sim_control({"paused": true}, Callable())


func _restore_sim_pause() -> void:
	if _we_paused_sim and not _sim_was_paused:
		API.sim_control({"paused": false}, Callable())
	_we_paused_sim = false


func _on_quit_to_menu_pressed() -> void:
	close_menu()
	_close_overlays_for_exit()
	quit_to_menu_requested.emit()
	get_tree().call_deferred("change_scene_to_file", GAME_HOME_SCENE)


func _on_quit_game_pressed() -> void:
	close_menu()
	quit_game_requested.emit()
	get_tree().quit()


func _close_overlays_for_exit() -> void:
	var main := get_tree().current_scene
	if main != null and main.has_method("_close_active_overlay"):
		main.call("_close_active_overlay")
