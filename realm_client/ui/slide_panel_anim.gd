class_name SlidePanelAnim
extends RefCounted
## Slide-in/out helpers for right-edge overlay panels.


static func layout_panel(panel: Panel, width_pct: float, hud_top: float) -> void:
	var vp := panel.get_viewport().get_visible_rect().size
	var w: float = vp.x * width_pct
	panel.size = Vector2(w, vp.y - hud_top)
	panel.position = Vector2(vp.x, hud_top)


static func panel_width(panel: Panel, width_pct: float) -> float:
	return panel.get_viewport().get_visible_rect().size.x * width_pct


static func slide_in(host: CanvasLayer, panel: Panel, width_pct: float, polished: bool = true) -> void:
	var vp := panel.get_viewport().get_visible_rect().size
	var w: float = vp.x * width_pct
	if polished:
		panel.position.x = vp.x + 20.0
		panel.modulate.a = 0.0
		var tw := host.create_tween()
		tw.set_parallel(true)
		tw.set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
		tw.tween_property(panel, "position:x", vp.x - w, 0.25)
		tw.tween_property(panel, "modulate:a", 1.0, 0.20)
	else:
		var tw := host.create_tween().set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
		tw.tween_property(panel, "position:x", vp.x - w, 0.28)


static func slide_out(host: CanvasLayer, panel: Panel, width_pct: float, on_done: Callable, polished: bool = true) -> void:
	var vp := panel.get_viewport().get_visible_rect().size
	var w: float = vp.x * width_pct
	if polished:
		var tw := host.create_tween()
		tw.set_parallel(true)
		tw.set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_IN)
		tw.tween_property(panel, "position:x", vp.x + 20.0, 0.20)
		tw.tween_property(panel, "modulate:a", 0.0, 0.18)
		tw.finished.connect(on_done, CONNECT_ONE_SHOT)
	else:
		var tw := host.create_tween().set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_IN)
		tw.tween_property(panel, "position:x", vp.x, 0.22)
		tw.finished.connect(on_done, CONNECT_ONE_SHOT)
