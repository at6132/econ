extends CanvasLayer
## Primary market shell — wide panel from the right with tabbed bazaar sections.

const PANEL_WIDTH_PCT := 0.75
const HUD_TOP := 96.0

const OrderBookTabScene := preload("res://scenes/panels/bazaar/OrderBookTab.tscn")
const MyListingsTabScene := preload("res://scenes/panels/bazaar/MyListingsTab.tscn")
const SignalsTabScene := preload("res://scenes/panels/bazaar/SignalsTab.tscn")
const IntelTabScene := preload("res://scenes/panels/bazaar/IntelTab.tscn")
const AnalyticsTabScene := preload("res://scenes/panels/bazaar/AnalyticsTab.tscn")

@onready var panel: Panel = %Panel
@onready var close_btn: Button = %CloseBtn
@onready var tab_container: TabContainer = %TabContainer


func _ready() -> void:
	_apply_theme()
	var vp := get_viewport().get_visible_rect().size
	var w: float = vp.x * PANEL_WIDTH_PCT
	panel.size = Vector2(w, vp.y - HUD_TOP)
	panel.position = Vector2(vp.x, HUD_TOP)
	close_btn.mouse_filter = Control.MOUSE_FILTER_STOP
	close_btn.z_index = 10
	close_btn.pressed.connect(close)
	_setup_tabs()
	SlidePanelAnim.slide_in(self, panel, PANEL_WIDTH_PCT, true)
	get_viewport().size_changed.connect(_on_viewport_resized)
	API.get_world(func(d): WorldState.apply_world(d))


func _apply_theme() -> void:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.08, 0.08, 0.1)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.35)
	panel.add_theme_stylebox_override("panel", sb)
	_style_btn(close_btn)


func _style_btn(btn: Button) -> void:
	var s := StyleBoxFlat.new()
	s.bg_color = Color(0.12, 0.12, 0.14)
	s.set_border_width_all(1)
	s.border_color = Color(0.85, 0.72, 0.2, 0.55)
	btn.add_theme_stylebox_override("normal", s)
	btn.add_theme_color_override("font_color", Color(0.9, 0.88, 0.82))


func _setup_tabs() -> void:
	_add_tab(OrderBookTabScene, "Order book")
	_add_tab(MyListingsTabScene, "My listings")
	_add_tab(SignalsTabScene, "Signals")
	_add_tab(IntelTabScene, "Intelligence")
	_add_tab(AnalyticsTabScene, "Analytics")


func _add_tab(scene: PackedScene, title: String) -> void:
	var node: Node = scene.instantiate()
	tab_container.add_child(node)
	var idx := tab_container.get_tab_count() - 1
	tab_container.set_tab_title(idx, title)


func _on_viewport_resized() -> void:
	var vp := get_viewport().get_visible_rect().size
	var w: float = vp.x * PANEL_WIDTH_PCT
	panel.size = Vector2(w, vp.y - HUD_TOP)
	if panel.position.x < vp.x - w + 1.0:
		panel.position.x = vp.x - w


func close() -> void:
	if not is_inside_tree():
		return
	SlidePanelAnim.slide_out(self, panel, PANEL_WIDTH_PCT, queue_free, true)
