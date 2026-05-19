extends Control
## Full-screen loading overlay shown during world creation or save loading.
## Animated globe visualization + progress stage text.

signal creation_finished

const CREATE_STAGES: Array = [
	"Generating terrain fields",
	"Rolling subsurface minerals",
	"Computing landmasses",
	"Seeding laborer population",
	"Founding settler NPCs",
	"Establishing exchange markets",
	"Building infrastructure",
	"Opening for business",
]

const CREATE_DETAILS: Array = [
	"Continental noise, coastlines, biome placement…",
	"Iron belts, coal seams, copper highlands…",
	"Continents, islands, islets classification…",
	"Towns, residences, job market…",
	"Archetypes, shippers, energy, bank…",
	"Cold-start listings, staple liquidity…",
	"Roads, docks, shipping routes…",
	"Final viability checks, recipe books…",
]

const LOAD_STAGES: Array = [
	"Reading save file",
	"Restoring world state",
	"Rebuilding ledger",
	"Reconstructing markets",
	"Resuming simulation",
]

const LOAD_DETAILS: Array = [
	"Loading snapshot from disk…",
	"Plots, terrain, subsurface data…",
	"Accounts, balances, transactions…",
	"Order books, contracts, prices…",
	"Agents, population, tick state…",
]

enum Mode { CREATE, LOAD }
var _mode: int = Mode.CREATE
var _subtitle: String = ""
var _t: float = 0.0
var _stage_idx: int = 0
var _progress: float = 0.0
var _target_progress: float = 0.0
var _done: bool = false
var _done_delay: float = 0.0
var _stage_timer: float = 0.0
var _waiting_for_engine: bool = false
var _engine_wait_elapsed: float = 0.0
var _engine_wait_timeout: float = 120.0
var _genesis_slow: bool = false

@onready var _title_label: Label = $VBox/TitleLabel
@onready var _scenario_label: Label = $VBox/ScenarioLabel
@onready var _stage_label: Label = $VBox/StageLabel
@onready var _detail_label: Label = $VBox/DetailLabel
@onready var _bar_bg: ColorRect = $VBox/BarBG
@onready var _bar_fill: ColorRect = $VBox/BarBG/BarFill
@onready var _globe: Control = $VBox/GlobeArea


func _stages() -> Array:
	return CREATE_STAGES if _mode == Mode.CREATE else LOAD_STAGES

func _details() -> Array:
	return CREATE_DETAILS if _mode == Mode.CREATE else LOAD_DETAILS


func open(scenario: String) -> void:
	_mode = Mode.CREATE
	_subtitle = scenario
	_genesis_slow = scenario == "genesis"
	_reset_state()


func begin_waiting_for_engine(timeout_seconds: float = 120.0) -> void:
	_waiting_for_engine = true
	_engine_wait_elapsed = 0.0
	_engine_wait_timeout = maxf(30.0, timeout_seconds)
	var stages := _stages()
	if not stages.is_empty():
		_stage_idx = stages.size() - 1
	_target_progress = 0.4
	_update_labels()


func end_waiting_for_engine() -> void:
	_waiting_for_engine = false
	_update_labels()


signal engine_wait_timed_out


func open_load(save_name: String) -> void:
	_mode = Mode.LOAD
	_subtitle = save_name
	_reset_state()


func _reset_state() -> void:
	_stage_idx = 0
	_progress = 0.0
	_target_progress = 0.0
	_done = false
	_done_delay = 0.0
	_waiting_for_engine = false
	_engine_wait_elapsed = 0.0
	_t = 0.0
	_stage_timer = 0.0
	visible = true
	_update_labels()


func mark_done() -> void:
	_done = true
	_stage_idx = _stages().size() - 1
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

	var stages := _stages()
	if not _done:
		if _waiting_for_engine:
			_engine_wait_elapsed += dt
			if _engine_wait_elapsed >= _engine_wait_timeout:
				engine_wait_timed_out.emit()
				return
			# Hold the bar below "done" until the engine acknowledges dev_reset.
			var wait_cap := 0.88 if _genesis_slow else 0.92
			var wait_frac := clampf(_engine_wait_elapsed / _engine_wait_timeout, 0.0, 1.0)
			_target_progress = lerpf(0.35, wait_cap, wait_frac)
			if _genesis_slow and int(_engine_wait_elapsed) % 4 == 0:
				_update_labels()
		else:
			var interval := 0.32 if _mode == Mode.CREATE else 0.2
			if _genesis_slow:
				interval = 1.1
			_stage_timer += dt
			var max_stage := stages.size() - 2 if _mode == Mode.CREATE else stages.size() - 1
			if _stage_timer > interval and _stage_idx < max_stage:
				_stage_timer = 0.0
				_stage_idx += 1
				_target_progress = float(_stage_idx + 1) / float(stages.size()) * 0.35
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
	var stages := _stages()
	var details := _details()
	if _title_label:
		_title_label.text = "CREATING WORLD" if _mode == Mode.CREATE else "LOADING WORLD"
	if _scenario_label:
		if _mode == Mode.CREATE:
			_scenario_label.text = "Scenario: %s" % _subtitle
		else:
			_scenario_label.text = _subtitle
	if _stage_label:
		var txt: String = stages[_stage_idx] if _stage_idx < stages.size() else "Done"
		if _done:
			txt = "World ready" if _mode == Mode.CREATE else "Save loaded"
		_stage_label.text = txt
	if _detail_label:
		var dtxt: String = details[_stage_idx] if _stage_idx < details.size() else ""
		if _done:
			dtxt = "Entering simulation…"
		elif _waiting_for_engine:
			if _genesis_slow:
				var secs := int(_engine_wait_elapsed)
				dtxt = "Building the 320x240 map and seeding settlers — typically 30-90s (%ds)…" % secs
			else:
				dtxt = "Waiting for the simulation engine…"
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
