extends "res://scenes/panels/TabbedSlidePanel.gd"


func _init() -> void:
	width_pct = 0.72
	panel_title = "🤝 Pacts & Contracts"


func _build_tabs() -> void:
	add_tab(PactsTabs.make_supply_tab(), "Supply")
	var forward := preload("res://scenes/panels/pacts/ForwardDeskTab.gd").new() as Control
	add_tab(forward, "Forwards")
	add_tab(preload("res://scenes/panels/pacts/EquityProposeTab.gd").new(), "Equity")
	add_tab(preload("res://scenes/panels/pacts/ServiceProposeTab.gd").new(), "Services")
	add_tab(preload("res://scenes/panels/pacts/InsuranceProposeTab.gd").new(), "Insurance")
	add_tab(preload("res://scenes/panels/pacts/LeaseProposeTab.gd").new(), "Leases")
	var construction := preload("res://scenes/panels/construction/ConstructionDeskTab.gd").new() as Control
	add_tab(construction, "Construction")
	var p2p_tab := VBoxContainer.new()
	p2p_tab.add_child(PactsTabs.make_p2p_strip())
	add_tab(p2p_tab, "P2P Trade")
