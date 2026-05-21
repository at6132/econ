extends CanvasLayer
## Chronicle — world feed, NPC messages, personal events, price alerts.

const PANEL_WIDTH_PCT := 0.70
const HUD_TOP := 96.0

const WorldFeedTabScript: GDScript = preload("res://scenes/panels/chronicle/WorldFeedTab.gd")
const NpcMessagesTabScript: GDScript = preload("res://scenes/panels/chronicle/NpcMessagesTab.gd")
const MyEventsTabScript: GDScript = preload("res://scenes/panels/chronicle/MyEventsTab.gd")
const AlertsTabScript: GDScript = preload("res://scenes/panels/chronicle/AlertsTab.gd")

@onready var panel: Panel = %Panel
@onready var close_btn: Button = %CloseBtn
@onready var tab_container: TabContainer = %TabContainer


func _ready() -> void:
	PanelUI.style_panel(panel)
	SlidePanelAnim.layout_panel(panel, PANEL_WIDTH_PCT, HUD_TOP)
	close_btn.pressed.connect(close)
	PanelUI.style_btn(close_btn)
	_add_tab(WorldFeedTabScript, "World Feed")
	_add_tab(NpcMessagesTabScript, "NPC Messages")
	_add_tab(MyEventsTabScript, "My Events")
	_add_tab(AlertsTabScript, "Alerts")
	SlidePanelAnim.slide_in(self, panel, PANEL_WIDTH_PCT, true)
	WorldState.unread_feed_count = 0
	WorldState.unread_npc_messages = 0
	WorldState.summary_updated.emit()
	WorldState.feed_updated.connect(_on_feed_updated)
	WorldState.world_updated.connect(_on_world_updated)
	get_viewport().size_changed.connect(_on_resized)
	API.get_world(func(d): WorldState.apply_world(d))


func _add_tab(script: GDScript, title: String) -> void:
	var node: Control = script.new() as Control
	node.name = title.replace(" ", "")
	tab_container.add_child(node)
	var idx := tab_container.get_tab_count() - 1
	tab_container.set_tab_title(idx, title)


func _on_resized() -> void:
	SlidePanelAnim.layout_panel(panel, PANEL_WIDTH_PCT, HUD_TOP)
	var w := SlidePanelAnim.panel_width(panel, PANEL_WIDTH_PCT)
	if panel.position.x < panel.get_viewport().get_visible_rect().size.x - w + 1.0:
		panel.position.x = panel.get_viewport().get_visible_rect().size.x - w


func _on_feed_updated() -> void:
	_refresh_tabs()


func _on_world_updated() -> void:
	_refresh_tabs()


func _refresh_tabs() -> void:
	for c in tab_container.get_children():
		if c.has_method("refresh"):
			c.call("refresh")


func close() -> void:
	if not is_inside_tree():
		return
	SlidePanelAnim.slide_out(self, panel, PANEL_WIDTH_PCT, queue_free, true)
