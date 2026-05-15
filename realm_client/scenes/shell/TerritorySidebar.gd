extends PanelContainer
## Persistent right command column (web ``realm-command-panel``).

@onready var plot_hint: Label = %PlotHint
@onready var production_label: Label = %ProductionLabel
@onready var inventory_list: VBoxContainer = %InventoryList


func _ready() -> void:
	add_theme_stylebox_override("panel", RealmColors.style_panel())
	_apply_typography()
	WorldState.world_updated.connect(_refresh)
	WorldState.summary_updated.connect(_refresh)
	_refresh()


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


func _refresh() -> void:
	production_label.text = "Active production: %d" % WorldState.active_production_count
	for c in inventory_list.get_children():
		c.queue_free()
	var inv: Dictionary = WorldState.player_inventory
	if inv.is_empty() and not WorldState.plots.is_empty():
		# Demo inventory for shell preview when API empty
		inv = {
			"grain": 10, "coal": 9, "iron_ore": 6, "clay": 7,
			"copper_ore": 6, "timber": 8, "electricity": 8,
		}
	if inv.is_empty():
		var empty := Label.new()
		empty.text = "(empty)"
		empty.add_theme_color_override("font_color", RealmColors.MUTED)
		inventory_list.add_child(empty)
		return
	var keys: Array = inv.keys()
	keys.sort()
	for k in keys:
		var row := HBoxContainer.new()
		var name_l := Label.new()
		name_l.text = str(k)
		name_l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		name_l.add_theme_color_override("font_color", RealmColors.TEXT)
		var qty_l := Label.new()
		qty_l.text = str(int(inv[k]))
		qty_l.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		qty_l.add_theme_color_override("font_color", RealmColors.MAGIC)
		if RealmFonts.font_body:
			name_l.add_theme_font_override("font", RealmFonts.font_body)
			qty_l.add_theme_font_override("font", RealmFonts.font_body)
		row.add_child(name_l)
		row.add_child(qty_l)
		inventory_list.add_child(row)
