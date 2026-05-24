extends CanvasLayer

signal nav_pressed(panel_name: String)

@onready var cash_label: Label = $PanelContainer/HBoxContainer/CashLabel
@onready var networth_label: Label = $PanelContainer/HBoxContainer/NetWorthLabel
@onready var time_label: Label = $PanelContainer/HBoxContainer/TimeLabel
@onready var cpi_label: Label = $PanelContainer/HBoxContainer/CPILabel
@onready var prod_count: Label = $PanelContainer/HBoxContainer/ProductionCount
@onready var maint_count: Label = $PanelContainer/HBoxContainer/MaintenanceCount
@onready var contract_count: Label = $PanelContainer/HBoxContainer/ContractCount
@onready var feed_count: Label = $PanelContainer/HBoxContainer/FeedCount
@onready var tick_indicator: Label = $PanelContainer/HBoxContainer/TickIndicator

@onready var map_btn: Button = $PanelContainer/HBoxContainer/NavButtons/MapBtn
@onready var territory_btn: Button = $PanelContainer/HBoxContainer/NavButtons/TerritoryBtn
@onready var market_btn: Button = $PanelContainer/HBoxContainer/NavButtons/MarketBtn
@onready var chronicle_btn: Button = $PanelContainer/HBoxContainer/NavButtons/ChronicleBtn
@onready var contracts_btn: Button = $PanelContainer/HBoxContainer/NavButtons/ContractsBtn
@onready var finance_btn: Button = $PanelContainer/HBoxContainer/NavButtons/FinanceBtn
@onready var labor_btn: Button = $PanelContainer/HBoxContainer/NavButtons/LaborBtn
@onready var lab_btn: Button = $PanelContainer/HBoxContainer/NavButtons/LabBtn
@onready var menu_btn: Button = $PanelContainer/HBoxContainer/NavButtons/MenuBtn


func _ready() -> void:
	WorldState.summary_updated.connect(_refresh)
	WS.tick_event.connect(_on_ws_tick_event)
	_refresh()
	_connect_nav_buttons()
	API.get_world_summary(WorldState.party_id, func(d): WorldState.apply_summary(d))
	API.get_cpi(func(d): WorldState.apply_cpi(d))


func _refresh() -> void:
	if WorldState.lab_mode:
		lab_btn.text = "Observatory"
		lab_btn.add_theme_color_override("font_color", RealmColors.ACCENT)
	else:
		lab_btn.text = "Lab"
		lab_btn.remove_theme_color_override("font_color")
	cash_label.text = WorldState.format_money(WorldState.player_cash_cents)
	networth_label.text = "NW %s" % WorldState.format_money(WorldState.player_net_worth_cents)
	time_label.text = "Day %d · %s · Y%d · tick %d" % [
		WorldState.game_day,
		WorldState.game_season,
		WorldState.game_year,
		WorldState.current_tick,
	]
	cpi_label.text = "CPI %.1f" % WorldState.cpi_current
	prod_count.text = str(WorldState.active_production_count)
	maint_count.text = str(WorldState.maintenance_warning_count)
	contract_count.text = str(WorldState.active_contracts_count)
	feed_count.text = str(WorldState.unread_feed_count)
	maint_count.modulate = Color(1, 0.35, 0.35) if WorldState.maintenance_warning_count > 0 else Color(0.94, 0.92, 0.85)
	feed_count.modulate = Color(1, 0.9, 0.35) if WorldState.unread_feed_count > 0 else Color(0.94, 0.92, 0.85)


func flash_tick_indicator() -> void:
	tick_indicator.modulate = Color(0.35, 1.0, 0.45)
	var t := get_tree().create_timer(0.2)
	t.timeout.connect(func(): tick_indicator.modulate = Color(0.94, 0.92, 0.85))


func _on_ws_tick_event(_data: Dictionary) -> void:
	flash_tick_indicator()


func _connect_nav_buttons() -> void:
	map_btn.pressed.connect(func(): nav_pressed.emit("map"))
	territory_btn.pressed.connect(func(): nav_pressed.emit("territory"))
	market_btn.pressed.connect(func(): nav_pressed.emit("market"))
	chronicle_btn.pressed.connect(func(): nav_pressed.emit("chronicle"))
	contracts_btn.pressed.connect(func(): nav_pressed.emit("contracts"))
	finance_btn.pressed.connect(func(): nav_pressed.emit("finance"))
	labor_btn.pressed.connect(func(): nav_pressed.emit("labor"))
	lab_btn.pressed.connect(func(): nav_pressed.emit("lab"))
	menu_btn.pressed.connect(func(): nav_pressed.emit("menu"))
