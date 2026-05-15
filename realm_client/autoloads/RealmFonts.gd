extends Node
## Web fonts: VT323 (body) + Press Start 2P (micro labels).

var font_body: FontFile
var font_display: FontFile


func _ready() -> void:
	font_body = load("res://assets/fonts/VT323-Regular.ttf") as FontFile
	font_display = load("res://assets/fonts/PressStart2P-Regular.ttf") as FontFile
	if font_body == null:
		push_warning("RealmFonts: VT323-Regular.ttf missing")
	if font_display == null:
		push_warning("RealmFonts: PressStart2P-Regular.ttf missing")


func apply_to_control(root: Control) -> void:
	if root == null:
		return
	for c in root.find_children("*", "", true, false):
		if c is Control:
			_style_control(c as Control)


func _style_control(c: Control) -> void:
	if font_body == null:
		return
	if c is Label:
		var lbl := c as Label
		if lbl.name.contains("Kicker") or lbl.name.contains("Brand") or lbl.name.contains("Group"):
			if font_display:
				lbl.add_theme_font_override("font", font_display)
				lbl.add_theme_font_size_override("font_size", 8)
		else:
			lbl.add_theme_font_override("font", font_body)
	elif c is Button:
		(c as Button).add_theme_font_override("font", font_body)
	elif c is RichTextLabel:
		(c as RichTextLabel).add_theme_font_override("normal_font", font_body)
