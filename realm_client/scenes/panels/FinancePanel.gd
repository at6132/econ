extends "res://scenes/panels/TabbedSlidePanel.gd"


func _init() -> void:
	width_pct = 0.74
	panel_title = "💰 Finance"


func _build_tabs() -> void:
	var accounts_tab := preload("res://scenes/panels/finance/FinanceAccountsTab.gd").new() as VBoxContainer
	accounts_tab.title = "Accounts"
	accounts_tab.fetch_callable = func(cb: Callable) -> void: API.get_accounts(cb)
	add_tab(accounts_tab, "Accounts")
	var loans := preload("res://scenes/panels/finance/FinanceLoansTab.gd").new() as VBoxContainer
	add_tab(loans, "Loans")
	var bank_tab := preload("res://scenes/panels/BankRatesTab.gd").new() as VBoxContainer
	bank_tab.title = "Bank rates"
	bank_tab.fetch_callable = func(cb: Callable) -> void: API.get_bank_rates(cb)
	add_tab(bank_tab, "Rates")
	_add_api_tab("Currencies", func(cb): API.get_banks_currencies(cb))
	add_tab(preload("res://scenes/panels/finance/FxDeskTab.gd").new(), "FX trade")
	add_tab(preload("res://scenes/panels/finance/FuturesDeskTab.gd").new(), "Futures")
	add_tab(preload("res://scenes/panels/finance/LoanMarketDeskTab.gd").new(), "Loan market")


func _add_api_tab(tab_title: String, fetcher: Callable) -> void:
	var tab := preload("res://scenes/panels/GenericListTab.gd").new() as VBoxContainer
	tab.title = tab_title
	tab.fetch_callable = fetcher
	add_tab(tab, tab_title)
