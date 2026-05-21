extends Node
## Debug logging — console + ``user://realm_debug.log``.

const LOG_FILE := "user://realm_debug.log"

var enabled: bool = true


func _ready() -> void:
	var path := log_file_absolute()
	var f := FileAccess.open(LOG_FILE, FileAccess.WRITE)
	if f != null:
		f.store_line("=== Realm session %s ===" % Time.get_datetime_string_from_system())
		f.store_line("log_file=%s" % path)
		f.close()
	log_line("RealmDebug", "ready %s" % path)
	_log_gpu_info()


func _log_gpu_info() -> void:
	var rs := RenderingServer
	var adapter := str(rs.get_video_adapter_name())
	var vendor := str(rs.get_video_adapter_vendor())
	var driver := str(OS.get_video_adapter_driver_info())
	var rmethod := str(ProjectSettings.get_setting("rendering/renderer/rendering_method", "?"))
	var item_buf := int(ProjectSettings.get_setting("rendering/gl_compatibility/item_buffer_size", 0))
	log_line("RealmDebug", "gpu vendor=%s adapter=%s" % [vendor, adapter])
	log_line("RealmDebug", "driver=%s" % driver)
	log_line("RealmDebug", "renderer=%s gl_item_buffer=%d" % [rmethod, item_buf])


func log_file_absolute() -> String:
	return ProjectSettings.globalize_path(LOG_FILE)


func log_line(tag: String, msg: String) -> void:
	if not enabled:
		return
	var line := "[%s] [%s] %s" % [Time.get_datetime_string_from_system(), tag, msg]
	print(line)
	_append_line(line)


func log_err(tag: String, msg: String) -> void:
	log_line(tag, "ERROR: %s" % msg)
	push_error("%s: %s" % [tag, msg])


func _append_line(line: String) -> void:
	var mode := FileAccess.READ_WRITE if FileAccess.file_exists(LOG_FILE) else FileAccess.WRITE
	var f := FileAccess.open(LOG_FILE, mode)
	if f == null:
		return
	if mode == FileAccess.READ_WRITE:
		f.seek_end()
	f.store_line(line)
	f.close()
