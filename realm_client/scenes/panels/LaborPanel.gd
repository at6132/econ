extends "res://scenes/panels/TabbedSlidePanel.gd"


func _init() -> void:
	width_pct = 0.70
	panel_title = "👷 Labor"


func _build_tabs() -> void:
	var browse := preload("res://scenes/panels/LaborBrowseTab.gd").new() as VBoxContainer
	browse.title = "Browse"
	browse.fetch_callable = func(cb: Callable) -> void: API.get_laborers(cb)
	add_tab(browse, "Browse")
	_add_api_tab("My employees", func(cb): API.get_laborers_filtered("?employer=%s" % WorldState.party_id.uri_encode(), cb))
	_add_api_tab("Job openings", func(cb): API.get_job_openings(WorldState.party_id, cb))


func _add_api_tab(tab_title: String, fetcher: Callable) -> void:
	var tab := preload("res://scenes/panels/GenericListTab.gd").new() as VBoxContainer
	tab.title = tab_title
	tab.fetch_callable = fetcher
	add_tab(tab, tab_title)
