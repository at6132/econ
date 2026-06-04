extends CanvasLayer
## Full building designer — footprint zones, BOM, custom materials/recipes, publish.

signal closed
signal blueprint_created(blueprint_id: String, bp_data: Dictionary)

const FootprintDesigner := preload("res://scenes/panels/build/BlueprintFootprintDesigner.gd")

@onready var _title: Label = %TitleLabel
@onready var _close_btn: Button = %CloseBtn
@onready var _tab_design: Button = %TabDesignBtn
@onready var _tab_bom: Button = %TabBomBtn
@onready var _tab_process: Button = %TabProcessBtn
@onready var _tab_publish: Button = %TabPublishBtn
@onready var _pages: VBoxContainer = %Pages
@onready var _design_page: VBoxContainer = %DesignPage
@onready var _bom_page: VBoxContainer = %BomPage
@onready var _process_page: VBoxContainer = %ProcessPage
@onready var _publish_page: VBoxContainer = %PublishPage
@onready var _center_panel: PanelContainer = %CenterPanel

var _footprint_designer: Control
var _name_in: LineEdit
var _desc_in: LineEdit
var _w_spin: SpinBox
var _h_spin: SpinBox
var _cat_opt: OptionButton
var _paint_row: HBoxContainer
var _constr_list: VBoxContainer
var _maint_list: VBoxContainer
var _recipe_list: ItemList
var _attached_recipes: Array = []
var _extra_inputs: VBoxContainer
var _extra_outputs: VBoxContainer
var _new_product_name: LineEdit
var _new_product_mass: SpinBox
var _machines_box: VBoxContainer
var _process_name_in: LineEdit
var _process_labor_spin: SpinBox
var _status: Label
var _tab_group: ButtonGroup


func _ready() -> void:
	layer = 46
	set_process_unhandled_input(true)
	_tab_group = ButtonGroup.new()
	_tab_group.allow_unpress = false
	for b in [_tab_design, _tab_bom, _tab_process, _tab_publish]:
		b.button_group = _tab_group
		b.pressed.connect(_on_tab.bind(b))
	_close_btn.pressed.connect(close)
	get_node("DimBackground").gui_input.connect(_on_dim_click)
	_apply_theme()
	_build_design_page()
	_build_bom_page()
	_build_process_page()
	_build_publish_page()
	_show_tab("design")
	_refresh_material_options()


func _apply_theme() -> void:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.07, 0.07, 0.09, 0.98)
	sb.set_border_width_all(1)
	sb.border_color = Color(0.85, 0.72, 0.2, 0.45)
	sb.set_corner_radius_all(8)
	_center_panel.add_theme_stylebox_override("panel", sb)
	PanelUI.style_btn(_close_btn)
	_title.add_theme_font_size_override("font_size", 20)


func _build_design_page() -> void:
	_name_in = LineEdit.new()
	_name_in.placeholder_text = "Building name"
	_design_page.add_child(_name_in)
	_desc_in = LineEdit.new()
	_desc_in.placeholder_text = "What this facility does"
	_design_page.add_child(_desc_in)
	var dim := HBoxContainer.new()
	_w_spin = SpinBox.new()
	_w_spin.min_value = 1
	_w_spin.max_value = 10
	_w_spin.value = 3
	_h_spin = SpinBox.new()
	_h_spin.min_value = 1
	_h_spin.max_value = 10
	_h_spin.value = 2
	dim.add_child(_label("Width cells"))
	dim.add_child(_w_spin)
	dim.add_child(_label("Height cells"))
	dim.add_child(_h_spin)
	_design_page.add_child(dim)
	_cat_opt = OptionButton.new()
	for c in ["extraction", "processing", "infrastructure", "commerce", "research", "custom"]:
		_cat_opt.add_item(c)
		_cat_opt.set_item_metadata(_cat_opt.item_count - 1, c)
	_design_page.add_child(_cat_opt)
	_paint_row = HBoxContainer.new()
	for mode in ["structure", "input", "output", "power", "clear"]:
		var btn := Button.new()
		btn.text = mode.capitalize()
		PanelUI.style_btn(btn)
		btn.pressed.connect(func() -> void: _footprint_designer.set_paint_mode(mode))
		_paint_row.add_child(btn)
	_design_page.add_child(_paint_row)
	_footprint_designer = FootprintDesigner.new()
	_footprint_designer.layout_changed.connect(_on_layout_changed)
	_design_page.add_child(_footprint_designer)
	_w_spin.value_changed.connect(_sync_footprint)
	_h_spin.value_changed.connect(_sync_footprint)
	_sync_footprint()


func _build_bom_page() -> void:
	_bom_page.add_child(_label("Construction materials (per build)"))
	var add_con := HBoxContainer.new()
	var c_mat := OptionButton.new()
	c_mat.name = "ConstrMat"
	add_con.add_child(c_mat)
	var c_qty := SpinBox.new()
	c_qty.min_value = 1
	c_qty.value = 5
	add_con.add_child(c_qty)
	var c_btn := Button.new()
	c_btn.text = "Add"
	PanelUI.style_btn(c_btn)
	c_btn.pressed.connect(_on_add_construction.bind(c_mat, c_qty))
	add_con.add_child(c_btn)
	_bom_page.add_child(add_con)
	var sc1 := PanelUI.make_scroll_list()
	sc1.custom_minimum_size = Vector2(0, 80)
	_constr_list = PanelUI.list_inner(sc1)
	_bom_page.add_child(sc1)
	_bom_page.add_child(_label("Maintenance materials (per cycle)"))
	var add_m := HBoxContainer.new()
	var m_mat := OptionButton.new()
	m_mat.name = "MaintMat"
	add_m.add_child(m_mat)
	var m_qty := SpinBox.new()
	m_qty.min_value = 1
	m_qty.value = 2
	add_m.add_child(m_qty)
	var m_btn := Button.new()
	m_btn.text = "Add"
	PanelUI.style_btn(m_btn)
	m_btn.pressed.connect(_on_add_maintenance.bind(m_mat, m_qty))
	add_m.add_child(m_btn)
	_bom_page.add_child(add_m)
	var sc2 := PanelUI.make_scroll_list()
	sc2.custom_minimum_size = Vector2(0, 60)
	_maint_list = PanelUI.list_inner(sc2)
	_bom_page.add_child(sc2)


func _build_process_page() -> void:
	var hint := _label(
		"Design a NEW product this world has never shipped. Install discovered "
		+ "machines (pumps, gears, controls). Inputs + power must balance outputs."
	)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_process_page.add_child(hint)
	var novel := _label("New product (required for custom factories)")
	_process_page.add_child(novel)
	var prod_row := HBoxContainer.new()
	_new_product_name = LineEdit.new()
	_new_product_name.placeholder_text = "e.g. Avi Protein Bar"
	_new_product_name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	prod_row.add_child(_new_product_name)
	_new_product_mass = SpinBox.new()
	_new_product_mass.prefix = "kg/unit "
	_new_product_mass.min_value = 0.1
	_new_product_mass.max_value = 5000
	_new_product_mass.value = 0.4
	prod_row.add_child(_new_product_mass)
	_process_page.add_child(prod_row)
	_process_name_in = LineEdit.new()
	_process_name_in.placeholder_text = "Process / line name"
	_process_page.add_child(_process_name_in)
	_process_page.add_child(_label("Machines to install in this factory"))
	_machines_box = VBoxContainer.new()
	_process_page.add_child(_machines_box)
	_refresh_machines_ui()
	_process_page.add_child(_label("Inputs (add multiple)"))
	var in_row := HBoxContainer.new()
	var in_mat := OptionButton.new()
	in_mat.name = "InMat"
	var in_qty := SpinBox.new()
	in_qty.value = 1
	in_qty.min_value = 1
	var add_in := Button.new()
	add_in.text = "+ Input"
	PanelUI.style_btn(add_in)
	_extra_inputs = VBoxContainer.new()
	add_in.pressed.connect(_on_add_recipe_io.bind(in_mat, in_qty, _extra_inputs))
	in_row.add_child(in_mat)
	in_row.add_child(in_qty)
	in_row.add_child(add_in)
	_process_page.add_child(in_row)
	_process_page.add_child(_extra_inputs)
	_process_page.add_child(_label("Outputs (add multiple)"))
	var out_row := HBoxContainer.new()
	var out_mat := OptionButton.new()
	out_mat.name = "OutMat"
	var out_qty := SpinBox.new()
	out_qty.value = 1
	out_qty.min_value = 1
	var add_out := Button.new()
	add_out.text = "+ Output"
	PanelUI.style_btn(add_out)
	_extra_outputs = VBoxContainer.new()
	add_out.pressed.connect(_on_add_recipe_io.bind(out_mat, out_qty, _extra_outputs))
	out_row.add_child(out_mat)
	out_row.add_child(out_qty)
	out_row.add_child(add_out)
	_process_page.add_child(out_row)
	_process_page.add_child(_extra_outputs)
	var dur_lab := SpinBox.new()
	dur_lab.prefix = "Duration ticks "
	dur_lab.min_value = 360
	dur_lab.value = 1440
	_process_page.add_child(dur_lab)
	_process_labor_spin = SpinBox.new()
	_process_labor_spin.prefix = "Labor ¢ "
	_process_labor_spin.max_value = 1_000_000
	_process_labor_spin.value = 500
	_process_page.add_child(_process_labor_spin)
	_recipe_list = ItemList.new()
	_recipe_list.custom_minimum_size = Vector2(0, 100)
	_process_page.add_child(_recipe_list)
	_refresh_recipe_picker()


func _build_publish_page() -> void:
	_publish_page.add_child(_label("Licensing & registration"))
	var pub := CheckButton.new()
	pub.text = "List publicly (others pay license)"
	pub.button_pressed = true
	pub.name = "PublicToggle"
	_publish_page.add_child(pub)
	var lic := SpinBox.new()
	lic.prefix = "License fee ¢ "
	lic.max_value = 1_000_000
	_publish_page.add_child(lic)
	var labor := SpinBox.new()
	labor.prefix = "Construction labor ¢ "
	labor.max_value = 10_000_000
	labor.value = 5000
	_publish_page.add_child(labor)
	var fee_lbl := Label.new()
	fee_lbl.name = "FeeLabel"
	_publish_page.add_child(fee_lbl)
	_update_fee_label(fee_lbl)
	_w_spin.value_changed.connect(func(_v): _update_fee_label(fee_lbl))
	_h_spin.value_changed.connect(func(_v): _update_fee_label(fee_lbl))
	var pub_btn := Button.new()
	pub_btn.text = "Register blueprint"
	PanelUI.style_btn(pub_btn, true)
	pub_btn.pressed.connect(_on_publish.bind(pub, lic, labor))
	_publish_page.add_child(pub_btn)
	_status = Label.new()
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_publish_page.add_child(_status)


func _label(t: String) -> Label:
	var l := Label.new()
	l.text = t
	return l


func _on_tab(btn: Button) -> void:
	for b in [_tab_design, _tab_bom, _tab_process, _tab_publish]:
		PanelUI.style_btn(b, b == btn)
	if btn == _tab_design:
		_show_tab("design")
	elif btn == _tab_bom:
		_show_tab("bom")
	elif btn == _tab_process:
		_show_tab("process")
	else:
		_show_tab("publish")


func _show_tab(which: String) -> void:
	_design_page.visible = which == "design"
	_bom_page.visible = which == "bom"
	_process_page.visible = which == "process"
	_publish_page.visible = which == "publish"


func _sync_footprint() -> void:
	if _footprint_designer:
		_footprint_designer.set_footprint(int(_w_spin.value), int(_h_spin.value), _footprint_designer.get_layout())


func _on_layout_changed(_layout: Dictionary) -> void:
	pass


func _layout_json() -> String:
	return JSON.stringify({"zones": _footprint_designer.get_layout(), "v": 1})


func _all_material_ids() -> PackedStringArray:
	var ids: Dictionary = {}
	for r in WorldState.recipes:
		if r is Dictionary:
			for k in (r as Dictionary).get("inputs", {}).keys():
				ids[str(k)] = true
			for k in (r as Dictionary).get("outputs", {}).keys():
				ids[str(k)] = true
	for row in WorldState.custom_materials:
		if row is Dictionary:
			ids[str((row as Dictionary).get("material_id", ""))] = true
	var out := PackedStringArray()
	for k in ids.keys():
		if not str(k).is_empty():
			out.append(str(k))
	out.sort()
	return out


func _refresh_material_options() -> void:
	var mats := _all_material_ids()
	for node in [_bom_page, _process_page]:
		for c in node.get_children():
			_fill_mat_opts(c, mats)


func _fill_mat_opts(node: Node, mats: PackedStringArray) -> void:
	if node is OptionButton and node.name in ["ConstrMat", "MaintMat", "InMat", "OutMat"]:
		var sel := node as OptionButton
		var prev := ""
		if sel.item_count > 0 and sel.selected >= 0:
			prev = str(sel.get_item_metadata(sel.selected))
		sel.clear()
		for m in mats:
			sel.add_item(WorldState.material_display_name(m))
			sel.set_item_metadata(sel.item_count - 1, m)
		if prev != "":
			for i in sel.item_count:
				if str(sel.get_item_metadata(i)) == prev:
					sel.select(i)
					break
	for ch in node.get_children():
		_fill_mat_opts(ch, mats)


func _construction_dict() -> Dictionary:
	var d: Dictionary = {}
	for c in _constr_list.get_children():
		if c.has_meta("mat"):
			d[str(c.get_meta("mat"))] = int(c.get_meta("qty"))
	return d


func _maintenance_dict() -> Dictionary:
	var d: Dictionary = {}
	for c in _maint_list.get_children():
		if c.has_meta("mat"):
			d[str(c.get_meta("mat"))] = int(c.get_meta("qty"))
	return d


func _on_add_construction(mat_sel: OptionButton, qty: SpinBox) -> void:
	if mat_sel.selected < 0:
		return
	_add_bom_row(_constr_list, str(mat_sel.get_item_metadata(mat_sel.selected)), int(qty.value))


func _on_add_maintenance(mat_sel: OptionButton, qty: SpinBox) -> void:
	if mat_sel.selected < 0:
		return
	_add_bom_row(_maint_list, str(mat_sel.get_item_metadata(mat_sel.selected)), int(qty.value))


func _add_bom_row(list: VBoxContainer, mat: String, qty: int) -> void:
	var row := HBoxContainer.new()
	row.set_meta("mat", mat)
	row.set_meta("qty", qty)
	var lbl := Label.new()
	lbl.text = "%s × %d" % [WorldState.material_display_name(mat), qty]
	lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(lbl)
	var rm := Button.new()
	rm.text = "×"
	rm.pressed.connect(func() -> void: row.queue_free())
	row.add_child(rm)
	list.add_child(row)


func _on_register_material(name_in: LineEdit) -> void:
	var n := name_in.text.strip_edges()
	if n.is_empty():
		return
	API.register_custom_material(
		n,
		"processed",
		"",
		func(r: Dictionary) -> void:
			if bool(r.get("ok", false)):
				MainFeedback.toast("Material: %s" % r.get("material_id", ""))
				API.get_world_player(func(p): WorldState.apply_player(p), WorldState.party_id)
				_refresh_material_options()
			else:
				MainFeedback.toast(str(r.get("reason", "Failed")), true),
	)


func _on_add_recipe_io(mat_sel: OptionButton, qty: SpinBox, list: VBoxContainer) -> void:
	if mat_sel.selected < 0:
		return
	_add_bom_row(list, str(mat_sel.get_item_metadata(mat_sel.selected)), int(qty.value))


func _io_dict_from_list(list: VBoxContainer) -> Dictionary:
	var d: Dictionary = {}
	for c in list.get_children():
		if c.has_meta("mat"):
			var mid := str(c.get_meta("mat"))
			d[mid] = int(d.get(mid, 0)) + int(c.get_meta("qty"))
	return d


func _on_create_recipe(
	name_in: LineEdit,
	in_mat: OptionButton,
	in_qty: SpinBox,
	out_mat: OptionButton,
	out_qty: SpinBox,
	dur: SpinBox,
) -> void:
	var n := name_in.text.strip_edges()
	if n.is_empty():
		return
	var inputs := _io_dict_from_list(_extra_inputs)
	var outputs := _io_dict_from_list(_extra_outputs)
	if in_mat.selected >= 0:
		var im := str(in_mat.get_item_metadata(in_mat.selected))
		inputs[im] = int(inputs.get(im, 0)) + int(in_qty.value)
	if out_mat.selected >= 0:
		var om := str(out_mat.get_item_metadata(out_mat.selected))
		outputs[om] = int(outputs.get(om, 0)) + int(out_qty.value)
	API.create_custom_recipe(
		n,
		inputs,
		outputs,
		int(dur.value),
		0,
		"",
		func(r: Dictionary) -> void:
			if bool(r.get("ok", false)):
				var rid := str(r.get("recipe_id", ""))
				_attached_recipes.append(rid)
				_refresh_recipe_picker()
				MainFeedback.toast("Process %s" % rid)
				API.get_world_player(func(p): WorldState.apply_player(p), WorldState.party_id)
			else:
				MainFeedback.toast(str(r.get("reason", "Failed")), true),
	)


func _refresh_recipe_picker() -> void:
	_recipe_list.clear()
	for rid in _attached_recipes:
		var row := WorldState.recipe_by_id(rid)
		var rid_s: String = str(rid)
		var display_name: String = str(row.get("display_name", rid_s)) if not row.is_empty() else rid_s
		_recipe_list.add_item(display_name)
	for row in WorldState.custom_recipes:
		if not (row is Dictionary):
			continue
		var rid := str((row as Dictionary).get("recipe_id", ""))
		if rid in _attached_recipes:
			continue
		_recipe_list.add_item("%s (saved)" % (row as Dictionary).get("display_name", rid))


func _enabled_recipe_ids() -> Array:
	var ids: Array = _attached_recipes.duplicate()
	for i in _recipe_list.get_selected_items():
		if i < _attached_recipes.size():
			var rid: String = str(_attached_recipes[i])
			if not rid in ids:
				ids.append(rid)
	return ids


func _installed_machines_dict() -> Dictionary:
	var d: Dictionary = {}
	if _machines_box == null:
		return d
	for row in _machines_box.get_children():
		if row is HBoxContainer and row.has_meta("machine_id"):
			var q := int(row.get_meta("qty"))
			if q > 0:
				d[str(row.get_meta("machine_id"))] = q
	return d


func _refresh_machines_ui() -> void:
	if _machines_box == null:
		return
	for c in _machines_box.get_children():
		c.queue_free()
	API.get_factory_machines(func(data: Dictionary) -> void:
		for row in data.get("machines", []) as Array:
			if row is not Dictionary:
				continue
			var mid := str((row as Dictionary).get("machine_id", ""))
			if mid.is_empty():
				continue
			var h := HBoxContainer.new()
			h.set_meta("machine_id", mid)
			var lbl := Label.new()
			var disc: bool = bool((row as Dictionary).get("discovered", false))
			var on_hand: int = int((row as Dictionary).get("on_hand", 0))
			lbl.text = "%s%s (have %d)" % [
				str((row as Dictionary).get("label", mid)),
				"" if disc else " [locked]",
				on_hand,
			]
			lbl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			if not disc:
				lbl.add_theme_color_override("font_color", Color(0.5, 0.5, 0.55))
			h.add_child(lbl)
			var sp := SpinBox.new()
			sp.min_value = 0
			sp.max_value = maxi(1, on_hand)
			sp.value = 0
			sp.value_changed.connect(func(v: float) -> void: h.set_meta("qty", int(v)))
			h.set_meta("qty", 0)
			h.add_child(sp)
			_machines_box.add_child(h)
	)


func _build_factory_outputs() -> Dictionary:
	var outputs := _io_dict_from_list(_extra_outputs)
	var novel := _new_product_name.text.strip_edges() if _new_product_name else ""
	if not novel.is_empty():
		outputs[novel] = maxi(1, int(outputs.get(novel, 1)))
	return outputs


func _on_publish(pub: CheckButton, lic: SpinBox, labor: SpinBox) -> void:
	if _name_in.text.strip_edges().is_empty():
		_status.text = "Name required."
		return
	var novel := _new_product_name.text.strip_edges() if _new_product_name else ""
	if novel.is_empty():
		_status.text = "Name your new product on the Process tab."
		return
	var outputs := _build_factory_outputs()
	if outputs.is_empty():
		_status.text = "Add at least one output (your new product)."
		return
	var inputs := _io_dict_from_list(_extra_inputs)
	if not inputs.has("electricity"):
		inputs["electricity"] = 1
	var desc := _desc_in.text.strip_edges()
	if not desc.is_empty():
		desc += "\n"
	desc += _layout_json()
	var proc_name := (
		_process_name_in.text.strip_edges()
		if _process_name_in
		else "Line: %s" % novel
	)
	API.design_custom_factory(
		{
			"party": WorldState.party_id,
			"name": _name_in.text.strip_edges(),
			"description": desc,
			"footprint_w": int(_w_spin.value),
			"footprint_h": int(_h_spin.value),
			"category": str(_cat_opt.get_item_metadata(_cat_opt.selected)),
			"construction_labor_cents": int(labor.value),
			"construction_materials": _construction_dict(),
			"construction_ticks": 1440,
			"maintenance_interval_ticks": 14400,
			"maintenance_materials": _maintenance_dict(),
			"maintenance_grace_ticks": 1440,
			"is_public": pub.button_pressed,
			"license_fee_cents": int(lic.value),
			"terrain_requirements": [],
			"requires_coastal": false,
			"requires_power": _footprint_designer.get_layout().values().has("power"),
			"installed_machines": _installed_machines_dict(),
			"process_name": proc_name,
			"process_inputs": inputs,
			"process_outputs": outputs,
			"process_duration_ticks": 1440,
			"process_labor_cents": int(_process_labor_spin.value) if _process_labor_spin else 500,
			"new_products": [
				{
					"display_name": novel,
					"output_slot": novel,
					"mass_per_unit_kg": float(_new_product_mass.value) if _new_product_mass else 0.4,
					"category": "processed",
				}
			],
		},
		func(data: Dictionary) -> void:
			if bool(data.get("ok", false)):
				var bid := str(data.get("blueprint_id", ""))
				var bp_data := {
					"blueprint_id": bid,
					"name": _name_in.text,
					"footprint_w": int(_w_spin.value),
					"footprint_h": int(_h_spin.value),
					"recipe_id": str(data.get("recipe_id", "")),
				}
				blueprint_created.emit(bid, bp_data)
				MainFeedback.toast("Custom factory registered — place it on a plot")
				API.get_world_player(func(p): WorldState.apply_player(p), WorldState.party_id)
				close()
			else:
				_status.text = str(data.get("reason", data.get("detail", "Failed"))),
	)


func _update_fee_label(lbl: Label) -> void:
	var cells := int(_w_spin.value) * int(_h_spin.value)
	lbl.text = "Registration fee: %s (%d cells)" % [
		WorldState.format_money(20_000 + cells * 5_000),
		cells,
	]


func close() -> void:
	closed.emit()
	queue_free()


func _on_dim_click(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed:
		close()


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		close()
		get_viewport().set_input_as_handled()
