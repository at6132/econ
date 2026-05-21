extends Control
## Build view — one deed footprint from engine ``world_cells`` (10m cells per world tile).

signal cell_hovered(gx: int, gy: int)
signal cell_clicked(gx: int, gy: int)
signal road_path_painted(cells: Array)
signal world_link_clicked(neighbor_plot_id: String)

const TERRAIN_COLORS := {
	"plains": Color(0.62, 0.58, 0.38),
	"forest": Color(0.22, 0.48, 0.22),
	"temperate_forest": Color(0.22, 0.48, 0.22),
	"mountain": Color(0.50, 0.50, 0.52),
	"coastal": Color(0.72, 0.68, 0.52),
	"valley": Color(0.55, 0.65, 0.38),
	"hills": Color(0.52, 0.50, 0.38),
	"desert": Color(0.78, 0.68, 0.38),
	"tropical": Color(0.18, 0.60, 0.28),
	"swamp": Color(0.28, 0.40, 0.22),
	"tundra": Color(0.82, 0.85, 0.88),
}
const VOID_FILL := Color(0.06, 0.06, 0.08, 0.92)
const VOID_LINE := Color(0.14, 0.14, 0.16, 0.55)
const GRID_LINE := Color(0.18, 0.17, 0.16, 0.65)
const TILE_LINE := Color(0.32, 0.30, 0.28, 0.85)
const DEED_LINE := Color(0.12, 0.11, 0.10, 0.95)
const DEED_LINE_HI := Color(0.85, 0.72, 0.20, 0.55)
const STREET_COLOR := Color(0.28, 0.28, 0.30, 0.45)
const ROAD_ASPHALT := Color(0.22, 0.24, 0.28, 0.92)
const ROAD_EDGE := Color(0.55, 0.58, 0.62, 0.95)
const ROAD_PREVIEW := Color(0.40, 0.85, 0.95, 0.55)
const ROAD_LINK := Color(0.85, 0.72, 0.20, 0.65)
const WORLD_LINK_COLOR := Color(0.35, 0.85, 0.95, 0.95)
const WORLD_LINK_DONE := Color(0.55, 0.72, 0.42, 0.9)
const OCCUPIED_COLOR := Color(0.25, 0.25, 0.30, 0.85)
const PREVIEW_OK := Color(0.30, 0.90, 0.40, 0.55)
const PREVIEW_BLOCK := Color(0.90, 0.25, 0.25, 0.55)
const METRE_LABEL := Color(0.75, 0.75, 0.75, 0.60)

var _plot_id: String = ""
var _plot_data: Dictionary = {}
var _terrain: String = "plains"
var _grid_w: int = 10
var _grid_h: int = 10
var _placed_buildings: Array = []
var _sub_plots: Array = []
var _lots: Array = []
var _deed_cells: Dictionary = {}  # "gx,gy" → true
var _street_rows: Array[int] = []

var _placing_blueprint_id: String = ""
var _placing_w: int = 0
var _placing_h: int = 0
var _hover_gx: int = -1
var _hover_gy: int = -1
var _hover_lot_idx: int = -1

var _confirm_callback: Callable = Callable()
var _confirming: bool = false
var _confirm_gx: int = -1
var _confirm_gy: int = -1

var _error_flash_until: float = 0.0
var _error_message: String = ""

var _interaction_mode: String = "building"
var _road_drag_active: bool = false
var _road_last_cell: Vector2i = Vector2i(-1, -1)
var _road_paint_stroke: Dictionary = {}
var _world_link_edges: Array = []


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	focus_mode = Control.FOCUS_ALL
	resized.connect(func() -> void: queue_redraw())


func load_plot(plot_id: String, data: Dictionary) -> void:
	_plot_id = plot_id
	_plot_data = data
	_terrain = str(data.get("terrain", "plains"))
	_set_grid_dims(data)
	_placed_buildings = data.get("placed_buildings", [])
	if _placed_buildings is not Array:
		_placed_buildings = []
	_sub_plots = data.get("sub_plots", [])
	if _sub_plots is not Array:
		_sub_plots = []
	# Deed footprint = engine ``world_cells`` (one source of truth with the world map).
	_lots = [_deed_lot_from_world_cells(data)]
	_deed_cells = _deed_cell_lookup(_lots)
	_street_rows = []
	var grid: Dictionary = data.get("grid", {}) if data.get("grid") is Dictionary else {}
	var edges: Variant = grid.get("world_link_edges", data.get("world_link_edges", []))
	_world_link_edges = edges if edges is Array else []
	queue_redraw()


func _deed_cell_lookup(lots: Array) -> Dictionary:
	var out := {}
	for lot in lots:
		if not (lot is Dictionary):
			continue
		for c in (lot as Dictionary).get("cells", []) as Array:
			if c is Vector2i:
				out["%d,%d" % [c.x, c.y]] = true
	return out


func _in_deed(gx: int, gy: int) -> bool:
	return _deed_cells.has("%d,%d" % [gx, gy])


## Build-grid cells (10m) covered by this deed — mirrors ``world_cells`` from the API.
func _deed_lot_from_world_cells(data: Dictionary) -> Dictionary:
	var cells: Array = []
	var min_wx := 1_000_000
	var min_wy := 1_000_000
	var raw: Variant = data.get("world_cells", [])
	if raw is Array and not (raw as Array).is_empty():
		for c in raw as Array:
			if c is Dictionary:
				var d: Dictionary = c as Dictionary
				min_wx = mini(min_wx, int(d.get("x", 0)))
				min_wy = mini(min_wy, int(d.get("y", 0)))
	else:
		min_wx = int(data.get("x", 0))
		min_wy = int(data.get("y", 0))
		raw = [{"x": min_wx, "y": min_wy}]
	for c in raw as Array:
		if not (c is Dictionary):
			continue
		var wx: int = int((c as Dictionary).get("x", 0)) - min_wx
		var wy: int = int((c as Dictionary).get("y", 0)) - min_wy
		for dx in range(10):
			for dy in range(10):
				cells.append(Vector2i(wx * 10 + dx, wy * 10 + dy))
	var shape := str(data.get("parcel_shape", "rect"))
	return {"cells": cells, "shape": shape}


func _set_grid_dims(data: Dictionary) -> void:
	var grid: Dictionary = data.get("grid", {}) if data.get("grid") is Dictionary else {}
	_grid_w = int(data.get("grid_cells_w", grid.get("grid_cells_w", 0)))
	_grid_h = int(data.get("grid_cells_h", grid.get("grid_cells_h", 0)))
	if _grid_w < 1 or _grid_h < 1:
		var wt := int(data.get("world_tiles_w", 1))
		var ht := int(data.get("world_tiles_h", 1))
		_grid_w = wt * 10
		_grid_h = ht * 10
	_grid_w = maxi(1, _grid_w)
	_grid_h = maxi(1, _grid_h)


func set_interaction_mode(mode: String) -> void:
	_interaction_mode = mode
	_road_drag_active = false
	_road_paint_stroke.clear()
	_confirming = false
	queue_redraw()


func set_placing_blueprint(blueprint_id: String, bp_data: Dictionary) -> void:
	_placing_blueprint_id = blueprint_id
	_placing_w = int(bp_data.get("footprint_w", 1))
	_placing_h = int(bp_data.get("footprint_h", 1))
	_confirming = false
	queue_redraw()


func _is_road_paint_mode() -> bool:
	return _interaction_mode == "roads" and _placing_blueprint_id == "road_segment"


func is_confirming() -> bool:
	return _confirming


func finish_confirm(confirmed: bool) -> void:
	if not _confirming:
		return
	_confirming = false
	var cb := _confirm_callback
	_confirm_callback = Callable()
	queue_redraw()
	if cb.is_valid():
		cb.call(confirmed)


func show_confirm(gx: int, gy: int, callback: Callable) -> void:
	_confirm_gx = gx
	_confirm_gy = gy
	_confirm_callback = callback
	_confirming = true
	grab_focus()
	queue_redraw()


func key_confirms(event: InputEventKey) -> bool:
	return (
		event.keycode == KEY_Y
		or event.physical_keycode == KEY_Y
		or event.keycode == KEY_ENTER
		or event.keycode == KEY_KP_ENTER
	)


func key_cancels(event: InputEventKey) -> bool:
	return (
		event.keycode == KEY_N
		or event.physical_keycode == KEY_N
		or event.keycode == KEY_ESCAPE
	)


func show_error(msg: String) -> void:
	_error_message = msg.strip_edges()
	_error_flash_until = Time.get_ticks_msec() / 1000.0 + 5.0
	set_process(true)
	queue_redraw()


func _process(_delta: float) -> void:
	if _error_message.is_empty():
		set_process(false)
		return
	if Time.get_ticks_msec() / 1000.0 >= _error_flash_until:
		_error_message = ""
		set_process(false)
		queue_redraw()


func _cell_size() -> float:
	return minf(size.x / float(_grid_w), size.y / float(_grid_h))


func _grid_origin() -> Vector2:
	var cs := _cell_size()
	return Vector2((size.x - cs * _grid_w) * 0.5, (size.y - cs * _grid_h) * 0.5)


func _cell_rect(gx: int, gy: int) -> Rect2:
	var cs := _cell_size()
	var o := _grid_origin()
	return Rect2(o.x + gx * cs, o.y + gy * cs, cs, cs)


func _cells_rect(gx: int, gy: int, w: int, h: int) -> Rect2:
	var r1 := _cell_rect(gx, gy)
	var r2 := _cell_rect(gx + w - 1, gy + h - 1)
	return Rect2(r1.position, Vector2(r2.end.x - r1.position.x, r2.end.y - r1.position.y))


func _occupied_set() -> Dictionary:
	var occ := {}
	for b in _placed_buildings:
		if not (b is Dictionary):
			continue
		var bx := int(b.get("grid_x", 0))
		var by := int(b.get("grid_y", 0))
		var bw := int(b.get("footprint_w", 1))
		var bh := int(b.get("footprint_h", 1))
		for dx in range(bw):
			for dy in range(bh):
				occ["%d,%d" % [bx + dx, by + dy]] = b
	return occ


func _draw() -> void:
	var cs := _cell_size()
	var terrain_color: Color = TERRAIN_COLORS.get(_terrain, Color(0.5, 0.5, 0.5))
	if Time.get_ticks_msec() / 1000.0 < _error_flash_until:
		terrain_color = terrain_color.lerp(Color(0.9, 0.2, 0.2), 0.12)

	_draw_cell_fills(terrain_color)
	_draw_streets(cs)
	_draw_schematic_grid(cs)
	_draw_deed_outline()

	for sp in _sub_plots:
		if not (sp is Dictionary):
			continue
		var spx := int(sp.get("grid_x", 0))
		var spy := int(sp.get("grid_y", 0))
		var spw := int(sp.get("grid_w", _grid_w))
		var sph := int(sp.get("grid_h", _grid_h))
		var border := _cells_rect(spx, spy, spw, sph)
		draw_rect(border, Color(0.85, 0.72, 0.20, 0.80), false, 2.5)
		var lbl := str(sp.get("sub_plot_id", "?")).split(":")[-1]
		_draw_text(border.position + Vector2(4, 14), lbl, 13, Color(0.85, 0.72, 0.20, 0.9))

	if (
		_hover_gx >= 0
		and _in_deed(_hover_gx, _hover_gy)
		and _placing_blueprint_id.is_empty()
	):
		draw_rect(_cell_rect(_hover_gx, _hover_gy), Color(1.0, 1.0, 1.0, 0.08))
		draw_rect(_cell_rect(_hover_gx, _hover_gy), DEED_LINE_HI, false, 1.5)

	var road_cells := _road_cell_set()
	for b in _placed_buildings:
		if not (b is Dictionary):
			continue
		var bid := str(b.get("blueprint_id", b.get("building_id", "")))
		var bx := int(b.get("grid_x", 0))
		var by := int(b.get("grid_y", 0))
		var bw := int(b.get("footprint_w", 1))
		var bh := int(b.get("footprint_h", 1))
		var building_rect := _cells_rect(bx, by, bw, bh)
		if bid == "road_segment":
			for dy in range(bh):
				for dx in range(bw):
					var r := _cell_rect(bx + dx, by + dy)
					draw_rect(r, ROAD_ASPHALT)
					draw_rect(r, ROAD_EDGE, false, 1.0)
			continue
		var eff := int(b.get("efficiency_pct", 100))
		var fill := OCCUPIED_COLOR
		if eff >= 90:
			fill = Color(0.20, 0.35, 0.20, 0.85)
		elif eff >= 50:
			fill = Color(0.40, 0.35, 0.10, 0.85)
		else:
			fill = Color(0.40, 0.15, 0.10, 0.85)
		draw_rect(building_rect, fill)
		draw_rect(building_rect, Color(0.85, 0.72, 0.20, 0.9), false, 2.0)
		var name_lbl: String = str(b.get("blueprint_name", b.get("blueprint_id", "?")))
		var lbl_size := 11 if cs > 28.0 else 8
		_draw_text(
			building_rect.position + Vector2(4, building_rect.size.y * 0.45),
			name_lbl,
			lbl_size,
			Color.WHITE,
		)
		var status_icon := "OK" if eff == 100 else ("~" if eff >= 50 else "!")
		_draw_text(
			building_rect.position + Vector2(4, building_rect.size.y - 12),
			"%s %d%%" % [status_icon, eff],
			9,
			Color(0.85, 0.85, 0.85, 0.8),
		)

	_draw_road_links(road_cells, cs)
	_draw_world_link_ports(cs)

	for key in _road_paint_stroke.keys():
		var parts: PackedStringArray = str(key).split(",")
		if parts.size() != 2:
			continue
		var r := _cell_rect(int(parts[0]), int(parts[1]))
		draw_rect(r, ROAD_PREVIEW)

	if not _placing_blueprint_id.is_empty() and _hover_gx >= 0 and not _is_road_paint_mode():
		var can_place := _can_place_at(_hover_gx, _hover_gy)
		var preview_color := PREVIEW_OK if can_place else PREVIEW_BLOCK
		for dy in range(_placing_h):
			for dx in range(_placing_w):
				var pgx := _hover_gx + dx
				var pgy := _hover_gy + dy
				if pgx < _grid_w and pgy < _grid_h and _in_deed(pgx, pgy):
					draw_rect(_cell_rect(pgx, pgy), preview_color)

	if _confirming:
		for dy in range(_placing_h):
			for dx in range(_placing_w):
				draw_rect(_cell_rect(_confirm_gx + dx, _confirm_gy + dy), Color(0.85, 0.72, 0.20, 0.7))
		var grid_bottom := _cell_rect(0, _grid_h - 1).end.y + 8.0
		_draw_text(
			Vector2(size.x * 0.5 - 120.0, grid_bottom + 12.0),
			"Place here?  [Y] Confirm  [N] Cancel",
			14,
			RealmColors.ACCENT,
		)

	if cs >= 6.0:
		var area_m := int(_plot_data.get("area_sq_metres", _deed_cells.size() * 100))
		var plot_rect := _cells_rect(0, 0, _grid_w, _grid_h)
		var mode_hint := "Drag to lay road (1 cell each)" if _is_road_paint_mode() else "Click to place building"
		_draw_text(
			Vector2(plot_rect.position.x, size.y - 10.0),
			"%d×%d grid (10m)  |  %d m²  |  %d free  |  %s"
			% [_grid_w, _grid_h, area_m, int(_free_cell_count()), mode_hint],
			10,
			METRE_LABEL,
		)

	_draw_error_banner()


func _draw_error_banner() -> void:
	if _error_message.is_empty():
		return
	if Time.get_ticks_msec() / 1000.0 >= _error_flash_until:
		return
	var plot_rect := _cells_rect(0, 0, _grid_w, _grid_h)
	var pad := 12.0
	var banner_w := minf(plot_rect.size.x - pad * 2.0, size.x - pad * 2.0)
	var banner_h := 56.0
	var pos := Vector2(
		plot_rect.position.x + (plot_rect.size.x - banner_w) * 0.5,
		plot_rect.position.y + plot_rect.size.y * 0.5 - banner_h * 0.5,
	)
	var banner := Rect2(pos, Vector2(banner_w, banner_h))
	draw_rect(banner, Color(0.12, 0.04, 0.04, 0.92))
	draw_rect(banner, Color(1.0, 0.35, 0.3, 0.95), false, 2.0)
	var font: Font = RealmFonts.font_body
	if font == null:
		return
	var title := "Cannot place here"
	var body := _error_message
	var y := banner.position.y + 8.0
	draw_string(font, Vector2(banner.position.x + 8.0, y), title, HORIZONTAL_ALIGNMENT_LEFT, -1, 13, Color(1.0, 0.45, 0.4))
	y += 18.0
	draw_string(
		font,
		Vector2(banner.position.x + 8.0, y),
		body,
		HORIZONTAL_ALIGNMENT_LEFT,
		int(banner.size.x - 16.0),
		12,
		Color(0.95, 0.9, 0.88),
	)


func _draw_cell_fills(terrain_color: Color) -> void:
	for gy in range(_grid_h):
		for gx in range(_grid_w):
			var r := _cell_rect(gx, gy)
			if _in_deed(gx, gy):
				draw_rect(r, terrain_color)
			else:
				draw_rect(r, VOID_FILL)


func _draw_schematic_grid(cs: float) -> void:
	if cs < 4.0:
		return
	for gx in range(_grid_w + 1):
		var x := _grid_origin().x + gx * cs
		var major := gx % 10 == 0
		var col := TILE_LINE if major else GRID_LINE
		var w := 1.5 if major else 1.0
		var top := _grid_origin().y
		var bottom := top + cs * _grid_h
		draw_line(Vector2(x, top), Vector2(x, bottom), col, w, true)
	for gy in range(_grid_h + 1):
		var y := _grid_origin().y + gy * cs
		var major := gy % 10 == 0
		var col := TILE_LINE if major else GRID_LINE
		var w := 1.5 if major else 1.0
		var left := _grid_origin().x
		var right := left + cs * _grid_w
		draw_line(Vector2(left, y), Vector2(right, y), col, w, true)


func _draw_deed_outline() -> void:
	for i in range(_lots.size()):
		var lot: Dictionary = _lots[i]
		var cells: Array = lot.get("cells", []) as Array
		var poly := _lot_boundary_polygon(cells, i, false)
		if poly.size() >= 3:
			_draw_polyline(poly, DEED_LINE, 2.0, true)


func _draw_streets(_cs: float) -> void:
	for row in _street_rows:
		if row >= _grid_h:
			continue
		var r := _cell_rect(0, row)
		r.size.x = _cells_rect(0, 0, _grid_w, _grid_h).size.x
		draw_rect(r, STREET_COLOR)


func _lot_boundary_polygon(cells: Array, lot_idx: int, sketchy: bool = false) -> PackedVector2Array:
	if cells.is_empty():
		return PackedVector2Array()
	var cell_set := {}
	for c in cells:
		if c is Vector2i:
			cell_set["%d,%d" % [c.x, c.y]] = true
	var segments: Array = []
	for c in cells:
		if not (c is Vector2i):
			continue
		var cell: Vector2i = c as Vector2i
		var x: int = cell.x
		var y: int = cell.y
		if x >= _grid_w or y >= _grid_h:
			continue
		if not cell_set.has("%d,%d" % [x, y - 1]):
			segments.append([Vector2(x, y), Vector2(x + 1, y)])
		if not cell_set.has("%d,%d" % [x, y + 1]):
			segments.append([Vector2(x, y + 1), Vector2(x + 1, y + 1)])
		if not cell_set.has("%d,%d" % [x - 1, y]):
			segments.append([Vector2(x, y), Vector2(x, y + 1)])
		if not cell_set.has("%d,%d" % [x + 1, y]):
			segments.append([Vector2(x + 1, y), Vector2(x + 1, y + 1)])
	var loop: Array = _chain_segments(segments)
	var poly := PackedVector2Array()
	for p in loop:
		if sketchy:
			poly.append(_grid_corner_px(int(p.x), int(p.y), lot_idx))
		else:
			poly.append(_grid_corner_crisp(int(p.x), int(p.y)))
	return poly


func _chain_segments(segments: Array) -> Array:
	if segments.is_empty():
		return []
	var remaining: Array = segments.duplicate()
	var loop: Array = [remaining[0][0], remaining[0][1]]
	remaining.remove_at(0)
	var guard := 0
	while not remaining.is_empty() and guard < 256:
		guard += 1
		var end: Vector2 = loop[loop.size() - 1]
		var found := -1
		var use_second := false
		for i in range(remaining.size()):
			var seg: Array = remaining[i]
			if seg[0] == end:
				found = i
				use_second = true
				break
			if seg[1] == end:
				found = i
				use_second = false
				break
		if found < 0:
			break
		var picked: Array = remaining[found]
		remaining.remove_at(found)
		loop.append(picked[1] if use_second else picked[0])
	return loop


func _grid_corner_crisp(gx: int, gy: int) -> Vector2:
	var cs := _cell_size()
	var o := _grid_origin()
	return Vector2(o.x + gx * cs, o.y + gy * cs)


func _grid_corner_px(gx: int, gy: int, lot_idx: int) -> Vector2:
	var base := _grid_corner_crisp(gx, gy)
	var j := MapHash.vertex_jitter(
		WorldState.world_seed,
		_plot_id.hash() ^ lot_idx,
		gx * 17 + gy,
		2.2,
	)
	return base + j


func _draw_polyline(points: PackedVector2Array, color: Color, width: float, closed: bool) -> void:
	if points.size() < 2:
		return
	for i in range(points.size() - 1):
		draw_line(points[i], points[i + 1], color, width, true)
	if closed and points.size() > 2:
		draw_line(points[points.size() - 1], points[0], color, width, true)


func _draw_text(pos: Vector2, text: String, font_size: int, color: Color) -> void:
	var font: Font = RealmFonts.font_body
	if font == null:
		return
	draw_string(font, pos, text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, color)


func _can_place_at(gx: int, gy: int) -> bool:
	if gx < 0 or gy < 0 or gx + _placing_w > _grid_w or gy + _placing_h > _grid_h:
		return false
	var occ := _occupied_set()
	for dy in range(_placing_h):
		for dx in range(_placing_w):
			var cx := gx + dx
			var cy := gy + dy
			if not _in_deed(cx, cy):
				return false
			if occ.has("%d,%d" % [cx, cy]):
				return false
	return true


func _free_cell_count() -> float:
	if _deed_cells.is_empty():
		return float(_grid_w * _grid_h - _occupied_set().size())
	var occ := _occupied_set()
	var free_n := 0
	for key in _deed_cells.keys():
		if not occ.has(key):
			free_n += 1
	return float(free_n)


func _road_cell_set() -> Dictionary:
	var out := {}
	for b in _placed_buildings:
		if not (b is Dictionary):
			continue
		if str(b.get("blueprint_id", b.get("building_id", ""))) != "road_segment":
			continue
		var bx := int(b.get("grid_x", 0))
		var by := int(b.get("grid_y", 0))
		var bw := int(b.get("footprint_w", 1))
		var bh := int(b.get("footprint_h", 1))
		for dy in range(bh):
			for dx in range(bw):
				out["%d,%d" % [bx + dx, by + dy]] = true
	return out


func _world_link_marker_pos(gx: int, gy: int, direction: String) -> Vector2:
	var r := _cell_rect(gx, gy)
	var c := r.get_center()
	var pad := mini(10.0, r.size.x * 0.35)
	match direction:
		"north":
			return Vector2(c.x, r.position.y + pad)
		"south":
			return Vector2(c.x, r.end.y - pad)
		"west":
			return Vector2(r.position.x + pad, c.y)
		"east":
			return Vector2(r.end.x - pad, c.y)
	return c


func _draw_world_link_ports(cs: float) -> void:
	if _interaction_mode != "roads" or _world_link_edges.is_empty():
		return
	for edge in _world_link_edges:
		if not (edge is Dictionary):
			continue
		var ed: Dictionary = edge as Dictionary
		var gx := int(ed.get("grid_x", -1))
		var gy := int(ed.get("grid_y", -1))
		if gx < 0:
			continue
		var direction := str(ed.get("direction", ""))
		var pos := _world_link_marker_pos(gx, gy, direction)
		var has_seg := bool(ed.get("segment_exists", false))
		var col := WORLD_LINK_DONE if has_seg else WORLD_LINK_COLOR
		var radius := clampf(cs * 0.22, 5.0, 11.0)
		draw_circle(pos, radius, col)
		draw_arc(pos, radius, 0.0, TAU, 24, Color(0.05, 0.05, 0.08, 0.85), 1.5, true)
		if cs >= 14.0:
			var nbr := str(ed.get("neighbor_plot_id", "")).split("-")[-1]
			_draw_text(pos + Vector2(-8, -radius - 4), nbr, 8, col)


func _hit_test_world_link(screen_pos: Vector2) -> String:
	if _interaction_mode != "roads":
		return ""
	var cs := _cell_size()
	var hit_r := clampf(cs * 0.35, 8.0, 16.0)
	for edge in _world_link_edges:
		if not (edge is Dictionary):
			continue
		var ed: Dictionary = edge as Dictionary
		if bool(ed.get("segment_exists", false)):
			continue
		var gx := int(ed.get("grid_x", -1))
		var gy := int(ed.get("grid_y", -1))
		if gx < 0:
			continue
		var pos := _world_link_marker_pos(gx, gy, str(ed.get("direction", "")))
		if pos.distance_to(screen_pos) <= hit_r:
			return str(ed.get("neighbor_plot_id", ""))
	return ""


func _draw_road_links(road_cells: Dictionary, cs: float) -> void:
	if road_cells.is_empty():
		return
	var occ := _occupied_set()
	for key in road_cells.keys():
		var parts: PackedStringArray = str(key).split(",")
		if parts.size() != 2:
			continue
		var gx := int(parts[0])
		var gy := int(parts[1])
		var center := _cell_rect(gx, gy).get_center()
		for off in [Vector2i(0, 1), Vector2i(0, -1), Vector2i(1, 0), Vector2i(-1, 0)]:
			var nk := "%d,%d" % [gx + off.x, gy + off.y]
			if road_cells.has(nk):
				draw_line(center, _cell_rect(gx + off.x, gy + off.y).get_center(), ROAD_EDGE, 2.0, true)
		for b in _placed_buildings:
			if not (b is Dictionary):
				continue
			var bid := str(b.get("blueprint_id", b.get("building_id", "")))
			if bid == "road_segment":
				continue
			var bx := int(b.get("grid_x", 0))
			var by := int(b.get("grid_y", 0))
			var bw := int(b.get("footprint_w", 1))
			var bh := int(b.get("footprint_h", 1))
			for dy in range(bh):
				for dx in range(bw):
					var cx := bx + dx
					var cy := by + dy
					if absi(cx - gx) + absi(cy - gy) == 1:
						var bcent := _cell_rect(cx, cy).get_center()
						draw_line(center, bcent, ROAD_LINK, 1.5, true)


func _stroke_add_cell(gx: int, gy: int) -> void:
	if not _in_deed(gx, gy):
		return
	if _occupied_set().has("%d,%d" % [gx, gy]):
		return
	_road_paint_stroke["%d,%d" % [gx, gy]] = true


func _stroke_line_to(gx: int, gy: int) -> void:
	if _road_last_cell.x < 0:
		_stroke_add_cell(gx, gy)
		_road_last_cell = Vector2i(gx, gy)
		return
	var x0 := _road_last_cell.x
	var y0 := _road_last_cell.y
	var x1 := gx
	var y1 := gy
	var n := maxi(absi(x1 - x0), absi(y1 - y0))
	for i in range(n + 1):
		var t := float(i) / float(maxi(n, 1))
		var cx := int(round(lerp(float(x0), float(x1), t)))
		var cy := int(round(lerp(float(y0), float(y1), t)))
		_stroke_add_cell(cx, cy)
	_road_last_cell = Vector2i(gx, gy)


func _finish_road_stroke() -> void:
	if _road_paint_stroke.is_empty():
		return
	var cells: Array = []
	for key in _road_paint_stroke.keys():
		var parts: PackedStringArray = str(key).split(",")
		if parts.size() == 2:
			cells.append(Vector2i(int(parts[0]), int(parts[1])))
	_road_paint_stroke.clear()
	_road_last_cell = Vector2i(-1, -1)
	if not cells.is_empty():
		road_path_painted.emit(cells)


func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion:
		var gpos := _screen_to_grid(event.position)
		if gpos.x >= 0:
			_hover_gx = gpos.x
			_hover_gy = gpos.y
			_hover_lot_idx = 0 if not _lots.is_empty() else -1
			cell_hovered.emit(gpos.x, gpos.y)
			if _is_road_paint_mode() and _road_drag_active:
				_stroke_line_to(gpos.x, gpos.y)
			queue_redraw()
	elif event is InputEventMouseButton:
		if event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
			if _is_road_paint_mode():
				var neighbor := _hit_test_world_link(event.position)
				if neighbor != "":
					world_link_clicked.emit(neighbor)
					accept_event()
					return
			var gpos := _screen_to_grid(event.position)
			if gpos.x >= 0:
				if _is_road_paint_mode():
					_road_drag_active = true
					_stroke_line_to(gpos.x, gpos.y)
					accept_event()
				elif _confirming:
					finish_confirm(true)
					accept_event()
				else:
					cell_clicked.emit(gpos.x, gpos.y)
		elif not event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
			if _road_drag_active:
				_road_drag_active = false
				_finish_road_stroke()
				accept_event()
		elif event.pressed and event.button_index == MOUSE_BUTTON_RIGHT:
			if _road_drag_active:
				_road_drag_active = false
				_road_paint_stroke.clear()
				_road_last_cell = Vector2i(-1, -1)
				queue_redraw()
				accept_event()
			elif _confirming:
				finish_confirm(false)
				accept_event()
			else:
				_confirming = false
				queue_redraw()
	elif event is InputEventKey and event.pressed and not event.echo and _confirming:
		if key_confirms(event as InputEventKey):
			finish_confirm(true)
			accept_event()
		elif key_cancels(event as InputEventKey):
			finish_confirm(false)
			accept_event()


func _screen_to_grid(screen_pos: Vector2) -> Vector2i:
	var cs := _cell_size()
	var o := _grid_origin()
	var gx := int((screen_pos.x - o.x) / cs)
	var gy := int((screen_pos.y - o.y) / cs)
	if gx < 0 or gy < 0 or gx >= _grid_w or gy >= _grid_h:
		return Vector2i(-1, -1)
	if not _in_deed(gx, gy):
		return Vector2i(-1, -1)
	return Vector2i(gx, gy)
