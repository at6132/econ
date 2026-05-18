extends CanvasLayer

const WIDTH_PCT := 0.30
const HUD_TOP := 96.0

@onready var panel: Panel = %Panel
@onready var close_btn: Button = %CloseBtn
@onready var stats_box: VBoxContainer = %StatsBox


func _ready() -> void:
	PanelUI.style_panel(panel)
	SlidePanelAnim.layout_panel(panel, WIDTH_PCT, HUD_TOP)
	PanelUI.style_btn(close_btn)
	close_btn.pressed.connect(close)
	SlidePanelAnim.slide_in(self, panel, WIDTH_PCT, true)
	_refresh()
	WorldState.summary_updated.connect(_refresh)


func _refresh() -> void:
	PanelUI.clear_children(stats_box)
	_add_line("Party: %s" % WorldState.party_id)
	_add_line("Cash: %s" % WorldState.format_money(WorldState.player_cash_cents))
	_add_line("Net worth: %s" % WorldState.format_money(WorldState.player_net_worth_cents))
	_add_line("Day %d · %s · Year %d" % [WorldState.game_day, WorldState.game_season, WorldState.game_year])
	_add_line("Tick %d" % WorldState.current_tick)
	var save_btn := Button.new()
	save_btn.text = "Save game now"
	save_btn.pressed.connect(func() -> void:
		API.save_game(func(d: Dictionary) -> void:
			if bool(d.get("ok", false)):
				MainFeedback.toast("Game saved")
			else:
				MainFeedback.toast("Save failed", true)
		)
	)
	stats_box.add_child(save_btn)
	var load_btn := Button.new()
	load_btn.text = "Load game"
	load_btn.pressed.connect(func() -> void:
		API.load_game(func(d: Dictionary) -> void:
			if bool(d.get("ok", false)):
				MainFeedback.toast("Game loaded")
				API.get_world(func(w): WorldState.apply_world(w))
			else:
				MainFeedback.toast("Load failed", true)
		)
	)
	stats_box.add_child(load_btn)


func _add_line(text: String) -> void:
	var lbl := Label.new()
	lbl.text = text
	lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	lbl.add_theme_color_override("font_color", RealmColors.TEXT)
	stats_box.add_child(lbl)


func close() -> void:
	SlidePanelAnim.slide_out(self, panel, WIDTH_PCT, queue_free, true)
