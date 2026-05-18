class_name PlotLotLayout
extends RefCounted
## Deterministic town-plat lot partition for a 100m plot (10×10 engine cells).
## Rectangles plus some L-shaped parcels (visual only).

const MIN_LOT_CELLS := 2
const MAX_LOT_CELLS := 18
const L_SHAPE_CHANCE := 0.30


static func generate(plot_id: String, world_seed: int = 42, side: int = 10) -> Array:
	var rng := RandomNumberGenerator.new()
	rng.seed = MapHash.hash32(world_seed, "plat:%s" % plot_id)
	var regions: Array[Rect2i] = [Rect2i(0, 0, side, side)]
	var guard := 0
	while guard < 64:
		guard += 1
		var split_any := false
		var next: Array[Rect2i] = []
		for r in regions:
			if _should_split(r, rng):
				var parts: Array = _split_region(r, rng)
				for p in parts:
					next.append(p as Rect2i)
				split_any = true
			else:
				next.append(r)
		regions = next
		if not split_any:
			break
	var lots := _regions_to_cell_lots(regions)
	_introduce_l_shapes(lots, rng)
	return lots


static func lot_cells(lot: Dictionary) -> Array:
	return lot.get("cells", []) as Array


static func lot_at(lots: Array, gx: int, gy: int) -> int:
	var p := Vector2i(gx, gy)
	for i in range(lots.size()):
		for c in lot_cells(lots[i]):
			if c is Vector2i and c == p:
				return i
	return -1


static func lot_bbox(lot: Dictionary) -> Rect2i:
	var cells := lot_cells(lot)
	if cells.is_empty():
		return Rect2i()
	var min_x := 99
	var min_y := 99
	var max_x := 0
	var max_y := 0
	for c in cells:
		if c is Vector2i:
			min_x = mini(min_x, c.x)
			min_y = mini(min_y, c.y)
			max_x = maxi(max_x, c.x)
			max_y = maxi(max_y, c.y)
	return Rect2i(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)


static func is_l_shape(lot: Dictionary) -> bool:
	return str(lot.get("shape", "")) == "l"


static func street_rows(plot_id: String, world_seed: int, side: int) -> Array[int]:
	var rng := RandomNumberGenerator.new()
	rng.seed = MapHash.hash32(world_seed, "streets:%s" % plot_id)
	var rows: Array[int] = []
	var count := 1 + rng.randi_range(0, 2)
	for _i in range(count):
		var y := rng.randi_range(2, side - 3)
		if y not in rows:
			rows.append(y)
	rows.sort()
	return rows


static func _introduce_l_shapes(lots: Array, rng: RandomNumberGenerator) -> void:
	var owner := _build_owner_map(lots)
	var order: Array = []
	for i in range(lots.size()):
		order.append(i)
	_shuffle_indices(order, rng)

	for lot_idx in order:
		if rng.randf() > L_SHAPE_CHANCE:
			continue
		var lot: Dictionary = lots[lot_idx]
		if is_l_shape(lot):
			continue
		var cells: Array = lot_cells(lot)
		if cells.size() < 4:
			continue
		var bb := lot_bbox(lot)
		if bb.size.x < 2 or bb.size.y < 2:
			continue

		var corners: Array[Vector2i] = [
			Vector2i(bb.position.x, bb.position.y),
			Vector2i(bb.position.x + bb.size.x - 1, bb.position.y),
			Vector2i(bb.position.x + bb.size.x - 1, bb.position.y + bb.size.y - 1),
			Vector2i(bb.position.x, bb.position.y + bb.size.y - 1),
		]
		_shuffle_corners(corners, rng)

		for corner in corners:
			if not _cells_has(cells, corner):
				continue
			var neighbor := _neighbor_lot_index(corner, lot_idx, owner)
			if neighbor < 0:
				continue
			var carved: Array = _cells_without(cells, corner)
			if not _is_rect_minus_one_corner(carved):
				continue
			var neighbor_cells: Array = lot_cells(lots[neighbor])
			var grown: Array = neighbor_cells.duplicate()
			grown.append(corner)
			if not _cells_connected(grown):
				continue
			lots[lot_idx]["cells"] = carved
			lots[lot_idx]["shape"] = "l"
			lots[neighbor]["cells"] = grown
			owner = _build_owner_map(lots)
			break


static func _regions_to_cell_lots(regions: Array[Rect2i]) -> Array:
	var lots: Array = []
	for r in regions:
		lots.append({"cells": _cells_from_rect(r), "shape": "rect"})
	return lots


static func _cells_from_rect(r: Rect2i) -> Array:
	var cells: Array = []
	for dx in range(r.size.x):
		for dy in range(r.size.y):
			cells.append(Vector2i(r.position.x + dx, r.position.y + dy))
	return cells


static func _build_owner_map(lots: Array) -> Dictionary:
	var owner := {}
	for i in range(lots.size()):
		for c in lot_cells(lots[i]):
			if c is Vector2i:
				owner[_cell_key(c)] = i
	return owner


static func _cell_key(c: Vector2i) -> String:
	return "%d,%d" % [c.x, c.y]


static func _cells_has(cells: Array, p: Vector2i) -> bool:
	for c in cells:
		if c is Vector2i and c == p:
			return true
	return false


static func _cells_without(cells: Array, remove: Vector2i) -> Array:
	var out: Array = []
	for c in cells:
		if c is Vector2i and c != remove:
			out.append(c)
	return out


static func _cells_connected(cells: Array) -> bool:
	if cells.is_empty():
		return false
	var start: Vector2i = cells[0] as Vector2i
	var target := cells.size()
	var seen := {_cell_key(start): true}
	var frontier: Array = [start]
	var dirs := [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]
	while not frontier.is_empty():
		var cur: Vector2i = frontier.pop_front() as Vector2i
		for d in dirs:
			var n := Vector2i(cur.x + d.x, cur.y + d.y)
			if seen.has(_cell_key(n)):
				continue
			if not _cells_has(cells, n):
				continue
			seen[_cell_key(n)] = true
			frontier.append(n)
	return seen.size() == target


static func _is_rect_minus_one_corner(cells: Array) -> bool:
	if cells.size() < 3:
		return false
	if not _cells_connected(cells):
		return false
	var bb := Rect2i()
	if cells.is_empty():
		return false
	bb = lot_bbox({"cells": cells})
	return cells.size() == bb.size.x * bb.size.y - 1


static func _neighbor_lot_index(cell: Vector2i, from_idx: int, owner: Dictionary) -> int:
	var dirs := [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]
	for d in dirs:
		var k := _cell_key(Vector2i(cell.x + d.x, cell.y + d.y))
		if not owner.has(k):
			continue
		var idx: int = int(owner[k])
		if idx != from_idx:
			return idx
	return -1


static func _shuffle_indices(indices: Array, rng: RandomNumberGenerator) -> void:
	for i in range(indices.size() - 1, 0, -1):
		var j := rng.randi_range(0, i)
		var tmp = indices[i]
		indices[i] = indices[j]
		indices[j] = tmp


static func _shuffle_corners(corners: Array[Vector2i], rng: RandomNumberGenerator) -> void:
	for i in range(corners.size() - 1, 0, -1):
		var j := rng.randi_range(0, i)
		var tmp := corners[i]
		corners[i] = corners[j]
		corners[j] = tmp


static func _should_split(r: Rect2i, rng: RandomNumberGenerator) -> bool:
	var area := r.size.x * r.size.y
	if area <= MIN_LOT_CELLS:
		return false
	if area >= MAX_LOT_CELLS:
		return true
	if r.size.x < 2 and r.size.y < 2:
		return false
	return rng.randf() < 0.72


static func _split_region(r: Rect2i, rng: RandomNumberGenerator) -> Array[Rect2i]:
	var vertical: bool
	if r.size.x > r.size.y:
		vertical = true
	elif r.size.y > r.size.x:
		vertical = false
	else:
		vertical = rng.randf() < 0.5

	if vertical and r.size.x >= 2:
		var cut := 1 + rng.randi_range(0, r.size.x - 2)
		if rng.randf() < 0.35 and r.size.x >= 4:
			cut = maxi(1, mini(r.size.x - 1, int(r.size.x * rng.randf_range(0.28, 0.72))))
		return [
			Rect2i(r.position.x, r.position.y, cut, r.size.y),
			Rect2i(r.position.x + cut, r.position.y, r.size.x - cut, r.size.y),
		]
	if r.size.y >= 2:
		var cut_y := 1 + rng.randi_range(0, r.size.y - 2)
		if rng.randf() < 0.35 and r.size.y >= 4:
			cut_y = maxi(1, mini(r.size.y - 1, int(r.size.y * rng.randf_range(0.28, 0.72))))
		return [
			Rect2i(r.position.x, r.position.y, r.size.x, cut_y),
			Rect2i(r.position.x, r.position.y + cut_y, r.size.x, r.size.y - cut_y),
		]
	return [r]
