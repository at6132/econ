extends "res://scenes/panels/TabbedSlidePanel.gd"


func _init() -> void:
	width_pct = 0.70
	panel_title = "🚢 Shipping"


func _build_tabs() -> void:
	_add_api_tab("Routes", func(cb): API.get_routes(cb))
	_add_api_tab("Uncharted", func(cb): API.get_routes_uncharted(cb))
	_add_api_tab("Active shipments", func(cb):
		API.get_world_player(
			func(p: Dictionary) -> void:
				if not cb.is_valid():
					return
				cb.call({"ok": true, "in_transit": p.get("in_transit", [])}),
			WorldState.party_id,
		)
	)
	_add_api_tab("Roads", func(cb): API.get_roads(cb))


func _add_api_tab(tab_title: String, fetcher: Callable) -> void:
	var tab := preload("res://scenes/panels/GenericListTab.gd").new() as VBoxContainer
	tab.title = tab_title
	tab.fetch_callable = fetcher
	add_tab(tab, tab_title)
