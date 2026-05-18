extends "res://scenes/panels/TabbedSlidePanel.gd"


func _init() -> void:
	width_pct = 0.72
	panel_title = "💰 Finance"


func _build_tabs() -> void:
	_add_api_tab("Accounts", func(cb): API.get_accounts(cb))
	_add_api_tab("Bank", func(cb):
		API.get_bank_rates(cb)
	)
	_add_api_tab("Currencies", func(cb): API.get_banks_currencies(cb))
	_add_api_tab("FX Market", func(cb): API.get_fx_rates(cb))
	_add_api_tab("Futures", func(cb): API.get_futures_orders(cb))
	_add_api_tab("Loan market", func(cb): API.get_loans_market(cb))


func _add_api_tab(tab_title: String, fetcher: Callable) -> void:
	var tab := preload("res://scenes/panels/GenericListTab.gd").new() as VBoxContainer
	tab.title = tab_title
	tab.fetch_callable = fetcher
	add_tab(tab, tab_title)
