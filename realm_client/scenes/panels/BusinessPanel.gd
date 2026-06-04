extends "res://scenes/panels/TabbedSlidePanel.gd"


func _init() -> void:
	width_pct = 0.74
	panel_title = "🏢 Business"


func _build_tabs() -> void:
	var desk := preload("res://scenes/panels/business/BusinessDeskTab.gd").new() as VBoxContainer
	add_tab(desk, "Desk")
	add_tab(preload("res://scenes/panels/business/GridUtilityLicensesTab.gd").new(), "Grid utility")
	add_tab(preload("res://scenes/panels/build/BlueprintCatalogTab.gd").new(), "Blueprints")
	add_tab(preload("res://scenes/panels/business/CodexStubTab.gd").new(), "Codex")
	_add_api_tab("Public registry", func(cb): API.get_businesses_public(cb))


func _add_api_tab(tab_title: String, fetcher: Callable) -> void:
	var tab := preload("res://scenes/panels/GenericListTab.gd").new() as VBoxContainer
	tab.title = tab_title
	tab.fetch_callable = fetcher
	add_tab(tab, tab_title)
