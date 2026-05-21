extends "res://scenes/panels/TabbedSlidePanel.gd"

var _overview_tab: VBoxContainer = null
var _ship_tab: VBoxContainer = null


func _init() -> void:
	width_pct = 0.74
	panel_title = "📦 Inventory & logistics"


func _after_open() -> void:
	API.get_world(func(d): WorldState.apply_world(d))
	API.get_world_player(func(p): WorldState.apply_player(p), WorldState.party_id)


func _build_tabs() -> void:
	_overview_tab = preload("res://scenes/panels/inventory/InventoryOverviewTab.gd").new() as VBoxContainer
	_ship_tab = preload("res://scenes/panels/inventory/InventoryShipTab.gd").new() as VBoxContainer
	if _overview_tab.has_signal("ship_requested"):
		_overview_tab.ship_requested.connect(_on_ship_requested)
	if _overview_tab.has_signal("harvest_requested"):
		_overview_tab.harvest_requested.connect(_on_harvest_requested)
	add_tab(_overview_tab, "All stock")
	add_tab(_ship_tab, "Dispatch")


func _on_ship_requested(row: Dictionary) -> void:
	tab_container.current_tab = 1
	if _ship_tab.has_method("prefill_from_row"):
		_ship_tab.call("prefill_from_row", row)


func _on_harvest_requested(plot_id: String, material: String, qty: int) -> void:
	API.harvest_plot_output(
		plot_id,
		material,
		qty,
		func(data: Dictionary) -> void:
			if bool(data.get("ok", false)):
				API.get_world(func(w: Dictionary) -> void: WorldState.apply_world(w))
				API.get_world_player(func(p): WorldState.apply_player(p), WorldState.party_id)
			elif get_tree().current_scene.has_method("show_feedback"):
				get_tree().current_scene.call(
					"show_feedback",
					str(data.get("reason", data.get("detail", "Harvest failed"))),
					true,
				),
	)
