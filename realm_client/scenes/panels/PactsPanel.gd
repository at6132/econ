extends "res://scenes/panels/TabbedSlidePanel.gd"


func _init() -> void:
	width_pct = 0.72
	panel_title = "🤝 Pacts & Contracts"


func _build_tabs() -> void:
	add_tab(PactsTabs.make_supply_tab(), "Supply")
	add_tab(PactsTabs.make_contract_list_tab(["forward_contract"], "Forwards"), "Forwards")
	add_tab(PactsTabs.make_contract_list_tab(["equity_stake", "equity"], "Equity"), "Equity")
	add_tab(PactsTabs.make_contract_list_tab(["service_subscription", "service"], "Services"), "Services")
	add_tab(PactsTabs.make_contract_list_tab(["insurance"], "Insurance"), "Insurance")
	add_tab(PactsTabs.make_contract_list_tab(["land_lease"], "Leases"), "Leases")
	add_tab(PactsTabs.make_contract_list_tab(["construction_order"], "Construction"), "Construction")
	var p2p_tab := VBoxContainer.new()
	p2p_tab.add_child(PactsTabs.make_p2p_strip())
	add_tab(p2p_tab, "P2P Trade")
