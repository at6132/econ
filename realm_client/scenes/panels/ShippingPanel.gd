extends "res://scenes/panels/TabbedSlidePanel.gd"


func _init() -> void:
	width_pct = 0.72
	panel_title = "🚢 Shipping"


func _build_tabs() -> void:
	var dispatch := preload("res://scenes/panels/shipping/DispatchTab.gd").new() as VBoxContainer
	add_tab(dispatch, "Dispatch")
	var routes_wrap := VBoxContainer.new()
	var routes := preload("res://scenes/panels/shipping/RoutesTab.gd").new() as VBoxContainer
	routes.fetch_callable = func(cb): API.get_routes(cb)
	routes_wrap.add_child(routes)
	routes_wrap.add_child(preload("res://scenes/panels/shipping/RouteRegisterStrip.gd").new())
	add_tab(routes_wrap, "Routes")
	var inflight := preload("res://scenes/panels/shipping/InFlightTab.gd").new() as VBoxContainer
	add_tab(inflight, "In flight")
