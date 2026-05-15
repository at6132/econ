extends Node
## Canonical Realm palette (matches ``web/app/globals.css``).

const BG := Color("0c0612")
const BG2 := Color("160a22")
const PANEL := Color("241a36")
const PANEL_DEEP := Color("140c1f")
const BORDER := Color("3d2f55")
const BORDER_LIT := Color("6b5a8a")
const TEXT := Color("f4ead8")
const DIM := Color("c9b8a8")
const MUTED := Color("8a7a98")
const ACCENT := Color("ffd84a")
const ACCENT_DIM := Color("c9a227")
const MAGIC := Color("6ee7ff")
const WARN := Color("ffb44a")
const DANGER := Color("ff6b6b")
const OK := Color("7bed9f")
const BLACK := Color("000000")
const CHIP_INACTIVE := Color("2a1f3d")
const CHIP_ACTIVE := Color("3d2d1a")
const STRIP_TOP := Color("1e1530")
const PILL_WELL := Color("1a1225")
const BTN_TEXT_ON_GOLD := Color("1a0f08")

const TERRAIN_HEX: Dictionary = {
	"plains": 0x4A8A38,
	"forest": 0x1F5028,
	"temperate_forest": 0x255028,
	"tropical": 0x1F6530,
	"mountain": 0x4A4A58,
	"hills": 0x5A5848,
	"desert": 0xC89838,
	"tundra": 0x78A8C8,
	"swamp": 0x2A6030,
	"valley": 0x5A7040,
	"coastal": 0x8A7858,
	"water_shallow": 0x2868A8,
	"water_deep": 0x0A1838,
	"unknown": 0x3A4048,
}


static func terrain_color(terrain: String) -> Color:
	var hex: int = int(TERRAIN_HEX.get(terrain, TERRAIN_HEX.unknown))
	return Color.from_rgba8((hex >> 16) & 0xFF, (hex >> 8) & 0xFF, hex & 0xFF, 255)


static func style_panel() -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = PANEL
	sb.border_width_left = 3
	sb.border_width_top = 3
	sb.border_width_right = 3
	sb.border_width_bottom = 3
	sb.border_color = BLACK
	sb.shadow_color = Color(0, 0, 0, 0.55)
	sb.shadow_size = 4
	sb.shadow_offset = Vector2(3, 3)
	return sb


static func style_chip(active: bool) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = CHIP_ACTIVE if active else CHIP_INACTIVE
	sb.border_width_left = 2
	sb.border_width_top = 2
	sb.border_width_right = 2
	sb.border_width_bottom = 2
	sb.border_color = BLACK
	return sb


static func style_btn_normal() -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = CHIP_INACTIVE
	sb.border_width_left = 2
	sb.border_width_top = 2
	sb.border_width_right = 2
	sb.border_width_bottom = 2
	sb.border_color = BLACK
	return sb


static func style_btn_hover() -> StyleBoxFlat:
	var sb := style_btn_normal()
	sb.border_color = BORDER_LIT
	return sb
