extends Node2D
## Organic jittered mesh map (visual parity with web ``RealmMapMeshPixi``).

const CELL_PX_MAX := 32.0
const CELL_PX_MIN := 4.5
## Multiply fit-to-view zoom so tiles read larger on screen (tune 1.0–2.0).
const DEFAULT_VIEW_ZOOM_BOOST := 1.4
const MESH_PAD := 12.0
const DEMO_SEED := 42
const DEMO_W := 48
const DEMO_H := 36
## Overview vs plot-level detail: when each cell is narrower than this on screen (in **pixels**),
## hide per-plot strokes and draw settlement-level chrome only (town bounds, nascent rings).
## Scales with zoom like Google Maps. Raise to show plot edges only when more zoomed in.
const DETAIL_MIN_CELL_SCREEN_PX := 14.0
## Future LOD hooks: add another threshold above to drop labels/owner fills, simplify terrain, etc.

signal plot_clicked(plot_id: String, plot_data: Dictionary)

@onready var camera: Camera2D = $Camera2D

var _mesh: MapOrganicMesh
var _world_seed: int = DEMO_SEED
var _selected_plot_id: String = ""
var _dragging: bool = false
var _did_drag: bool = false
var _did_fit_camera: bool = false

var _demo_mode: bool = false
var _view_size: Vector2 = Vector2(1200, 700)


func set_view_size(sz: Vector2) -> void:
	_view_size = sz
	if WorldState.plots.size() > 0 or _demo_mode:
		_rebuild_mesh()
		queue_redraw()
	_fit_camera_to_mesh()


func reset_view() -> void:
	_fit_camera_to_mesh()


func _ready() -> void:
	camera.enabled = true
	camera.make_current()
	WorldState.world_updated.connect(_on_world_updated)
	API.get_world(_on_world_loaded)


func _on_world_loaded(data: Dictionary) -> void:
	if not data.is_empty():
		WorldState.apply_world(data)
		_world_seed = int(data.get("seed", DEMO_SEED))
		_demo_mode = false
	else:
		_seed_demo_plots()
		_demo_mode = true
		WorldState.world_seed = DEMO_SEED
		WorldState.world_updated.emit()
	if WorldState.plots.is_empty():
		push_warning("Realm map: world payload had no plots — using demo grid (check GET /world)")
		_seed_demo_plots()
		_demo_mode = true
		WorldState.world_seed = DEMO_SEED
		WorldState.world_updated.emit()
	_rebuild_mesh()
	_fit_camera_to_mesh()
	queue_redraw()
	API.get_world_summary(WorldState.party_id, func(s): WorldState.apply_summary(s))


func _on_world_updated() -> void:
	if WorldState.plots.is_empty():
		return
	_rebuild_mesh()
	queue_redraw()
	call_deferred("_fit_camera_to_mesh")


func _seed_demo_plots() -> void:
	WorldState.plots.clear()
	var terrains: PackedStringArray = PackedStringArray([
		"plains", "forest", "mountain", "desert", "tundra", "swamp",
		"water_shallow", "water_deep", "hills", "coastal", "temperate_forest", "valley",
	])
	var rng := RandomNumberGenerator.new()
	rng.seed = DEMO_SEED
	for gy in range(DEMO_H):
		for gx in range(DEMO_W):
			var pid := "demo-%d-%d" % [gx, gy]
			var t_idx := int((hash32_demo(gx, gy) + gx * 3 + gy * 7) % terrains.size())
			var terrain: String = terrains[t_idx]
			if terrain.begins_with("water") and gy > 8 and gy < 14:
				terrain = "water_shallow" if rng.randf() > 0.4 else "water_deep"
			var owner_v: Variant = null
			if gx < 6 and gy < 5 and not terrain.begins_with("water"):
				owner_v = WorldState.party_id
			WorldState.plots[pid] = {
				"id": pid,
				"x": gx,
				"y": gy,
				"terrain": terrain,
				"owner": owner_v,
				"surveyed": owner_v == WorldState.party_id,
			}


func hash32_demo(gx: int, gy: int) -> int:
	return (gx * 374761393 + gy * 668265263) & 0x7FFFFFFF


func _grid_bounds() -> Vector2i:
	var mw := 1
	var mh := 1
	for plot_id in WorldState.plots.keys():
		var p: Dictionary = WorldState.plots[plot_id]
		mw = maxi(mw, int(p.get("x", 0)) + 1)
		mh = maxi(mh, int(p.get("y", 0)) + 1)
	if _demo_mode:
		mw = maxi(mw, DEMO_W)
		mh = maxi(mh, DEMO_H)
	return Vector2i(mw, mh)


func _cell_px_for_bounds(gw: int, gh: int) -> float:
	var vp := _view_size
	if vp.x < 32.0 or vp.y < 32.0:
		return CELL_PX_MAX * 0.5
	var margin := 56.0
	var inner_x := maxf(80.0, vp.x - margin)
	var inner_y := maxf(80.0, vp.y - margin)
	var pad_total := MESH_PAD * 2.0
	var cw := (inner_x - pad_total) / float(maxi(1, gw))
	var ch := (inner_y - pad_total) / float(maxi(1, gh))
	return clampf(minf(cw, ch), CELL_PX_MIN, CELL_PX_MAX)


func _rebuild_mesh() -> void:
	var bounds := _grid_bounds()
	var px := _cell_px_for_bounds(bounds.x, bounds.y)
	_mesh = MapOrganicMesh.new(_world_seed, bounds.x, bounds.y, MESH_PAD, px)


func _fit_camera_to_mesh() -> void:
	if _mesh == null:
		return
	var vp := _view_size
	if vp.x < 10.0:
		call_deferred("_fit_camera_to_mesh")
		return
	var content := Vector2(_mesh.content_width, _mesh.content_height)
	var margin := 32.0
	var zx := (vp.x - margin) / content.x
	var zy := (vp.y - margin) / content.y
	var z: float = clampf(minf(zx, zy) * DEFAULT_VIEW_ZOOM_BOOST, 0.35, 4.5)
	camera.zoom = Vector2(z, z)
	camera.position = content * 0.5
	_did_fit_camera = true
	queue_redraw()


func _draw() -> void:
	if _mesh == null:
		return
	# Deep void behind mesh
	draw_rect(Rect2(0, 0, _mesh.content_width, _mesh.content_height), RealmColors.BG2)
	var sorted: Array = []
	for plot_id in WorldState.plots.keys():
		var p: Dictionary = WorldState.plots[plot_id]
		sorted.append(p)
	sorted.sort_custom(func(a: Variant, b: Variant) -> bool:
		var ad: Dictionary = a as Dictionary
		var bd: Dictionary = b as Dictionary
		var asel := str(ad.get("id", "")) == _selected_plot_id
		var bsel := str(bd.get("id", "")) == _selected_plot_id
		if asel != bsel:
			return not asel
		return int(ad.get("y", 0)) < int(bd.get("y", 0))
	)
	var detail := _use_plot_detail()
	for item in sorted:
		_draw_plot(item as Dictionary, detail)
	if not detail:
		_draw_overview_settlement_chrome()


func _use_plot_detail() -> bool:
	if _mesh == null:
		return true
	var cell_screen: float = _mesh.cell_px * camera.zoom.x
	return cell_screen >= DETAIL_MIN_CELL_SCREEN_PX


func _world_line_width_screen_px(px: float) -> float:
	return px / maxf(0.001, camera.zoom.x)


func _town_bounds_poly(minx: int, miny: int, maxx: int, maxy: int) -> PackedVector2Array:
	var p00: Vector2 = _mesh.plot_polygon(minx, miny)[0]
	var p10: Vector2 = _mesh.plot_polygon(maxx, miny)[1]
	var p11: Vector2 = _mesh.plot_polygon(maxx, maxy)[2]
	var p01: Vector2 = _mesh.plot_polygon(minx, maxy)[3]
	return PackedVector2Array([p00, p10, p11, p01])


func _draw_overview_settlement_chrome() -> void:
	var outline_w := _world_line_width_screen_px(2.0)
	var accent := RealmColors.ACCENT
	accent.a = 0.62
	for t in WorldState.towns:
		if not (t is Dictionary):
			continue
		var td: Dictionary = t as Dictionary
		if td.has("bound_min_x"):
			var poly := _town_bounds_poly(
				int(td["bound_min_x"]),
				int(td["bound_min_y"]),
				int(td["bound_max_x"]),
				int(td["bound_max_y"])
			)
			draw_polyline(poly, accent, outline_w, true)
			draw_line(poly[poly.size() - 1], poly[0], accent, outline_w)
		else:
			var cx: int = int(td.get("center_x", -1))
			var cy: int = int(td.get("center_y", -1))
			if cx < 0 or cy < 0:
				continue
			var ctr := _mesh.plot_centroid(cx, cy)
			var r := 6.0 / maxf(0.001, camera.zoom.x)
			draw_arc(ctr, r, 0.0, TAU, 36, accent, maxf(outline_w, 1.0), true)


func _draw_plot(p: Dictionary, detail: bool) -> void:
	var gx := int(p.get("x", 0))
	var gy := int(p.get("y", 0))
	var poly := _mesh.plot_polygon(gx, gy)
	var terrain: String = str(p.get("terrain", "plains"))
	var fill: Color = RealmColors.terrain_color(terrain)
	if bool(p.get("surveyed", false)):
		fill = fill.lightened(0.06)
	if p.get("powered", true) == false:
		fill = fill.darkened(0.22)
	var pts: PackedVector2Array = PackedVector2Array([poly[0], poly[1], poly[2], poly[3]])
	draw_colored_polygon(pts, fill)
	var owner_v: Variant = p.get("owner", null)
	if owner_v != null:
		var tint := MapHash.owner_tint_color(str(owner_v))
		if tint.a > 0.01:
			draw_colored_polygon(pts, tint)
	var pid := str(p.get("id", ""))
	var is_sel := pid == _selected_plot_id
	if not detail:
		if is_sel:
			var sc := RealmColors.ACCENT
			var sw := _world_line_width_screen_px(3.5)
			draw_polyline(pts, sc, sw, true)
			draw_line(pts[3], pts[0], sc, sw)
		return
	var is_mine := str(owner_v) == WorldState.party_id
	var stroke_w := _world_line_width_screen_px(1.0)
	var stroke_c := Color(0, 0, 0, 0.38)
	if is_sel:
		stroke_c = RealmColors.ACCENT
		stroke_w = _world_line_width_screen_px(3.5)
	elif is_mine:
		stroke_c = RealmColors.MAGIC
		stroke_c.a = 0.55
		stroke_w = _world_line_width_screen_px(1.5)
	elif owner_v != null:
		stroke_c = MapHash.owner_accent_color(str(owner_v))
		stroke_c.a = 0.5
		stroke_w = _world_line_width_screen_px(1.25)
	draw_polyline(pts, stroke_c, stroke_w, true)
	draw_line(pts[3], pts[0], stroke_c, stroke_w)


func _unhandled_input(event: InputEvent) -> void:
	_handle_map_input(event)


func handle_gui_input(event: InputEvent) -> void:
	_handle_map_input(event)


func _handle_map_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.button_index == MOUSE_BUTTON_MIDDLE:
			_dragging = mb.pressed
		elif mb.button_index == MOUSE_BUTTON_LEFT:
			if mb.pressed:
				_dragging = true
				_did_drag = false
			else:
				if _dragging and not _did_drag:
					_handle_plot_click(mb.position)
				_dragging = false
		elif mb.button_index == MOUSE_BUTTON_WHEEL_UP and mb.pressed:
			_zoom_at_screen_pos(mb.position, 1.12)
		elif mb.button_index == MOUSE_BUTTON_WHEEL_DOWN and mb.pressed:
			_zoom_at_screen_pos(mb.position, 1.0 / 1.12)
		if mb.pressed or mb.button_index == MOUSE_BUTTON_LEFT:
			get_viewport().set_input_as_handled()
	elif event is InputEventMouseMotion and _dragging:
		var mm := event as InputEventMouseMotion
		if mm.relative.length_squared() > 4.0:
			_did_drag = true
		camera.position -= mm.relative / camera.zoom
		get_viewport().set_input_as_handled()


func _zoom_at_screen_pos(screen_pos: Vector2, factor: float) -> void:
	var world_before := _screen_to_world(screen_pos)
	camera.zoom = (camera.zoom * factor).clamp(Vector2(0.2, 0.2), Vector2(8.0, 8.0))
	camera.position += world_before - _screen_to_world(screen_pos)
	queue_redraw()


func _screen_to_world(screen_pos: Vector2) -> Vector2:
	return get_viewport().get_canvas_transform().affine_inverse() * screen_pos


func _handle_plot_click(screen_pos: Vector2) -> void:
	if _mesh == null:
		return
	var world_pos := _screen_to_world(screen_pos)
	var best_id := ""
	var best_d := 1e9
	var cell := _mesh.cell_px
	for plot_id in WorldState.plots.keys():
		var p: Dictionary = WorldState.plots[plot_id]
		var c := _mesh.plot_centroid(int(p.get("x", 0)), int(p.get("y", 0)))
		var d := world_pos.distance_squared_to(c)
		if d < best_d:
			best_d = d
			best_id = str(plot_id)
	var hit_r2: float = cell * cell * 4.0
	if best_id.is_empty() or best_d > hit_r2:
		return
	_selected_plot_id = best_id
	queue_redraw()
	plot_clicked.emit(best_id, WorldState.plots[best_id] as Dictionary)
