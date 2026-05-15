extends VBoxContainer
## Survey report listings (intel market).

@onready var listings_list: VBoxContainer = %ListingsList
@onready var my_reports_list: VBoxContainer = %MyReportsList
@onready var refresh_btn: Button = %RefreshBtn


func _ready() -> void:
	_style_btn(refresh_btn)
	refresh_btn.pressed.connect(_refresh)
	_refresh()


func _style_btn(btn: Button) -> void:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.12, 0.12, 0.14)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.55)
	btn.add_theme_stylebox_override("normal", sb)
	btn.add_theme_color_override("font_color", Color(0.9, 0.88, 0.82))


func _refresh() -> void:
	for c in listings_list.get_children():
		c.queue_free()
	for c in my_reports_list.get_children():
		c.queue_free()
	API.get_intel_listings(_on_intel_listings_loaded)


func _on_intel_listings_loaded(data: Dictionary) -> void:
	var listings: Variant = data.get("listings", [])
	if listings is Array and (listings as Array).is_empty():
		var lbl := Label.new()
		lbl.text = "No survey reports listed for sale."
		lbl.add_theme_color_override("font_color", Color(0.65, 0.65, 0.68))
		listings_list.add_child(lbl)
	else:
		for row in listings as Array:
			if row is Dictionary:
				listings_list.add_child(_make_listing_row(row as Dictionary))
	var owned: Variant = data.get("owned_reports", [])
	if owned is Array and (owned as Array).is_empty():
		var lbl2 := Label.new()
		lbl2.text = "You do not own any survey reports yet."
		lbl2.add_theme_color_override("font_color", Color(0.65, 0.65, 0.68))
		my_reports_list.add_child(lbl2)
	else:
		for rep in owned as Array:
			if rep is Dictionary:
				my_reports_list.add_child(_make_my_report_row(rep as Dictionary))


func _make_listing_row(listing: Dictionary) -> PanelContainer:
	var pc := PanelContainer.new()
	var hbox := HBoxContainer.new()
	pc.add_child(hbox)
	var info := VBoxContainer.new()
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var row1 := Label.new()
	row1.text = "Plot %s · %s · tick %d" % [
		str(listing.get("plot_id", "?")),
		str(listing.get("survey_type", "standard")).capitalize(),
		int(listing.get("conducted_at_tick", 0)),
	]
	row1.add_theme_color_override("font_color", Color(0.9, 0.88, 0.82))
	info.add_child(row1)
	var row2 := Label.new()
	row2.text = "Seller: %s — grades hidden until purchase" % WorldState.party_label(str(listing.get("seller", "?")))
	row2.add_theme_font_size_override("font_size", 10)
	row2.add_theme_color_override("font_color", Color(0.65, 0.72, 0.85))
	info.add_child(row2)
	hbox.add_child(info)
	var price: int = int(listing.get("ask_price_cents", 0))
	var buy_btn := Button.new()
	buy_btn.text = "Buy %s" % WorldState.format_money(price)
	var listing_id: String = str(listing.get("listing_id", ""))
	buy_btn.pressed.connect(_on_buy_listing_pressed.bind(listing_id))
	hbox.add_child(buy_btn)
	return pc


func _make_my_report_row(rep: Dictionary) -> PanelContainer:
	var pc := PanelContainer.new()
	var vbox := VBoxContainer.new()
	pc.add_child(vbox)
	var row1 := Label.new()
	row1.text = "Plot %s · %s survey" % [
		str(rep.get("plot_id", "?")),
		str(rep.get("survey_type", "standard")).capitalize(),
	]
	row1.add_theme_color_override("font_color", Color(0.9, 0.88, 0.82))
	vbox.add_child(row1)
	var grades: Variant = rep.get("grades", {})
	if grades is Dictionary:
		var parts: PackedStringArray = []
		for k in (grades as Dictionary).keys():
			var g: float = float((grades as Dictionary)[k])
			if g >= 0.10:
				parts.append("%s %.0f%%" % [str(k).replace("_grade", "").replace("_", " "), g * 100.0])
		var grade_lbl := Label.new()
		grade_lbl.text = ", ".join(parts) if parts.size() > 0 else "No significant grades"
		grade_lbl.add_theme_font_size_override("font_size", 10)
		grade_lbl.add_theme_color_override("font_color", Color(0.65, 0.95, 0.72))
		vbox.add_child(grade_lbl)
	var list_bar := HBoxContainer.new()
	var price_box := SpinBox.new()
	price_box.min_value = 50
	price_box.max_value = 5_000_000
	price_box.value = 60_000
	price_box.suffix = "¢"
	list_bar.add_child(price_box)
	var list_btn := Button.new()
	list_btn.text = "List for sale"
	var report_id: String = str(rep.get("report_id", ""))
	list_btn.pressed.connect(_on_list_report_pressed.bind(report_id, price_box))
	list_bar.add_child(list_btn)
	vbox.add_child(list_bar)
	return pc


func _on_buy_listing_pressed(listing_id: String) -> void:
	API.intel_buy(listing_id, _on_intel_buy_done, WorldState.party_id)


func _on_intel_buy_done(data: Dictionary) -> void:
	if not bool(data.get("ok", false)):
		return
	_refresh()
	API.get_world_summary(WorldState.party_id, _on_world_summary_loaded)
	API.get_world(_on_world_loaded)


func _on_world_summary_loaded(summary: Dictionary) -> void:
	WorldState.apply_summary(summary)


func _on_world_loaded(world: Dictionary) -> void:
	WorldState.apply_world(world)


func _on_list_report_pressed(report_id: String, price_box: SpinBox) -> void:
	API.intel_list_report(report_id, int(price_box.value), _on_intel_list_done, WorldState.party_id)


func _on_intel_list_done(data: Dictionary) -> void:
	if bool(data.get("ok", false)):
		_refresh()
