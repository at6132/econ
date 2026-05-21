extends CanvasLayer
## Cmd/Ctrl+K quick navigation (Phase 2 parity with web command palette).

signal closed

const ACTIONS: Array = [
	["territory", "Territory & works", "FIELD"],
	["operations", "Operations hub", "FIELD"],
	["market", "Bazaar & market tape", "COMMERCE"],
	["inventory", "Inventory & logistics", "COMMERCE"],
	["caravans", "Shipping & routes", "COMMERCE"],
	["economics", "Economics dashboards", "COMMERCE"],
	["tenders", "Tenders & bids", "COMMERCE"],
	["chronicle", "Chronicle & feed", "REALM"],
	["contracts", "Pacts & contracts", "REALM"],
	["finance", "Finance & banking", "REALM"],
	["labor", "Labor & hiring", "REALM"],
	["business", "Business entities", "REALM"],
	["lab", "Science lab", "REALM"],
	["menu", "Profile & settings", "REALM"],
]

@onready var _dim: ColorRect = $Dim
@onready var _panel: PanelContainer = $Panel
@onready var _search: LineEdit = %Search
@onready var _list: ItemList = %List

var _filtered: Array = []


func _ready() -> void:
	layer = 60
	visible = false
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.08, 0.08, 0.1, 0.98)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.45)
	sb.set_corner_radius_all(6)
	_panel.add_theme_stylebox_override("panel", sb)
	_dim.gui_input.connect(_on_dim_input)
	_search.text_changed.connect(_on_search_changed)
	_list.item_activated.connect(_on_item_activated)
	_rebuild_filter("")


func open_palette() -> void:
	visible = true
	_search.text = ""
	_rebuild_filter("")
	_search.grab_focus()
	_list.select(0)


func close_palette() -> void:
	if not visible:
		return
	visible = false
	closed.emit()


func _on_dim_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.pressed and mb.button_index == MOUSE_BUTTON_LEFT:
			close_palette()


func _unhandled_input(event: InputEvent) -> void:
	if not visible:
		return
	if event.is_action_pressed("ui_cancel"):
		close_palette()
		get_viewport().set_input_as_handled()
	elif event is InputEventKey and event.pressed:
		var key := event as InputEventKey
		if key.keycode == KEY_DOWN or key.keycode == KEY_UP:
			get_viewport().set_input_as_handled()


func _on_search_changed(text: String) -> void:
	_rebuild_filter(text)


func _rebuild_filter(query: String) -> void:
	_list.clear()
	_filtered.clear()
	var q := query.strip_edges().to_lower()
	for row in ACTIONS:
		var pid: String = row[0]
		var label: String = row[1]
		var group: String = row[2]
		var hay := ("%s %s %s" % [pid, label, group]).to_lower()
		if q.is_empty() or hay.contains(q):
			_filtered.append(row)
			_list.add_item("[%s]  %s" % [group, label])
	if _list.item_count > 0:
		_list.select(0)


func _on_item_activated(index: int) -> void:
	if index < 0 or index >= _filtered.size():
		return
	var pid: String = str(_filtered[index][0])
	close_palette()
	var host := get_tree().current_scene
	if host != null and host.has_method("_on_nav_pressed"):
		host.call("_on_nav_pressed", pid)
