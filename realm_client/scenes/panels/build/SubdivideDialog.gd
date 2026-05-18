extends CanvasLayer

signal subdivided(sub_plot_ids: Array)

const GRID_CELLS := 10
const LABEL_CHARS := "ABCDEFGHI"
const PARTITION_COLORS := [
	Color(0.85, 0.35, 0.35, 0.60),
	Color(0.35, 0.65, 0.85, 0.60),
	Color(0.35, 0.85, 0.55, 0.60),
	Color(0.85, 0.72, 0.20, 0.60),
	Color(0.75, 0.35, 0.85, 0.60),
	Color(0.85, 0.55, 0.25, 0.60),
]

@onready var grid_area: Control = %GridArea
@onready var status_label: Label = %StatusLabel
@onready var fee_label: Label = %FeeLabel
@onready var subdivide_btn: Button = %SubdivideBtn
@onready var cancel_btn: Button = %CancelBtn

var _plot_id: String = ""
var _partitions: Array = []
var _drawing: bool = false
var _draw_start: Vector2i = Vector2i(-1, -1)
var _draw_end: Vector2i = Vector2i(-1, -1)


func _ready() -> void:
	layer = 50
	subdivide_btn.pressed.connect(_on_subdivide)
	cancel_btn.pressed.connect(queue_free)
	grid_area.draw.connect(_on_grid_draw)
	grid_area.gui_input.connect(_on_grid_input)
	_update_fee()


func setup(plot_id: String) -> void:
	_plot_id = plot_id
	_partitions.clear()
	_update_status()


func _cell_size() -> float:
	return minf(grid_area.size.x, grid_area.size.y) / float(GRID_CELLS)


func _grid_origin() -> Vector2:
	var cs := _cell_size()
	return Vector2(
		(grid_area.size.x - cs * GRID_CELLS) * 0.5,
		(grid_area.size.y - cs * GRID_CELLS) * 0.5,
	)


func _cell_rect(gx: int, gy: int) -> Rect2:
	var cs := _cell_size()
	var o := _grid_origin()
	return Rect2(o.x + gx * cs, o.y + gy * cs, cs, cs)


func _screen_to_grid(pos: Vector2) -> Vector2i:
	var cs := _cell_size()
	var o := _grid_origin()
	var gx := int((pos.x - o.x) / cs)
	var gy := int((pos.y - o.y) / cs)
	if gx < 0 or gy < 0 or gx >= GRID_CELLS or gy >= GRID_CELLS:
		return Vector2i(-1, -1)
	return Vector2i(gx, gy)


func _normalize_rect(a: Vector2i, b: Vector2i) -> Dictionary:
	var x0 := mini(a.x, b.x)
	var y0 := mini(a.y, b.y)
	var x1 := maxi(a.x, b.x)
	var y1 := maxi(a.y, b.y)
	return {"grid_x": x0, "grid_y": y0, "grid_w": x1 - x0 + 1, "grid_h": y1 - y0 + 1}


func _partition_cells(p: Dictionary) -> Array:
	var out: Array = []
	var gx := int(p.get("grid_x", 0))
	var gy := int(p.get("grid_y", 0))
	var gw := int(p.get("grid_w", 1))
	var gh := int(p.get("grid_h", 1))
	for dy in range(gh):
		for dx in range(gw):
			out.append(Vector2i(gx + dx, gy + dy))
	return out


func _on_grid_draw() -> void:
	var cs := _cell_size()
	for gy in GRID_CELLS:
		for gx in GRID_CELLS:
			var r := _cell_rect(gx, gy)
			grid_area.draw_rect(r, Color(0.18, 0.20, 0.16))
			grid_area.draw_rect(r, Color(0, 0, 0, 0.35), false, 1.0)
	for i in range(_partitions.size()):
		var p: Dictionary = _partitions[i]
		var gx := int(p.get("grid_x", 0))
		var gy := int(p.get("grid_y", 0))
		var gw := int(p.get("grid_w", 1))
		var gh := int(p.get("grid_h", 1))
		var col: Color = PARTITION_COLORS[i % PARTITION_COLORS.size()]
		for dy in range(gh):
			for dx in range(gw):
				grid_area.draw_rect(_cell_rect(gx + dx, gy + dy), col)
		var lbl := LABEL_CHARS[i] if i < LABEL_CHARS.length() else "?"
		grid_area.draw_string(
			RealmFonts.font_body,
			_cell_rect(gx, gy).position + Vector2(4, cs * 0.4),
			lbl,
			HORIZONTAL_ALIGNMENT_LEFT,
			-1,
			14,
			Color.WHITE,
		)
	if _drawing and _draw_start.x >= 0:
		var norm := _normalize_rect(_draw_start, _draw_end)
		var col := Color(0.85, 0.72, 0.20, 0.35)
		for dy in range(int(norm.grid_h)):
			for dx in range(int(norm.grid_w)):
				grid_area.draw_rect(
					_cell_rect(int(norm.grid_x) + dx, int(norm.grid_y) + dy),
					col,
				)


func _on_grid_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		if event.pressed:
			var g := _screen_to_grid(event.position)
			if g.x < 0:
				return
			_drawing = true
			_draw_start = g
			_draw_end = g
			grid_area.queue_redraw()
		else:
			if _drawing:
				_drawing = false
				var norm := _normalize_rect(_draw_start, _draw_end)
				if int(norm.grid_w) >= 2 and int(norm.grid_h) >= 2:
					_add_partition(norm)
				grid_area.queue_redraw()
	elif event is InputEventMouseMotion and _drawing:
		_draw_end = _screen_to_grid(event.position)
		grid_area.queue_redraw()
	elif event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_RIGHT:
		if not _partitions.is_empty():
			_partitions.pop_back()
			_update_status()
			grid_area.queue_redraw()


func _add_partition(p: Dictionary) -> void:
	if _partitions.size() >= 9:
		status_label.text = "Maximum 9 sub-plots"
		return
	var new_cells: Array = _partition_cells(p)
	for existing in _partitions:
		for c in _partition_cells(existing):
			if c in new_cells:
				status_label.text = "Partition overlaps existing region"
				return
	_partitions.append(p)
	_update_status()


func _update_status() -> void:
	var n := _partitions.size()
	fee_label.text = "Surveyor fee: %s (%d partitions)" % [
		WorldState.format_money(n * 10_000),
		n,
	]
	if n < 2:
		status_label.text = "Draw at least 2 rectangles (drag on grid). Min 2x2 cells each."
	else:
		status_label.text = "%d partition(s) — draw more or click Subdivide" % n


func _update_fee() -> void:
	fee_label.text = "Surveyor fee: $100 per sub-plot"


func _on_subdivide() -> void:
	if _partitions.size() < 2:
		status_label.text = "Need at least 2 partitions"
		return
	subdivide_btn.disabled = true
	API.post_request(
		"/plots/%s/subdivide" % _plot_id.uri_encode(),
		{"party": WorldState.party_id, "partitions": _partitions},
		func(data: Dictionary) -> void:
			subdivide_btn.disabled = false
			if bool(data.get("ok", false)):
				subdivided.emit(data.get("sub_plot_ids", []))
				queue_free()
			else:
				status_label.text = str(data.get("reason", "Subdivide failed")),
	)
