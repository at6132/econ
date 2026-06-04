class_name BuildingMapIcons
extends RefCounted
## Top-down building art for world-map SITE LOD — type-colored silhouettes, not grey boxes.

const ROAD_FILL := Color(0.05, 0.05, 0.06, 0.96)
const ROAD_EDGE := Color(0.38, 0.40, 0.44, 0.9)
const ROAD_LINK := Color(0.22, 0.24, 0.28, 0.85)

const WATER_SHORE := Color(0.22, 0.48, 0.72, 0.55)
const WATER_DEEP := Color(0.08, 0.20, 0.38, 0.65)
const OUTLINE := Color(0.12, 0.11, 0.10, 0.92)

## All seeded blueprint ids shown in BuildingIconGallery (keep in sync with engine catalog).
const GALLERY_BLUEPRINT_IDS = [
	"dock",
	"shipyard",
	"waystation",
	"strip_mine",
	"drill_rig",
	"timber_yard",
	"grain_row",
	"gristmill",
	"warehouse",
	"tool_cache",
	"foundry",
	"blast_furnace",
	"forge_press",
	"kiln_shed",
	"chemical_works",
	"wood_shop",
	"stone_works",
	"tool_workshop",
	"machine_shop",
	"power_shed",
	"tidal_mill",
	"battery_bank",
	"residence",
	"watch_hut",
	"field_stockade",
	"store",
	"bank_building",
	"assay_lab",
	"laboratory",
	"apothecary",
	"road_segment",
]


## Per-blueprint palette: fill, roof, accent, detail (top-down read).
static func palette_for(blueprint_id: String) -> Dictionary:
	var s := blueprint_id.to_lower()
	match s:
		"dock":
			return {
				"fill": Color(0.58, 0.48, 0.34),
				"roof": Color(0.72, 0.60, 0.42),
				"accent": Color(0.45, 0.36, 0.26),
				"detail": Color(0.32, 0.26, 0.18),
			}
		"shipyard":
			return {
				"fill": Color(0.52, 0.44, 0.38),
				"roof": Color(0.68, 0.55, 0.40),
				"accent": Color(0.38, 0.48, 0.55),
				"detail": Color(0.22, 0.20, 0.18),
			}
		"waystation":
			return {
				"fill": Color(0.55, 0.50, 0.40),
				"roof": Color(0.78, 0.68, 0.45),
				"accent": Color(0.40, 0.55, 0.38),
				"detail": Color(0.25, 0.22, 0.18),
			}
		"strip_mine", "drill_rig":
			return {
				"fill": Color(0.48, 0.42, 0.34),
				"roof": Color(0.55, 0.48, 0.38),
				"accent": Color(0.72, 0.38, 0.22),
				"detail": Color(0.18, 0.14, 0.12),
			}
		"timber_yard":
			return {
				"fill": Color(0.42, 0.32, 0.22),
				"roof": Color(0.52, 0.38, 0.26),
				"accent": Color(0.62, 0.48, 0.30),
				"detail": Color(0.28, 0.20, 0.14),
			}
		"grain_row", "gristmill":
			return {
				"fill": Color(0.38, 0.52, 0.28),
				"roof": Color(0.55, 0.68, 0.32),
				"accent": Color(0.78, 0.72, 0.38),
				"detail": Color(0.28, 0.38, 0.18),
			}
		"foundry", "blast_furnace", "forge_press", "kiln_shed":
			return {
				"fill": Color(0.50, 0.38, 0.32),
				"roof": Color(0.62, 0.45, 0.35),
				"accent": Color(0.85, 0.42, 0.18),
				"detail": Color(0.22, 0.16, 0.14),
			}
		"chemical_works":
			return {
				"fill": Color(0.42, 0.48, 0.38),
				"roof": Color(0.55, 0.62, 0.48),
				"accent": Color(0.65, 0.78, 0.42),
				"detail": Color(0.20, 0.24, 0.18),
			}
		"power_shed", "tidal_mill", "battery_bank", "coal_generator":
			return {
				"fill": Color(0.38, 0.42, 0.48),
				"roof": Color(0.50, 0.55, 0.62),
				"accent": Color(0.95, 0.82, 0.35),
				"detail": Color(0.22, 0.24, 0.28),
			}
		"warehouse", "tool_cache":
			return {
				"fill": Color(0.46, 0.48, 0.52),
				"roof": Color(0.58, 0.60, 0.64),
				"accent": Color(0.72, 0.74, 0.78),
				"detail": Color(0.24, 0.25, 0.28),
			}
		"residence", "watch_hut", "field_stockade":
			return {
				"fill": Color(0.55, 0.42, 0.32),
				"roof": Color(0.68, 0.32, 0.28),
				"accent": Color(0.82, 0.72, 0.48),
				"detail": Color(0.30, 0.22, 0.16),
			}
		"store", "bank_building":
			return {
				"fill": Color(0.52, 0.46, 0.38),
				"roof": Color(0.72, 0.62, 0.42),
				"accent": Color(0.90, 0.78, 0.35),
				"detail": Color(0.28, 0.24, 0.20),
			}
		"assay_lab", "laboratory", "apothecary":
			return {
				"fill": Color(0.42, 0.44, 0.58),
				"roof": Color(0.55, 0.58, 0.72),
				"accent": Color(0.75, 0.85, 0.95),
				"detail": Color(0.22, 0.24, 0.32),
			}
		"wood_shop", "stone_works", "tool_workshop", "machine_shop":
			return {
				"fill": Color(0.48, 0.44, 0.38),
				"roof": Color(0.60, 0.54, 0.44),
				"accent": Color(0.78, 0.65, 0.40),
				"detail": Color(0.26, 0.22, 0.18),
			}
		_:
			return {
				"fill": Color(0.46, 0.46, 0.50),
				"roof": Color(0.58, 0.58, 0.62),
				"accent": Color(0.72, 0.68, 0.55),
				"detail": Color(0.22, 0.22, 0.24),
			}


## Maintenance / efficiency read — same thresholds as Build ``PlotGridView`` status icons.
static func efficiency_from_building(row: Dictionary) -> int:
	if row.has("_efficiency_pct"):
		return clampi(int(row.get("_efficiency_pct", 100)), 0, 100)
	var m: Variant = row.get("maintenance", {})
	if m is Dictionary:
		return clampi(
			int((m as Dictionary).get("efficiency_pct", row.get("efficiency_pct", 100))), 0, 100
		)
	return clampi(int(row.get("efficiency_pct", 100)), 0, 100)


static func summarize_plot_buildings(buildings: Array) -> Dictionary:
	var worst := 100
	var count := 0
	var attention := 0
	for row in buildings:
		if not (row is Dictionary):
			continue
		count += 1
		var eff := efficiency_from_building(row as Dictionary)
		worst = mini(worst, eff)
		if eff < 95:
			attention += 1
	if count == 0:
		worst = 100
	return {"worst_eff": worst, "count": count, "attention": attention}


static func efficiency_color(eff_pct: int) -> Color:
	if eff_pct >= 95:
		return Color(0.58, 0.62, 0.66, 0.88)
	if eff_pct >= 70:
		return Color(0.35, 0.85, 0.45, 0.9)
	if eff_pct >= 40:
		return Color(0.95, 0.75, 0.25, 0.92)
	return Color(0.92, 0.32, 0.28, 0.92)


## Per-plot marker — detail scales with map LOD (0=continent … 3=plot).
static func draw_plot_efficiency_marker(
	canvas: CanvasItem,
	center: Vector2,
	worst_eff: int,
	lod: int,
	line_w: Callable,
) -> void:
	var screen_d := 2.5
	match lod:
		0:
			screen_d = 2.5
		1:
			screen_d = 3.5
		2:
			screen_d = 5.0
		_:
			screen_d = 4.5
	var rad: float = float(line_w.call(screen_d)) * 0.5
	var col := efficiency_color(worst_eff)
	canvas.draw_circle(center, rad, col)
	if worst_eff < 95:
		canvas.draw_arc(center, rad, 0.0, TAU, 10, OUTLINE, float(line_w.call(0.65)), true)


## Per-building corner marker at SITE LOD — fixed screen size, not world scale.
static func draw_building_efficiency_marker(
	canvas: CanvasItem,
	rect: Rect2,
	eff_pct: int,
	line_w: Callable,
) -> void:
	if eff_pct >= 95 or not line_w.is_valid():
		return
	var col := efficiency_color(eff_pct)
	var rad: float = float(line_w.call(3.5))
	var corner := rect.position + Vector2(rect.size.x - rad * 0.35, rad * 0.65)
	canvas.draw_circle(corner, rad, col)
	canvas.draw_arc(corner, rad, 0.0, TAU, 12, OUTLINE, float(line_w.call(0.75)), true)


static func draw_road_cell(canvas: CanvasItem, rect: Rect2, edge_w: float) -> void:
	if rect.size.x < 0.5:
		return
	canvas.draw_rect(rect, ROAD_FILL, true)
	if edge_w > 0.05:
		canvas.draw_rect(rect, ROAD_EDGE, false, maxf(edge_w, 0.5))


static func draw_building(
	canvas: CanvasItem,
	rect: Rect2,
	blueprint_id: String,
	eff_pct: int,
	stroke_w: float,
	line_w: Callable = Callable(),
) -> void:
	if rect.size.x < 1.0 or rect.size.y < 1.0:
		return
	var pal := palette_for(blueprint_id)
	var bid := blueprint_id.to_lower()
	var inset := rect.grow(-maxf(0.5, minf(rect.size.x, rect.size.y) * 0.04))
	if inset.size.x < 1.0:
		inset = rect
	match bid:
		"dock":
			_draw_dock(canvas, inset, pal, stroke_w)
		"shipyard":
			_draw_shipyard(canvas, inset, pal, stroke_w)
		"waystation":
			_draw_waystation(canvas, inset, pal, stroke_w)
		"strip_mine":
			_draw_strip_mine(canvas, inset, pal, stroke_w)
		"drill_rig":
			_draw_drill_rig(canvas, inset, pal, stroke_w)
		"timber_yard":
			_draw_timber_yard(canvas, inset, pal, stroke_w)
		"grain_row":
			_draw_grain_row(canvas, inset, pal, stroke_w)
		"gristmill":
			_draw_gristmill(canvas, inset, pal, stroke_w)
		"warehouse":
			_draw_warehouse(canvas, inset, pal, stroke_w)
		"foundry", "blast_furnace":
			_draw_foundry(canvas, inset, pal, stroke_w)
		"power_shed", "tidal_mill", "battery_bank":
			_draw_power(canvas, inset, pal, stroke_w)
		"residence":
			_draw_residence(canvas, inset, pal, stroke_w)
		"store", "bank_building":
			_draw_storefront(canvas, inset, pal, stroke_w)
		"assay_lab", "laboratory":
			_draw_lab(canvas, inset, pal, stroke_w)
		_:
			_draw_workshop(canvas, inset, pal, stroke_w)
	draw_building_efficiency_marker(canvas, inset, eff_pct, line_w)


static func _outline(canvas: CanvasItem, r: Rect2, w: float) -> void:
	canvas.draw_rect(r, OUTLINE, false, maxf(w, 0.5))


## Land shed + wooden pier fingers into water (south edge = waterfront).
static func _draw_dock(canvas: CanvasItem, r: Rect2, pal: Dictionary, sw: float) -> void:
	var p := r.position
	var w := r.size.x
	var h := r.size.y
	# Water along south (typical coastal placement).
	var water_h := h * 0.38
	canvas.draw_rect(Rect2(p.x, p.y + h - water_h, w, water_h), WATER_DEEP, true)
	canvas.draw_rect(Rect2(p.x, p.y + h - water_h * 0.55, w, water_h * 0.2), WATER_SHORE, true)
	# Main pier deck (T-shape).
	var deck_y := p.y + h * 0.22
	var deck_h := h * 0.48
	canvas.draw_rect(Rect2(p.x + w * 0.08, deck_y, w * 0.84, deck_h), pal.fill, true)
	_outline(canvas, Rect2(p.x + w * 0.08, deck_y, w * 0.84, deck_h), sw)
	# Pier fingers into water.
	var finger_w := w * 0.14
	var finger_gap := w * 0.06
	var start_x := p.x + w * 0.12
	for i in range(4):
		var fx := start_x + float(i) * (finger_w + finger_gap)
		if fx + finger_w > p.x + w * 0.92:
			break
		var finger := Rect2(fx, deck_y + deck_h * 0.35, finger_w, h * 0.42)
		canvas.draw_rect(finger, pal.roof, true)
		canvas.draw_rect(finger, pal.detail, false, maxf(sw * 0.7, 0.5))
	# Land-side office / hoist shed.
	var shed := Rect2(p.x + w * 0.55, p.y + h * 0.04, w * 0.38, h * 0.28)
	canvas.draw_rect(shed, pal.accent, true)
	canvas.draw_rect(shed, pal.detail, false, sw)
	# Crane arm over deck.
	canvas.draw_line(
		Vector2(p.x + w * 0.58, p.y + h * 0.06),
		Vector2(p.x + w * 0.35, deck_y + deck_h * 0.2),
		pal.detail,
		maxf(sw, 1.0),
		true,
	)
	# Bollards on deck.
	for i in range(3):
		var bx := p.x + w * (0.22 + float(i) * 0.22)
		canvas.draw_circle(Vector2(bx, deck_y + deck_h * 0.65), maxf(1.0, sw), pal.detail)


static func _draw_waystation(canvas: CanvasItem, r: Rect2, pal: Dictionary, sw: float) -> void:
	var p := r.position
	var w := r.size.x
	var h := r.size.y
	canvas.draw_rect(r, pal.fill, true)
	# Small platform + signpost (road hub).
	canvas.draw_rect(Rect2(p.x + w * 0.15, p.y + h * 0.35, w * 0.7, h * 0.45), pal.roof, true)
	canvas.draw_line(
		Vector2(p.x + w * 0.5, p.y + h * 0.08),
		Vector2(p.x + w * 0.5, p.y + h * 0.38),
		pal.detail,
		maxf(sw, 1.0),
		true,
	)
	canvas.draw_rect(Rect2(p.x + w * 0.42, p.y + h * 0.02, w * 0.16, h * 0.12), pal.accent, true)
	_outline(canvas, r, sw)


static func _draw_shipyard(canvas: CanvasItem, r: Rect2, pal: Dictionary, sw: float) -> void:
	var p := r.position
	var w := r.size.x
	var h := r.size.y
	canvas.draw_rect(Rect2(p.x, p.y + h * 0.55, w, h * 0.45), WATER_DEEP, true)
	# Slipway (tapered).
	canvas.draw_colored_polygon(
		PackedVector2Array([
			p + Vector2(w * 0.15, p.y + h * 0.55),
			p + Vector2(w * 0.85, p.y + h * 0.55),
			p + Vector2(w * 0.72, p.y + h * 0.95),
			p + Vector2(w * 0.28, p.y + h * 0.95),
		]),
		pal.accent,
	)
	# Hull under construction.
	canvas.draw_colored_polygon(
		PackedVector2Array([
			p + Vector2(w * 0.32, p.y + h * 0.48),
			p + Vector2(w * 0.68, p.y + h * 0.48),
			p + Vector2(w * 0.62, p.y + h * 0.72),
			p + Vector2(w * 0.38, p.y + h * 0.72),
		]),
		Color(0.55, 0.42, 0.32, 0.9),
	)
	# Big shed.
	var shed := Rect2(p.x + w * 0.05, p.y + h * 0.05, w * 0.45, h * 0.42)
	canvas.draw_rect(shed, pal.fill, true)
	canvas.draw_rect(shed, pal.roof, false, sw)
	_outline(canvas, shed, sw)


static func _draw_strip_mine(canvas: CanvasItem, r: Rect2, pal: Dictionary, sw: float) -> void:
	var p := r.position
	var w := r.size.x
	var h := r.size.y
	canvas.draw_rect(r, pal.fill, true)
	# Open cut (dark trench).
	var trench := Rect2(p.x + w * 0.08, p.y + h * 0.32, w * 0.84, h * 0.52)
	canvas.draw_rect(trench, pal.detail, true)
	canvas.draw_rect(trench, OUTLINE, false, sw)
	# Spoil piles on sides.
	canvas.draw_colored_polygon(
		PackedVector2Array([
			p + Vector2(w * 0.05, p.y + h * 0.35),
			p + Vector2(w * 0.22, p.y + h * 0.15),
			p + Vector2(w * 0.28, p.y + h * 0.45),
		]),
		pal.roof,
	)
	canvas.draw_colored_polygon(
		PackedVector2Array([
			p + Vector2(w * 0.95, p.y + h * 0.35),
			p + Vector2(w * 0.78, p.y + h * 0.15),
			p + Vector2(w * 0.72, p.y + h * 0.45),
		]),
		pal.roof,
	)
	# Conveyor / headframe.
	canvas.draw_line(
		p + Vector2(w * 0.5, p.y + h * 0.05),
		p + Vector2(w * 0.5, p.y + h * 0.30),
		pal.accent,
		maxf(sw, 1.2),
		true,
	)
	canvas.draw_line(
		p + Vector2(w * 0.38, p.y + h * 0.12),
		p + Vector2(w * 0.62, p.y + h * 0.12),
		pal.accent,
		maxf(sw, 1.0),
		true,
	)
	_outline(canvas, r, sw)


static func _draw_drill_rig(canvas: CanvasItem, r: Rect2, pal: Dictionary, sw: float) -> void:
	var p := r.position
	var w := r.size.x
	var h := r.size.y
	canvas.draw_rect(r, pal.fill, true)
	var cx := p.x + w * 0.5
	canvas.draw_line(
		Vector2(cx, p.y + h * 0.08),
		Vector2(cx, p.y + h * 0.88),
		pal.accent,
		maxf(sw * 1.2, 1.0),
		true,
	)
	canvas.draw_line(
		Vector2(cx - w * 0.22, p.y + h * 0.72),
		Vector2(cx + w * 0.22, p.y + h * 0.72),
		pal.detail,
		maxf(sw, 1.0),
		true,
	)
	canvas.draw_circle(Vector2(cx, p.y + h * 0.12), w * 0.12, pal.roof)
	_outline(canvas, r, sw)


static func _draw_timber_yard(canvas: CanvasItem, r: Rect2, pal: Dictionary, sw: float) -> void:
	var p := r.position
	var w := r.size.x
	var h := r.size.y
	canvas.draw_rect(r, pal.fill, true)
	for i in range(5):
		var log := Rect2(
			p.x + w * (0.06 + float(i) * 0.17),
			p.y + h * (0.25 + float(i % 2) * 0.12),
			w * 0.12,
			h * 0.55,
		)
		canvas.draw_rect(log, pal.accent, true)
		canvas.draw_rect(log, pal.detail, false, maxf(sw * 0.5, 0.5))
	_outline(canvas, r, sw)


static func _draw_grain_row(canvas: CanvasItem, r: Rect2, pal: Dictionary, sw: float) -> void:
	var p := r.position
	var w := r.size.x
	var h := r.size.y
	for i in range(5):
		var patch := Rect2(
			p.x + w * (0.04 + float(i) * 0.19),
			p.y + h * 0.15,
			w * 0.16,
			h * 0.72,
		)
		var shade: Color = (pal.fill as Color).darkened(0.04 * float(i))
		canvas.draw_rect(patch, shade, true)
		canvas.draw_rect(patch, pal.detail, false, maxf(sw * 0.4, 0.5))
	# Small silo cap.
	canvas.draw_circle(p + Vector2(w * 0.88, h * 0.22), minf(w, h) * 0.1, pal.roof)
	_outline(canvas, r, sw)


static func _draw_gristmill(canvas: CanvasItem, r: Rect2, pal: Dictionary, sw: float) -> void:
	var p := r.position
	var w := r.size.x
	var h := r.size.y
	canvas.draw_rect(r, pal.fill, true)
	# Mill wheel side.
	canvas.draw_circle(p + Vector2(w * 0.22, h * 0.55), minf(w, h) * 0.22, pal.accent)
	canvas.draw_arc(p + Vector2(w * 0.22, h * 0.55), minf(w, h) * 0.22, 0.0, TAU, 16, pal.detail, sw, true)
	canvas.draw_rect(Rect2(p.x + w * 0.38, p.y + h * 0.12, w * 0.55, h * 0.72), pal.roof, true)
	_outline(canvas, r, sw)


static func _draw_warehouse(canvas: CanvasItem, r: Rect2, pal: Dictionary, sw: float) -> void:
	var p := r.position
	var w := r.size.x
	var h := r.size.y
	canvas.draw_rect(r, pal.fill, true)
	# Corrugated roof stripes.
	for i in range(4):
		var stripe_x := p.x + w * (0.05 + float(i) * 0.24)
		canvas.draw_line(
			Vector2(stripe_x, p.y + h * 0.05),
			Vector2(stripe_x, p.y + h * 0.28),
			pal.accent,
			maxf(sw * 0.6, 0.5),
			true,
		)
	# Loading bays.
	for i in range(3):
		var bay := Rect2(
			p.x + w * (0.12 + float(i) * 0.28),
			p.y + h * 0.55,
			w * 0.18,
			h * 0.38,
		)
		canvas.draw_rect(bay, pal.detail, true)
		canvas.draw_rect(bay, OUTLINE, false, sw)
	_outline(canvas, r, sw)


static func _draw_foundry(canvas: CanvasItem, r: Rect2, pal: Dictionary, sw: float) -> void:
	var p := r.position
	var w := r.size.x
	var h := r.size.y
	canvas.draw_rect(r, pal.fill, true)
	# Chimney stack.
	var stack := Rect2(p.x + w * 0.68, p.y + h * 0.02, w * 0.18, h * 0.55)
	canvas.draw_rect(stack, pal.detail, true)
	canvas.draw_circle(p + Vector2(w * 0.77, h * 0.06), w * 0.1, pal.accent)
	# Glow at furnace mouth.
	canvas.draw_rect(Rect2(p.x + w * 0.12, p.y + h * 0.62, w * 0.35, h * 0.28), pal.accent, true)
	_outline(canvas, r, sw)


static func _draw_power(canvas: CanvasItem, r: Rect2, pal: Dictionary, sw: float) -> void:
	var p := r.position
	var w := r.size.x
	var h := r.size.y
	canvas.draw_rect(r, pal.fill, true)
	var cx := p.x + w * 0.5
	var cy := p.y + h * 0.45
	# Transformer / tower silhouette.
	canvas.draw_line(Vector2(cx, p.y + h * 0.1), Vector2(cx, p.y + h * 0.75), pal.detail, maxf(sw, 1.0), true)
	canvas.draw_line(
		Vector2(cx - w * 0.28, cy),
		Vector2(cx + w * 0.28, cy),
		pal.detail,
		maxf(sw, 1.0),
		true,
	)
	canvas.draw_line(
		Vector2(cx - w * 0.18, cy + h * 0.15),
		Vector2(cx + w * 0.18, cy + h * 0.15),
		pal.detail,
		maxf(sw, 0.8),
		true,
	)
	# Bolt accent.
	canvas.draw_colored_polygon(
		PackedVector2Array([
			Vector2(cx, cy - h * 0.18),
			Vector2(cx + w * 0.12, cy),
			Vector2(cx, cy + h * 0.12),
			Vector2(cx - w * 0.12, cy),
		]),
		pal.accent,
	)
	_outline(canvas, r, sw)


static func _draw_residence(canvas: CanvasItem, r: Rect2, pal: Dictionary, sw: float) -> void:
	var p := r.position
	var w := r.size.x
	var h := r.size.y
	var body := Rect2(p.x + w * 0.15, p.y + h * 0.42, w * 0.7, h * 0.52)
	canvas.draw_rect(body, pal.fill, true)
	canvas.draw_colored_polygon(
		PackedVector2Array([
			p + Vector2(w * 0.5, p.y + h * 0.08),
			p + Vector2(w * 0.12, p.y + h * 0.44),
			p + Vector2(w * 0.88, p.y + h * 0.44),
		]),
		pal.roof,
	)
	canvas.draw_rect(Rect2(p.x + w * 0.42, p.y + h * 0.58, w * 0.16, h * 0.28), pal.detail, true)
	_outline(canvas, body, sw)


static func _draw_storefront(canvas: CanvasItem, r: Rect2, pal: Dictionary, sw: float) -> void:
	var p := r.position
	var w := r.size.x
	var h := r.size.y
	canvas.draw_rect(r, pal.fill, true)
	# Awning.
	canvas.draw_rect(Rect2(p.x, p.y + h * 0.22, w, h * 0.14), pal.accent, true)
	# Window / door front.
	canvas.draw_rect(Rect2(p.x + w * 0.12, p.y + h * 0.42, w * 0.76, h * 0.48), pal.roof, true)
	canvas.draw_line(
		Vector2(p.x + w * 0.5, p.y + h * 0.42),
		Vector2(p.x + w * 0.5, p.y + h * 0.90),
		pal.detail,
		sw,
		true,
	)
	_outline(canvas, r, sw)


static func _draw_lab(canvas: CanvasItem, r: Rect2, pal: Dictionary, sw: float) -> void:
	var p := r.position
	var w := r.size.x
	var h := r.size.y
	canvas.draw_rect(r, pal.fill, true)
	canvas.draw_rect(Rect2(p.x + w * 0.1, p.y + h * 0.08, w * 0.8, h * 0.22), pal.roof, true)
	canvas.draw_circle(p + Vector2(w * 0.5, h * 0.58), minf(w, h) * 0.18, pal.accent)
	canvas.draw_arc(p + Vector2(w * 0.5, h * 0.58), minf(w, h) * 0.18, 0.0, TAU, 20, pal.detail, sw, true)
	# Flask hint.
	canvas.draw_rect(Rect2(p.x + w * 0.72, p.y + h * 0.45, w * 0.12, h * 0.35), pal.accent, true)
	_outline(canvas, r, sw)


static func _draw_workshop(canvas: CanvasItem, r: Rect2, pal: Dictionary, sw: float) -> void:
	var p := r.position
	var w := r.size.x
	var h := r.size.y
	canvas.draw_rect(r, pal.fill, true)
	canvas.draw_rect(Rect2(p.x, p.y, w, h * 0.25), pal.roof, true)
	canvas.draw_rect(Rect2(p.x + w * 0.35, p.y + h * 0.42, w * 0.3, h * 0.38), pal.detail, true)
	_outline(canvas, r, sw)
