extends Control
## Realm entry: main menu → Solo (New / Continue) → in-game ``Main``.

const MAIN_SCENE := "res://scenes/Main.tscn"

const SCENARIOS: Array = [
	["frontier", "Frontier — default solo slice"],
	["genesis", "Genesis — large map (slow first boot)"],
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

var _scenario_opt: OptionButton
var _seed_spin: SpinBox
var _footer: Label
var _saves_scroll: ScrollContainer
var _saves_vbox: VBoxContainer

var _dialog: AcceptDialog


func _ready() -> void:
	_dialog = AcceptDialog.new()
	_dialog.title = "Realm"
	add_child(_dialog)
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
	for p in [_panel_root, _panel_solo, _panel_new, _panel_continue]:
		p.visible = false
		inner.add_child(p)


func _make_root_menu() -> VBoxContainer:
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 12)
	v.add_child(_menu_heading("Main menu"))

	var b_settings := _menu_button("Settings", true)
	b_settings.pressed.connect(_on_coming_soon_pressed.bind("Settings"))

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
	_scenario_opt.select(0)
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
	_seed_spin.value = 42
	_seed_spin.step = 1
	_seed_spin.custom_minimum_size.x = 200
	_style_primary_button(_seed_spin)
	row_seed.add_child(lseed)
	row_seed.add_child(_seed_spin)
	v.add_child(row_seed)

	var hint := Label.new()
	hint.text = "Uses the dev API: POST /dev/reset. Start the engine on port 8000 first."
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
	hint2.text = "Lists *.sqlite under the repo saves/ folder (GET /persistence/list)."
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


func _on_coming_soon_pressed(feature: String) -> void:
	_dialog.dialog_text = "%s — coming soon." % feature
	_dialog.popup_centered()


func _on_solo_pressed() -> void:
	_show_panel("solo")


func _on_continue_pressed() -> void:
	_show_panel("continue")
	_refresh_save_list()


func _refresh_save_list() -> void:
	for c in _saves_vbox.get_children():
		c.queue_free()
	API.persistence_list(
		func(data: Dictionary) -> void:
			if not bool(data.get("ok", false)):
				var err := Label.new()
				err.text = "Could not list saves (is the API running on port 8000?)."
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
				var nm: String = str(d.get("name", path))
				var btn := _menu_button(nm + "  →  " + path, false)
				btn.pressed.connect(_on_pick_save.bind(path))
				_saves_vbox.add_child(btn)
	)


func _on_pick_save(relative_path: String) -> void:
	_footer.text = "Loading…"
	API.persistence_load_path(
		relative_path,
		func(data: Dictionary) -> void:
			_footer.text = ""
			if bool(data.get("ok", false)):
				get_tree().call_deferred("change_scene_to_file", MAIN_SCENE)
			else:
				_dialog.dialog_text = "Load failed: %s" % str(data)
				_dialog.popup_centered()
	)


func _on_start_new_world() -> void:
	var scenario: String = str(_scenario_opt.get_item_metadata(_scenario_opt.selected))
	var seed := int(_seed_spin.value)
	_footer.text = "Creating world on server… (uvicorn: look for Realm: POST /dev/reset received — genesis can take minutes before the access-log line appears.)"
	API.dev_reset(
		seed,
		scenario,
		func(data: Dictionary) -> void:
			if bool(data.get("ok", false)):
				_footer.text = ""
				get_tree().call_deferred("change_scene_to_file", MAIN_SCENE)
			else:
				_footer.text = ""
				_dialog.dialog_text = "Reset failed: %s" % str(data)
				_dialog.popup_centered()
	)
