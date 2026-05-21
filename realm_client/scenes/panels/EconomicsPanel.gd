extends "res://scenes/panels/TabbedSlidePanel.gd"


func _init() -> void:
	width_pct = 0.68
	panel_title = "📊 Economics"


func _build_tabs() -> void:
	_add_api_tab("CPI", func(cb): API.get_cpi(cb))
	_add_api_tab("CPI components", func(cb): API.get_cpi_components(cb))
	_add_api_tab("FX rates", func(cb): API.get_fx_rates(cb))
	_add_api_tab("Futures curves", func(cb): API.get_futures_curve("coal", cb))
	_add_advantage_tab()
	_add_trade_balance_tab()


func _add_trade_balance_tab() -> void:
	var tab := preload("res://scenes/panels/economics/TradeBalanceTab.gd").new() as VBoxContainer
	tab.title = "Trade Flows"
	tab.fetch_callable = func(cb: Callable) -> void: API.get_trade_balance(cb)
	add_tab(tab, "Trade Flows")


func _add_api_tab(tab_title: String, fetcher: Callable) -> void:
	var tab := preload("res://scenes/panels/GenericListTab.gd").new() as VBoxContainer
	tab.title = tab_title
	tab.fetch_callable = fetcher
	add_tab(tab, tab_title)


func _add_advantage_tab() -> void:
	var tab := VBoxContainer.new()
	var sc := PanelUI.make_scroll_list()
	var list := PanelUI.list_inner(sc)
	tab.add_child(sc)
	tab.set_script(preload("res://scenes/panels/economics/AdvantageTabLogic.gd"))
	tab.set_meta("list", list)
	add_tab(tab, "Regional advantage")
