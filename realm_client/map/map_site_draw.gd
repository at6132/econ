class_name MapSiteDraw
extends RefCounted
## Draw plot-local roads + buildings on the world map at SITE zoom (10m grid aligned to deeds).
## Mirrors ``PlotGridView`` grid math and ``plot_deed_grid_cells`` from the engine.

const _BuildingMapIcons := preload("res://map/building_map_icons.gd")

const SUBCELLS_PER_TILE := 10

## Seeded blueprint footprints — keep in sync with engine ``_SEEDED_FOOTPRINTS``.
const SEEDED_FOOTPRINTS := {
	"strip_mine": Vector2i(6, 4),
	"foundry": Vector2i(4, 4),
	"timber_yard": Vector2i(5, 3),
	"grain_row": Vector2i(8, 4),
	"gristmill": Vector2i(3, 3),
	"power_shed": Vector2i(2, 2),
	"wood_shop": Vector2i(3, 3),
	"stone_works": Vector2i(4, 3),
	"kiln_shed": Vector2i(3, 3),
	"residence": Vector2i(2, 2),
	"store": Vector2i(3, 2),
	"dock": Vector2i(4, 2),
	"waystation": Vector2i(2, 2),
	"tidal_mill": Vector2i(3, 2),
	"apothecary": Vector2i(2, 2),
	"laboratory": Vector2i(4, 3),
	"blast_furnace": Vector2i(5, 4),
	"forge_press": Vector2i(3, 3),
	"tool_workshop": Vector2i(3, 3),
	"assay_lab": Vector2i(3, 2),
	"bank_building": Vector2i(4, 3),
	"chemical_works": Vector2i(4, 3),
	"machine_shop": Vector2i(4, 4),
	"drill_rig": Vector2i(3, 3),
	"shipyard": Vector2i(5, 3),
	"field_stockade": Vector2i(2, 2),
	"road_segment": Vector2i(1, 1),
	"tool_cache": Vector2i(2, 2),
	"watch_hut": Vector2i(2, 2),
	"warehouse": Vector2i(4, 4),
	"battery_bank": Vector2i(2, 2),
}


static func plot_world_origin(plot: Dictionary) -> Vector2i:
	var min_wx := 1_000_000
	var min_wy := 1_000_000
	var cells_v: Variant = plot.get("world_cells", [])
	if cells_v is Array and not (cells_v as Array).is_empty():
		for c in cells_v as Array:
			if c is Dictionary:
				var d: Dictionary = c as Dictionary
				min_wx = mini(min_wx, int(d.get("x", 0)))
				min_wy = mini(min_wy, int(d.get("y", 0)))
		return Vector2i(min_wx, min_wy)
	return Vector2i(int(plot.get("x", 0)), int(plot.get("y", 0)))


## 10m build cells on this deed — same set as ``PlotGridView._deed_lot_from_world_cells``.
static func deed_cell_set(plot: Dictionary) -> Dictionary:
	var out := {}
	var cells_v: Variant = plot.get("world_cells", [])
	if cells_v is Array and not (cells_v as Array).is_empty():
		var min_wx := 1_000_000
		var min_wy := 1_000_000
		for c in cells_v as Array:
			if c is Dictionary:
				var d: Dictionary = c as Dictionary
				min_wx = mini(min_wx, int(d.get("x", 0)))
				min_wy = mini(min_wy, int(d.get("y", 0)))
		for c in cells_v as Array:
			if not (c is Dictionary):
				continue
			var wx: int = int((c as Dictionary).get("x", 0)) - min_wx
			var wy: int = int((c as Dictionary).get("y", 0)) - min_wy
			for dx in range(SUBCELLS_PER_TILE):
				for dy in range(SUBCELLS_PER_TILE):
					out["%d,%d" % [wx * SUBCELLS_PER_TILE + dx, wy * SUBCELLS_PER_TILE + dy]] = true
		return out
	var wt := maxi(1, int(plot.get("world_tiles_w", 1)))
	var ht := maxi(1, int(plot.get("world_tiles_h", 1)))
	for ty in range(ht):
		for tx in range(wt):
			for dx in range(SUBCELLS_PER_TILE):
				for dy in range(SUBCELLS_PER_TILE):
					out["%d,%d" % [tx * SUBCELLS_PER_TILE + dx, ty * SUBCELLS_PER_TILE + dy]] = true
	return out


static func footprint_wh(building: Dictionary) -> Vector2i:
	## ``plot_buildings`` rows omit footprints; always resolve from blueprint catalog
	## (same source as ``plot_grid_state`` / Build ``PlotGridView``).
	var bid := WorldState.workshop_id_for_building(building)
	if SEEDED_FOOTPRINTS.has(bid):
		return SEEDED_FOOTPRINTS[bid]
	var bp := WorldState.blueprint_dict(bid)
	var fw := int(bp.get("footprint_w", 0))
	var fh := int(bp.get("footprint_h", 0))
	if fw >= 1 and fh >= 1:
		return Vector2i(fw, fh)
	return Vector2i(1, 1)


static func _footprint_on_deed(deed: Dictionary, gx: int, gy: int, fw: int, fh: int) -> bool:
	if deed.is_empty():
		return true
	for dy in range(fh):
		for dx in range(fw):
			if not deed.has("%d,%d" % [gx + dx, gy + dy]):
				return false
	return true


static func grid_cell_world_rect(mesh: MapOrganicMesh, plot: Dictionary, gx: int, gy: int) -> Rect2:
	var origin := plot_world_origin(plot)
	var cp := mesh.cell_px
	var sub := cp / float(SUBCELLS_PER_TILE)
	var lx := posmod(gx, SUBCELLS_PER_TILE)
	var ly := posmod(gy, SUBCELLS_PER_TILE)
	var wx := origin.x + int((gx - lx) / SUBCELLS_PER_TILE)
	var wy := origin.y + int((gy - ly) / SUBCELLS_PER_TILE)
	var pad := mesh.pad
	return Rect2(
		pad + float(wx) * cp + float(lx) * sub,
		pad + float(wy) * cp + float(ly) * sub,
		sub,
		sub,
	)


static func building_world_rect(
	mesh: MapOrganicMesh,
	plot: Dictionary,
	gx: int,
	gy: int,
	fw: int,
	fh: int,
) -> Rect2:
	var r0 := grid_cell_world_rect(mesh, plot, gx, gy)
	if fw <= 1 and fh <= 1:
		return r0
	var r1 := grid_cell_world_rect(mesh, plot, gx + fw - 1, gy + fh - 1)
	return Rect2(r0.position, r1.end - r0.position)


static func draw_plot_site(
	canvas: CanvasItem,
	mesh: MapOrganicMesh,
	plot: Dictionary,
	buildings: Array,
	world_line_width: Callable,
) -> void:
	if mesh == null or buildings.is_empty():
		return
	var deed := deed_cell_set(plot)
	var road_cells := {}
	var structures: Array = []
	for row in buildings:
		if not (row is Dictionary):
			continue
		var b: Dictionary = row as Dictionary
		var bid := WorldState.workshop_id_for_building(b)
		var gx := int(b.get("grid_x", 0))
		var gy := int(b.get("grid_y", 0))
		var fp := footprint_wh(b)
		if not _footprint_on_deed(deed, gx, gy, fp.x, fp.y):
			continue
		if bid == "road_segment":
			for dy in range(fp.y):
				for dx in range(fp.x):
					var cx := gx + dx
					var cy := gy + dy
					var key := "%d,%d" % [cx, cy]
					if deed.is_empty() or deed.has(key):
						road_cells[key] = true
			continue
		structures.append(b)
	var edge_w: float = world_line_width.call(0.75)
	for key in road_cells.keys():
		var parts: PackedStringArray = str(key).split(",")
		if parts.size() != 2:
			continue
		var rcx := int(parts[0])
		var rcy := int(parts[1])
		var r := grid_cell_world_rect(mesh, plot, rcx, rcy)
		_BuildingMapIcons.draw_road_cell(canvas, r, edge_w)
	structures.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		var ay := int(a.get("grid_y", 0))
		var by := int(b.get("grid_y", 0))
		if ay != by:
			return ay < by
		return int(a.get("grid_x", 0)) < int(b.get("grid_x", 0))
	)
	var stroke_w: float = world_line_width.call(1.0)
	for b in structures:
		var bid := WorldState.workshop_id_for_building(b)
		var gx := int(b.get("grid_x", 0))
		var gy := int(b.get("grid_y", 0))
		var fp := footprint_wh(b)
		var rect := building_world_rect(mesh, plot, gx, gy, fp.x, fp.y)
		var eff := int(b.get("_efficiency_pct", b.get("efficiency_pct", 100)))
		_BuildingMapIcons.draw_building(canvas, rect, bid, eff, stroke_w, world_line_width)
