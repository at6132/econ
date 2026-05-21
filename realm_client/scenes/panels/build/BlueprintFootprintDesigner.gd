extends Control
## Paint footprint cells: structure / input dock / output dock / power.

signal layout_changed(layout: Dictionary)

const CELL := 28
const MODES := ["structure", "input", "output", "power", "clear"]

var _w: int = 2
var _h: int = 2
var _mode: String = "structure"
var _layout: Dictionary = {}


func _ready() -> void:
	custom_minimum_size = Vector2(320, 320)
	mouse_filter = Control.MOUSE_FILTER_STOP
	queue_redraw()


func set_footprint(w: int, h: int, layout: Dictionary = {}) -> void:
	_w = clampi(w, 1, 10)
	_h = clampi(h, 1, 10)
	_layout = layout.duplicate(true)
	custom_minimum_size = Vector2(_w * CELL + 8, _h * CELL + 8)
	queue_redraw()


func get_layout() -> Dictionary:
	return _layout.duplicate(true)


func set_paint_mode(mode: String) -> void:
	if mode in MODES:
		_mode = mode
	elif mode == "clear":
		_mode = "clear"


func _gui_input(event: InputEvent) -> void:
	if not (event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT):
		return
	var local := get_local_mouse_position()
	var gx := int(local.x / CELL)
	var gy := int(local.y / CELL)
	if gx < 0 or gy < 0 or gx >= _w or gy >= _h:
		return
	var key := "%d,%d" % [gx, gy]
	if _mode == "clear":
		_layout.erase(key)
	else:
		_layout[key] = _mode
	layout_changed.emit(get_layout())
	queue_redraw()


func _draw() -> void:
	for y in _h:
		for x in _w:
			var rect := Rect2(x * CELL + 2, y * CELL + 2, CELL - 4, CELL - 4)
			var key := "%d,%d" % [x, y]
			var zone: String = str(_layout.get(key, "structure"))
			draw_rect(rect, _zone_color(zone), true)
			draw_rect(rect, Color(0.3, 0.3, 0.35), false, 1.0)


func _zone_color(zone: String) -> Color:
	match zone:
		"input":
			return Color(0.2, 0.45, 0.9, 0.85)
		"output":
			return Color(0.2, 0.75, 0.35, 0.85)
		"power":
			return Color(0.9, 0.75, 0.2, 0.85)
		_:
			return Color(0.18, 0.18, 0.22, 0.95)
