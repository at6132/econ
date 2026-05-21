extends "res://scenes/panels/TabbedSlidePanel.gd"


func _init() -> void:
	width_pct = 0.72
	panel_title = "💰 Finance"


func _build_tabs() -> void:
	var accounts_tab := preload("res://scenes/panels/finance/FinanceAccountsTab.gd").new() as VBoxContainer
	accounts_tab.title = "Accounts"
	accounts_tab.fetch_callable = func(cb: Callable) -> void: API.get_accounts(cb)
	add_tab(accounts_tab, "Accounts")
	var bank_tab := preload("res://scenes/panels/BankRatesTab.gd").new() as VBoxContainer
	bank_tab.title = "Bank"
	bank_tab.fetch_callable = func(cb: Callable) -> void: API.get_bank_rates(cb)
	add_tab(bank_tab, "Bank")
	_add_api_tab("Currencies", func(cb): API.get_banks_currencies(cb))
	_add_api_tab("FX Market", func(cb): API.get_fx_rates(cb))
	_add_api_tab("Futures", func(cb): API.get_futures_orders(cb))
	_add_api_tab("Loan market", func(cb): API.get_loans_market(cb))


func _add_api_tab(tab_title: String, fetcher: Callable) -> void:
	var tab := preload("res://scenes/panels/GenericListTab.gd").new() as VBoxContainer
	tab.title = tab_title
	tab.fetch_callable = fetcher
	add_tab(tab, tab_title)
