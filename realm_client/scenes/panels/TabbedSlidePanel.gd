extends CanvasLayer
## Base for right-edge tabbed overlays (subclasses set WIDTH_PCT, TITLE, setup tabs).

var width_pct: float = 0.72
var hud_top: float = 96.0
var panel_title: String = "Panel"

@onready var panel: Panel = %Panel
@onready var close_btn: Button = %CloseBtn
@onready var title_lbl: Label = %TitleLabel
@onready var tab_container: TabContainer = %TabContainer


func _ready() -> void:
	PanelUI.style_panel(panel)
	title_lbl.text = panel_title
	SlidePanelAnim.layout_panel(panel, width_pct, hud_top)
	PanelUI.style_btn(close_btn)
	close_btn.pressed.connect(close)
	_build_tabs()
	SlidePanelAnim.slide_in(self, panel, width_pct, true)
	WorldState.world_updated.connect(_on_world_updated)
	WorldState.player_updated.connect(_on_world_updated)
	get_viewport().size_changed.connect(_on_resized)
	call_deferred("_after_open")


func _build_tabs() -> void:
	pass


func _after_open() -> void:
	API.get_world(func(d): WorldState.apply_world(d))


func _on_world_updated() -> void:
	for c in tab_container.get_children():
		if c.has_method("refresh"):
			c.call("refresh")


func _on_resized() -> void:
	SlidePanelAnim.layout_panel(panel, width_pct, hud_top)
	var w := SlidePanelAnim.panel_width(panel, width_pct)
	var vp := panel.get_viewport().get_visible_rect().size
	if panel.position.x < vp.x - w + 1.0:
		panel.position.x = vp.x - w


func add_tab(node: Control, title: String) -> void:
	tab_container.add_child(node)
	tab_container.set_tab_title(tab_container.get_tab_count() - 1, title)


func close() -> void:
	if not is_inside_tree():
		return
	SlidePanelAnim.slide_out(self, panel, width_pct, queue_free, true)
