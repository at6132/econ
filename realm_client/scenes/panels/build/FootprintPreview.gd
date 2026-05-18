extends Control
## Mini 10×10 grid showing blueprint footprint for CreateBlueprintDialog.

var footprint_w: int = 2
var footprint_h: int = 2

const GRID_CELLS := 10


func _ready() -> void:
	resized.connect(func() -> void: queue_redraw())


func set_footprint(w: int, h: int) -> void:
	footprint_w = w
	footprint_h = h
	queue_redraw()


func _draw() -> void:
	var cs := minf(size.x / float(GRID_CELLS), size.y / float(GRID_CELLS))
	for gy in GRID_CELLS:
		for gx in GRID_CELLS:
			var r := Rect2(gx * cs, gy * cs, cs, cs)
			if gx < footprint_w and gy < footprint_h:
				draw_rect(r, Color(0.30, 0.90, 0.40, 0.70))
			else:
				draw_rect(r, Color(0.15, 0.15, 0.18))
			draw_rect(r, Color(0.3, 0.3, 0.3, 0.5), false, 0.5)
