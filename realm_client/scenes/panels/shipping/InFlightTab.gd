extends VBoxContainer


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var sc := PanelUI.make_scroll_list()
	sc.size_flags_vertical = Control.SIZE_EXPAND_FILL
	var list := PanelUI.list_inner(sc)
	add_child(sc)
	set_meta("list", list)
	WorldState.player_updated.connect(refresh)
	refresh()


func refresh() -> void:
	var list: VBoxContainer = get_meta("list") as VBoxContainer
	if list == null:
		return
	PanelUI.clear_children(list)
	for ship in WorldState.in_transit:
		if not (ship is Dictionary):
			continue
		var s: Dictionary = ship
		var lbl := Label.new()
		lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		lbl.text = "%s × %d · %s → %s · ETA %s" % [
			s.get("material", "?"),
			int(s.get("qty", 0)),
			s.get("from_plot_id", "?"),
			s.get("dest_plot_id", "?"),
			WorldState.format_ticks_as_gametime(
				maxi(0, int(s.get("arrive_tick", 0)) - WorldState.current_tick)
			),
		]
		list.add_child(lbl)
	if list.get_child_count() == 0:
		var e := Label.new()
		e.text = "No active shipments — use Inventory → Dispatch."
		e.add_theme_color_override("font_color", RealmColors.MUTED)
		list.add_child(e)
