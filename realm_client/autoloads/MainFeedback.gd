extends Node
## Global action feedback toasts (success / error).

var _toast: Label
var _host: Node


func _ready() -> void:
	_toast = Label.new()
	_toast.visible = false
	_toast.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_toast.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_toast.add_theme_font_size_override("font_size", 16)
	_toast.z_index = 100
	call_deferred("_bind_host")


func _bind_host() -> void:
	var tree := get_tree()
	if tree == null:
		return
	_host = tree.root.get_node_or_null("Main")
	if _host == null:
		_host = tree.current_scene
	if _host == null:
		return
	if _toast.get_parent() != _host:
		if _toast.get_parent():
			_toast.get_parent().remove_child(_toast)
		_host.add_child(_toast)
	_toast.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	_toast.offset_top = -80
	_toast.offset_bottom = -40


func toast(message: String, is_error: bool = false) -> void:
	if _toast == null:
		return
	_bind_host()
	_toast.text = message
	_toast.modulate = Color(1.0, 0.4, 0.4, 1.0) if is_error else RealmColors.OK
	_toast.modulate.a = 1.0
	_toast.visible = true
	var tw := create_tween()
	tw.tween_interval(2.0)
	tw.tween_property(_toast, "modulate:a", 0.0, 0.5)
	tw.finished.connect(func() -> void:
		_toast.visible = false
		_toast.modulate.a = 1.0
	)
