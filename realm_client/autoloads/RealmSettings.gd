extends Node
## Client preferences persisted under ``user://`` (no effect on engine determinism).

const FILE_PATH := "user://realm_settings.cfg"
const SECTION := "prefs"

const OVERLAY_MODES: Array = [
	["none", "Map (default)"],
	["ownership", "Ownership"],
	["power", "Power"],
	["mineral", "Minerals"],
	["routes", "Shipping routes"],
	["roads", "Roads"],
	["population", "Population"],
	["advantage", "Advantage"],
]

const SPEED_OPTIONS: Array = [1.0, 2.0, 4.0]

var start_paused: bool = false
var default_speed: float = 1.0
var default_overlay: String = "none"
var default_save_slot: String = "current"


func _ready() -> void:
	load_from_disk()


func load_from_disk() -> void:
	var f := ConfigFile.new()
	var err := f.load(FILE_PATH)
	if err != OK and err != ERR_FILE_NOT_FOUND:
		push_warning("RealmSettings: could not load (%s)" % err)
		return
	if err != OK:
		return
	start_paused = bool(f.get_value(SECTION, "start_paused", false))
	default_speed = _snap_speed(float(f.get_value(SECTION, "default_speed", 1.0)))
	default_overlay = str(f.get_value(SECTION, "default_overlay", "none"))
	default_save_slot = str(f.get_value(SECTION, "default_save_slot", "current")).strip_edges()
	if default_save_slot.is_empty():
		default_save_slot = "current"
	if overlay_index_from_id(default_overlay) < 0:
		default_overlay = "none"


func save_to_disk() -> void:
	var f := ConfigFile.new()
	f.set_value(SECTION, "start_paused", start_paused)
	f.set_value(SECTION, "default_speed", default_speed)
	f.set_value(SECTION, "default_overlay", default_overlay)
	f.set_value(SECTION, "default_save_slot", default_save_slot)
	var err := f.save(FILE_PATH)
	if err != OK:
		push_warning("RealmSettings: could not save (%s)" % err)


func _snap_speed(s: float) -> float:
	for m in SPEED_OPTIONS:
		if is_equal_approx(float(m), s):
			return float(m)
	return 1.0


func overlay_index_from_id(id: String) -> int:
	for i in range(OVERLAY_MODES.size()):
		if str((OVERLAY_MODES[i] as Array)[0]) == id:
			return i
	return -1


func overlay_id_from_index(idx: int) -> String:
	if idx < 0 or idx >= OVERLAY_MODES.size():
		return "none"
	return str((OVERLAY_MODES[idx] as Array)[0])


func speed_index_from_value(speed: float) -> int:
	for i in range(SPEED_OPTIONS.size()):
		if is_equal_approx(float(SPEED_OPTIONS[i]), speed):
			return i
	return 0


func persist() -> void:
	save_to_disk()
