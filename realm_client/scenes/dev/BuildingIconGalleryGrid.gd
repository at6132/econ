extends Control
class_name BuildingIconGalleryGrid
## Grid of building silhouettes — child of BuildingIconGallery.

const COLS := 5
const CELL_W := 112.0
const CELL_H := 88.0
const LABEL_H := 22.0
const PAD := 16.0


func _ready() -> void:
	_update_min_size()


func _update_min_size() -> void:
	var ids := BuildingMapIcons.GALLERY_BLUEPRINT_IDS
	var rows := int(ceil(float(ids.size()) / float(COLS)))
	custom_minimum_size = Vector2(
		PAD * 2.0 + COLS * CELL_W,
		PAD * 2.0 + rows * (CELL_H + LABEL_H),
	)


func _draw() -> void:
	var font: Font = ThemeDB.fallback_font
	var ids := BuildingMapIcons.GALLERY_BLUEPRINT_IDS
	for i in ids.size():
		var bid: String = ids[i]
		var col := i % COLS
		var row := int(floor(float(i) / float(COLS)))
		var ox := PAD + float(col) * CELL_W
		var oy := PAD + float(row) * (CELL_H + LABEL_H)
		var frame := Rect2(ox + 4.0, oy, CELL_W - 8.0, CELL_H)
		var icon_r := Rect2(ox + 8.0, oy + 4.0, CELL_W - 16.0, CELL_H - 12.0)
		draw_rect(frame, Color(0.12, 0.10, 0.14), true)
		draw_rect(frame, Color(0.28, 0.24, 0.32), false, 1.0)
		if bid == "road_segment":
			BuildingMapIcons.draw_road_cell(self, icon_r, 1.5)
		else:
			BuildingMapIcons.draw_building(self, icon_r, bid, 100, 1.5)
		if font != null:
			var fs := 11
			var sz := font.get_string_size(bid, HORIZONTAL_ALIGNMENT_LEFT, -1, fs)
			var tx := ox + (CELL_W - sz.x) * 0.5
			draw_string(
				font,
				Vector2(tx, oy + CELL_H + 14.0),
				bid,
				HORIZONTAL_ALIGNMENT_LEFT,
				-1,
				fs,
				Color(0.85, 0.82, 0.78),
			)
