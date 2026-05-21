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
var _group: ButtonGroup


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	add_theme_constant_override("separation", 4)
	_group = ButtonGroup.new()
	_group.allow_unpress = false
	for item in BUTTONS:
		var mode: String = str(item[0])
		var label: String = str(item[1])
		var btn := Button.new()
		btn.text = label
		btn.toggle_mode = true
		btn.button_group = _group
		btn.button_pressed = mode == "none"
		PanelUI.style_btn(btn, mode == "none")
		btn.toggled.connect(_on_toggled.bind(mode))
		add_child(btn)
		_buttons[mode] = btn
	_active = "none"


func _on_toggled(pressed: bool, mode: String) -> void:
	if not pressed or _active == mode:
		return
	_set_active(mode)
	overlay_changed.emit(mode)


func _set_active(mode: String) -> void:
	_active = mode
	for key in _buttons.keys():
		var b: Button = _buttons[key] as Button
		var on: bool = str(key) == mode
		if b.button_pressed != on:
			b.button_pressed = on
		PanelUI.style_btn(b, on)


## Apply overlay from settings or boot prefs (updates buttons + emits ``overlay_changed``).
func apply_mode(mode: String) -> void:
	if not _buttons.has(mode):
		mode = "none"
	if _active == mode:
		return
	_set_active(mode)
	overlay_changed.emit(mode)
