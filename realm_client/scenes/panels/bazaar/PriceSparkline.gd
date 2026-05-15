extends Control
## Best ask + best bid chart (web ``MarketHistoryChart`` parity, compact).

const _MISSING := -1.0

var _asks: PackedFloat32Array = PackedFloat32Array()
var _bids: PackedFloat32Array = PackedFloat32Array()


func _ready() -> void:
	custom_minimum_size = Vector2(0, 140)
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func set_market_series(asks: PackedFloat32Array, bids: PackedFloat32Array) -> void:
	_asks = asks
	_bids = bids
	queue_redraw()


func _font() -> Font:
	if RealmFonts.font_body != null:
		return RealmFonts.font_body
	return ThemeDB.fallback_font


func _draw() -> void:
	var rect := Rect2(Vector2.ZERO, size)
	if rect.size.x < 8.0 or rect.size.y < 8.0:
		return

	var inner := rect.grow(-6.0)
	draw_rect(inner, RealmColors.PANEL_DEEP)
	draw_rect(inner, RealmColors.BORDER, false, 1.0)

	_draw_grid(inner)

	var n := maxi(_asks.size(), _bids.size())
	if n == 0:
		_draw_empty(inner, "No market snapshots yet. Advance ticks so the book records prices.")
		return

	var has_ask := _series_has_valid(_asks)
	var has_bid := _series_has_valid(_bids)
	if not has_ask and not has_bid:
		_draw_empty(inner, "No bid or ask prints for this symbol in recorded history yet.")
		return

	if has_ask:
		_draw_series(inner, _asks, RealmColors.MAGIC, false)
	if has_bid:
		_draw_series(inner, _bids, RealmColors.ACCENT, true)

	_draw_legend(inner, has_ask, has_bid)


func _series_has_valid(series: PackedFloat32Array) -> bool:
	for i in range(series.size()):
		if series[i] >= 0.0:
			return true
	return false


func _draw_grid(inner: Rect2) -> void:
	var grid_col := RealmColors.BORDER.lerp(Color(0, 0, 0, 0), 0.65)
	for i in range(1, 4):
		var y := inner.position.y + inner.size.y * float(i) / 4.0
		draw_line(Vector2(inner.position.x, y), Vector2(inner.position.x + inner.size.x, y), grid_col, 1.0)


func _draw_empty(inner: Rect2, message: String) -> void:
	var font := _font()
	var font_size := 14
	var lines := message.split(" ")
	var wrapped: PackedStringArray = []
	var line := ""
	for word in lines:
		var trial := line if line.is_empty() else line + " " + word
		if font.get_string_size(trial, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x > inner.size.x - 12.0:
			if not line.is_empty():
				wrapped.append(line)
			line = word
		else:
			line = trial
	if not line.is_empty():
		wrapped.append(line)
	var y := inner.position.y + 12.0
	for ln in wrapped:
		draw_string(font, Vector2(inner.position.x + 8.0, y), ln, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, RealmColors.MUTED)
		y += font_size + 4.0


func _draw_legend(inner: Rect2, has_ask: bool, has_bid: bool) -> void:
	var font := _font()
	var x := inner.position.x + 8.0
	var y := inner.position.y + inner.size.y - 8.0
	var fs := 12
	if has_ask:
		draw_line(Vector2(x, y - 4.0), Vector2(x + 18.0, y - 4.0), RealmColors.MAGIC, 2.0)
		draw_string(font, Vector2(x + 22.0, y), "ask", HORIZONTAL_ALIGNMENT_LEFT, -1, fs, RealmColors.MUTED)
		x += 56.0
	if has_bid:
		draw_line(Vector2(x, y - 4.0), Vector2(x + 18.0, y - 4.0), RealmColors.ACCENT, 2.0)
		draw_string(font, Vector2(x + 22.0, y), "bid", HORIZONTAL_ALIGNMENT_LEFT, -1, fs, RealmColors.MUTED)


func _draw_series(inner: Rect2, series: PackedFloat32Array, color: Color, dashed: bool) -> void:
	var mn := INF
	var mx := -INF
	for i in range(series.size()):
		var v := series[i]
		if v < 0.0:
			continue
		mn = minf(mn, v)
		mx = maxf(mx, v)
	if mx < 0.0:
		return
	if mx <= mn:
		mx = mn + 1.0

	var n := series.size()
	var prev: Vector2 = Vector2.ZERO
	var have_prev := false
	for i in range(n):
		var v := series[i]
		if v < 0.0:
			have_prev = false
			continue
		var t := float(i) / float(maxi(n - 1, 1))
		var x := inner.position.x + t * inner.size.x
		var y := inner.position.y + inner.size.y * (1.0 - ((v - mn) / (mx - mn)))
		var pt := Vector2(x, y)
		if n == 1:
			draw_circle(pt, 3.0, color)
			return
		if have_prev:
			if dashed:
				_draw_dashed(prev, pt, color)
			else:
				draw_line(prev, pt, color, 2.0)
		else:
			draw_circle(pt, 2.0, color)
		prev = pt
		have_prev = true


func _draw_dashed(a: Vector2, b: Vector2, color: Color) -> void:
	var seg := 6.0
	var gap := 4.0
	var dir := b - a
	var len := dir.length()
	if len < 0.5:
		return
	dir /= len
	var t := 0.0
	while t < len:
		var t1 := minf(t + seg, len)
		draw_line(a + dir * t, a + dir * t1, color, 2.0)
		t = t1 + gap
