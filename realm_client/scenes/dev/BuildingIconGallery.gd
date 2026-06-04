extends Control
## Preview every SITE-map building silhouette. Run this scene alone (F6) — not the main game.

const EXPORT_DIR := "res://assets/icons/buildings/gallery/"

@onready var _grid: Control = %IconGrid
@onready var _status: Label = %StatusLabel
@onready var _export_btn: Button = %ExportBtn


func _ready() -> void:
	_export_btn.pressed.connect(_on_export_pressed)


func _on_export_pressed() -> void:
	_export_btn.disabled = true
	_status.text = "Exporting PNGs…"
	await get_tree().process_frame
	var n := await _export_all_pngs()
	_status.text = "Exported %d PNGs → realm_client/assets/icons/buildings/gallery/" % n
	_export_btn.disabled = false


func _export_all_pngs() -> int:
	var abs_dir := ProjectSettings.globalize_path(EXPORT_DIR)
	DirAccess.make_dir_recursive_absolute(abs_dir)
	var count := 0
	for bid in BuildingMapIcons.GALLERY_BLUEPRINT_IDS:
		var img := await _render_icon_image(bid, 100, Vector2i(224, 176))
		if img == null:
			continue
		var path := abs_dir.path_join("%s.png" % bid)
		if img.save_png(path) == OK:
			count += 1
	return count


func _render_icon_image(blueprint_id: String, eff_pct: int, size: Vector2i) -> Image:
	var vp := SubViewport.new()
	vp.size = size
	vp.transparent_bg = true
	vp.render_target_update_mode = SubViewport.UPDATE_ONCE
	var holder := _ExportTile.new()
	holder.blueprint_id = blueprint_id
	holder.efficiency_pct = eff_pct
	holder.set_anchors_preset(Control.PRESET_FULL_RECT)
	holder.set_offsets_preset(Control.PRESET_FULL_RECT)
	vp.add_child(holder)
	add_child(vp)
	await RenderingServer.frame_post_draw
	var tex := vp.get_texture()
	remove_child(vp)
	vp.queue_free()
	if tex == null:
		return null
	return tex.get_image()


class _ExportTile extends Control:
	var blueprint_id: String = ""
	var efficiency_pct: int = 100

	func _draw() -> void:
		draw_rect(Rect2(Vector2.ZERO, size), Color(0.12, 0.10, 0.14), true)
		var inner := Rect2(Vector2(16, 16), size - Vector2(32, 32))
		if blueprint_id == "road_segment":
			BuildingMapIcons.draw_road_cell(self, inner, 2.0)
		else:
			BuildingMapIcons.draw_building(self, inner, blueprint_id, efficiency_pct, 2.0)
