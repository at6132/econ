class_name MapOverlays
extends RefCounted

const MODES: PackedStringArray = [
	"none", "ownership", "power", "mineral", "routes", "roads", "population", "advantage",
]

const MINERAL_COLORS: Dictionary = {
	"coal": Color(0.3, 0.3, 0.3),
	"iron_ore": Color(0.7, 0.3, 0.2),
	"copper_ore": Color(0.8, 0.5, 0.2),
	"phosphate": Color(0.6, 0.8, 0.3),
	"phosphate_ore": Color(0.6, 0.8, 0.3),
	"gold": Color(1.0, 0.85, 0.2),
	"au": Color(1.0, 0.85, 0.2),
}


static func overlay_tint_for_plot(
	mode: String,
	plot: Dictionary,
	party: String,
	mineral: String,
	advantage_cat: String = "mining",
) -> Color:
	if mode == "none" or plot.is_empty():
		return Color(0, 0, 0, 0)
	match mode:
		"ownership":
			var owner_v: Variant = plot.get("owner", null)
			if owner_v == null:
				return Color(0, 0, 0, 0)
			if str(owner_v) == party:
				var c := RealmColors.MAGIC
				c.a = 0.4
				return c
			var t := MapHash.owner_tint_color(str(owner_v))
			t.a = maxf(t.a, 0.35)
			return t
		"power":
			if bool(plot.get("powered", true)):
				return Color(1.0, 0.85, 0.3, 0.25)
			return Color(0.15, 0.05, 0.25, 0.35)
		"mineral":
			return _mineral_tint(plot, party, mineral)
		"population":
			var dens: float = float(plot.get("population_density", 0.0))
			if dens < 0.05:
				return Color(0, 0, 0, 0)
			return Color(0.9, 0.4, 0.8, clampf(dens, 0.1, 0.45))
		"roads":
			return _roads_tint(plot)
		"advantage":
			return _advantage_tint(plot, advantage_cat)
		"routes":
			return Color(0, 0, 0, 0)
	return Color(0, 0, 0, 0)


static func _roads_tint(plot: Dictionary) -> Color:
	var pid := str(plot.get("id", ""))
	if pid == "" or WorldState.road_segments.is_empty():
		return Color(0, 0, 0, 0)
	for seg in WorldState.road_segments:
		if not (seg is Dictionary):
			continue
		var sd: Dictionary = seg as Dictionary
		if str(sd.get("from_plot", "")) == pid or str(sd.get("to_plot", "")) == pid:
			return Color(0.62, 0.52, 0.28, 0.42)
	return Color(0, 0, 0, 0)


static func _advantage_tint(plot: Dictionary, advantage_cat: String) -> Color:
	if not plot.has("landmass_id"):
		return Color(0, 0, 0, 0)
	var lm_key := str(plot.get("landmass_id", ""))
	var table: Variant = WorldState.regional_advantages.get(lm_key, WorldState.regional_advantages.get(int(lm_key), null))
	if not (table is Dictionary):
		return Color(0, 0, 0, 0)
	var cat := advantage_cat if advantage_cat != "" else "mining"
	var mult: float = float((table as Dictionary).get(cat, (table as Dictionary).get(cat.to_lower(), 1.0)))
	if mult >= 1.2:
		return Color(0.35, 0.85, 0.45, 0.38)
	if mult >= 1.05:
		return Color(0.45, 0.75, 0.55, 0.32)
	if mult < 0.95:
		return Color(0.75, 0.35, 0.35, 0.34)
	return Color(0.55, 0.55, 0.6, 0.22)


static func _mineral_tint(plot: Dictionary, party: String, mineral: String) -> Color:
	var sub: Variant = plot.get("subsurface", {})
	if not (sub is Dictionary):
		if not bool(plot.get("surveyed", false)) or str(plot.get("owner", "")) != party:
			return Color(0, 0, 0, 0)
		sub = {}
	var grade_key: String = mineral
	if not grade_key.ends_with("_grade"):
		grade_key = mineral + "_grade"
	var grade: float = float((sub as Dictionary).get(grade_key, (sub as Dictionary).get(mineral, 0.0)))
	if grade <= 0.001:
		return Color(0, 0, 0, 0)
	var indicator: Color = MINERAL_COLORS.get(mineral, Color(0.7, 0.7, 0.7))
	indicator.a = clampf(grade, 0.15, 0.85)
	return indicator
