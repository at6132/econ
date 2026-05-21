extends HSplitContainer
## Material selector + live book (asks/bids from ``WorldState``) + buy/sell.

@onready var search_box: LineEdit = %SearchBox
@onready var category_filter: OptionButton = %CategoryFilter
@onready var material_list: ItemList = %MaterialList
@onready var material_name_label: Label = %MaterialNameLabel
@onready var best_ask_label: Label = %BestAskLabel
@onready var best_bid_label: Label = %BestBidLabel
@onready var your_holding_label: Label = %YourHoldingLabel
@onready var chart_title: Label = $RightColumn/ChartTitle
@onready var price_chart: Control = %PriceChart
@onready var book_split: HSplitContainer = %BookSplit
@onready var asks_list: VBoxContainer = %AsksList
@onready var bids_list: VBoxContainer = %BidsList
@onready var buy_qty: SpinBox = %BuyQtySpinBox
@onready var buy_max_price: SpinBox = %BuyMaxPriceBox
@onready var buy_total_label: Label = %BuyTotalLabel
@onready var buy_btn: Button = %BuyBtn
@onready var sell_qty: SpinBox = %SellQtySpinBox
@onready var sell_price: SpinBox = %SellPriceBox
@onready var sell_total_label: Label = %SellTotalLabel
@onready var sell_btn: Button = %SellBtn

var _selected_material: String = "coal"
var _quality_filter: String = "all"
var _sell_from_plot: OptionButton
var _sell_terms: OptionButton
var _buy_deliver_plot: OptionButton


func _ready() -> void:
	split_offset = 220
	call_deferred("_center_book_split")
	_apply_theme()
	_populate_category_filter()
	_populate_material_list("", "All Categories")
	material_list.item_selected.connect(_on_material_selected)
	search_box.text_changed.connect(
		func(t: String) -> void:
			_populate_material_list(t, category_filter.get_item_text(category_filter.selected))
	)
	category_filter.item_selected.connect(
		func(_i: int) -> void:
			_populate_material_list(search_box.text, category_filter.get_item_text(category_filter.selected))
	)
	buy_qty.value_changed.connect(func(_v: float) -> void: _update_buy_total())
	buy_max_price.value_changed.connect(func(_v: float) -> void: _update_buy_total())
	sell_qty.value_changed.connect(func(_v: float) -> void: _update_sell_total())
	sell_price.value_changed.connect(func(_v: float) -> void: _update_sell_total())
	buy_btn.pressed.connect(_on_buy)
	sell_btn.pressed.connect(_on_sell)
	WorldState.world_updated.connect(_on_world_updated)
	_build_quality_filter_row()
	_build_sell_from_plot_row()
	_build_sell_terms_row()
	_build_buy_deliver_row()
	_select_material(_selected_material)


func _build_sell_from_plot_row() -> void:
	var sell_vbox: Node = sell_qty.get_parent()
	if sell_vbox == null:
		return
	if sell_vbox.get_node_or_null("SellFromPlotRow") != null:
		return
	var row := HBoxContainer.new()
	row.name = "SellFromPlotRow"
	row.add_theme_constant_override("separation", 6)
	var lbl := Label.new()
	lbl.text = "List from plot"
	lbl.add_theme_font_size_override("font_size", 11)
	row.add_child(lbl)
	_sell_from_plot = OptionButton.new()
	_sell_from_plot.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_sell_from_plot.item_selected.connect(func(_i: int) -> void: _update_sell_total())
	row.add_child(_sell_from_plot)
	sell_vbox.add_child(row)
	var title: Node = sell_vbox.get_node_or_null("SellTitle")
	if title != null:
		sell_vbox.move_child(row, title.get_index() + 1)
	else:
		sell_vbox.add_child(row)
		sell_vbox.move_child(row, 0)


func _build_sell_terms_row() -> void:
	var sell_vbox: Node = sell_qty.get_parent()
	if sell_vbox == null or sell_vbox.get_node_or_null("SellTermsRow") != null:
		return
	var row := HBoxContainer.new()
	row.name = "SellTermsRow"
	row.add_theme_constant_override("separation", 6)
	var lbl := Label.new()
	lbl.text = "Delivery"
	lbl.add_theme_font_size_override("font_size", 11)
	row.add_child(lbl)
	_sell_terms = OptionButton.new()
	_sell_terms.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_sell_terms.add_item("DDP — you ship after sale")
	_sell_terms.set_item_metadata(0, "ddp")
	_sell_terms.add_item("FOB — buyer collects at your plot")
	_sell_terms.set_item_metadata(1, "fob")
	_sell_terms.select(0)
	row.add_child(_sell_terms)
	sell_vbox.add_child(row)


func _build_buy_deliver_row() -> void:
	var buy_vbox: Node = buy_qty.get_parent()
	if buy_vbox == null or buy_vbox.get_node_or_null("BuyDeliverRow") != null:
		return
	var row := HBoxContainer.new()
	row.name = "BuyDeliverRow"
	row.add_theme_constant_override("separation", 6)
	var lbl := Label.new()
	lbl.text = "Deliver to"
	lbl.add_theme_font_size_override("font_size", 11)
	row.add_child(lbl)
	_buy_deliver_plot = OptionButton.new()
	_buy_deliver_plot.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(_buy_deliver_plot)
	buy_vbox.add_child(row)
	var title: Node = buy_vbox.get_node_or_null("BuyTitle")
	if title != null:
		buy_vbox.move_child(row, title.get_index() + 1)


func _build_quality_filter_row() -> void:
	var parent_col := material_list.get_parent()
	if parent_col == null:
		return
	if parent_col.get_node_or_null("QualityFilterRow") != null:
		return
	var row := HBoxContainer.new()
	row.name = "QualityFilterRow"
	row.add_theme_constant_override("separation", 6)
	parent_col.add_child(row)
	parent_col.move_child(row, material_list.get_index())
	for label_text in ["All Quality", "★ High", "Standard", "▼ Low"]:
		var chip := Button.new()
		chip.text = label_text
		chip.toggle_mode = true
		chip.add_theme_font_size_override("font_size", 10)
		_style_btn(chip)
		chip.pressed.connect(_on_quality_filter_chip.bind(label_text, chip, row))
		row.add_child(chip)
	if row.get_child_count() > 0:
		(row.get_child(0) as Button).button_pressed = true


func _on_quality_filter_chip(label_text: String, chip: Button, row: HBoxContainer) -> void:
	for c in row.get_children():
		if c is Button:
			(c as Button).button_pressed = c == chip
	match label_text:
		"★ High":
			_quality_filter = "high"
		"Standard":
			_quality_filter = "standard"
		"▼ Low":
			_quality_filter = "low"
		_:
			_quality_filter = "all"
	_refresh_order_book()


func _exit_tree() -> void:
	if WorldState.world_updated.is_connected(_on_world_updated):
		WorldState.world_updated.disconnect(_on_world_updated)


func _apply_theme() -> void:
	material_name_label.add_theme_font_size_override("font_size", 18)
	material_name_label.add_theme_color_override("font_color", Color(0.92, 0.9, 0.84))
	_style_btn(buy_btn)
	_style_btn(sell_btn)


func _style_btn(btn: Button) -> void:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.12, 0.12, 0.14)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.55)
	btn.add_theme_stylebox_override("normal", sb)
	btn.add_theme_color_override("font_color", Color(0.9, 0.88, 0.82))


func _on_world_updated() -> void:
	if not _selected_material.is_empty():
		_refresh_order_book()


func _populate_category_filter() -> void:
	category_filter.clear()
	category_filter.add_item("All Categories")
	for cat in BazaarMaterials.MATERIAL_CATEGORIES.keys():
		category_filter.add_item(str(cat))


func _populate_material_list(filter: String, category: String) -> void:
	material_list.clear()
	var mats: Array[String] = []
	if category == "All Categories":
		for i in range(BazaarMaterials.ALL_MATERIALS.size()):
			mats.append(BazaarMaterials.ALL_MATERIALS[i])
	else:
		var bucket: Variant = BazaarMaterials.MATERIAL_CATEGORIES.get(category, [])
		if bucket is Array:
			for x in bucket:
				mats.append(str(x))
	var f := filter.strip_edges().to_lower()
	for m in mats:
		if f != "" and not f in m.to_lower():
			continue
		var display := m.replace("_", " ").capitalize()
		material_list.add_item(display)
		material_list.set_item_metadata(material_list.item_count - 1, m)


func _on_material_selected(idx: int) -> void:
	if idx < 0:
		return
	var mat := str(material_list.get_item_metadata(idx))
	_select_material(mat)


func _select_material(mat: String) -> void:
	_selected_material = mat
	material_name_label.text = mat.replace("_", " ").capitalize()
	material_name_label.modulate = Color.WHITE
	chart_title.text = "Price · %s" % mat.replace("_", " ").capitalize()
	_refresh_order_book()


func _asks_for_material(mat: String) -> Array:
	var out: Array = []
	for row in WorldState.market_asks_rows:
		if row is Dictionary and str((row as Dictionary).get("material", "")) == mat:
			out.append(row)
	return out


func _bids_for_material(mat: String) -> Array:
	var out: Array = []
	for row in WorldState.market_bids_rows:
		if row is Dictionary and str((row as Dictionary).get("material", "")) == mat:
			out.append(row)
	return out


func _ask_qty(row: Dictionary) -> int:
	var q: int = int(row.get("qty_total_remaining", row.get("qty", 0)))
	return maxi(0, q)


func _bid_price(row: Dictionary) -> int:
	return int(row.get("max_price_per_unit_cents", row.get("price_per_unit_cents", 0)))


func _refresh_order_book() -> void:
	if _selected_material.is_empty():
		return
	var sorted_asks: Array = _asks_for_material(_selected_material)
	if _quality_filter != "all":
		var filtered: Array = []
		for row in sorted_asks:
			if row is Dictionary and str((row as Dictionary).get("quality", "standard")) == _quality_filter:
				filtered.append(row)
		sorted_asks = filtered
	sorted_asks.sort_custom(
		func(a: Variant, b: Variant) -> bool:
			return int((a as Dictionary).get("price_per_unit_cents", 0)) < int((b as Dictionary).get("price_per_unit_cents", 0))
	)
	var sorted_bids: Array = _bids_for_material(_selected_material)
	sorted_bids.sort_custom(
		func(a: Variant, b: Variant) -> bool:
			return _bid_price(a as Dictionary) > _bid_price(b as Dictionary)
	)

	for c in asks_list.get_children():
		c.queue_free()
	for c in bids_list.get_children():
		c.queue_free()

	if sorted_asks.is_empty():
		best_ask_label.text = "Best ask: —"
	else:
		best_ask_label.text = "Best ask: %s" % WorldState.format_money(
			int((sorted_asks[0] as Dictionary).get("price_per_unit_cents", 0))
		)
	if sorted_bids.is_empty():
		best_bid_label.text = "Best bid: —"
	else:
		best_bid_label.text = "Best bid: %s" % WorldState.format_money(_bid_price(sorted_bids[0] as Dictionary))

	_refresh_sell_from_plot_options()
	_refresh_buy_deliver_options()
	var carried: int = WorldState.player_material_total(_selected_material)
	var on_site: int = WorldState.player_plot_stash_total(_selected_material)
	var hq := WorldState.player_material_qty(_selected_material, "high")
	var lq := WorldState.player_material_qty(_selected_material, "low")
	if on_site > 0 and carried > 0:
		your_holding_label.text = "Carry %d · on-site %d" % [carried, on_site]
	elif on_site > 0:
		your_holding_label.text = "On-site: %d" % on_site
	elif hq > 0 or lq > 0:
		your_holding_label.text = "Carry: %d (★%d ▼%d)" % [carried, hq, lq]
	else:
		your_holding_label.text = "Carry: %d" % carried

	if sorted_asks.is_empty():
		var empty_ask := Label.new()
		empty_ask.text = "No asks — list for sale below."
		empty_ask.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		empty_ask.add_theme_color_override("font_color", RealmColors.MUTED)
		asks_list.add_child(empty_ask)
	else:
		for i in range(mini(sorted_asks.size(), 12)):
			asks_list.add_child(_make_ask_row(sorted_asks[i] as Dictionary))
	if sorted_bids.is_empty():
		var empty_bid := Label.new()
		empty_bid.text = "No bids — place a limit bid below."
		empty_bid.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		empty_bid.add_theme_color_override("font_color", RealmColors.MUTED)
		bids_list.add_child(empty_bid)
	else:
		for i in range(mini(sorted_bids.size(), 12)):
			bids_list.add_child(_make_bid_row(sorted_bids[i] as Dictionary))

	if not sorted_asks.is_empty():
		buy_max_price.value = float((sorted_asks[0] as Dictionary).get("price_per_unit_cents", 100))
	if not sorted_bids.is_empty():
		sell_price.value = float(_bid_price(sorted_bids[0] as Dictionary) + 1)
	_update_buy_total()
	_update_sell_total()

	var series := _build_market_series(_selected_material)
	if price_chart.has_method("set_market_series"):
		price_chart.call("set_market_series", series.asks, series.bids)


func _build_market_series(mat: String) -> Dictionary:
	var asks := PackedFloat32Array()
	var bids := PackedFloat32Array()
	var window := maxi(2, WorldState.market_history_free_window_ticks)
	var cutoff: int = WorldState.current_tick - window
	for row in WorldState.market_history_rows:
		if not (row is Dictionary):
			continue
		var d: Dictionary = row as Dictionary
		if int(d.get("tick", 0)) < cutoff:
			continue
		var ba: Variant = d.get("best_asks_cents", {})
		var bb: Variant = d.get("best_bids_cents", {})
		var av := -1.0
		var bv := -1.0
		if ba is Dictionary and (ba as Dictionary).has(mat):
			av = float((ba as Dictionary)[mat])
		if bb is Dictionary and (bb as Dictionary).has(mat):
			bv = float((bb as Dictionary)[mat])
		if av < 0.0 and bv < 0.0:
			continue
		asks.append(av)
		bids.append(bv)
	return {"asks": asks, "bids": bids}


func _material_ask_depth(mat: String) -> Dictionary:
	var total := 0
	var sellers: Dictionary = {}
	for row in WorldState.market_asks_rows:
		if not (row is Dictionary):
			continue
		var d: Dictionary = row as Dictionary
		if str(d.get("material", "")) != mat:
			continue
		var q := _ask_qty(d)
		total += q
		sellers[str(d.get("party", ""))] = true
	return {"total": total, "sellers": sellers.size()}


func _make_ask_row(ask: Dictionary) -> HBoxContainer:
	var row := HBoxContainer.new()
	var price: int = int(ask.get("price_per_unit_cents", 0))
	var qty: int = _ask_qty(ask)
	var party: String = str(ask.get("party", "?"))
	var is_mine := party == WorldState.party_id

	var price_lbl := Label.new()
	price_lbl.text = "%d¢" % price
	price_lbl.modulate = Color(1.0, 0.55, 0.55)
	price_lbl.custom_minimum_size.x = 56
	price_lbl.add_theme_color_override("font_color", Color(0.92, 0.9, 0.84))
	row.add_child(price_lbl)

	var depth := _material_ask_depth(_selected_material)
	var qty_lbl := Label.new()
	var depth_suffix := ""
	if depth.total > qty:
		depth_suffix = " (%d sellers)" % depth.sellers
	qty_lbl.text = "×%d%s" % [qty, depth_suffix]
	qty_lbl.custom_minimum_size.x = 72
	qty_lbl.add_theme_color_override("font_color", Color(0.85, 0.83, 0.78))
	row.add_child(qty_lbl)

	var depth_lbl := Label.new()
	depth_lbl.add_theme_font_size_override("font_size", 9)
	depth_lbl.modulate = Color(0.5, 0.5, 0.5)
	var tpgd := maxi(1, WorldState.ticks_per_game_day)
	var days_old := int(WorldState.current_tick - int(ask.get("posted_at_tick", 0))) / tpgd
	if days_old > 20:
		depth_lbl.text = "⏳"
		depth_lbl.modulate = Color(1.0, 0.6, 0.2)
	row.add_child(depth_lbl)

	var terms := str(ask.get("delivery_terms", "ddp")).to_lower()
	var fp := str(ask.get("from_plot_id", ""))
	var seller_lbl := Label.new()
	seller_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	seller_lbl.add_theme_font_size_override("font_size", 10)
	var site := WorldState.plot_site_label(fp) if not fp.is_empty() else ""
	var term_tag := "DDP" if terms != "fob" else "FOB"
	seller_lbl.text = "%s · %s%s" % [
		WorldState.party_label(party),
		term_tag,
		(" @ %s" % site) if not site.is_empty() else "",
	]
	if party == WorldState.party_id:
		seller_lbl.modulate = Color(0.95, 0.82, 0.35)
	elif party == "genesis_exchange":
		seller_lbl.modulate = Color(0.62, 0.68, 0.9)
	else:
		seller_lbl.modulate = Color(0.92, 0.9, 0.84)
	row.add_child(seller_lbl)

	var quality := str(ask.get("quality", "standard"))
	var quality_color := Color(0.4, 1.0, 0.4) if quality == "high" else (
		Color(1.0, 0.4, 0.4) if quality == "low" else Color(0.7, 0.7, 0.7)
	)
	var quality_lbl := Label.new()
	match quality:
		"high":
			quality_lbl.text = "★ HQ"
		"low":
			quality_lbl.text = "▼ LQ"
		_:
			quality_lbl.text = ""
	if not quality_lbl.text.is_empty():
		quality_lbl.modulate = quality_color
		quality_lbl.add_theme_font_size_override("font_size", 9)
		row.add_child(quality_lbl)

	if not is_mine and qty > 0:
		var qb := Button.new()
		qb.text = "Buy"
		_style_btn(qb)
		qb.custom_minimum_size.x = 52
		qb.pressed.connect(func() -> void: _quick_buy(ask))
		row.add_child(qb)

	return row


func _make_bid_row(bid: Dictionary) -> HBoxContainer:
	var row := HBoxContainer.new()
	var price: int = _bid_price(bid)
	var qty: int = int(bid.get("qty_total_remaining", bid.get("qty", 0)))
	var party: String = str(bid.get("party", "?"))

	var price_lbl := Label.new()
	price_lbl.text = "%d¢" % price
	price_lbl.modulate = Color(0.45, 1.0, 0.55)
	price_lbl.custom_minimum_size.x = 56
	price_lbl.add_theme_color_override("font_color", Color(0.92, 0.9, 0.84))
	row.add_child(price_lbl)

	var qty_lbl := Label.new()
	qty_lbl.text = "×%d" % qty
	qty_lbl.custom_minimum_size.x = 48
	qty_lbl.add_theme_color_override("font_color", Color(0.85, 0.83, 0.78))
	row.add_child(qty_lbl)

	var depth_lbl := Label.new()
	depth_lbl.add_theme_font_size_override("font_size", 9)
	var tpgd := maxi(1, WorldState.ticks_per_game_day)
	var days_old := int(WorldState.current_tick - int(bid.get("posted_at_tick", 0))) / tpgd
	if days_old > 20:
		depth_lbl.text = "⏳"
		depth_lbl.modulate = Color(1.0, 0.6, 0.2)
	else:
		depth_lbl.modulate = Color(0.5, 0.5, 0.5)
	row.add_child(depth_lbl)

	var buyer_lbl := Label.new()
	buyer_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	buyer_lbl.add_theme_font_size_override("font_size", 10)
	buyer_lbl.text = WorldState.party_label(party)
	buyer_lbl.modulate = Color(0.95, 0.82, 0.35) if party == WorldState.party_id else Color(0.92, 0.9, 0.84)
	row.add_child(buyer_lbl)

	return row


func _center_book_split() -> void:
	if not is_instance_valid(book_split):
		return
	var w := book_split.size.x
	if w > 40.0:
		book_split.split_offset = int(w * 0.5)


func _quick_buy(ask: Dictionary) -> void:
	var price: int = int(ask.get("price_per_unit_cents", 0))
	var aq := _ask_qty(ask)
	if aq <= 0 or price <= 0:
		return
	var qm: int = mini(1, aq)
	API.market_buy(
		_selected_material,
		qm,
		0,
		_on_quick_buy_result,
		WorldState.party_id,
		price,
		_buy_delivery_plot_id(),
	)


func _on_quick_buy_result(data: Dictionary) -> void:
	_apply_market_action_result(data, "Buy failed")


func _update_buy_total() -> void:
	var total_cents := int(buy_qty.value) * int(buy_max_price.value)
	buy_total_label.text = "Total: %s" % WorldState.format_money(total_cents)
	var afford := total_cents <= WorldState.player_cash_cents
	buy_btn.modulate = Color.WHITE if afford else Color(1, 0.4, 0.4)


func _refresh_sell_from_plot_options() -> void:
	if _sell_from_plot == null:
		return
	var prev := _sell_source_plot_id()
	_sell_from_plot.clear()
	if WorldState.is_carried_material(_selected_material):
		_sell_from_plot.add_item("Personal carry")
		_sell_from_plot.set_item_metadata(0, "")
		return
	var plots := WorldState.plots_with_material(_selected_material, 1)
	if plots.is_empty():
		_sell_from_plot.add_item("(no plot stock — produce or ship first)")
		_sell_from_plot.set_item_metadata(0, "")
		_sell_from_plot.set_item_disabled(0, true)
		return
	for entry in plots:
		if not (entry is Dictionary):
			continue
		var e: Dictionary = entry
		var pid := str(e.get("plot_id", ""))
		var q: int = int(e.get("qty", 0))
		_sell_from_plot.add_item("%s (%d)" % [str(e.get("label", pid)), q])
		_sell_from_plot.set_item_metadata(_sell_from_plot.item_count - 1, pid)
	if not prev.is_empty():
		for i in _sell_from_plot.item_count:
			if str(_sell_from_plot.get_item_metadata(i)) == prev:
				_sell_from_plot.select(i)
				return
	if _sell_from_plot.item_count > 0:
		_sell_from_plot.select(0)


func _refresh_buy_deliver_options() -> void:
	if _buy_deliver_plot == null:
		return
	var prev := _buy_delivery_plot_id()
	_buy_deliver_plot.clear()
	var opts := WorldState.ship_destination_options()
	if opts.is_empty():
		_buy_deliver_plot.add_item("(claim a plot first)")
		_buy_deliver_plot.set_item_metadata(0, "")
		_buy_deliver_plot.set_item_disabled(0, true)
		return
	for entry in opts:
		if not (entry is Dictionary):
			continue
		var e: Dictionary = entry
		_buy_deliver_plot.add_item(str(e.get("label", e.get("plot_id", ""))))
		_buy_deliver_plot.set_item_metadata(_buy_deliver_plot.item_count - 1, str(e.get("plot_id", "")))
	if not prev.is_empty():
		for i in _buy_deliver_plot.item_count:
			if str(_buy_deliver_plot.get_item_metadata(i)) == prev:
				_buy_deliver_plot.select(i)
				return
	if _buy_deliver_plot.item_count > 0:
		_buy_deliver_plot.select(0)


func _sell_delivery_terms() -> String:
	if _sell_terms == null or _sell_terms.item_count == 0:
		return "ddp"
	return str(_sell_terms.get_item_metadata(_sell_terms.selected))


func _buy_delivery_plot_id() -> String:
	if _buy_deliver_plot == null or _buy_deliver_plot.item_count == 0:
		return ""
	if _buy_deliver_plot.selected < 0:
		return ""
	return str(_buy_deliver_plot.get_item_metadata(_buy_deliver_plot.selected))


func _sell_source_plot_id() -> String:
	if _sell_from_plot == null or _sell_from_plot.item_count == 0:
		return ""
	if _sell_from_plot.selected < 0:
		return ""
	return str(_sell_from_plot.get_item_metadata(_sell_from_plot.selected))


func _sell_stock_available() -> int:
	if WorldState.is_carried_material(_selected_material):
		return WorldState.player_material_total(_selected_material)
	var pid := _sell_source_plot_id()
	if pid.is_empty():
		return 0
	return WorldState.plot_output_stock_qty(pid, _selected_material)


func _update_sell_total() -> void:
	var revenue := int(sell_qty.value) * int(sell_price.value)
	sell_total_label.text = "Revenue: %s" % WorldState.format_money(revenue)
	var have := _sell_stock_available()
	if have > 0:
		sell_qty.max_value = float(have)
	var have_stock := int(sell_qty.value) <= have and have > 0
	sell_btn.modulate = Color.WHITE if have_stock else Color(1, 0.4, 0.4)


func _on_buy() -> void:
	var qty := int(buy_qty.value)
	var max_px := int(buy_max_price.value)
	if qty <= 0 or max_px <= 0:
		return
	buy_btn.disabled = true
	API.market_buy(
		_selected_material,
		qty,
		0,
		_on_buy_result,
		WorldState.party_id,
		max_px,
		_buy_delivery_plot_id(),
	)


func _on_buy_result(data: Dictionary) -> void:
	buy_btn.disabled = false
	_apply_market_action_result(data, "Purchase failed")


func _apply_market_action_result(data: Dictionary, fallback_reason: String) -> void:
	if bool(data.get("ok", false)):
		API.get_world(func(w: Dictionary) -> void: WorldState.apply_world(w))
		_refresh_order_book()
		API.get_world_summary(WorldState.party_id, func(s: Dictionary) -> void: WorldState.apply_summary(s))
	else:
		_show_error(str(data.get("reason", fallback_reason)))


func _on_sell() -> void:
	var qty := int(sell_qty.value)
	var price := int(sell_price.value)
	if qty <= 0 or price <= 0:
		return
	var from_plot := _sell_source_plot_id()
	if not WorldState.is_carried_material(_selected_material) and from_plot.is_empty():
		_show_error("Pick a plot with stock to list from")
		return
	sell_btn.disabled = true
	API.market_sell(
		_selected_material,
		qty,
		price,
		_on_sell_result,
		WorldState.party_id,
		from_plot,
		_sell_delivery_terms(),
	)


func _on_sell_result(data: Dictionary) -> void:
	sell_btn.disabled = false
	_apply_market_action_result(data, "Listing failed")


func _show_error(msg: String) -> void:
	var old := material_name_label.text
	material_name_label.text = "⚠ %s" % msg
	material_name_label.modulate = Color(1, 0.35, 0.35)
	await get_tree().create_timer(2.5).timeout
	material_name_label.text = old
	material_name_label.modulate = Color.WHITE
