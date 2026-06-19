class_name ChronicleFeedStyles
extends RefCounted
## World feed kind → icon, tint, and filter category.

const KIND_STYLE: Dictionary = {
	"drought": {"icon": "🌵", "color": Color(0.85, 0.65, 0.2), "cat": "World"},
	"epidemic": {"icon": "🦠", "color": Color(1.0, 0.4, 0.4), "cat": "Population"},
	"mine_collapse": {"icon": "💥", "color": Color(1.0, 0.5, 0.2), "cat": "World"},
	"storm": {"icon": "⛈", "color": Color(0.5, 0.7, 1.0), "cat": "World"},
	"seismic": {"icon": "🌋", "color": Color(0.8, 0.6, 0.3), "cat": "World"},
	"flood": {"icon": "🌊", "color": Color(0.3, 0.6, 1.0), "cat": "World"},
	"price_panic": {"icon": "📉", "color": Color(1.0, 0.4, 0.4), "cat": "Market"},
	"credit_crunch": {"icon": "🏦", "color": Color(1.0, 0.6, 0.2), "cat": "Banking"},
	"route_blocked": {"icon": "🚫", "color": Color(0.9, 0.4, 0.4), "cat": "World"},
	"boom_town": {"icon": "🏗", "color": Color(0.4, 1.0, 0.5), "cat": "World"},
	"currency": {"icon": "💱", "color": Color(0.85, 0.72, 0.2), "cat": "Banking"},
	"laborer_death": {"icon": "💀", "color": Color(0.7, 0.4, 0.4), "cat": "Population"},
	"new_town": {"icon": "🏘", "color": Color(0.5, 1.0, 0.6), "cat": "Population"},
	"experiment": {"icon": "🔬", "color": Color(0.6, 0.8, 1.0), "cat": "Discovery"},
	"reaction": {"icon": "⚗", "color": Color(0.6, 0.8, 1.0), "cat": "Discovery"},
	"price_spike": {"icon": "📈", "color": Color(1.0, 0.7, 0.3), "cat": "Market"},
	"shortage": {"icon": "⚠", "color": Color(1.0, 0.6, 0.2), "cat": "Market"},
	"price_alert": {"icon": "🔔", "color": Color(0.85, 0.72, 0.2), "cat": "Market"},
	"market_bid": {"icon": "📥", "color": Color(0.55, 0.85, 1.0), "cat": "Market"},
	"market_ask": {"icon": "📤", "color": Color(0.65, 1.0, 0.75), "cat": "Market"},
	"market_fill": {"icon": "🤝", "color": Color(0.85, 0.72, 0.2), "cat": "Market"},
	"large_buy": {"icon": "🐋", "color": Color(1.0, 0.55, 0.35), "cat": "Market"},
	"tender_posted": {"icon": "📋", "color": Color(0.7, 0.85, 1.0), "cat": "Contracts"},
	"tender_awarded": {"icon": "✅", "color": Color(0.55, 1.0, 0.65), "cat": "Contracts"},
	"bilateral_contract": {"icon": "📝", "color": Color(0.75, 0.85, 1.0), "cat": "Contracts"},
	"equity_ipo": {"icon": "🏛", "color": Color(0.85, 0.72, 0.2), "cat": "Banking"},
	"equity_fill": {"icon": "💹", "color": Color(0.55, 1.0, 0.65), "cat": "Banking"},
	"company_formed": {"icon": "🏢", "color": Color(0.75, 0.85, 1.0), "cat": "World"},
	"supply_capacity": {"icon": "🏭", "color": Color(0.65, 0.9, 0.75), "cat": "Market"},
	"weekly_digest": {"icon": "📊", "color": Color(0.7, 0.85, 1.0), "cat": "World"},
	"world_feed": {"icon": "🌍", "color": Color(0.75, 0.75, 0.8), "cat": "World"},
}

const FILTER_CATEGORIES: PackedStringArray = [
	"All", "World", "Market", "Population", "Banking", "Discovery", "Contracts",
]

const MY_EVENT_FILTERS: PackedStringArray = [
	"All", "Production", "Trades", "Contracts", "Buildings", "Labor",
]


static func style_for_kind(kind: String) -> Dictionary:
	var k := kind.to_lower()
	for key in KIND_STYLE.keys():
		if key in k:
			return KIND_STYLE[key] as Dictionary
	return {"icon": "•", "color": Color(0.75, 0.75, 0.8), "cat": "World"}


static func category_for_kind(kind: String) -> String:
	return str(style_for_kind(kind).get("cat", "World"))


static func my_event_bucket(kind: String) -> String:
	var k := kind.to_lower()
	if "production" in k or "produce" in k:
		return "Production"
	if "market" in k or "trade" in k or "p2p" in k or "sell" in k or "buy" in k:
		return "Trades"
	if "contract" in k or "supply" in k or "forward" in k or "loan" in k or "lease" in k:
		return "Contracts"
	if "build" in k or "maintain" in k or "decay" in k or "blueprint" in k:
		return "Buildings"
	if "hire" in k or "labor" in k or "wage" in k or "fire" in k:
		return "Labor"
	return "All"
