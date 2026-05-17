class_name MapOrganicMesh
extends RefCounted
## Jittered quad mesh per plot (``web/app/mapOrganicMesh.ts``).
## Vertices and centroids are pre-computed at construction for O(1) lookup.

var cell_px: float
var pad: float
var content_width: float
var content_height: float
var _world_seed: int
var _grid_w: int
var _grid_h: int
var _amp: float
## Pre-computed corner positions: (grid_w+1) × (grid_h+1) flat array.
var _corners: PackedVector2Array
## Pre-computed polygon PackedVector2Arrays per plot (grid_w × grid_h).
var _polys: Array[PackedVector2Array]
## Pre-computed centroids per plot (grid_w × grid_h).
var _centroids: PackedVector2Array


func _init(world_seed: int, grid_w: int, grid_h: int, pad_px: float, cell_px_val: float) -> void:
	_world_seed = world_seed
	_grid_w = grid_w
	_grid_h = grid_h
	pad = pad_px
	cell_px = cell_px_val
	# 10% corner jitter — readable grid with slight hand-drawn softness (was ~42%).
	_amp = cell_px * 0.10
	content_width = pad * 2.0 + float(grid_w) * cell_px
	content_height = pad * 2.0 + float(grid_h) * cell_px
	_precompute_corners()
	_precompute_polys_and_centroids()


func plot_polygon(gx: int, gy: int) -> PackedVector2Array:
	var idx := gy * _grid_w + gx
	if idx >= 0 and idx < _polys.size():
		return _polys[idx]
	return PackedVector2Array([Vector2.ZERO, Vector2.ZERO, Vector2.ZERO, Vector2.ZERO])


func plot_centroid(gx: int, gy: int) -> Vector2:
	var idx := gy * _grid_w + gx
	if idx >= 0 and idx < _centroids.size():
		return _centroids[idx]
	return Vector2.ZERO


func _precompute_corners() -> void:
	var cols := _grid_w + 1
	var rows := _grid_h + 1
	_corners.resize(cols * rows)
	for vy in rows:
		for vx in cols:
			var j := MapHash.vertex_jitter(_world_seed, vx, vy, _amp)
			_corners[vy * cols + vx] = Vector2(pad + float(vx) * cell_px + j.x, pad + float(vy) * cell_px + j.y)


func _precompute_polys_and_centroids() -> void:
	var total := _grid_w * _grid_h
	_polys.resize(total)
	_centroids.resize(total)
	var cols := _grid_w + 1
	for gy in _grid_h:
		for gx in _grid_w:
			var c00 := _corners[gy * cols + gx]
			var c10 := _corners[gy * cols + gx + 1]
			var c11 := _corners[(gy + 1) * cols + gx + 1]
			var c01 := _corners[(gy + 1) * cols + gx]
			var idx := gy * _grid_w + gx
			_polys[idx] = PackedVector2Array([c00, c10, c11, c01])
			_centroids[idx] = (c00 + c10 + c11 + c01) * 0.25
