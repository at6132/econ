extends Control
## Animated procedural globe for the world creation screen.
## Three spinning orbital rings, pulsing core, terrain cells appearing.

var _t: float = 0.0
var _cells_revealed: int = 0
const CELL_GRID := 12
const CELL_TOTAL := CELL_GRID * CELL_GRID


func _process(dt: float) -> void:
	_t += dt
	var reveal_rate := 2.8
	_cells_revealed = mini(CELL_TOTAL, int(_t * reveal_rate * float(CELL_TOTAL) / 3.0))
	queue_redraw()


func _draw() -> void:
	var r := get_rect()
	if r.size.x < 16.0 or r.size.y < 16.0:
		return

	var cx := r.size.x * 0.5
	var cy := r.size.y * 0.5
	var radius := minf(r.size.x, r.size.y) * 0.36

	# Background glow
	var glow := RealmColors.ACCENT
	glow.a = 0.06 + 0.03 * sin(_t * 1.2)
	draw_circle(Vector2(cx, cy), radius * 1.4, glow)

	# Terrain cells filling in (spiral pattern)
	_draw_terrain_cells(cx, cy, radius)

	# Orbital rings
	_draw_ring(cx, cy, radius * 1.15, _t * 0.8, RealmColors.MAGIC, 0.4, 2.5)
	_draw_ring(cx, cy, radius * 1.05, -_t * 0.55, RealmColors.ACCENT, 0.3, 2.0)
	_draw_ring(cx, cy, radius * 1.28, _t * 1.2, RealmColors.OK, 0.25, 1.5)

	# Core pulse
	var pulse := 0.7 + 0.3 * sin(_t * 2.5)
	var core_c := RealmColors.ACCENT
	core_c.a = pulse * 0.6
	draw_circle(Vector2(cx, cy), 8.0 + 3.0 * sin(_t * 3.0), core_c)

	# Orbiting dots (representing agents/settlers being placed)
	for i in 5:
		var angle := _t * (0.6 + float(i) * 0.15) + float(i) * TAU / 5.0
		var dist := radius * (0.5 + 0.3 * sin(_t * 0.4 + float(i)))
		var dot_pos := Vector2(cx + cos(angle) * dist, cy + sin(angle) * dist * 0.7)
		var dot_c := RealmColors.WARN if i % 2 == 0 else RealmColors.MAGIC
		dot_c.a = 0.8
		draw_circle(dot_pos, 3.5, dot_c)


func _draw_terrain_cells(cx: float, cy: float, radius: float) -> void:
	var cell_size := radius * 2.0 / float(CELL_GRID)
	var origin_x := cx - radius
	var origin_y := cy - radius

	var terrain_colors: Array = [
		RealmColors.terrain_color("plains"),
		RealmColors.terrain_color("forest"),
		RealmColors.terrain_color("mountain"),
		RealmColors.terrain_color("desert"),
		RealmColors.terrain_color("water_shallow"),
		RealmColors.terrain_color("water_deep"),
		RealmColors.terrain_color("tundra"),
		RealmColors.terrain_color("swamp"),
	]

	# Spiral reveal order
	for idx in mini(_cells_revealed, CELL_TOTAL):
		var pos := _spiral_pos(idx)
		var gx: int = pos.x
		var gy: int = pos.y
		if gx < 0 or gx >= CELL_GRID or gy < 0 or gy >= CELL_GRID:
			continue

		var cell_cx := origin_x + (float(gx) + 0.5) * cell_size
		var cell_cy := origin_y + (float(gy) + 0.5) * cell_size

		# Only draw within the circle
		var dx := cell_cx - cx
		var dy := cell_cy - cy
		if dx * dx + dy * dy > radius * radius:
			continue

		# Deterministic color from position
		var color_idx := (gx * 7 + gy * 13) % terrain_colors.size()
		var c: Color = terrain_colors[color_idx]
		# Fade in
		var age := _t - float(idx) / (2.8 * float(CELL_TOTAL) / 3.0)
		c.a = clampf(age * 4.0, 0.0, 0.85)
		if c.a <= 0.0:
			continue

		var rect := Rect2(
			origin_x + float(gx) * cell_size + 1.0,
			origin_y + float(gy) * cell_size + 1.0,
			cell_size - 2.0,
			cell_size - 2.0,
		)
		draw_rect(rect, c, true)


func _draw_ring(cx: float, cy: float, radius: float, angle_offset: float, color: Color, alpha: float, width: float) -> void:
	var c := color
	c.a = alpha
	var arc_length := TAU * 0.6
	draw_arc(Vector2(cx, cy), radius, angle_offset, angle_offset + arc_length, 36, c, width, true)
	# Small dot at the leading edge
	var dot_angle := angle_offset + arc_length
	var dot_c := color
	dot_c.a = alpha * 2.0
	draw_circle(Vector2(cx + cos(dot_angle) * radius, cy + sin(dot_angle) * radius), width + 1.0, dot_c)


func _spiral_pos(idx: int) -> Vector2i:
	# Center-out spiral for the cell grid
	var half := CELL_GRID / 2
	var x := half
	var y := half
	if idx == 0:
		return Vector2i(x, y)
	var layer := 1
	var pos := 1
	while pos <= idx:
		# Right
		for _i in layer:
			if pos > idx:
				break
			x += 1
			if pos == idx:
				return Vector2i(x, y)
			pos += 1
		# Down
		for _i in layer:
			if pos > idx:
				break
			y += 1
			if pos == idx:
				return Vector2i(x, y)
			pos += 1
		layer += 1
		# Left
		for _i in layer:
			if pos > idx:
				break
			x -= 1
			if pos == idx:
				return Vector2i(x, y)
			pos += 1
		# Up
		for _i in layer:
			if pos > idx:
				break
			y -= 1
			if pos == idx:
				return Vector2i(x, y)
			pos += 1
		layer += 1
	return Vector2i(x, y)
