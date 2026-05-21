extends "res://scenes/panels/TabbedSlidePanel.gd"


func _init() -> void:
	width_pct = 0.76
	panel_title = "⚙ Operations hub"


func _build_tabs() -> void:
	var dash := preload("res://scenes/panels/operations/OperationsDashboardTab.gd").new() as VBoxContainer
	add_tab(dash, "Dashboard")
	var schematic := preload("res://scenes/panels/operations/PlotSchematicTab.gd").new() as VBoxContainer
	add_tab(schematic, "Recipe chains")
	var construction := preload("res://scenes/panels/construction/ConstructionDeskTab.gd").new() as VBoxContainer
	add_tab(construction, "Construction")
