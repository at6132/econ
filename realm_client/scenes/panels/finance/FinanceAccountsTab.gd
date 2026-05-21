extends VBoxContainer

var fetch_callable: Callable = Callable()
var title: String = ""
var _net_worth: Label
var _cash: Label
var _inv: Label
var _bldg: Label
var _accounts_list: VBoxContainer


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var hdr := Label.new()
	hdr.text = title if title != "" else "Accounts"
	hdr.add_theme_color_override("font_color", RealmColors.ACCENT)
	add_child(hdr)
	_net_worth = _line_label("NetWorthLabel")
	_cash = _line_label("CashComponent")
	_inv = _line_label("InvComponent")
	_bldg = _line_label("BldgComponent")
	var sc := PanelUI.make_scroll_list()
	sc.name = "Scroll"
	add_child(sc)
	_accounts_list = PanelUI.list_inner(sc)
	_refresh_net_worth()
	WorldState.summary_updated.connect(_refresh_net_worth)
	WorldState.player_updated.connect(_refresh_net_worth)
	if fetch_callable.is_valid():
		refresh()


func _line_label(node_name: String) -> Label:
	var lbl := Label.new()
	lbl.name = node_name
	lbl.add_theme_font_size_override("font_size", 12)
	lbl.add_theme_color_override("font_color", RealmColors.TEXT)
	add_child(lbl)
	return lbl


func _refresh_net_worth() -> void:
	var cash_val := WorldState.player_cash_cents
	var inv_val := WorldState.player_inventory_value_cents
	var bldg_val := WorldState.player_building_book_value_cents
	_net_worth.text = "Net worth: " + WorldState.format_money(cash_val + inv_val + bldg_val)
	_cash.text = "  Cash:       " + WorldState.format_money(cash_val)
	_inv.text = "  Inventory:  " + WorldState.format_money(inv_val)
	_bldg.text = "  Buildings:  " + WorldState.format_money(bldg_val)


func refresh() -> void:
	if not is_inside_tree() or not fetch_callable.is_valid():
		return
	fetch_callable.call(func(data: Dictionary) -> void: _on_accounts(data))


func _on_accounts(data: Dictionary) -> void:
	if not is_instance_valid(self):
		return
	PanelUI.clear_children(_accounts_list)
	_refresh_net_worth()
	var accounts: Variant = data.get("accounts", [])
	if not (accounts is Array) or (accounts as Array).is_empty():
		var lbl := Label.new()
		lbl.text = "No sub-accounts."
		lbl.add_theme_color_override("font_color", RealmColors.MUTED)
		_accounts_list.add_child(lbl)
		return
	for row in accounts as Array:
		if row is Dictionary:
			var line := Label.new()
			line.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			line.text = "%s: %s" % [
				str((row as Dictionary).get("label", "?")),
				WorldState.format_money(
					int((row as Dictionary).get("balance_cents", 0))
				),
			]
			line.add_theme_color_override("font_color", RealmColors.TEXT)
			_accounts_list.add_child(line)
