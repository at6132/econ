extends VBoxContainer


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var mat := OptionButton.new()
	for m in BazaarMaterials.ALL_MATERIALS:
		mat.add_item(str(m))
		mat.set_item_metadata(mat.item_count - 1, str(m))
	add_child(mat)
	var lbl := Label.new()
	lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(lbl)
	var load := func() -> void:
		if mat.selected < 0:
			return
		API.get_futures_curve(str(mat.get_item_metadata(mat.selected)), func(d: Dictionary) -> void:
			lbl.text = str(d)
		)
	mat.item_selected.connect(func(_i): load.call())
	load.call()
