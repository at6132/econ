extends VBoxContainer
## Lists your resting asks and bids with cancel actions.

@onready var asks_list: VBoxContainer = %AsksList
@onready var bids_list: VBoxContainer = %BidsList
@onready var refresh_btn: Button = %RefreshBtn


func _ready() -> void:
	_style_btn(refresh_btn)
	refresh_btn.pressed.connect(_refresh)
	WorldState.world_updated.connect(_refresh)
	_refresh()


func _exit_tree() -> void:
	if WorldState.world_updated.is_connected(_refresh):
		WorldState.world_updated.disconnect(_refresh)


func _style_btn(btn: Button) -> void:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.12, 0.12, 0.14)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.55)
	btn.add_theme_stylebox_override("normal", sb)
	btn.add_theme_color_override("font_color", Color(0.9, 0.88, 0.82))


func _refresh() -> void:
	for c in asks_list.get_children():
		c.queue_free()
	for c in bids_list.get_children():
		c.queue_free()
	var my_asks: Array = []
	var my_bids: Array = []
	for row in WorldState.market_asks_rows:
		if row is Dictionary and str((row as Dictionary).get("party", "")) == WorldState.party_id:
			my_asks.append(row)
	for row in WorldState.market_bids_rows:
		if row is Dictionary and str((row as Dictionary).get("party", "")) == WorldState.party_id:
			my_bids.append(row)
	_render_asks(my_asks)
	_render_bids(my_bids)


func _render_asks(asks: Array) -> void:
	if asks.is_empty():
		var lbl := Label.new()
		lbl.text = "No active sell listings."
		lbl.modulate = Color(0.55, 0.55, 0.58)
		lbl.add_theme_color_override("font_color", Color(0.85, 0.83, 0.78))
		asks_list.add_child(lbl)
		return
	for a in asks:
		if a is Dictionary:
			asks_list.add_child(_make_ask_row(a as Dictionary))


func _render_bids(bids: Array) -> void:
	if bids.is_empty():
		var lbl := Label.new()
		lbl.text = "No active buy orders."
		lbl.modulate = Color(0.55, 0.55, 0.58)
		lbl.add_theme_color_override("font_color", Color(0.85, 0.83, 0.78))
		bids_list.add_child(lbl)
		return
	for b in bids:
		if b is Dictionary:
			bids_list.add_child(_make_bid_row(b as Dictionary))


func _make_ask_row(ask: Dictionary) -> HBoxContainer:
	var row := HBoxContainer.new()
	var mat: String = str(ask.get("material", "?"))
	var price: int = int(ask.get("price_per_unit_cents", 0))
	var qty: int = int(ask.get("qty_total_remaining", ask.get("qty", 0)))
	var info := Label.new()
	var terms := str(ask.get("delivery_terms", "ddp")).to_upper()
	var fp := str(ask.get("from_plot_id", ""))
	var site := (" @ %s" % WorldState.plot_site_label(fp)) if not fp.is_empty() else ""
	info.text = "%s × %d @ %d¢ (%s%s) ≈ %s" % [
		mat.replace("_", " ").capitalize(),
		qty,
		price,
		terms,
		site,
		WorldState.format_money(price * qty),
	]
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	info.add_theme_color_override("font_color", Color(0.9, 0.88, 0.82))
	row.add_child(info)
	var cancel_btn := Button.new()
	cancel_btn.text = "Cancel"
	cancel_btn.add_theme_color_override("font_color", Color(1.0, 0.55, 0.55))
	cancel_btn.pressed.connect(
		func() -> void:
			API.market_cancel(
				str(ask.get("order_id", "")),
				func(data: Dictionary) -> void:
					if bool(data.get("ok", false)):
						API.get_world(func(w): WorldState.apply_world(w))
						_refresh()
			)
	)
	row.add_child(cancel_btn)
	return row


func _make_bid_row(bid: Dictionary) -> HBoxContainer:
	var row := HBoxContainer.new()
	var mat: String = str(bid.get("material", "?"))
	var price: int = int(bid.get("max_price_per_unit_cents", bid.get("price_per_unit_cents", 0)))
	var qty: int = int(bid.get("qty_total_remaining", bid.get("qty", 0)))
	var info := Label.new()
	info.text = "Bid %s × %d @ %d¢ max" % [mat.replace("_", " ").capitalize(), qty, price]
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	info.add_theme_color_override("font_color", Color(0.9, 0.88, 0.82))
	row.add_child(info)
	var cancel_btn := Button.new()
	cancel_btn.text = "Cancel"
	cancel_btn.add_theme_color_override("font_color", Color(1.0, 0.55, 0.55))
	cancel_btn.pressed.connect(
		func() -> void:
			API.market_cancel_bid(
				str(bid.get("order_id", "")),
				func(data: Dictionary) -> void:
					if bool(data.get("ok", false)):
						API.get_world(func(w): WorldState.apply_world(w))
						_refresh()
			)
	)
	row.add_child(cancel_btn)
	return row
