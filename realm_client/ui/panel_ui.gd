class_name PanelUI
extends RefCounted
## Shared widgets for slide-in panels.


static func style_panel(panel: Panel) -> void:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.08, 0.08, 0.1)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.35)
	panel.add_theme_stylebox_override("panel", sb)


static func style_btn(btn: Button, accent: bool = false) -> void:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.16, 0.14, 0.1) if accent else Color(0.12, 0.12, 0.14)
	sb.set_border_width_all(1)
	sb.border_color = RealmColors.ACCENT if accent else Color(0.85, 0.72, 0.2, 0.55)
	btn.add_theme_stylebox_override("normal", sb)
	btn.add_theme_color_override("font_color", RealmColors.TEXT if accent else Color(0.9, 0.88, 0.82))


static func make_chip_row(
	parent: Control,
	labels: PackedStringArray,
	active: String,
	on_pick: Callable,
) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	for label in labels:
		var btn := Button.new()
		btn.text = label
		btn.toggle_mode = true
		btn.button_pressed = label == active
		style_btn(btn, label == active)
		btn.pressed.connect(func() -> void: on_pick.call(label))
		row.add_child(btn)
	parent.add_child(row)
	return row


static func make_scroll_list() -> ScrollContainer:
	var sc := ScrollContainer.new()
	sc.size_flags_vertical = Control.SIZE_EXPAND_FILL
	sc.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	var inner := VBoxContainer.new()
	inner.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	inner.name = "ListInner"
	sc.add_child(inner)
	return sc


static func list_inner(sc: ScrollContainer) -> VBoxContainer:
	return sc.get_node("ListInner") as VBoxContainer


static func clear_children(node: Node) -> void:
	for c in node.get_children():
		c.queue_free()
