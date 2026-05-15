class_name MapOrganicMesh
extends RefCounted
## Jittered quad mesh per plot (``web/app/mapOrganicMesh.ts``).

var cell_px: float
var pad: float
var content_width: float
var content_height: float
var _world_seed: int
var _grid_w: int
var _grid_h: int
var _amp: float


func _init(world_seed: int, grid_w: int, grid_h: int, pad_px: float, cell_px_val: float) -> void:
	_world_seed = world_seed
	_grid_w = grid_w
	_grid_h = grid_h
	pad = pad_px
	cell_px = cell_px_val
	_amp = cell_px * 0.42
	content_width = pad * 2.0 + float(grid_w) * cell_px
	content_height = pad * 2.0 + float(grid_h) * cell_px


func plot_polygon(gx: int, gy: int) -> PackedVector2Array:
	var c00 := _corner(gx, gy)
	var c10 := _corner(gx + 1, gy)
	var c11 := _corner(gx + 1, gy + 1)
	var c01 := _corner(gx, gy + 1)
	return PackedVector2Array([c00, c10, c11, c01])


func plot_centroid(gx: int, gy: int) -> Vector2:
	var poly := plot_polygon(gx, gy)
	return (poly[0] + poly[1] + poly[2] + poly[3]) * 0.25


func _corner(vx: int, vy: int) -> Vector2:
	var j := MapHash.vertex_jitter(_world_seed, vx, vy, _amp)
	return Vector2(pad + float(vx) * cell_px + j.x, pad + float(vy) * cell_px + j.y)
