extends VBoxContainer

var fetch_callable: Callable = Callable()
var title: String = ""
var _region_list: VBoxContainer


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var hdr := Label.new()
	hdr.text = title if title != "" else "Trade Flows"
	hdr.add_theme_color_override("font_color", RealmColors.ACCENT)
	add_child(hdr)
	var sc := PanelUI.make_scroll_list()
	sc.name = "Scroll"
	add_child(sc)
	_region_list = PanelUI.list_inner(sc)
	if fetch_callable.is_valid():
		refresh()


func refresh() -> void:
	if not is_inside_tree():
		return
	if not fetch_callable.is_valid():
		return
	fetch_callable.call(_on_data)


func _on_data(data: Dictionary) -> void:
	if not is_instance_valid(self):
		return
	PanelUI.clear_children(_region_list)
	var balance: Dictionary = data.get("trade_balance", {})
	if balance.is_empty():
		var empty := Label.new()
		empty.text = "No inter-region trade recorded yet."
		empty.add_theme_color_override("font_color", RealmColors.MUTED)
		_region_list.add_child(empty)
		return
	var regions: Array = balance.keys()
	regions.sort_custom(
		func(a: String, b: String) -> bool:
			return int((balance[a] as Dictionary).get("net_cents", 0)) > int(
				(balance[b] as Dictionary).get("net_cents", 0)
			)
	)
	for rid in regions:
		var r: Dictionary = balance[rid] as Dictionary
		var net := int(r.get("net_cents", 0))
		_region_list.add_child(_make_row(str(rid), r, net))


func _make_row(rid: String, r: Dictionary, net: int) -> HBoxContainer:
	var hbox := HBoxContainer.new()
	hbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var name_lbl := Label.new()
	name_lbl.text = rid
	name_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	hbox.add_child(name_lbl)
	var exp_lbl := Label.new()
	exp_lbl.text = "↑ %s" % WorldState.format_money(int(r.get("exports_cents", 0)))
	exp_lbl.modulate = Color(0.4, 1.0, 0.4)
	hbox.add_child(exp_lbl)
	var imp_lbl := Label.new()
	imp_lbl.text = "↓ %s" % WorldState.format_money(int(r.get("imports_cents", 0)))
	imp_lbl.modulate = Color(1.0, 0.4, 0.4)
	hbox.add_child(imp_lbl)
	var net_lbl := Label.new()
	net_lbl.text = ("+" if net >= 0 else "") + WorldState.format_money(net)
	net_lbl.modulate = Color(0.4, 1.0, 0.4) if net >= 0 else Color(1.0, 0.4, 0.4)
	hbox.add_child(net_lbl)
	return hbox
