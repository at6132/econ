class_name BlueprintIcons
extends RefCounted
## Icon glyph + accent per blueprint (build sidebar / grid labels).

const CATEGORY_COLORS: Dictionary = {
	"extraction": Color(0.75, 0.55, 0.28),
	"processing": Color(0.45, 0.65, 0.95),
	"infrastructure": Color(0.55, 0.72, 0.42),
	"commerce": Color(0.95, 0.82, 0.35),
	"population": Color(0.85, 0.55, 0.75),
	"research": Color(0.65, 0.85, 0.95),
	"custom": Color(0.7, 0.7, 0.75),
}

const BLUEPRINT_ICONS: Dictionary = {
	"strip_mine": "⛏",
	"timber_yard": "🪵",
	"grain_row": "🌾",
	"stone_works": "🪨",
	"gristmill": "⚙",
	"kiln_shed": "🔥",
	"foundry": "🏭",
	"wood_shop": "🪚",
	"blast_furnace": "🔥",
	"chemical_works": "⚗",
	"forge_press": "🔨",
	"tool_workshop": "🔧",
	"machine_shop": "⚙",
	"assay_lab": "🔬",
	"laboratory": "🧪",
	"power_shed": "⚡",
	"tidal_mill": "🌊",
	"dock": "⚓",
	"waystation": "📦",
	"road_segment": "🛣",
	"residence": "🏠",
	"store": "🏪",
	"bank_building": "🏦",
	"apothecary": "💊",
	"field_stockade": "▣",
	"tool_cache": "🧰",
	"watch_hut": "👁",
	"drill_rig": "⛏",
	"shipyard": "🚢",
	"coal_generator": "⚡",
}

const CATEGORY_FALLBACK: Dictionary = {
	"extraction": "⛏",
	"processing": "🏭",
	"infrastructure": "⚙",
	"commerce": "🏪",
	"population": "🏠",
	"research": "🔬",
	"custom": "◆",
}


static func texture_for(bp: Dictionary) -> Texture2D:
	var bid := str(bp.get("blueprint_id", ""))
	if bid.is_empty():
		return null
	var path := "res://assets/icons/buildings/%s.png" % bid
	if ResourceLoader.exists(path):
		return load(path) as Texture2D
	return null


static func texture_for_id(blueprint_id: String) -> Texture2D:
	if blueprint_id.is_empty():
		return null
	var path := "res://assets/icons/buildings/%s.png" % blueprint_id
	if ResourceLoader.exists(path):
		return load(path) as Texture2D
	return null


static func icon_for(bp: Dictionary) -> String:
	var bid := str(bp.get("blueprint_id", ""))
	if BLUEPRINT_ICONS.has(bid):
		return str(BLUEPRINT_ICONS[bid])
	var cat := str(bp.get("category", "custom"))
	return str(CATEGORY_FALLBACK.get(cat, "◆"))


static func color_for(bp: Dictionary) -> Color:
	var cat := str(bp.get("category", "custom"))
	return CATEGORY_COLORS.get(cat, CATEGORY_COLORS["custom"]) as Color
