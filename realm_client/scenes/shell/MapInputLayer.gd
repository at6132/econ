extends Control
## Transparent hit area over the map stage; forwards pointer input to ``WorldMap``.

var world_map: Node2D = null


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	mouse_default_cursor_shape = Control.CURSOR_MOVE


func _gui_input(event: InputEvent) -> void:
	if world_map == null or not is_instance_valid(world_map):
		return
	if world_map.has_method("handle_gui_input"):
		world_map.call("handle_gui_input", event)
	accept_event()
