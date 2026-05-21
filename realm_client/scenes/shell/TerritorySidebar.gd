extends PanelContainer
## Persistent right command column (web ``realm-command-panel``).

@onready var plot_hint: Label = %PlotHint
@onready var production_label: Label = %ProductionLabel
@onready var inv_scroll: ScrollContainer = %InvScroll
@onready var inventory_list: VBoxContainer = %InventoryList


func _ready() -> void:
	add_theme_stylebox_override("panel", RealmColors.style_panel())
	_apply_typography()
	_configure_labels()
	inv_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	inv_scroll.resized.connect(_sync_inventory_width)
	call_deferred("_sync_inventory_width")
	WorldState.world_updated.connect(_refresh)
	WorldState.summary_updated.connect(_refresh)
	# Inventory + owned-plot HUD ticks every 2 s with /world/player.
	WorldState.player_updated.connect(_refresh)
	_refresh()


func _configure_labels() -> void:
	for lbl in [plot_hint, production_label]:
		lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART


func _sync_inventory_width() -> void:
	var w := inv_scroll.size.x
	if w > 4.0:
		inventory_list.custom_minimum_size.x = w


func _apply_typography() -> void:
	for n in ["TitleLabel", "SectionProd", "SectionInv"]:
		var lbl := find_child(n, true, false) as Label
		if lbl and RealmFonts.font_display:
			lbl.add_theme_font_override("font", RealmFonts.font_display)
			lbl.add_theme_font_size_override("font_size", 9)
			lbl.add_theme_color_override("font_color", RealmColors.ACCENT)
	if RealmFonts.font_body:
		plot_hint.add_theme_font_override("font", RealmFonts.font_body)
		production_label.add_theme_font_override("font", RealmFonts.font_body)
		plot_hint.add_theme_color_override("font_color", RealmColors.DIM)
		production_label.add_theme_color_override("font_color", RealmColors.TEXT)


func _style_inventory_label(lbl: Label, clip: bool = false) -> void:
	if RealmFonts.font_body:
		lbl.add_theme_font_override("font", RealmFonts.font_body)
	if clip:
		lbl.clip_text = true
		lbl.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS


func _material_display(mat_id: String) -> String:
	return mat_id.replace("_", " ").capitalize()


func _refresh() -> void:
	production_label.text = "Active production: %d" % WorldState.active_production_count
	for c in inventory_list.get_children():
		c.queue_free()
	call_deferred("_sync_inventory_width")
	var inv: Dictionary = WorldState.player_inventory
	if inv.is_empty() and not WorldState.plots.is_empty():
		inv = {
			"grain": 10, "coal": 9, "iron_ore": 6, "clay": 7,
			"copper_ore": 6, "timber": 8,
		}
	if inv.is_empty():
		var empty := Label.new()
		empty.text = "(empty)"
		empty.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		_style_inventory_label(empty)
		empty.add_theme_color_override("font_color", RealmColors.MUTED)
		inventory_list.add_child(empty)
		return
	var keys: Array = inv.keys()
	keys.sort()
	for k in keys:
		var row := HBoxContainer.new()
		row.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var name_l := Label.new()
		name_l.text = _material_display(str(k))
		name_l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		name_l.size_flags_stretch_ratio = 1.0
		name_l.add_theme_color_override("font_color", RealmColors.TEXT)
		_style_inventory_label(name_l, true)
		var qty_l := Label.new()
		qty_l.text = str(int(inv[k]))
		qty_l.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		qty_l.custom_minimum_size.x = 40.0
		qty_l.size_flags_horizontal = Control.SIZE_SHRINK_END
		qty_l.add_theme_color_override("font_color", RealmColors.MAGIC)
		_style_inventory_label(qty_l)
		row.add_child(name_l)
		row.add_child(qty_l)
		inventory_list.add_child(row)
