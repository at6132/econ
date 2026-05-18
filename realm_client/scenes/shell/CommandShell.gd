extends CanvasLayer
## Web-style top strip + grouped nav chips (``realm-top-strip`` / ``realm-top-nav``).

signal nav_pressed(panel_name: String)

const TOP_STRIP_H := 52.0
const NAV_ROW_H := 44.0
const SIDEBAR_W := 400.0
const SAVE_SLOT := "current"
const STATUS_POLL_SECONDS := 5.0

@onready var strip: PanelContainer = %TopStrip
@onready var brand_title: Label = %BrandTitle
@onready var brand_sub: Label = %BrandSub
@onready var tick_pill: Label = %TickPill
@onready var seed_pill: Label = %SeedPill
@onready var cash_pill: Label = %CashPill
@onready var save_button: Button = %SaveButton
@onready var save_status: Label = %SaveStatus
@onready var nav_row: HBoxContainer = %NavRow
@onready var map_footnote: Label = %MapFootnote

var _active_nav: String = "territory"
var _nav_buttons: Dictionary = {}
var _last_save_at: int = 0
var _saving: bool = false
var _status_timer: Timer
var _pause_button: Button = null
var _speed_buttons: Array[Button] = []  # one per non-zero preset (1×, 2×, 4×)


func _ready() -> void:
	layer = 15
	_apply_chrome()
	_build_nav()
	_build_sim_controls()
	WorldState.summary_updated.connect(_refresh_stats)
	WorldState.world_updated.connect(_on_world_changed)
	WorldState.sim_clock_updated.connect(_refresh_sim_controls)
	_refresh_stats()
	_refresh_seed()
	_refresh_sim_controls()
	save_button.pressed.connect(_on_save_pressed)
	_status_timer = Timer.new()
	_status_timer.wait_time = STATUS_POLL_SECONDS
	_status_timer.autostart = true
	_status_timer.timeout.connect(_refresh_save_status)
	add_child(_status_timer)
	_begin_save_status_poll()
	set_process(true)


func _begin_save_status_poll() -> void:
	if Transport.mode == Transport.Mode.SOLO and not Transport.is_engine_ready():
		Transport.engine_ready.connect(_refresh_save_status, CONNECT_ONE_SHOT)
	else:
		_refresh_save_status()


## Pause / 1× / 2× / 4× chips in the top strip. All call ``POST /sim/control``
## and rely on the engine's ``kind: "sim_status"`` push to update local state.
func _build_sim_controls() -> void:
	var pills_parent: Node = tick_pill.get_parent()
	if pills_parent == null:
		return

	_pause_button = Button.new()
	_pause_button.text = "Pause"
	_pause_button.toggle_mode = false
	_pause_button.focus_mode = Control.FOCUS_NONE
	_style_pill_btn(_pause_button)
	_pause_button.pressed.connect(_on_pause_pressed)
	pills_parent.add_child(_pause_button)

	for mult in [1.0, 2.0, 4.0]:
		var b := Button.new()
		b.text = "%dx" % int(mult)
		b.toggle_mode = false
		b.focus_mode = Control.FOCUS_NONE
		_style_pill_btn(b)
		b.pressed.connect(_on_speed_pressed.bind(mult))
		pills_parent.add_child(b)
		_speed_buttons.append(b)


func _style_pill_btn(b: Button) -> void:
	b.add_theme_stylebox_override("normal", RealmColors.style_chip(false))
	b.add_theme_stylebox_override("hover", RealmColors.style_chip(false))
	b.add_theme_stylebox_override("pressed", RealmColors.style_chip(true))
	b.add_theme_color_override("font_color", RealmColors.DIM)
	b.add_theme_color_override("font_hover_color", RealmColors.ACCENT)
	if RealmFonts.font_body:
		b.add_theme_font_override("font", RealmFonts.font_body)
		b.add_theme_font_size_override("font_size", 16)


func _on_pause_pressed() -> void:
	API.sim_control({"paused": not WorldState.sim_paused}, Callable())


func _on_speed_pressed(mult: float) -> void:
	# Speed click always resumes (engine pause flag is cleared on non-zero speed).
	API.sim_control({"speed": float(mult), "paused": false}, Callable())


func _refresh_sim_controls() -> void:
	if _pause_button != null:
		_pause_button.text = "Resume" if WorldState.sim_paused else "Pause"
		var pause_active := WorldState.sim_paused
		_pause_button.add_theme_stylebox_override("normal", RealmColors.style_chip(pause_active))
		_pause_button.add_theme_color_override(
			"font_color",
			RealmColors.ACCENT if pause_active else RealmColors.DIM,
		)
	# Highlight whichever speed matches the engine's effective rate.
	for i in range(_speed_buttons.size()):
		var mult: float = [1.0, 2.0, 4.0][i]
		var active := not WorldState.sim_paused and is_equal_approx(WorldState.sim_speed, mult)
		_speed_buttons[i].add_theme_stylebox_override("normal", RealmColors.style_chip(active))
		_speed_buttons[i].add_theme_color_override(
			"font_color",
			RealmColors.ACCENT if active else RealmColors.DIM,
		)


func shell_top_height() -> float:
	return TOP_STRIP_H + NAV_ROW_H


func sidebar_width() -> float:
	return SIDEBAR_W


func _apply_chrome() -> void:
	var strip_sb := StyleBoxFlat.new()
	strip_sb.bg_color = RealmColors.STRIP_TOP
	strip_sb.border_width_bottom = 3
	strip_sb.border_color = RealmColors.BLACK
	strip.add_theme_stylebox_override("panel", strip_sb)
	brand_title.add_theme_color_override("font_color", RealmColors.ACCENT)
	brand_sub.add_theme_color_override("font_color", RealmColors.MUTED)
	for pill in [tick_pill, seed_pill, cash_pill]:
		_style_pill(pill)
	map_footnote.mouse_filter = Control.MOUSE_FILTER_IGNORE
	map_footnote.add_theme_color_override("font_color", RealmColors.MUTED)
	save_button.add_theme_stylebox_override("normal", RealmColors.style_btn_normal())
	save_button.add_theme_stylebox_override("hover", RealmColors.style_btn_hover())
	save_button.add_theme_color_override("font_color", RealmColors.ACCENT)
	save_button.add_theme_color_override("font_hover_color", RealmColors.TEXT)
	save_status.add_theme_color_override("font_color", RealmColors.MUTED)
	if RealmFonts.font_body:
		save_button.add_theme_font_override("font", RealmFonts.font_body)
		save_button.add_theme_font_size_override("font_size", 17)
		save_status.add_theme_font_override("font", RealmFonts.font_body)
		save_status.add_theme_font_size_override("font_size", 13)
	if RealmFonts.font_display:
		brand_title.add_theme_font_override("font", RealmFonts.font_display)
		brand_title.add_theme_font_size_override("font_size", 11)
	if RealmFonts.font_body:
		brand_sub.add_theme_font_override("font", RealmFonts.font_body)
		brand_sub.add_theme_font_size_override("font_size", 16)
		map_footnote.add_theme_font_override("font", RealmFonts.font_body)
		map_footnote.add_theme_font_size_override("font_size", 14)


func _style_pill(lbl: Label) -> void:
	lbl.add_theme_color_override("font_color", RealmColors.MAGIC)
	if RealmFonts.font_body:
		lbl.add_theme_font_override("font", RealmFonts.font_body)
		lbl.add_theme_font_size_override("font_size", 18)


func _build_nav() -> void:
	_add_nav_group("FIELD OPS", [
		["territory", "Territory & works"],
	])
	_add_nav_group("COMMERCE", [
		["market", "Bazaar & tape"],
		["caravans", "Shipping"],
		["economics", "Economics"],
		["tenders", "Tenders"],
	])
	_add_nav_group("REALM", [
		["chronicle", "Chronicle"],
		["contracts", "Pacts"],
		["finance", "Finance"],
		["labor", "Labor"],
		["business", "Business"],
		["lab", "Science"],
		["menu", "Profile"],
	])
	WorldState.summary_updated.connect(_refresh_nav_badges)
	WorldState.feed_updated.connect(_refresh_nav_badges)
	_set_active_nav("territory")


func _add_nav_group(group_title: String, items: Array) -> void:
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 4)
	var kicker := Label.new()
	kicker.name = "GroupKicker"
	kicker.text = group_title
	kicker.add_theme_color_override("font_color", RealmColors.MUTED)
	if RealmFonts.font_display:
		kicker.add_theme_font_override("font", RealmFonts.font_display)
		kicker.add_theme_font_size_override("font_size", 7)
	col.add_child(kicker)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	for item in items:
		var pid: String = str(item[0])
		var label: String = str(item[1])
		var btn := Button.new()
		btn.text = label
		btn.toggle_mode = true
		_style_nav_btn(btn, false)
		btn.pressed.connect(_on_nav_btn_pressed.bind(pid, btn))
		row.add_child(btn)
		_nav_buttons[pid] = btn
	col.add_child(row)
	nav_row.add_child(col)


func _style_nav_btn(btn: Button, active: bool) -> void:
	btn.add_theme_stylebox_override("normal", RealmColors.style_chip(active))
	btn.add_theme_stylebox_override("pressed", RealmColors.style_chip(true))
	btn.add_theme_stylebox_override("hover", RealmColors.style_chip(active))
	btn.add_theme_color_override("font_color", RealmColors.ACCENT if active else RealmColors.DIM)
	btn.add_theme_color_override("font_hover_color", RealmColors.ACCENT)
	if RealmFonts.font_body:
		btn.add_theme_font_override("font", RealmFonts.font_body)
		btn.add_theme_font_size_override("font_size", 17)


func _on_nav_btn_pressed(panel_id: String, btn: Button) -> void:
	_set_active_nav(panel_id)
	nav_pressed.emit(panel_id)


func _set_active_nav(panel_id: String) -> void:
	_active_nav = panel_id
	for key in _nav_buttons.keys():
		var pid: String = str(key)
		var b: Button = _nav_buttons[key] as Button
		var on: bool = pid == panel_id
		b.button_pressed = on
		_style_nav_btn(b, on)


func _refresh_stats() -> void:
	var clock_label: String
	if WorldState.sim_paused:
		clock_label = "PAUSED · Day %d · tick %d" % [WorldState.game_day, WorldState.current_tick]
	else:
		clock_label = "Day %d · %s · tick %d" % [
			WorldState.game_day,
			WorldState.game_season,
			WorldState.current_tick,
		]
	tick_pill.text = clock_label
	cash_pill.text = "Cash %s" % WorldState.format_money(WorldState.player_cash_cents)
	_refresh_nav_badges()


func _refresh_nav_badges() -> void:
	var chron_btn: Button = _nav_buttons.get("chronicle", null) as Button
	if chron_btn == null:
		return
	var unread: int = WorldState.unread_feed_count + WorldState.unread_npc_messages
	var base: String = "Chronicle"
	if unread > 0:
		chron_btn.text = "%s (%d)" % [base, unread]
	else:
		chron_btn.text = base


func _on_world_changed() -> void:
	_refresh_stats()
	_refresh_seed()


func _refresh_seed() -> void:
	seed_pill.text = "Seed %d" % WorldState.world_seed


func flash_tick() -> void:
	tick_pill.modulate = RealmColors.OK
	var t := get_tree().create_timer(0.2)
	t.timeout.connect(func(): tick_pill.modulate = Color.WHITE)


func _on_save_pressed() -> void:
	_run_save()


func _run_save() -> void:
	if _saving:
		return
	_saving = true
	save_button.disabled = true
	save_status.text = "saving…"
	save_status.add_theme_color_override("font_color", RealmColors.MAGIC)
	if Transport.mode == Transport.Mode.SOLO and not Transport.is_engine_ready():
		save_status.text = "waiting for engine…"
		await Transport.engine_ready
	var on_saved := func(data: Dictionary) -> void:
		_saving = false
		save_button.disabled = false
		if bool(data.get("ok", false)):
			_last_save_at = int(Time.get_unix_time_from_system())
			save_button.modulate = RealmColors.OK
			var t := get_tree().create_timer(0.25)
			t.timeout.connect(func(): save_button.modulate = Color.WHITE)
			_refresh_save_label()
		else:
			save_status.add_theme_color_override("font_color", RealmColors.DANGER)
			save_status.text = _save_failure_message(data)
	API.save_game(on_saved, SAVE_SLOT)


func _save_failure_message(data: Dictionary) -> String:
	if data.is_empty():
		if Transport.mode == Transport.Mode.SOLO:
			return "save failed — solo engine not reachable (port 9000)"
		return "save failed — server not reachable"
	var reason := str(data.get("reason", "")).strip_edges()
	if reason.is_empty():
		return "save failed"
	return "save failed: %s" % reason


func _refresh_save_status() -> void:
	API.persistence_status(
		func(data: Dictionary) -> void:
			if not (data is Dictionary) or not bool(data.get("ok", false)):
				return
			var ts := int(data.get("last_save_at", 0))
			if ts > 0:
				_last_save_at = ts
			_refresh_save_label()
	)


func _refresh_save_label() -> void:
	if _last_save_at <= 0:
		save_status.text = "no save yet"
		save_status.add_theme_color_override("font_color", RealmColors.MUTED)
		return
	var now := int(Time.get_unix_time_from_system())
	var dt: int = maxi(0, now - _last_save_at)
	save_status.add_theme_color_override("font_color", RealmColors.DIM)
	save_status.text = "saved %s ago" % _human_seconds(dt)


func _process(_dt: float) -> void:
	if _last_save_at > 0 and not _saving:
		_refresh_save_label()


func _human_seconds(s: int) -> String:
	if s < 60:
		return "%ds" % s
	if s < 3600:
		return "%dm" % int(s / 60)
	return "%dh%dm" % [int(s / 3600), int((s % 3600) / 60)]
