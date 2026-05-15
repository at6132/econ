extends Control
## Right-side main-menu decoration: abstract map, routes, and moving “commerce” dots.

var _t: float = 0.0


func _process(dt: float) -> void:
	_t += dt
	queue_redraw()


func _draw() -> void:
	var r := get_rect()
	if r.size.x < 8.0 or r.size.y < 8.0:
		return
	draw_rect(r, RealmColors.BG2, true)
	var grid := 56.0
	var ox := fposmod(_t * 18.0, grid)
	var oy := fposmod(_t * 11.0, grid)
	var c_muted := RealmColors.MUTED
	c_muted.a = 0.22
	var x := -grid + ox
	while x < r.size.x + grid:
		draw_line(Vector2(x, 0.0), Vector2(x, r.size.y), c_muted, 1.0, true)
		x += grid
	var y := -grid + oy
	while y < r.size.y + grid:
		draw_line(Vector2(0.0, y), Vector2(r.size.x, y), c_muted, 1.0, true)
		y += grid

	var cx := r.size.x * 0.38
	var cy := r.size.y * 0.42
	var pulse := 0.55 + 0.45 * sin(_t * 1.7)
	var gold := RealmColors.ACCENT
	gold.a = pulse
	draw_circle(Vector2(cx, cy), 14.0 + 6.0 * sin(_t * 2.1), gold)
	var ring := RealmColors.MAGIC
	ring.a = 0.35
	draw_arc(Vector2(cx, cy), 48.0 + 8.0 * sin(_t * 1.3), _t * 0.9, _t * 0.9 + TAU * 0.62, 48, ring, 3.0, true)

	var n_dots := 9
	for i in n_dots:
		var u := float(i) / float(n_dots)
		var ang := u * TAU + _t * 0.35
		var rad := 0.28 * minf(r.size.x, r.size.y) + 40.0 * sin(_t * 0.4 + u * 5.0)
		var p := Vector2(cx + cos(ang) * rad, cy + sin(ang * 1.1) * rad * 0.88)
		var hue := RealmColors.MAGIC if int(i) % 2 == 0 else RealmColors.WARN
		hue.a = 0.75
		draw_circle(p, 5.0 + 2.0 * sin(_t * 3.0 + u * 8.0), hue)

	var bx := r.size.x * 0.72
	var by := r.size.y * 0.28
	var bw := r.size.x * 0.18
	var bh := r.size.y * 0.14
	var brect := Rect2(bx - bw * 0.5, by - bh * 0.5, bw, bh)
	var panel := RealmColors.PANEL
	panel.a = 0.92
	draw_rect(brect, panel, true)
	draw_rect(brect, RealmColors.BLACK, false, 3.0)
	var flow := Color(RealmColors.OK)
	flow.a = 0.55
	var wave := sin(_t * 2.4) * 0.15 * bh
	draw_line(
		brect.position + Vector2(8.0, brect.size.y * 0.55 + wave),
		brect.position + Vector2(brect.size.x - 8.0, brect.size.y * 0.35 - wave),
		flow,
		2.5,
		true,
	)
