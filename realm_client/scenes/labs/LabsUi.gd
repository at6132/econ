class_name LabsUi
extends RefCounted
## Scientific / analytical chrome for Realm Labs (palette per doc 20).

const CATEGORIES: PackedStringArray = [
	"All", "Strategy", "Markets", "Social", "Production", "Stress", "Tutorial",
]


static func style_data_panel() -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.06, 0.05, 0.10, 0.95)
	sb.border_width_left = 2
	sb.border_width_top = 2
	sb.border_width_right = 2
	sb.border_width_bottom = 2
	sb.border_color = RealmColors.BORDER
	sb.set_corner_radius_all(2)
	return sb


static func style_grid_header() -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = RealmColors.PILL_WELL
	sb.border_width_bottom = 2
	sb.border_color = RealmColors.MAGIC
	return sb


static func style_row(alt: bool) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.10, 0.08, 0.14) if alt else Color(0.08, 0.06, 0.12)
	sb.border_width_bottom = 1
	sb.border_color = Color(RealmColors.BORDER, 0.35)
	return sb


static func kicker_label(text: String) -> Label:
	var l := Label.new()
	l.text = text.to_upper()
	l.add_theme_color_override("font_color", RealmColors.MAGIC)
	if RealmFonts.font_display:
		l.add_theme_font_override("font", RealmFonts.font_display)
	l.add_theme_font_size_override("font_size", 10)
	return l


static func title_label(text: String, size: int = 28) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_color_override("font_color", RealmColors.ACCENT)
	if RealmFonts.font_display:
		l.add_theme_font_override("font", RealmFonts.font_display)
	l.add_theme_font_size_override("font_size", size)
	return l


static func body_label(text: String, color: Color = RealmColors.DIM) -> Label:
	var l := Label.new()
	l.text = text
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.add_theme_color_override("font_color", color)
	if RealmFonts.font_body:
		l.add_theme_font_override("font", RealmFonts.font_body)
	l.add_theme_font_size_override("font_size", 18)
	return l


static func metric_cell(title: String, value: String) -> VBoxContainer:
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 2)
	var t := kicker_label(title)
	var val := Label.new()
	val.text = value
	val.add_theme_color_override("font_color", RealmColors.MAGIC)
	if RealmFonts.font_body:
		val.add_theme_font_override("font", RealmFonts.font_body)
	val.add_theme_font_size_override("font_size", 20)
	v.add_child(t)
	v.add_child(val)
	return v


static func header_cell(text: String, min_w: float = 0.0) -> Label:
	var l := Label.new()
	l.text = text.to_upper()
	l.add_theme_color_override("font_color", RealmColors.MUTED)
	if RealmFonts.font_display:
		l.add_theme_font_override("font", RealmFonts.font_display)
	l.add_theme_font_size_override("font_size", 9)
	if min_w > 0.0:
		l.custom_minimum_size.x = min_w
	return l


static func data_cell(text: String, accent: bool = false) -> Label:
	var l := Label.new()
	l.text = text
	l.clip_text = true
	l.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	l.add_theme_color_override("font_color", RealmColors.MAGIC if accent else RealmColors.TEXT)
	if RealmFonts.font_body:
		l.add_theme_font_override("font", RealmFonts.font_body)
	l.add_theme_font_size_override("font_size", 17)
	return l


static func style_menu_button(btn: Button, accent: bool = false) -> void:
	btn.custom_minimum_size.y = 44
	btn.alignment = HORIZONTAL_ALIGNMENT_LEFT
	var sb := RealmColors.style_btn_normal()
	if accent:
		sb.bg_color = RealmColors.CHIP_ACTIVE
		btn.add_theme_color_override("font_color", RealmColors.ACCENT)
	else:
		btn.add_theme_color_override("font_color", RealmColors.TEXT)
	btn.add_theme_stylebox_override("normal", sb)
	btn.add_theme_stylebox_override("hover", RealmColors.style_btn_hover())
	btn.add_theme_stylebox_override("pressed", sb)
	if RealmFonts.font_body:
		btn.add_theme_font_override("font", RealmFonts.font_body)
		btn.add_theme_font_size_override("font_size", 20)


static func style_chip(btn: Button, active: bool) -> void:
	btn.toggle_mode = true
	btn.button_pressed = active
	btn.add_theme_stylebox_override("normal", RealmColors.style_chip(active))
	btn.add_theme_stylebox_override("hover", RealmColors.style_chip(active))
	btn.add_theme_color_override("font_color", RealmColors.ACCENT if active else RealmColors.MUTED)
	if RealmFonts.font_body:
		btn.add_theme_font_override("font", RealmFonts.font_body)
		btn.add_theme_font_size_override("font_size", 16)
