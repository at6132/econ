extends Control
## Procedural blueprint icon (category shape + accent) for build sidebar.

var _blueprint: Dictionary = {}


func setup(bp: Dictionary) -> void:
	_blueprint = bp.duplicate(true)
	custom_minimum_size = Vector2(36, 36)
	queue_redraw()


func _draw() -> void:
	var tex := BlueprintIcons.texture_for(_blueprint)
	if tex != null:
		var pad := Vector2(2, 2)
		var r := Rect2(pad, size - pad * 2.0)
		draw_texture_rect(tex, r, false)
		return
	var bid := str(_blueprint.get("blueprint_id", ""))
	var cat := str(_blueprint.get("category", "custom"))
	var accent: Color = BlueprintIcons.color_for(_blueprint)
	var bg := accent.darkened(0.55)
	if size.x < 8.0 or size.y < 8.0:
		return
	var r := Rect2(Vector2(2, 2), size - Vector2(4, 4))
	draw_rect(r, bg)
	draw_rect(r, accent.lightened(0.15), false, 1.5)
	var cx := r.position.x + r.size.x * 0.5
	var cy := r.position.y + r.size.y * 0.5
	var inner := r.grow(-6)
	match cat:
		"extraction":
			draw_rect(inner, accent.lightened(0.1))
			draw_line(
				Vector2(cx - 6, cy + 5),
				Vector2(cx, cy - 7),
				Color(0.95, 0.9, 0.85),
				2.0,
				true,
			)
			draw_line(
				Vector2(cx, cy - 7),
				Vector2(cx + 6, cy + 5),
				Color(0.95, 0.9, 0.85),
				2.0,
				true,
			)
		"infrastructure":
			if bid == "road_segment":
				draw_rect(inner, Color(0.22, 0.24, 0.28))
				draw_line(
					inner.position + Vector2(4, inner.size.y * 0.5),
					inner.end - Vector2(4, inner.size.y * 0.5),
					Color(0.75, 0.78, 0.82),
					2.5,
					true,
				)
			else:
				draw_rect(inner, accent.lightened(0.05))
				draw_line(
					Vector2(cx, inner.position.y + 2),
					Vector2(cx, inner.end.y - 2),
					Color(0.95, 0.85, 0.35),
					2.0,
					true,
				)
		"commerce":
			draw_rect(inner, accent.lightened(0.12))
			draw_rect(
				Rect2(inner.position + Vector2(4, 6), Vector2(inner.size.x - 8, inner.size.y - 10)),
				Color(0.12, 0.1, 0.08, 0.5),
			)
		"population":
			draw_circle(Vector2(cx, cy - 2), 5.0, accent.lightened(0.2))
			draw_rect(
				Rect2(cx - 7, cy + 4, 14, 8),
				accent.lightened(0.1),
			)
		_:
			draw_rect(inner, accent.lightened(0.08))
			draw_circle(Vector2(cx, cy), 4.0, Color(0.95, 0.92, 0.88, 0.9))
