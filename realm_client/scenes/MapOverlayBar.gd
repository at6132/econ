extends HBoxContainer
## Bottom-left map overlay mode toggles (radio).

signal overlay_changed(mode: String)

const BUTTONS: Array = [
	["none", "🗺 Map"],
	["ownership", "👤 Own"],
	["power", "⚡ Pwr"],
	["mineral", "💎 Mine"],
	["routes", "🚢 Ship"],
	["roads", "🛣 Road"],
	["population", "👥 Pop"],
	["advantage", "⚙ Adv"],
]

var _active: String = "none"
var _buttons: Dictionary = {}


func _ready() -> void:
	add_theme_constant_override("separation", 4)
	for item in BUTTONS:
		var mode: String = str(item[0])
		var label: String = str(item[1])
		var btn := Button.new()
		btn.text = label
		btn.toggle_mode = true
		btn.button_pressed = mode == "none"
		PanelUI.style_btn(btn, mode == "none")
		btn.pressed.connect(_on_pressed.bind(mode))
		add_child(btn)
		_buttons[mode] = btn


func _on_pressed(mode: String) -> void:
	_active = mode
	for key in _buttons.keys():
		var b: Button = _buttons[key] as Button
		var on: bool = str(key) == mode
		b.button_pressed = on
		PanelUI.style_btn(b, on)
	overlay_changed.emit(mode)
