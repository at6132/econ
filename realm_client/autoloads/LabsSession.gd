extends Node
## Transient state between Labs hub → launch → in-game lab run.

var selected_preset_id: String = ""
var selected_preset_summary: Dictionary = {}
var last_start_response: Dictionary = {}


func clear() -> void:
	selected_preset_id = ""
	selected_preset_summary = {}
	last_start_response = {}
