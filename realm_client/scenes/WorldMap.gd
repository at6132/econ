extends Node2D
## Organic jittered mesh map — Google Maps–style 5-level LOD + parity with web ``RealmMapMeshPixi``.

const WORLD_CELL_PX := 28.0
## World-space jitter amplitude derives from cell size (``MapOrganicMesh``).
const MESH_PAD := 12.0
## Zoom limits use ``_fit_ref_zoom`` = minimum zoom that **covers** the viewport (no side letterbox).
## ``1.0`` = cannot zoom out past that cover zoom (map always fills the map panel; excess crops top/bottom or sides).
const FIT_ZOOM_EPS := 1e-9
const ZOOM_RELATIVE_MIN := 1.0
## Enough headroom to multiply tiny overview zooms up to street-level; bounded below by hard max.
const ZOOM_RELATIVE_MAX := 65536.0
const CAM_ZOOM_ABS_MAX := 16384.0
const WHEEL_ZOOM_STEP := 1.18
const DEMO_SEED := 42
const DEMO_W := 48
const DEMO_H := 36

# ── LOD thresholds (cell pixels on screen: mesh cell × camera zoom) ─────────
const LOD_CONTINENT_MAX := 3.5
const LOD_ISLAND_MAX := 14.0
const LOD_REGION_MAX := 32.0
## Above: PLOT (labels, mine ring). At SITE and closer: per-building pads + abbrev on the parcel.
const LOD_PLOT_MAX := 56.0
## When more than this many cells are visible, use pre-aggregated paths (see ``MapLodCache``).
const OVERVIEW_DRAW_CELL_THRESHOLD := 1800
## Far zoom (between overview and full mesh): per-cell rects, not 16×16 chunk blocks.
const FAR_ALIGNED_DRAW_CELL_THRESHOLD := 600
const ALIGNED_DRAW_CELL_THRESHOLD := 1200

signal plot_clicked(plot_id: String, plot_data: Dictionary)

@onready var camera: Camera2D = $Camera2D

var _mesh: MapOrganicMesh
var _lod_cache: MapLodCache = MapLodCache.new()
## SubViewportContainer uses nearest only while drawing the overview texture.
var _subviewport_filter_overview: bool = false
var _world_seed: int = DEMO_SEED
var _selected_plot_id: String = ""
var _selected_gx: int = -1
var _selected_gy: int = -1
var _dragging: bool = false
var _did_drag: bool = false
var _did_fit_camera: bool = false

var _demo_mode: bool = false
## Initial guess until ``Main._layout_shell`` calls ``set_view_size`` (match ``project.godot`` default window).
var _view_size: Vector2 = Vector2(1920, 1080)
## Grid bounds used for the current ``_mesh``; rebuild when this changes.
var _last_mesh_bounds: Vector2i = Vector2i(-1, -1)
## ``apply_world`` emits ``world_updated`` during ``_on_world_loaded``; skip duplicate rebuild/fit.
var _loading_world: bool = false
## Last zoom from `_fit_camera_to_mesh` (full map in view). Wheel clamps are multiples of this.
var _fit_ref_zoom: float = 1.0
## Authoritative uniform zoom; kept in sync with `camera.zoom`.
var _cam_zoom: float = 1.0
## plot_id → building count (from ``WorldState.plot_buildings``; rebuilt on world updates).
var _plot_building_counts: Dictionary = {}
## plot_id → Array of building rows (same source) for SITE-level layout.
var _plot_buildings_by_plot: Dictionary = {}
## Cached visible-plot range (grid col/row bounds) — recalculated per draw.
var _vis_min_x: int = 0
var _vis_max_x: int = 0
var _vis_min_y: int = 0
var _vis_max_y: int = 0

# ── Pre-cached flat cell data (rebuilt on world change; eliminates string/dict ops from draw loop) ──
## Indexed by ``gy * _last_mesh_bounds.x + gx``. Null entries = no plot at that cell.
var _cell_colors: PackedColorArray = PackedColorArray()
var _cell_owner_tints: PackedColorArray = PackedColorArray()
var _cell_owner_accents: PackedColorArray = PackedColorArray()
## Bit flags per cell: 0x1 = has_plot, 0x2 = is_mine, 0x4 = surveyed, 0x8 = has_owner
var _cell_flags: PackedInt32Array = PackedInt32Array()
## String IDs (for selection check and higher LOD lookups). Flat indexed like above.
var _cell_pids: PackedStringArray = PackedStringArray()

## Overdraw buffer: we draw a region larger than the viewport, then skip redraws while the camera stays inside it.
const OVERDRAW_FACTOR := 1.8
var _drawn_world_rect: Rect2 = Rect2()
var _drawn_zoom: float = -1.0
## Zoom coalescing: accumulate zoom during rapid scrolling, apply once per frame.
var _zoom_pending_factor: float = 1.0
var _zoom_pending_pos: Vector2 = Vector2.ZERO
var _zoom_pending: bool = false
var _overlay_mode: String = "none"
var _overlay_mineral: String = "coal"
var _overlay_advantage_cat: String = "mining"


func set_view_size(sz: Vector2) -> void:
	var prev := _view_size
	var prev_ok := prev.x > 32.0 and prev.y > 32.0
	_view_size = sz
	# SubViewport size follows shell layout — scale camera zoom so framing stays stable.
	# Do **not** rebuild mesh from viewport (that erased wheel-zoom) or refit (that reset pan/zoom).
	if prev_ok and _did_fit_camera:
		var rf := minf(sz.x / maxf(prev.x, 1.0), sz.y / maxf(prev.y, 1.0))
		_cam_zoom = maxf(_cam_zoom * rf, FIT_ZOOM_EPS)
		_clamp_cam_zoom()
		_sync_camera_zoom()
		_clamp_camera_position()
	queue_redraw()


func reset_view() -> void:
	_fit_camera_to_mesh()


func set_overlay_mode(mode: String, mineral: String = "coal") -> void:
	_overlay_mode = mode
	if mineral != "":
		_overlay_mineral = mineral
	_rebuild_cell_cache()
	queue_redraw()


func _ready() -> void:
	camera.enabled = true
	camera.make_current()
	# Smoothing lags behind zoom/pivot corrections and breaks zoom-to-cursor inside SubViewport.
	camera.position_smoothing_enabled = false
	WorldState.world_updated.connect(_on_world_updated)
	WorldState.map_updated.connect(_on_map_ready)
	# Player-only updates (cash, inventory, owned plots) ride on the
	# realtime tick and don't need a 76800-cell cache rebuild.
	WorldState.player_updated.connect(_on_player_updated)
	call_deferred("_bootstrap_map_view")


func _bootstrap_map_view() -> void:
	if not WorldState.plots.is_empty():
		_refresh_map_view_from_world_state()


func _on_map_ready() -> void:
	_refresh_map_view_from_world_state()


func _refresh_map_view_from_world_state() -> void:
	if WorldState.plots.is_empty():
		return
	_loading_world = true
	_sync_demo_mode_from_world()
	_world_seed = int(WorldState.world_seed)
	_rebuild_mesh()
	_rebuild_building_cache()
	_fit_camera_to_mesh()
	_loading_world = false
	queue_redraw()
	API.get_world_summary(WorldState.party_id, func(s): WorldState.apply_summary(s))


func _on_player_updated() -> void:
	if _loading_world:
		return
	if WorldState.plots.is_empty():
		return
	# Rebuild the per-plot building counts (cheap — iterates
	# ``plot_buildings`` which is a small list). Do NOT touch the
	# 76800-cell colour cache here; that only changes when the map
	# itself changes (claim / survey / build → apply_map).
	_rebuild_building_cache_only()
	_invalidate_draw_buffer()


func _on_world_updated() -> void:
	if _loading_world:
		return
	if WorldState.plots.is_empty():
		return
	_sync_demo_mode_from_world()
	var bounds_now := _grid_bounds()
	# Mesh must exist before the cell cache; otherwise _draw() bails out on
	# empty ``_cell_flags`` and the viewport stays blank.
	if _mesh == null or _cell_flags.is_empty() or bounds_now != _last_mesh_bounds:
		_refresh_map_view_from_world_state()
		return
	_rebuild_building_cache_only()
	_invalidate_draw_buffer()


## Keep ``_demo_mode`` aligned with ``WorldState.plots`` keys. A stale
## ``_demo_mode`` after ``apply_map`` leaves ``demo-*`` in ``_cell_pids``
## while plots use ``p-x-y`` — click then crashes on ``plots[best_id]``.
func _sync_demo_mode_from_world() -> void:
	if WorldState.plots.is_empty():
		return
	for pid in WorldState.plots.keys():
		if not str(pid).begins_with("demo-"):
			_demo_mode = false
			return
	_demo_mode = true


func _plot_dict_for_cell(pid: String, gx: int, gy: int) -> Dictionary:
	var p: Dictionary = WorldState.plots.get(pid, {})
	if not p.is_empty():
		return p
	var canonical := "p-%d-%d" % [gx, gy]
	return WorldState.plots.get(canonical, {})


func _rebuild_building_cache() -> void:
	_rebuild_building_cache_only()
	_rebuild_cell_cache()


## Just the buildings-by-plot index. Called on the realtime tick via
## ``player_updated``; cheap (iterates a small list).
func _rebuild_building_cache_only() -> void:
	_plot_building_counts.clear()
	_plot_buildings_by_plot.clear()
	for row in WorldState.plot_buildings:
		if not (row is Dictionary):
			continue
		var d: Dictionary = row as Dictionary
		var pid := str(d.get("plot_id", ""))
		if pid.is_empty():
			continue
		_plot_building_counts[pid] = int(_plot_building_counts.get(pid, 0)) + 1
		if not _plot_buildings_by_plot.has(pid):
			_plot_buildings_by_plot[pid] = []
		(_plot_buildings_by_plot[pid] as Array).append(d)


func _rebuild_cell_cache() -> void:
	_sync_demo_mode_from_world()
	var bx := _last_mesh_bounds.x
	var by := _last_mesh_bounds.y
	if bx <= 0 or by <= 0:
		return
	var total := bx * by
	_cell_colors.resize(total)
	_cell_owner_tints.resize(total)
	_cell_owner_accents.resize(total)
	_cell_flags.resize(total)
	_cell_pids.resize(total)
	var my_party := WorldState.party_id
	var transparent := Color(0.0, 0.0, 0.0, 0.0)
	for gy in range(by):
		for gx in range(bx):
			var idx := gy * bx + gx
			var pid: String
			if _demo_mode:
				pid = "demo-%d-%d" % [gx, gy]
			else:
				var key := "%d,%d" % [gx, gy]
				if WorldState.world_cell_to_plot.has(key):
					pid = str(WorldState.world_cell_to_plot[key])
				elif WorldState.plots.has("p-%d-%d" % [gx, gy]):
					pid = "p-%d-%d" % [gx, gy]
				else:
					pid = ""
			_cell_pids[idx] = pid
			var p: Dictionary = WorldState.plots.get(pid, {})
			if p.is_empty():
				_cell_flags[idx] = 0
				_cell_colors[idx] = transparent
				_cell_owner_tints[idx] = transparent
				_cell_owner_accents[idx] = transparent
				continue
			var terrain: String = str(p.get("terrain", "plains"))
			var fill: Color = RealmColors.terrain_color(terrain)
			if bool(p.get("surveyed", false)):
				fill = fill.lightened(0.06)
			if p.get("powered", true) == false:
				fill = fill.darkened(0.22)
			var ov := MapOverlays.overlay_tint_for_plot(
				_overlay_mode, p, my_party, _overlay_mineral
			)
			if ov.a > 0.01:
				fill = fill.lerp(ov, clampf(ov.a, 0.0, 1.0))
			_cell_colors[idx] = fill
			var flags := 0x1
			var owner_v: Variant = p.get("owner", null)
			if owner_v != null:
				flags |= 0x8
				var ov_str := str(owner_v)
				if ov_str == my_party:
					flags |= 0x2
				_cell_owner_tints[idx] = MapHash.owner_tint_color(ov_str)
				_cell_owner_accents[idx] = MapHash.owner_accent_color(ov_str)
			else:
				_cell_owner_tints[idx] = transparent
				_cell_owner_accents[idx] = transparent
			if bool(p.get("surveyed", false)):
				flags |= 0x4
			_cell_flags[idx] = flags
	_lod_cache.rebuild(bx, by, _cell_colors, _cell_flags, RealmColors.BG2)
	_invalidate_draw_buffer()


func _seed_demo_plots() -> void:
	WorldState.plots.clear()
	WorldState.world_cell_to_plot.clear()
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
	if not _demo_mode and not WorldState.world_cell_to_plot.is_empty():
		for key in WorldState.world_cell_to_plot.keys():
			var parts: PackedStringArray = str(key).split(",")
			if parts.size() != 2:
				continue
			mw = maxi(mw, int(parts[0]) + 1)
			mh = maxi(mh, int(parts[1]) + 1)
	for plot_id in WorldState.plots.keys():
		var p: Dictionary = WorldState.plots[plot_id]
		var cells: Variant = p.get("world_cells", [])
		if cells is Array and not (cells as Array).is_empty():
			for c in cells:
				if c is Dictionary:
					mw = maxi(mw, int((c as Dictionary).get("x", 0)) + 1)
					mh = maxi(mh, int((c as Dictionary).get("y", 0)) + 1)
		else:
			mw = maxi(mw, int(p.get("x", 0)) + 1)
			mh = maxi(mh, int(p.get("y", 0)) + 1)
	if _demo_mode:
		mw = maxi(mw, DEMO_W)
		mh = maxi(mh, DEMO_H)
	return Vector2i(mw, mh)


func _rebuild_mesh() -> void:
	var bounds := _grid_bounds()
	_mesh = MapOrganicMesh.new(_world_seed, bounds.x, bounds.y, MESH_PAD, WORLD_CELL_PX)
	_last_mesh_bounds = bounds


## Minimum Camera2D.zoom so the map **covers** ``_view_size`` (CSS ``object-fit: cover`` — no letterbox bars).
## Higher than ``min(vp/content)``; may crop an edge until you pan.
func _min_zoom_viewport_cover_map() -> float:
	if _mesh == null or _view_size.x < 10.0:
		return FIT_ZOOM_EPS
	var content := Vector2(_mesh.content_width, _mesh.content_height)
	var zx := _view_size.x / maxf(content.x, FIT_ZOOM_EPS)
	var zy := _view_size.y / maxf(content.y, FIT_ZOOM_EPS)
	return maxf(maxf(zx, zy), FIT_ZOOM_EPS)


## Keep the camera center inside bounds so the viewport never shows void outside the map.
func _clamp_camera_position() -> void:
	if _mesh == null or _view_size.x < 10.0:
		return
	var z := maxf(_cam_zoom, FIT_ZOOM_EPS)
	var cx := _mesh.content_width
	var cy := _mesh.content_height
	var hw := _view_size.x / (2.0 * z)
	var hh := _view_size.y / (2.0 * z)
	var min_x := hw
	var max_x := cx - hw
	var min_y := hh
	var max_y := cy - hh
	if min_x > max_x:
		camera.position.x = cx * 0.5
	else:
		camera.position.x = clampf(camera.position.x, min_x, max_x)
	if min_y > max_y:
		camera.position.y = cy * 0.5
	else:
		camera.position.y = clampf(camera.position.y, min_y, max_y)


func _fit_camera_to_mesh() -> void:
	if _mesh == null:
		return
	var vp := _view_size
	if vp.x < 10.0:
		call_deferred("_fit_camera_to_mesh")
		return
	var content := Vector2(_mesh.content_width, _mesh.content_height)
	var z_fit: float = _min_zoom_viewport_cover_map()
	_fit_ref_zoom = z_fit
	_cam_zoom = z_fit
	_sync_camera_zoom()
	camera.position = content * 0.5
	_clamp_camera_position()
	_did_fit_camera = true
	queue_redraw()


func _clamp_cam_zoom() -> void:
	var z_fit := _min_zoom_viewport_cover_map()
	_fit_ref_zoom = z_fit
	var z_min := z_fit * ZOOM_RELATIVE_MIN
	var z_max := minf(z_fit * ZOOM_RELATIVE_MAX, CAM_ZOOM_ABS_MAX)
	_cam_zoom = clampf(_cam_zoom, z_min, z_max)


func _sync_camera_zoom() -> void:
	camera.zoom = Vector2(_cam_zoom, _cam_zoom)


func _visible_world_rect() -> Rect2:
	var z := maxf(_cam_zoom, FIT_ZOOM_EPS)
	var hw := _view_size.x / (2.0 * z)
	var hh := _view_size.y / (2.0 * z)
	return Rect2(camera.position.x - hw, camera.position.y - hh, 2.0 * hw, 2.0 * hh)


func _invalidate_draw_buffer() -> void:
	_drawn_zoom = -1.0
	queue_redraw()


func _viewport_inside_drawn_buffer() -> bool:
	if _drawn_zoom < 0.0:
		return false
	if absf(_cam_zoom - _drawn_zoom) > 0.001:
		return false
	var vr := _visible_world_rect()
	return _drawn_world_rect.encloses(vr)


func _visible_cell_count() -> int:
	return maxi(0, (_vis_max_x - _vis_min_x) * (_vis_max_y - _vis_min_y))


func _draw() -> void:
	if _mesh == null or _cell_flags.is_empty():
		return
	# Fill everything the camera sees (kills SubViewport letterbox / wrong clear around the mesh).
	draw_rect(_visible_world_rect(), RealmColors.BG2)
	draw_rect(Rect2(0, 0, _mesh.content_width, _mesh.content_height), RealmColors.BG2)

	var lod := _lod()
	var csp := _cell_screen_px()
	_compute_visible_range_overdraw()
	var vis_cells := _visible_cell_count()

	# Record what we drew for the overdraw buffer check.
	_drawn_zoom = _cam_zoom
	_drawn_world_rect = _overdraw_world_rect()

	var bx := _last_mesh_bounds.x
	var sel_gx := _selected_gx
	var sel_gy := _selected_gy

	_sync_subviewport_pixel_filter()

	if _uses_overview_draw():
		_draw_overview_terrain()
		_draw_selection_highlight(sel_gx, sel_gy)
		_draw_town_dots()
		return

	# Square map cells — matches engine hectare grid and multi-tile deeds (no wavy quads).
	var draw_cell_strokes := lod >= 2 and vis_cells < FAR_ALIGNED_DRAW_CELL_THRESHOLD
	if draw_cell_strokes:
		_draw_aligned_cell_terrain_stroked(sel_gx, sel_gy, lod)
	else:
		_draw_aligned_cell_terrain()
	_draw_parcel_boundaries(lod)
	_draw_selection_highlight(sel_gx, sel_gy)
	_draw_town_dots()
	_draw_town_chrome(lod, csp)

	if lod >= 2 and lod < 4:
		_draw_building_dots()
	elif lod >= 4:
		_draw_site_layout()

	if lod >= 3:
		_draw_plot_detail_labels()


func _draw_overview_terrain() -> void:
	var tex := _lod_cache.overview_texture
	if tex == null:
		return
	var prev_filter := texture_filter
	texture_filter = TEXTURE_FILTER_NEAREST
	draw_texture_rect(
		tex,
		Rect2(0.0, 0.0, _mesh.content_width, _mesh.content_height),
		false
	)
	texture_filter = prev_filter


func _cell_rect(gx: int, gy: int) -> Rect2:
	var cp := _mesh.cell_px
	var pad := _mesh.pad
	return Rect2(pad + float(gx) * cp, pad + float(gy) * cp, cp, cp)


func _neighbor_same_parcel(gx: int, gy: int, dx: int, dy: int) -> bool:
	var bx := _last_mesh_bounds.x
	var by := _last_mesh_bounds.y
	var nx := gx + dx
	var ny := gy + dy
	if nx < 0 or ny < 0 or nx >= bx or ny >= by:
		return false
	var idx := gy * bx + gx
	var nidx := ny * bx + nx
	if (_cell_flags[idx] & 0x1) == 0 or (_cell_flags[nidx] & 0x1) == 0:
		return false
	return _cell_pids[idx] == _cell_pids[nidx]


func _draw_aligned_cell_terrain() -> void:
	var bx := _last_mesh_bounds.x
	for gy in range(_vis_min_y, _vis_max_y):
		var row_off := gy * bx
		for gx in range(_vis_min_x, _vis_max_x):
			var idx := row_off + gx
			if (_cell_flags[idx] & 0x1) == 0:
				continue
			draw_rect(_cell_rect(gx, gy), _cell_colors[idx])


func _draw_aligned_cell_terrain_stroked(sel_gx: int, sel_gy: int, lod: int) -> void:
	var bx := _last_mesh_bounds.x
	var stroke_w_base := _world_line_width(1.0)
	var stroke_w_mine := _world_line_width(1.5)
	var stroke_w_other := _world_line_width(1.25)
	var mine_ring_r := _mesh.cell_px * 0.28
	var mine_ring_w := stroke_w_base
	var default_stroke_c := Color(0, 0, 0, 0.38)

	for gy in range(_vis_min_y, _vis_max_y):
		var row_off := gy * bx
		for gx in range(_vis_min_x, _vis_max_x):
			var idx := row_off + gx
			var flags := _cell_flags[idx]
			if (flags & 0x1) == 0:
				continue
			var r := _cell_rect(gx, gy)
			draw_rect(r, _cell_colors[idx])
			if (flags & 0x8) != 0:
				var tint := _cell_owner_tints[idx]
				if tint.a > 0.01:
					draw_rect(r, tint)

			var is_mine := (flags & 0x2) != 0
			var is_sel := gx == sel_gx and gy == sel_gy
			if is_sel:
				continue

			var stroke_w: float
			var stroke_c: Color
			if is_mine:
				stroke_c = RealmColors.MAGIC
				stroke_c.a = 0.55
				stroke_w = stroke_w_mine
			elif (flags & 0x8) != 0:
				stroke_c = _cell_owner_accents[idx]
				stroke_c.a = 0.5
				stroke_w = stroke_w_other
			else:
				stroke_c = default_stroke_c
				stroke_w = stroke_w_base

			# Only stroke deed boundaries — skip edges shared with the same parcel.
			if not _neighbor_same_parcel(gx, gy, 0, -1):
				draw_line(r.position, r.position + Vector2(r.size.x, 0.0), stroke_c, stroke_w)
			if not _neighbor_same_parcel(gx, gy, 0, 1):
				draw_line(r.end, r.end - Vector2(r.size.x, 0.0), stroke_c, stroke_w)
			if not _neighbor_same_parcel(gx, gy, -1, 0):
				draw_line(r.position, r.position + Vector2(0.0, r.size.y), stroke_c, stroke_w)
			if not _neighbor_same_parcel(gx, gy, 1, 0):
				draw_line(r.end, r.end - Vector2(0.0, r.size.y), stroke_c, stroke_w)

			if lod >= 3 and is_mine:
				var ctr := r.position + r.size * 0.5
				var ring_c := RealmColors.MAGIC
				ring_c.a = 0.35
				draw_arc(ctr, mine_ring_r, 0.0, TAU, 10, ring_c, mine_ring_w)


func _draw_selection_highlight(sel_gx: int, sel_gy: int) -> void:
	if sel_gx < _vis_min_x or sel_gx >= _vis_max_x or sel_gy < _vis_min_y or sel_gy >= _vis_max_y:
		return
	var bx := _last_mesh_bounds.x
	var sel_idx := sel_gy * bx + sel_gx
	if (_cell_flags[sel_idx] & 0x1) == 0:
		return
	var sw := _world_line_width(3.5)
	var accent := RealmColors.ACCENT
	var pid := _cell_pids[sel_idx]
	if pid.is_empty():
		draw_rect(_cell_rect(sel_gx, sel_gy), Color(accent, 0.0), false, sw)
		return
	# Highlight the whole deed when it spans multiple map cells.
	var cells_v: Variant = WorldState.plots.get(pid, {}).get("world_cells", [])
	if cells_v is Array and (cells_v as Array).size() > 1:
		var cell_set: Dictionary = {}
		for c in cells_v as Array:
			if c is Dictionary:
				var d: Dictionary = c as Dictionary
				cell_set["%d,%d" % [int(d.get("x", 0)), int(d.get("y", 0))]] = true
		var deed_rect := _parcel_aligned_rect(cell_set)
		if deed_rect.size.x > 0.0:
			draw_rect(deed_rect, Color(accent, 0.0), false, sw)
			return
	draw_rect(_cell_rect(sel_gx, sel_gy), Color(accent, 0.0), false, sw)


func _overdraw_world_rect() -> Rect2:
	var z := maxf(_cam_zoom, FIT_ZOOM_EPS)
	var hw := _view_size.x / (2.0 * z) * OVERDRAW_FACTOR
	var hh := _view_size.y / (2.0 * z) * OVERDRAW_FACTOR
	return Rect2(camera.position.x - hw, camera.position.y - hh, 2.0 * hw, 2.0 * hh)


func _compute_visible_range_overdraw() -> void:
	var odr := _overdraw_world_rect()
	var bounds := _last_mesh_bounds
	_vis_min_x = maxi(0, int((odr.position.x - _mesh.pad) / _mesh.cell_px) - 1)
	_vis_min_y = maxi(0, int((odr.position.y - _mesh.pad) / _mesh.cell_px) - 1)
	_vis_max_x = mini(bounds.x, int((odr.end.x - _mesh.pad) / _mesh.cell_px) + 2)
	_vis_max_y = mini(bounds.y, int((odr.end.y - _mesh.pad) / _mesh.cell_px) + 2)
	# Cap: if overdraw produces too many cells, shrink to 1× viewport.
	var cell_count := (_vis_max_x - _vis_min_x) * (_vis_max_y - _vis_min_y)
	if cell_count > 4000:
		var vr := _visible_world_rect()
		_vis_min_x = maxi(0, int((vr.position.x - _mesh.pad) / _mesh.cell_px) - 1)
		_vis_min_y = maxi(0, int((vr.position.y - _mesh.pad) / _mesh.cell_px) - 1)
		_vis_max_x = mini(bounds.x, int((vr.end.x - _mesh.pad) / _mesh.cell_px) + 2)
		_vis_max_y = mini(bounds.y, int((vr.end.y - _mesh.pad) / _mesh.cell_px) + 2)


func _cell_screen_px() -> float:
	if _mesh == null:
		return 0.0
	return _mesh.cell_px * camera.zoom.x


## Returns 0=CONTINENT, 1=ISLAND, 2=REGION, 3=PLOT, 4=SITE (building pads on parcel).
func _lod() -> int:
	var csp := _cell_screen_px()
	if csp < LOD_CONTINENT_MAX:
		return 0
	if csp < LOD_ISLAND_MAX:
		return 1
	if csp < LOD_REGION_MAX:
		return 2
	if csp < LOD_PLOT_MAX:
		return 3
	return 4


## Precomputed overview texture (max zoom-out only).
func _uses_overview_draw() -> bool:
	if _mesh == null or not _lod_cache.overview_ready:
		return false
	if _lod() > 1:
		return false
	_compute_visible_range_overdraw()
	return _visible_cell_count() >= OVERVIEW_DRAW_CELL_THRESHOLD


func _overview_lod_active() -> bool:
	return _uses_overview_draw()


func _sync_subviewport_pixel_filter() -> void:
	var want_nearest := _uses_overview_draw()
	if want_nearest == _subviewport_filter_overview:
		return
	_subviewport_filter_overview = want_nearest
	var vp := get_viewport()
	if vp == null:
		return
	var container := vp.get_parent()
	if container is SubViewportContainer:
		container.texture_filter = (
			TEXTURE_FILTER_NEAREST if want_nearest else TEXTURE_FILTER_LINEAR
		)


func _world_line_width(screen_px: float) -> float:
	return screen_px / maxf(0.001, camera.zoom.x)


func _town_bounds_poly(minx: int, miny: int, maxx: int, maxy: int) -> PackedVector2Array:
	var p00: Vector2 = _mesh.plot_polygon(minx, miny)[0]
	var p10: Vector2 = _mesh.plot_polygon(maxx, miny)[1]
	var p11: Vector2 = _mesh.plot_polygon(maxx, maxy)[2]
	var p01: Vector2 = _mesh.plot_polygon(minx, maxy)[3]
	return PackedVector2Array([p00, p10, p11, p01])


## Terrain drawing is now inlined in ``_draw()`` using flat pre-cached arrays.


func _parcel_aligned_rect(cell_set: Dictionary) -> Rect2:
	if cell_set.is_empty() or _mesh == null:
		return Rect2()
	var min_gx := 1_000_000
	var min_gy := 1_000_000
	var max_gx := -1
	var max_gy := -1
	for key in cell_set.keys():
		var parts: PackedStringArray = str(key).split(",")
		if parts.size() != 2:
			continue
		var gx := int(parts[0])
		var gy := int(parts[1])
		min_gx = mini(min_gx, gx)
		min_gy = mini(min_gy, gy)
		max_gx = maxi(max_gx, gx)
		max_gy = maxi(max_gy, gy)
	if max_gx < min_gx:
		return Rect2()
	var cp := _mesh.cell_px
	var pad := _mesh.pad
	return Rect2(
		pad + float(min_gx) * cp,
		pad + float(min_gy) * cp,
		float(max_gx - min_gx + 1) * cp,
		float(max_gy - min_gy + 1) * cp,
	)


func _draw_parcel_boundaries(lod: int) -> void:
	## Gold frame around multi-hectare deeds (2×1, 2×2, …).
	if _demo_mode or lod < 2 or _mesh == null:
		return
	var stroke_c := Color(0.95, 0.78, 0.22, 0.95)
	var stroke_w := _world_line_width(3.0)
	for plot_id in WorldState.plots.keys():
		var p: Dictionary = WorldState.plots[plot_id]
		var cells_v: Variant = p.get("world_cells", [])
		if not (cells_v is Array):
			continue
		var cells_arr: Array = cells_v as Array
		if cells_arr.size() <= 1:
			continue
		var cell_set: Dictionary = {}
		var any_visible := false
		for c in cells_arr:
			if not (c is Dictionary):
				continue
			var d: Dictionary = c as Dictionary
			var gx := int(d.get("x", 0))
			var gy := int(d.get("y", 0))
			cell_set["%d,%d" % [gx, gy]] = true
			if gx >= _vis_min_x and gx < _vis_max_x and gy >= _vis_min_y and gy < _vis_max_y:
				any_visible = true
		if not any_visible:
			continue
		var deed_rect := _parcel_aligned_rect(cell_set)
		if deed_rect.size.x > 0.0:
			draw_rect(deed_rect, Color(stroke_c, 0.0), false, stroke_w)


func _draw_town_dots() -> void:
	var dot_r := _world_line_width(1.5)
	for t in WorldState.towns:
		if not (t is Dictionary):
			continue
		var td: Dictionary = t as Dictionary
		var cx: int = int(td.get("center_x", -1))
		var cy: int = int(td.get("center_y", -1))
		if cx < 0 or cy < 0:
			continue
		if cx < _vis_min_x or cx >= _vis_max_x or cy < _vis_min_y or cy >= _vis_max_y:
			continue
		var ctr := _mesh.plot_centroid(cx, cy)
		draw_circle(ctr, dot_r, RealmColors.ACCENT)


func _draw_town_chrome(lod: int, csp: float) -> void:
	var outline_w := _world_line_width(2.0)
	var accent := RealmColors.ACCENT
	accent.a = 0.62

	var label_alpha := clampf((csp - 6.0) / 8.0, 0.0, 1.0)
	var font: Font = RealmFonts.font_body

	for t in WorldState.towns:
		if not (t is Dictionary):
			continue
		var td: Dictionary = t as Dictionary
		var cx: int = int(td.get("center_x", -1))
		var cy: int = int(td.get("center_y", -1))
		if cx < 0 or cy < 0:
			continue
		if cx < _vis_min_x - 5 or cx >= _vis_max_x + 5 or cy < _vis_min_y - 5 or cy >= _vis_max_y + 5:
			continue
		var ctr := _mesh.plot_centroid(cx, cy)

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
			var r := 6.0 / maxf(0.001, camera.zoom.x)
			draw_arc(ctr, r, 0.0, TAU, 36, accent, maxf(outline_w, 1.0), true)

		if font != null and label_alpha > 0.05:
			var town_name: String = str(td.get("name", "Town"))
			var pop: int = int(td.get("laborer_count", 0))
			var label_text := town_name
			if lod >= 2 and pop > 0:
				label_text = "%s  (%d)" % [town_name, pop]
			var font_size_world := clampi(int(_world_line_width(14.0)), 8, 24)
			var sz := font.get_string_size(label_text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size_world)
			var label_col := RealmColors.ACCENT
			label_col.a = label_alpha
			var label_pos := ctr + Vector2(-sz.x * 0.5, -_world_line_width(10.0))
			draw_string(font, label_pos, label_text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size_world, label_col)


func _draw_building_dots() -> void:
	var dot_r := _world_line_width(2.5)
	var bx := _last_mesh_bounds.x
	for gy in range(_vis_min_y, _vis_max_y):
		var row_off := gy * bx
		for gx in range(_vis_min_x, _vis_max_x):
			var idx := row_off + gx
			if (_cell_flags[idx] & 0x1) == 0:
				continue
			var pid := _cell_pids[idx]
			if not _plot_building_counts.has(pid):
				continue
			var ctr := _mesh.plot_centroid(gx, gy)
			var is_mine := (_cell_flags[idx] & 0x2) != 0
			var dot_col := RealmColors.ACCENT if is_mine else RealmColors.MUTED
			dot_col.a = 0.85
			draw_circle(ctr, dot_r, dot_col)


func _plot_aabb_from_poly(poly: PackedVector2Array) -> Rect2:
	var mn := poly[0]
	var mx := poly[0]
	for k in range(1, 4):
		mn.x = minf(mn.x, poly[k].x)
		mn.y = minf(mn.y, poly[k].y)
		mx.x = maxf(mx.x, poly[k].x)
		mx.y = maxf(mx.y, poly[k].y)
	return Rect2(mn, mx - mn)


func _abbrev_building_id(building_id: String) -> String:
	var s := building_id
	var u := s.rfind("_")
	if u >= 0 and u + 1 < s.length():
		s = s.substr(u + 1)
	if s.length() > 6:
		s = s.substr(0, 6)
	return s


## SITE LOD: building footpads in a grid inside the plot, readable at very high zoom.
func _draw_site_layout() -> void:
	var font: Font = RealmFonts.font_body
	var pad_w := _world_line_width(1.25)
	var label_fs := clampi(int(_world_line_width(10.0)), 6, 20)
	var bx := _last_mesh_bounds.x
	for gy in range(_vis_min_y, _vis_max_y):
		var row_off := gy * bx
		for gx in range(_vis_min_x, _vis_max_x):
			var idx := row_off + gx
			if (_cell_flags[idx] & 0x1) == 0:
				continue
			var pid := _cell_pids[idx]
			if not _plot_buildings_by_plot.has(pid):
				continue
			var p: Dictionary = WorldState.plots.get(pid, {})
			if p.is_empty():
				continue
			var poly := _mesh.plot_polygon(gx, gy)
			var pts := PackedVector2Array([poly[0], poly[1], poly[2], poly[3]])
			var bbox := _plot_aabb_from_poly(pts)
			var inset := _mesh.cell_px * 0.12
			bbox = bbox.grow(-inset)
			if bbox.size.x < 4.0 or bbox.size.y < 4.0:
				continue
			var rows: Array = _plot_buildings_by_plot[pid] as Array
			var n := rows.size()
			if n < 1:
				continue
			var is_mine := (_cell_flags[idx] & 0x2) != 0
			var cols_i := maxi(1, int(ceil(sqrt(float(n)))))
			var nrows_i := maxi(1, int(ceil(float(n) / float(cols_i))))
			var gap := _mesh.cell_px * 0.06
			var cell_w := (bbox.size.x - gap * float(cols_i - 1)) / float(cols_i)
			var cell_h := (bbox.size.y - gap * float(nrows_i - 1)) / float(nrows_i)
			cell_w = maxf(cell_w, _mesh.cell_px * 0.08)
			cell_h = maxf(cell_h, _mesh.cell_px * 0.08)
			for i in range(n):
				var row: Dictionary = rows[i] as Dictionary
				var row_i := int(floor(float(i) / float(cols_i)))
				var col_i := i % cols_i
				var x0 := bbox.position.x + float(col_i) * (cell_w + gap)
				var y0 := bbox.position.y + float(row_i) * (cell_h + gap)
				var pad := Rect2(Vector2(x0, y0), Vector2(cell_w, cell_h))
				var fill_c := RealmColors.PANEL
				fill_c.a = 0.72 if is_mine else 0.5
				var stroke_c := RealmColors.ACCENT if is_mine else RealmColors.BORDER_LIT
				stroke_c.a = 0.95 if is_mine else 0.65
				draw_rect(pad, fill_c, true)
				draw_rect(pad, stroke_c, false, pad_w)
				var bid := str(row.get("building_id", "?"))
				var abbrev := _abbrev_building_id(bid)
				if font != null and not abbrev.is_empty():
					var tc := RealmColors.TEXT
					tc.a = 0.92
					var sz := font.get_string_size(abbrev, HORIZONTAL_ALIGNMENT_CENTER, -1, label_fs)
					var tp := Vector2(
						pad.position.x + (pad.size.x - sz.x) * 0.5,
						pad.position.y + (pad.size.y - sz.y) * 0.5
					)
					draw_string(
						font,
						tp,
						abbrev,
						HORIZONTAL_ALIGNMENT_LEFT,
						-1,
						label_fs,
						tc
					)


func _draw_plot_detail_labels() -> void:
	var font: Font = RealmFonts.font_body
	if font == null:
		return

	var lod_now := _lod()
	var font_size := clampi(int(_world_line_width(11.0)), 6, 24 if lod_now >= 4 else 18)

	var grade_keys: Array = [
		["iron_ore_grade", "Fe"],
		["copper_ore_grade", "Cu"],
		["coal_grade", "Co"],
		["clay_grade", "Cl"],
		["phosphate_grade", "Ph"],
		["sulfur_grade", "Su"],
		["saltpeter_grade", "Sa"],
		["tin_grade", "Ti"],
		["lead_grade", "Pb"],
		["silica_grade", "Si"],
		["platinum_grade", "Pt"],
		["oil_shale_grade", "Oil"],
		["rare_earth_grade", "RE"],
	]

	var bx := _last_mesh_bounds.x
	for gy in range(_vis_min_y, _vis_max_y):
		var row_off := gy * bx
		for gx in range(_vis_min_x, _vis_max_x):
			var idx := row_off + gx
			if (_cell_flags[idx] & 0x3) != 0x3:
				continue
			var pid := _cell_pids[idx]

			var ctr := _mesh.plot_centroid(gx, gy)

			var bcount: int = int(_plot_building_counts.get(pid, 0))
			if bcount > 0:
				var badge := "⚙%d" % bcount
				var badge_col := RealmColors.ACCENT
				badge_col.a = 0.9
				var bpos := ctr + Vector2(_world_line_width(-6.0), _world_line_width(-4.0))
				draw_string(font, bpos, badge, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, badge_col)

			if (_cell_flags[idx] & 0x4) == 0:
				continue

			var p: Dictionary = WorldState.plots.get(pid, {})
			var sub: Dictionary = WorldState.subsurface_for_plot_ui(pid, p)
			var best_grade := 0.0
			var best_name := ""
			for pair in grade_keys:
				var fld := str((pair as Array)[0])
				var abbrev := str((pair as Array)[1])
				var g := float(sub.get(fld, 0.0))
				if g > best_grade:
					best_grade = g
					best_name = abbrev
			if best_grade >= 0.15:
				var grade_text := "%s %.0f%%" % [best_name, best_grade * 100.0]
				var grade_col := Color(0.4, 1.0, 0.4) if best_grade >= 0.5 else Color(0.9, 0.85, 0.3)
				grade_col.a = 0.85
				var gpos := ctr + Vector2(_world_line_width(-8.0), _world_line_width(6.0))
				draw_string(font, gpos, grade_text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, grade_col)


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
			_zoom_at_screen_pos(mb.position, WHEEL_ZOOM_STEP)
		elif mb.button_index == MOUSE_BUTTON_WHEEL_DOWN and mb.pressed:
			_zoom_at_screen_pos(mb.position, 1.0 / WHEEL_ZOOM_STEP)
		if mb.pressed or mb.button_index == MOUSE_BUTTON_LEFT:
			get_viewport().set_input_as_handled()
	elif event is InputEventMouseMotion and _dragging:
		var mm := event as InputEventMouseMotion
		if mm.relative.length_squared() > 4.0:
			_did_drag = true
		camera.position -= mm.relative / camera.zoom
		_clamp_camera_position()
		if not _viewport_inside_drawn_buffer():
			queue_redraw()
		get_viewport().set_input_as_handled()


func _zoom_at_screen_pos(screen_pos: Vector2, factor: float) -> void:
	# Coalesce rapid wheel events within the same frame: accumulate factor, apply in _process.
	if not _zoom_pending:
		_zoom_pending_factor = factor
		_zoom_pending_pos = screen_pos
		_zoom_pending = true
	else:
		_zoom_pending_factor *= factor
		_zoom_pending_pos = screen_pos


func _apply_pending_zoom() -> void:
	if not _zoom_pending:
		return
	_zoom_pending = false
	var world_before := _screen_to_world(_zoom_pending_pos)
	_cam_zoom *= _zoom_pending_factor
	_zoom_pending_factor = 1.0
	_clamp_cam_zoom()
	_sync_camera_zoom()
	camera.position += world_before - _screen_to_world(_zoom_pending_pos)
	_clamp_camera_position()
	_sync_subviewport_pixel_filter()
	queue_redraw()


func _process(_delta: float) -> void:
	_apply_pending_zoom()


func _viewport_center() -> Vector2:
	var r := get_viewport().get_visible_rect()
	return r.position + r.size * 0.5


## Screen px → world (WorldMap space). Uses Camera2D math explicitly — canvas inverse was wrong
## under ``SubViewportContainer`` stretch + Camera smoothing, so zoom-at-cursor and hit-tests broke.
func _screen_to_world(screen_pos: Vector2) -> Vector2:
	var z := camera.zoom
	var zx := z.x if absf(z.x) > 1e-6 else 1.0
	return camera.position + (screen_pos - _viewport_center()) / Vector2(zx, zx)


func _handle_plot_click(screen_pos: Vector2) -> void:
	if _mesh == null or _overview_lod_active():
		return
	var world_pos := _screen_to_world(screen_pos)
	var cell := _mesh.cell_px
	var approx_gx := int((world_pos.x - _mesh.pad) / cell)
	var approx_gy := int((world_pos.y - _mesh.pad) / cell)
	var best_id := ""
	var best_gx := -1
	var best_gy := -1
	var best_d := cell * cell * 4.0
	var bounds := _last_mesh_bounds
	for dy in range(-1, 2):
		for dx in range(-1, 2):
			var gx := approx_gx + dx
			var gy := approx_gy + dy
			if gx < 0 or gy < 0 or gx >= bounds.x or gy >= bounds.y:
				continue
			var idx := gy * bounds.x + gx
			if (_cell_flags[idx] & 0x1) == 0:
				continue
			var c := _mesh.plot_centroid(gx, gy)
			var d := world_pos.distance_squared_to(c)
			if d < best_d:
				best_d = d
				best_gx = gx
				best_gy = gy
				best_id = _cell_pids[idx]
	if best_id.is_empty():
		return
	var plot_data: Dictionary = _plot_dict_for_cell(best_id, best_gx, best_gy)
	if plot_data.is_empty():
		return
	var emit_id := str(plot_data.get("id", best_id))
	if emit_id.is_empty():
		emit_id = best_id
	_selected_plot_id = emit_id
	_selected_gx = best_gx
	_selected_gy = best_gy
	_invalidate_draw_buffer()
	plot_clicked.emit(emit_id, plot_data)
