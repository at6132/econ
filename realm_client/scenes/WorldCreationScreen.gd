extends Control
## Full-screen loading overlay shown while bootstrap_genesis runs on the server.
## Animated globe visualization + progress stage text.

signal creation_finished

const STAGES: Array = [
	"Generating terrain fields",
	"Rolling subsurface minerals",
	"Computing landmasses",
	"Seeding laborer population",
	"Founding settler NPCs",
	"Establishing exchange markets",
	"Building infrastructure",
	"Opening for business",
]

const STAGE_DETAILS: Array = [
	"Continental noise, coastlines, biome placement…",
	"Iron belts, coal seams, copper highlands…",
	"Continents, islands, islets classification…",
	"Towns, residences, job market…",
	"Archetypes, shippers, energy, bank…",
	"Cold-start listings, staple liquidity…",
	"Roads, docks, shipping routes…",
	"Final viability checks, recipe books…",
]

var _scenario: String = "genesis"
var _t: float = 0.0
var _stage_idx: int = 0
var _progress: float = 0.0
var _target_progress: float = 0.0
var _done: bool = false
var _done_delay: float = 0.0
var _stage_timer: float = 0.0

@onready var _title_label: Label = $VBox/TitleLabel
@onready var _scenario_label: Label = $VBox/ScenarioLabel
@onready var _stage_label: Label = $VBox/StageLabel
@onready var _detail_label: Label = $VBox/DetailLabel
@onready var _bar_bg: ColorRect = $VBox/BarBG
@onready var _bar_fill: ColorRect = $VBox/BarBG/BarFill
@onready var _globe: Control = $VBox/GlobeArea


func open(scenario: String) -> void:
	_scenario = scenario
	_stage_idx = 0
	_progress = 0.0
	_target_progress = 0.0
	_done = false
	_done_delay = 0.0
	_t = 0.0
	_stage_timer = 0.0
	visible = true
	_update_labels()


func mark_done() -> void:
	_done = true
	_stage_idx = STAGES.size() - 1
	_target_progress = 1.0
	_update_labels()


func _ready() -> void:
	visible = false
	mouse_filter = Control.MOUSE_FILTER_STOP
	_style_labels()


func _process(dt: float) -> void:
	if not visible:
		return
	_t += dt

	if not _done:
		_stage_timer += dt
		if _stage_timer > 0.32 and _stage_idx < STAGES.size() - 1:
			_stage_timer = 0.0
			_stage_idx += 1
			_target_progress = float(_stage_idx + 1) / float(STAGES.size()) * 0.92
			_update_labels()
	else:
		_done_delay += dt
		if _done_delay > 0.4:
			creation_finished.emit()
			visible = false
			return

	_progress = lerpf(_progress, _target_progress, minf(1.0, dt * 6.0))
	_bar_fill.anchor_right = clampf(_progress, 0.0, 1.0)

	_globe.queue_redraw()


func _update_labels() -> void:
	if _title_label:
		_title_label.text = "CREATING WORLD"
	if _scenario_label:
		_scenario_label.text = "Scenario: %s" % _scenario
	if _stage_label:
		var txt: String = STAGES[_stage_idx] if _stage_idx < STAGES.size() else "Done"
		if _done:
			txt = "World ready"
		_stage_label.text = txt
	if _detail_label:
		var dtxt: String = STAGE_DETAILS[_stage_idx] if _stage_idx < STAGE_DETAILS.size() else ""
		if _done:
			dtxt = "Entering simulation…"
		_detail_label.text = dtxt


func _style_labels() -> void:
	if _title_label:
		_title_label.add_theme_color_override("font_color", RealmColors.ACCENT)
		if RealmFonts.font_display:
			_title_label.add_theme_font_override("font", RealmFonts.font_display)
			_title_label.add_theme_font_size_override("font_size", 12)
	if _scenario_label:
		_scenario_label.add_theme_color_override("font_color", RealmColors.MUTED)
		if RealmFonts.font_body:
			_scenario_label.add_theme_font_override("font", RealmFonts.font_body)
			_scenario_label.add_theme_font_size_override("font_size", 18)
	if _stage_label:
		_stage_label.add_theme_color_override("font_color", RealmColors.TEXT)
		if RealmFonts.font_body:
			_stage_label.add_theme_font_override("font", RealmFonts.font_body)
			_stage_label.add_theme_font_size_override("font_size", 22)
	if _detail_label:
		_detail_label.add_theme_color_override("font_color", RealmColors.DIM)
		if RealmFonts.font_body:
			_detail_label.add_theme_font_override("font", RealmFonts.font_body)
			_detail_label.add_theme_font_size_override("font_size", 16)
