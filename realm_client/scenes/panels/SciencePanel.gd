extends "res://scenes/panels/TabbedSlidePanel.gd"


func _init() -> void:
	width_pct = 0.68
	panel_title = "🔬 Science Lab"


func _build_tabs() -> void:
	_add_api_tab("Elements", func(cb): API.get_science_elements(cb))
	_add_api_tab("Reactions", func(cb): API.get_science_reactions(cb))
	add_tab(preload("res://scenes/panels/science/AssayBookTab.gd").new(), "Assay book")
	add_tab(preload("res://scenes/panels/science/ScienceExperimentTab.gd").new(), "Experiment")


func _add_api_tab(tab_title: String, fetcher: Callable) -> void:
	var tab := preload("res://scenes/panels/GenericListTab.gd").new() as VBoxContainer
	tab.title = tab_title
	tab.fetch_callable = fetcher
	add_tab(tab, tab_title)
