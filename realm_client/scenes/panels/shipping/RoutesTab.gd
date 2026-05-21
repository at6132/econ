extends VBoxContainer
## Registered routes with daily capacity utilization.

var fetch_callable: Callable = Callable()


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var sc := PanelUI.make_scroll_list()
	sc.name = "Scroll"
	add_child(sc)
	refresh()


func refresh() -> void:
	if not fetch_callable.is_valid():
		return
	fetch_callable.call(_on_routes)


func _on_routes(data: Dictionary) -> void:
	var sc: ScrollContainer = get_node_or_null("Scroll") as ScrollContainer
	if sc == null:
		return
	var list := PanelUI.list_inner(sc)
	PanelUI.clear_children(list)
	if not bool(data.get("ok", true)):
		var err := Label.new()
		err.text = str(data.get("reason", "Error"))
		err.add_theme_color_override("font_color", RealmColors.DANGER)
		list.add_child(err)
		return
	for route in data.get("routes", []) as Array:
		if route is Dictionary:
			list.add_child(_route_block(route as Dictionary))


func _route_block(route: Dictionary) -> VBoxContainer:
	var box := VBoxContainer.new()
	var hdr := Label.new()
	hdr.text = "%s ↔ %s" % [route.get("region_a", ""), route.get("region_b", "")]
	hdr.add_theme_color_override("font_color", RealmColors.ACCENT)
	box.add_child(hdr)
	var today_vol := int(route.get("units_shipped_today", 0))
	var capacity := int(route.get("daily_capacity", 500))
	var pct := float(today_vol) / float(max(1, capacity))
	var cap_lbl := Label.new()
	if pct >= 1.0:
		cap_lbl.text = "⚠ Congested (%d/%d units today)" % [today_vol, capacity]
		cap_lbl.modulate = Color(1.0, 0.4, 0.3)
	elif pct >= 0.7:
		cap_lbl.text = "🟡 Busy (%d/%d units today)" % [today_vol, capacity]
		cap_lbl.modulate = Color(1.0, 0.85, 0.2)
	else:
		cap_lbl.text = "🟢 Available (%d/%d units today)" % [today_vol, capacity]
		cap_lbl.modulate = Color(0.4, 1.0, 0.4)
	box.add_child(cap_lbl)
	for op in route.get("operators", []) as Array:
		if op is Dictionary:
			var ol := Label.new()
			ol.text = "  %s @ %s — %d¢/tile" % [
				op.get("party", ""),
				op.get("plot_id", ""),
				int(op.get("fee_per_tile_cents", 0)),
			]
			ol.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			box.add_child(ol)
	var sep := HSeparator.new()
	box.add_child(sep)
	return box
