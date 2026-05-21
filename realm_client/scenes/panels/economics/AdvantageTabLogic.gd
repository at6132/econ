extends VBoxContainer


func _ready() -> void:
	WorldState.world_updated.connect(refresh)
	call_deferred("refresh")


func refresh() -> void:
	var list: VBoxContainer = get_meta("list") as VBoxContainer
	PanelUI.clear_children(list)
	var adv: Dictionary = WorldState.regional_advantage
	if adv.is_empty() and not WorldState.regional_advantages.is_empty():
		var keys := WorldState.regional_advantages.keys()
		var row: Variant = WorldState.regional_advantages[keys[0]]
		adv = row if row is Dictionary else {}
	if adv.is_empty():
		var lbl := Label.new()
		lbl.text = "Regional advantage data loads from GET /world."
		lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		list.add_child(lbl)
		return
	for cat in BazaarMaterials.EFFICIENCY_CATEGORIES:
		var mult: float = float(adv.get(cat, adv.get(cat.to_lower(), 1.0)))
		var row := Label.new()
		var band := "Average"
		if mult > 1.2:
			band = "Excellent"
		elif mult > 1.05:
			band = "Good"
		elif mult < 0.95:
			band = "Poor"
		row.text = "%s: %s (×%.2f)" % [cat.capitalize(), band, mult]
		list.add_child(row)
