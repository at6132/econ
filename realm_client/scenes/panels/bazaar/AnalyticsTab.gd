extends VBoxContainer
## Paid analytics products (engine ``purchase_analytics_product``).

const PRODUCTS: Array = [
	{"id": "price_history", "label": "Price history", "cost": 300, "desc": "Best-ask snapshots for one material (last 30 game-days).", "param": "material"},
	{"id": "regional_survey", "label": "Regional survey aggregate", "cost": 500, "desc": "Average subsurface grade for a mineral in a region.", "param": "mineral_region"},
	{"id": "party_volume", "label": "Party trade volume", "cost": 800, "desc": "Significant buy/sell flows for a party (7-day window).", "param": "party_id"},
	{"id": "supply_shortage", "label": "Supply shortage scan", "cost": 400, "desc": "Materials with thin ask depth right now.", "param": "none"},
	{"id": "regional_risk", "label": "Regional risk report", "cost": 1000, "desc": "Seasonal notes + active world events by island.", "param": "none"},
	{"id": "market_cycle", "label": "Market cycle report", "cost": 800, "desc": "Materials trading above moving average + bank posture.", "param": "none"},
	{"id": "regional_efficiency", "label": "Regional efficiency", "cost": 2000, "desc": "Qualitative production band for a category on a landmass.", "param": "landmass_category"},
]

@onready var product_list: VBoxContainer = %ProductList
@onready var result_panel: PanelContainer = %ResultPanel
@onready var result_label: RichTextLabel = %RichTextLabel
@onready var history_list: VBoxContainer = %HistoryList


func _ready() -> void:
	result_panel.hide()
	_populate_products()
	_load_history()


func _populate_products() -> void:
	for p in PRODUCTS:
		if p is Dictionary:
			product_list.add_child(_make_product_card(p as Dictionary))


func _make_product_card(product: Dictionary) -> PanelContainer:
	var pc := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.1, 0.1, 0.12)
	sb.set_content_margin_all(8)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.22)
	pc.add_theme_stylebox_override("panel", sb)
	var vbox := VBoxContainer.new()
	pc.add_child(vbox)
	var header := HBoxContainer.new()
	var name_lbl := Label.new()
	name_lbl.text = str(product.get("label", ""))
	name_lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	name_lbl.add_theme_color_override("font_color", Color(0.92, 0.9, 0.84))
	header.add_child(name_lbl)
	var cost_lbl := Label.new()
	cost_lbl.text = WorldState.format_money(int(product.get("cost", 0)))
	cost_lbl.modulate = Color(0.92, 0.82, 0.35)
	header.add_child(cost_lbl)
	vbox.add_child(header)
	var desc_lbl := Label.new()
	desc_lbl.text = str(product.get("desc", ""))
	desc_lbl.add_theme_font_size_override("font_size", 10)
	desc_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	desc_lbl.add_theme_color_override("font_color", Color(0.72, 0.72, 0.75))
	vbox.add_child(desc_lbl)

	var param_type: String = str(product.get("param", "none"))
	var param_box: Control = null
	var action_bar := HBoxContainer.new()
	if param_type == "material":
		var opt := OptionButton.new()
		for i in range(BazaarMaterials.ALL_MATERIALS.size()):
			var mid := str(BazaarMaterials.ALL_MATERIALS[i])
			opt.add_item(mid.replace("_", " ").capitalize())
			opt.set_item_metadata(i, mid)
		param_box = opt
		action_bar.add_child(opt)
	elif param_type == "mineral_region":
		var h := HBoxContainer.new()
		var mopt := OptionButton.new()
		for i in range(BazaarMaterials.SURVEY_MINERALS.size()):
			var mn := str(BazaarMaterials.SURVEY_MINERALS[i])
			mopt.add_item(mn.replace("_", " ").capitalize())
			mopt.set_item_metadata(i, mn)
		h.add_child(mopt)
		var ropt := OptionButton.new()
		for j in range(BazaarMaterials.REGION_IDS.size()):
			var rid := str(BazaarMaterials.REGION_IDS[j])
			ropt.add_item(rid)
			ropt.set_item_metadata(j, rid)
		h.add_child(ropt)
		param_box = h
		action_bar.add_child(h)
	elif param_type == "party_id":
		var le := LineEdit.new()
		le.placeholder_text = "Party id (e.g. genesis_settlement)"
		le.custom_minimum_size.x = 220.0
		param_box = le
		action_bar.add_child(le)
	elif param_type == "landmass_category":
		var h2 := HBoxContainer.new()
		var sbx := SpinBox.new()
		sbx.min_value = 0
		sbx.max_value = 12
		sbx.value = 0
		h2.add_child(sbx)
		var copt := OptionButton.new()
		for k in range(BazaarMaterials.EFFICIENCY_CATEGORIES.size()):
			var cid := str(BazaarMaterials.EFFICIENCY_CATEGORIES[k])
			copt.add_item(cid.capitalize())
			copt.set_item_metadata(k, cid)
		h2.add_child(copt)
		param_box = h2
		action_bar.add_child(h2)

	var buy_btn := Button.new()
	buy_btn.text = "Purchase"
	buy_btn.pressed.connect(func() -> void: _purchase_product(product, param_box))
	action_bar.add_child(buy_btn)
	vbox.add_child(action_bar)
	return pc


func _purchase_product(product: Dictionary, param_box: Variant) -> void:
	var pid: String = str(product.get("id", ""))
	var params := {}
	var ptype: String = str(product.get("param", "none"))
	if ptype == "material" and param_box is OptionButton:
		params["material"] = str((param_box as OptionButton).get_item_metadata((param_box as OptionButton).selected))
	elif ptype == "mineral_region" and param_box is HBoxContainer:
		var kids: Array = (param_box as HBoxContainer).get_children()
		if kids.size() >= 2 and kids[0] is OptionButton and kids[1] is OptionButton:
			var mineral := str((kids[0] as OptionButton).get_item_metadata((kids[0] as OptionButton).selected))
			var region_id := str((kids[1] as OptionButton).get_item_metadata((kids[1] as OptionButton).selected))
			params["mineral"] = mineral
			params["region_id"] = region_id
	elif ptype == "party_id" and param_box is LineEdit:
		params["party_id"] = (param_box as LineEdit).text.strip_edges()
	elif ptype == "landmass_category" and param_box is HBoxContainer:
		var kids2: Array = (param_box as HBoxContainer).get_children()
		if kids2.size() >= 2 and kids2[0] is SpinBox and kids2[1] is OptionButton:
			params["landmass_id"] = int((kids2[0] as SpinBox).value)
			params["category"] = str((kids2[1] as OptionButton).get_item_metadata((kids2[1] as OptionButton).selected))

	var title: String = str(product.get("label", ""))
	API.analytics_purchase(pid, params, _on_analytics_purchase_done.bind(pid, title), WorldState.party_id)


func _on_analytics_purchase_done(product_id: String, title: String, data: Dictionary) -> void:
	if bool(data.get("ok", false)):
		_display_result(product_id, data.get("data", {}) as Dictionary, title)
		_load_history()
		API.get_world_summary(WorldState.party_id, _on_world_summary_loaded)
	else:
		result_panel.show()
		result_label.text = "[color=#ff6666]⚠ %s[/color]" % str(data.get("reason", "Purchase failed"))


func _on_world_summary_loaded(summary: Dictionary) -> void:
	WorldState.apply_summary(summary)


func _display_result(product_id: String, data: Dictionary, title: String) -> void:
	result_panel.show()
	var text := "[b]%s[/b]\n\n" % title
	match product_id:
		"price_history":
			var series: Variant = data.get("series", [])
			if not (series is Array) or (series as Array).is_empty():
				text += "No price points in this window yet."
			else:
				var arr: Array = series as Array
				var tail: int = mini(12, arr.size())
				for i in range(arr.size() - tail, arr.size()):
					var p: Variant = arr[i]
					if p is Dictionary:
						text += "Tick %d: %d¢\n" % [
							int((p as Dictionary).get("tick", 0)),
							int((p as Dictionary).get("price_cents", 0)),
						]
		"supply_shortage":
			var mats: Variant = data.get("materials_in_shortage", [])
			text += "Thin ask depth:\n"
			if mats is Array and (mats as Array).is_empty():
				text += "  (none flagged)\n"
			elif mats is Array:
				for m in mats as Array:
					text += "  • %s\n" % str(m).replace("_", " ").capitalize()
		"party_volume":
			var prof: Variant = data.get("profile", [])
			text += "Party: %s\n" % str(data.get("party", ""))
			if prof is Array:
				for line in prof as Array:
					if line is Dictionary:
						text += "  • %s (%s) — %s\n" % [
							str((line as Dictionary).get("material", "?")),
							str((line as Dictionary).get("side", "?")),
							str((line as Dictionary).get("signal", "?")),
						]
		"regional_survey":
			text += "Region %s · %s\nAvg grade %.3f (%s)\n" % [
				str(data.get("region_id", "")),
				str(data.get("mineral", "")),
				float(data.get("avg_grade", 0.0)),
				str(data.get("label", "")),
			]
		"regional_risk":
			text += "Season %s\n" % str(data.get("season", ""))
			var islands: Variant = data.get("islands", [])
			if islands is Array:
				for isl in islands as Array:
					if isl is Dictionary:
						var ae: Variant = (isl as Dictionary).get("active_events", [])
						var n_active := (ae as Array).size() if ae is Array else 0
						text += "Island %s: %d active event(s)\n" % [
							str((isl as Dictionary).get("island_id", "?")),
							n_active,
						]
		"market_cycle":
			var flagged: Variant = data.get("flagged_materials", [])
			var fc := (flagged as Array).size() if flagged is Array else 0
			text += "Flagged materials: %d\n" % fc
			var bc: Variant = data.get("bank_credit", {})
			if bc is Dictionary:
				text += "Credit crunch: %s\n" % str((bc as Dictionary).get("crunch_active", "?"))
		"regional_efficiency":
			text += "Landmass %s · %s\nBand: [b]%s[/b]\n" % [
				str(data.get("landmass_id", "")),
				str(data.get("category", "")),
				str(data.get("band", "")),
			]
		_:
			for k in data.keys():
				text += "%s: %s\n" % [str(k), str(data[k])]
	result_label.text = text


func _load_history() -> void:
	for c in history_list.get_children():
		c.queue_free()
	API.get_analytics_history(_on_analytics_history_loaded, WorldState.party_id)


func _on_analytics_history_loaded(data: Dictionary) -> void:
	var hist: Variant = data.get("purchases", [])
	if not (hist is Array) or (hist as Array).is_empty():
		return
	var arr: Array = hist as Array
	var start: int = maxi(0, arr.size() - 8)
	for i in range(start, arr.size()):
		var entry: Variant = arr[i]
		if entry is Dictionary:
			var lbl := Label.new()
			lbl.text = "Tick %d · %s" % [
				int((entry as Dictionary).get("tick", 0)),
				str((entry as Dictionary).get("product", "?")),
			]
			lbl.add_theme_font_size_override("font_size", 10)
			lbl.add_theme_color_override("font_color", Color(0.65, 0.65, 0.7))
			history_list.add_child(lbl)
