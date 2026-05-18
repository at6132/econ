extends CanvasLayer

signal blueprint_created(blueprint_id: String, bp_data: Dictionary)

@onready var name_input: LineEdit = %NameInput
@onready var desc_input: LineEdit = %DescInput
@onready var width_spin: SpinBox = %WidthSpin
@onready var height_spin: SpinBox = %HeightSpin
@onready var category_opt: OptionButton = %CategoryOpt
@onready var labor_spin: SpinBox = %LaborSpin
@onready var license_spin: SpinBox = %LicenseSpin
@onready var public_toggle: CheckButton = %PublicToggle
@onready var footprint_preview: Control = %FootprintPreview
@onready var fee_label: Label = %RegFeeLabel
@onready var create_btn: Button = %CreateBtn
@onready var cancel_btn: Button = %CancelBtn

const CATEGORIES := [
	"extraction",
	"processing",
	"infrastructure",
	"commerce",
	"population",
	"research",
	"custom",
]


func _ready() -> void:
	layer = 50
	for cat in CATEGORIES:
		category_opt.add_item(cat.capitalize())
		category_opt.set_item_metadata(category_opt.item_count - 1, cat)
	width_spin.min_value = 1
	width_spin.max_value = 10
	height_spin.min_value = 1
	height_spin.max_value = 10
	width_spin.value = 2
	height_spin.value = 2
	labor_spin.min_value = 0
	labor_spin.max_value = 10_000_000
	labor_spin.step = 1000
	license_spin.min_value = 0
	license_spin.max_value = 1_000_000
	license_spin.step = 500
	width_spin.value_changed.connect(func(_v: float) -> void: _update_preview())
	height_spin.value_changed.connect(func(_v: float) -> void: _update_preview())
	width_spin.value_changed.connect(func(_v: float) -> void: _update_fee())
	height_spin.value_changed.connect(func(_v: float) -> void: _update_fee())
	create_btn.pressed.connect(_on_create)
	cancel_btn.pressed.connect(queue_free)
	_update_preview()
	_update_fee()


func _update_preview() -> void:
	if footprint_preview.has_method("set_footprint"):
		footprint_preview.call(
			"set_footprint", int(width_spin.value), int(height_spin.value)
		)
	else:
		footprint_preview.queue_redraw()


func _update_fee() -> void:
	var w := int(width_spin.value)
	var h := int(height_spin.value)
	var cells := w * h
	var reg_fee := 20_000 + cells * 5_000
	fee_label.text = "Registration fee: %s  (%d cells = %dm x %dm)" % [
		WorldState.format_money(reg_fee),
		cells,
		w * 10,
		h * 10,
	]


func _on_create() -> void:
	if name_input.text.strip_edges().is_empty():
		return
	var w := int(width_spin.value)
	var h := int(height_spin.value)
	var cat_idx := category_opt.selected
	var cat: String = str(category_opt.get_item_metadata(cat_idx))
	create_btn.disabled = true
	API.post_request(
		"/blueprints/create",
		{
			"party": WorldState.party_id,
			"name": name_input.text.strip_edges(),
			"description": desc_input.text.strip_edges(),
			"footprint_w": w,
			"footprint_h": h,
			"category": cat,
			"construction_labor_cents": int(labor_spin.value),
			"construction_materials": {},
			"construction_ticks": 1440,
			"enabled_recipe_ids": [],
			"maintenance_interval_ticks": 14400,
			"maintenance_materials": {},
			"maintenance_grace_ticks": 1440,
			"is_public": public_toggle.button_pressed,
			"license_fee_cents": int(license_spin.value),
			"terrain_requirements": [],
			"requires_coastal": false,
			"requires_power": false,
		},
		func(data: Dictionary) -> void:
			create_btn.disabled = false
			if bool(data.get("ok", false)):
				var bp_data := {
					"blueprint_id": str(data.get("blueprint_id", "")),
					"name": name_input.text,
					"footprint_w": w,
					"footprint_h": h,
					"category": cat,
					"is_seeded": false,
					"creator_party": WorldState.party_id,
					"is_public": public_toggle.button_pressed,
					"license_fee_cents": int(license_spin.value),
					"construction_labor_cents": int(labor_spin.value),
					"description": desc_input.text,
				}
				blueprint_created.emit(str(data.get("blueprint_id", "")), bp_data)
				queue_free(),
	)
