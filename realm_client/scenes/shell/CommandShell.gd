extends CanvasLayer
## Web-style top strip + grouped nav chips (``realm-top-strip`` / ``realm-top-nav``).

signal nav_pressed(panel_name: String)

const TOP_STRIP_H := 52.0
const NAV_ROW_H := 44.0
const SIDEBAR_W := 400.0

@onready var strip: PanelContainer = %TopStrip
@onready var brand_title: Label = %BrandTitle
@onready var brand_sub: Label = %BrandSub
@onready var tick_pill: Label = %TickPill
@onready var seed_pill: Label = %SeedPill
@onready var cash_pill: Label = %CashPill
@onready var nav_row: HBoxContainer = %NavRow
@onready var map_footnote: Label = %MapFootnote

var _active_nav: String = "territory"
var _nav_buttons: Dictionary = {}


func _ready() -> void:
	layer = 15
	_apply_chrome()
	_build_nav()
	WorldState.summary_updated.connect(_refresh_stats)
	WorldState.world_updated.connect(_on_world_changed)
	_refresh_stats()
	_refresh_seed()


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
		["caravans", "Caravans"],
	])
	_add_nav_group("REALM", [
		["chronicle", "Chronicle"],
		["contracts", "Pacts & hires"],
		["finance", "Finance"],
		["labor", "Labor"],
		["lab", "Lab"],
		["menu", "Menu"],
	])
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
	tick_pill.text = "World tick %d" % WorldState.current_tick
	cash_pill.text = "Cash %s" % WorldState.format_money(WorldState.player_cash_cents)


func _on_world_changed() -> void:
	_refresh_stats()
	_refresh_seed()


func _refresh_seed() -> void:
	seed_pill.text = "Seed %d" % WorldState.world_seed


func flash_tick() -> void:
	tick_pill.modulate = RealmColors.OK
	var t := get_tree().create_timer(0.2)
	t.timeout.connect(func(): tick_pill.modulate = Color.WHITE)
