extends CanvasLayer
## Scanlines + vignette (``globals.css`` body::before / ::after).

@onready var scanlines: ColorRect = %Scanlines
@onready var vignette: ColorRect = %Vignette


func _ready() -> void:
	layer = 50
	scanlines.mouse_filter = Control.MOUSE_FILTER_IGNORE
	vignette.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_resize_overlays()
	get_viewport().size_changed.connect(_resize_overlays)


func _resize_overlays() -> void:
	var vp := get_viewport().get_visible_rect().size
	scanlines.size = vp
	vignette.size = vp
