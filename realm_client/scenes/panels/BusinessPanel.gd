extends "res://scenes/panels/TabbedSlidePanel.gd"


func _init() -> void:
	width_pct = 0.70
	panel_title = "🏢 Business"


func _build_tabs() -> void:
	_add_api_tab("My businesses", func(cb): API.get_businesses_mine(WorldState.party_id, cb))
	_add_api_tab("Templates", func(cb): API.get_business_templates(cb))
	_add_api_tab("Public registry", func(cb): API.get_businesses_public(cb))


func _add_api_tab(tab_title: String, fetcher: Callable) -> void:
	var tab := preload("res://scenes/panels/GenericListTab.gd").new() as VBoxContainer
	tab.title = tab_title
	tab.fetch_callable = fetcher
	add_tab(tab, tab_title)
