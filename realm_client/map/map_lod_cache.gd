class_name MapLodCache
extends RefCounted
## Pre-aggregated terrain for zoomed-out map drawing (overview texture + chunk rects).

## Native overview pixels (nearest-scaled); higher = sharper at max zoom-out.
const OVERVIEW_MAX_W: int = 1024
const CHUNK_CELLS: int = 16

var chunk_w: int = 0
var chunk_h: int = 0
var chunk_colors: PackedColorArray = PackedColorArray()
## 0x1 = chunk has at least one land cell.
var chunk_flags: PackedInt32Array = PackedInt32Array()

var overview_texture: ImageTexture
var overview_ready: bool = false


func clear() -> void:
	chunk_w = 0
	chunk_h = 0
	chunk_colors = PackedColorArray()
	chunk_flags = PackedInt32Array()
	overview_ready = false


func rebuild(
	grid_w: int,
	grid_h: int,
	cell_colors: PackedColorArray,
	cell_flags: PackedInt32Array,
	ocean_color: Color,
) -> void:
	clear()
	if grid_w < 1 or grid_h < 1:
		return
	_build_chunks(grid_w, grid_h, cell_colors, cell_flags)
	_build_overview(grid_w, grid_h, cell_colors, cell_flags, ocean_color)


func _build_chunks(
	grid_w: int,
	grid_h: int,
	cell_colors: PackedColorArray,
	cell_flags: PackedInt32Array,
) -> void:
	chunk_w = int(ceil(float(grid_w) / float(CHUNK_CELLS)))
	chunk_h = int(ceil(float(grid_h) / float(CHUNK_CELLS)))
	var n := chunk_w * chunk_h
	chunk_colors.resize(n)
	chunk_flags.resize(n)
	for cy in range(chunk_h):
		for cx in range(chunk_w):
			var cidx := cy * chunk_w + cx
			var r_sum := 0.0
			var g_sum := 0.0
			var b_sum := 0.0
			var count := 0
			for ly in range(CHUNK_CELLS):
				var gy := cy * CHUNK_CELLS + ly
				if gy >= grid_h:
					continue
				for lx in range(CHUNK_CELLS):
					var gx := cx * CHUNK_CELLS + lx
					if gx >= grid_w:
						continue
					var idx := gy * grid_w + gx
					if (cell_flags[idx] & 0x1) == 0:
						continue
					var c: Color = cell_colors[idx]
					r_sum += c.r
					g_sum += c.g
					b_sum += c.b
					count += 1
			if count > 0:
				var inv := 1.0 / float(count)
				chunk_colors[cidx] = Color(r_sum * inv, g_sum * inv, b_sum * inv, 1.0)
				chunk_flags[cidx] = 0x1
			else:
				chunk_colors[cidx] = Color(0, 0, 0, 0)
				chunk_flags[cidx] = 0


func _build_overview(
	grid_w: int,
	grid_h: int,
	cell_colors: PackedColorArray,
	cell_flags: PackedInt32Array,
	ocean_color: Color,
) -> void:
	var ow := mini(OVERVIEW_MAX_W, grid_w)
	var oh := maxi(1, int(round(float(grid_h) * float(ow) / float(grid_w))))
	oh = mini(oh, OVERVIEW_MAX_W)
	var img := Image.create(ow, oh, false, Image.FORMAT_RGBA8)
	img.fill(ocean_color)
	for oy in range(oh):
		var gy := int(float(oy) * float(grid_h) / float(oh))
		gy = clampi(gy, 0, grid_h - 1)
		for ox in range(ow):
			var gx := int(float(ox) * float(grid_w) / float(ow))
			gx = clampi(gx, 0, grid_w - 1)
			var idx := gy * grid_w + gx
			if (cell_flags[idx] & 0x1) != 0:
				img.set_pixel(ox, oy, cell_colors[idx])
	if overview_texture == null:
		overview_texture = ImageTexture.create_from_image(img)
	else:
		overview_texture.set_image(img)
	overview_ready = true
