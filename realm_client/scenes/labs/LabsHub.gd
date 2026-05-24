extends Control
## Realm Labs — analytical preset catalog (paginated experiment registry).

const GAME_HOME := "res://scenes/GameHome.tscn"
const LABS_LAUNCH := "res://scenes/labs/LabsLaunch.tscn"
const PAGE_SIZE := 48

var _category: String = "All"
var _featured_only: bool = false
var _search_q: String = ""
var _offset: int = 0
var _total: int = 0
var _loading: bool = false

var _search_edit: LineEdit
var _table_inner: VBoxContainer
var _status_label: Label
var _page_label: Label
var _metric_total: Label
var _metric_featured: Label
var _chip_row: HBoxContainer


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	_build_chrome()
	if RealmFonts:
		RealmFonts.apply_to_control(self)
	_fetch_page()


func _build_chrome() -> void:
	var bg := ColorRect.new()
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	bg.color = RealmColors.BG
	bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(bg)

	var margin := MarginContainer.new()
	margin.set_anchors_preset(Control.PRESET_FULL_RECT)
	margin.add_theme_constant_override("margin_left", 36)
	margin.add_theme_constant_override("margin_right", 36)
	margin.add_theme_constant_override("margin_top", 32)
	margin.add_theme_constant_override("margin_bottom", 28)
	add_child(margin)

	var root := VBoxContainer.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_theme_constant_override("separation", 14)
	margin.add_child(root)

	var top := HBoxContainer.new()
	top.add_theme_constant_override("separation", 20)
	root.add_child(top)

	var brand := VBoxContainer.new()
	brand.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	brand.add_child(LabsUi.kicker_label("Realm · economic research"))
	brand.add_child(LabsUi.title_label("LABS", 22))
	brand.add_child(LabsUi.body_label(
		"Contained simulators for strategy, markets, and population dynamics. "
		+ "Deterministic seeds · conservation enforced · isolated from campaign saves.",
		RealmColors.MUTED,
	))
	top.add_child(brand)

	var back := Button.new()
	back.text = "← Main menu"
	LabsUi.style_menu_button(back, false)
	back.pressed.connect(_go_home)
	top.add_child(back)

	var metrics := HBoxContainer.new()
	metrics.add_theme_constant_override("separation", 24)
	var m1 := LabsUi.metric_cell("Presets", "—")
	var m2 := LabsUi.metric_cell("Featured", "—")
	_metric_total = m1.get_child(1) as Label
	_metric_featured = m2.get_child(1) as Label
	metrics.add_child(m1)
	metrics.add_child(m2)
	root.add_child(metrics)

	var toolbar := HBoxContainer.new()
	toolbar.add_theme_constant_override("separation", 10)
	_search_edit = LineEdit.new()
	_search_edit.placeholder_text = "Filter by id, title, tag…"
	_search_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_search_edit.custom_minimum_size.y = 40
	_search_edit.add_theme_stylebox_override("normal", RealmColors.style_btn_normal())
	_search_edit.add_theme_color_override("font_color", RealmColors.TEXT)
	if RealmFonts.font_body:
		_search_edit.add_theme_font_override("font", RealmFonts.font_body)
	_search_edit.text_submitted.connect(_on_search_submit)
	toolbar.add_child(_search_edit)
	var search_btn := Button.new()
	search_btn.text = "Apply filter"
	PanelUI.style_btn(search_btn, true)
	search_btn.pressed.connect(_on_search_submit.bind(_search_edit.text))
	toolbar.add_child(search_btn)
	var feat := CheckButton.new()
	feat.text = "Featured only"
	feat.add_theme_color_override("font_color", RealmColors.DIM)
	feat.toggled.connect(_on_featured_toggled)
	toolbar.add_child(feat)
	root.add_child(toolbar)

	_chip_row = HBoxContainer.new()
	_chip_row.add_theme_constant_override("separation", 6)
	for cat in LabsUi.CATEGORIES:
		var chip := Button.new()
		chip.text = cat
		LabsUi.style_chip(chip, cat == _category)
		var c := cat
		chip.pressed.connect(_on_category_pick.bind(c))
		_chip_row.add_child(chip)
	root.add_child(_chip_row)

	var panel := PanelContainer.new()
	panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
	panel.add_theme_stylebox_override("panel", LabsUi.style_data_panel())
	root.add_child(panel)

	var pv := VBoxContainer.new()
	pv.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	pv.add_theme_constant_override("separation", 0)
	panel.add_child(pv)

	var header_row := HBoxContainer.new()
	header_row.add_theme_constant_override("separation", 8)
	header_row.custom_minimum_size.y = 28
	header_row.add_theme_stylebox_override("panel", LabsUi.style_grid_header())
	for h in ["ID", "Experiment", "Class", "Grid", "Base"]:
		var w := 120.0 if h == "ID" else (0.0 if h == "Experiment" else 88.0)
		var cell := LabsUi.header_cell(h, w)
		cell.size_flags_horizontal = Control.SIZE_EXPAND_FILL if h == "Experiment" else Control.SIZE_SHRINK_BEGIN
		header_row.add_child(cell)
	pv.add_child(header_row)

	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	pv.add_child(scroll)

	_table_inner = VBoxContainer.new()
	_table_inner.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(_table_inner)

	var footer := HBoxContainer.new()
	footer.add_theme_constant_override("separation", 12)
	_status_label = LabsUi.body_label("", RealmColors.MUTED)
	_status_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	footer.add_child(_status_label)
	var prev := Button.new()
	prev.text = "◀ Prev"
	LabsUi.style_menu_button(prev, false)
	prev.pressed.connect(_page_prev)
	footer.add_child(prev)
	_page_label = LabsUi.body_label("Page —", RealmColors.DIM)
	footer.add_child(_page_label)
	var next := Button.new()
	next.text = "Next ▶"
	LabsUi.style_menu_button(next, false)
	next.pressed.connect(_page_next)
	footer.add_child(next)
	root.add_child(footer)


func _on_category_pick(cat: String) -> void:
	_category = cat
	for c in _chip_row.get_children():
		if c is Button:
			LabsUi.style_chip(c as Button, (c as Button).text == _category)
	_offset = 0
	_fetch_page()


func _on_featured_toggled(on: bool) -> void:
	_featured_only = on
	_offset = 0
	_fetch_page()


func _on_search_submit(_t: String = "") -> void:
	_search_q = _search_edit.text.strip_edges()
	_offset = 0
	_fetch_page()


func _page_prev() -> void:
	_offset = maxi(0, _offset - PAGE_SIZE)
	_fetch_page()


func _page_next() -> void:
	if _offset + PAGE_SIZE < _total:
		_offset += PAGE_SIZE
		_fetch_page()


func _fetch_page() -> void:
	if _loading:
		return
	_loading = true
	_status_label.text = "Scanning catalog…"
	PanelUI.clear_children(_table_inner)

	var q := "/labs/presets?offset=%d&limit=%d" % [_offset, PAGE_SIZE]
	if _category != "All":
		q += "&category=%s" % _category.uri_encode()
	if _featured_only:
		q += "&featured_only=true"
	if not _search_q.is_empty():
		q += "&q=%s" % _search_q.uri_encode()

	API.get_request(
		q,
		func(data: Dictionary) -> void:
			_loading = false
			if not bool(data.get("ok", true)):
				_status_label.text = "Catalog error: %s" % str(data)
				return
			_total = int(data.get("total", 0))
			var stats: Dictionary = data.get("stats", {})
			_metric_total.text = str(stats.get("total", _total))
			_metric_featured.text = str(stats.get("featured", "—"))
			var presets: Array = data.get("presets", [])
			_render_rows(presets)
			var page := int(_offset / PAGE_SIZE) + 1
			var pages := maxi(1, int(ceil(float(_total) / float(PAGE_SIZE))))
			_page_label.text = "Page %d / %d · %d rows" % [page, pages, presets.size()]
			_status_label.text = "Select a row to configure parameters and initiate a run."
	)


func _render_rows(presets: Array) -> void:
	var alt := false
	for raw in presets:
		if not (raw is Dictionary):
			continue
		var p: Dictionary = raw
		_table_inner.add_child(_make_row(p, alt))
		alt = not alt


func _make_row(p: Dictionary, alt: bool) -> Button:
	var pid := str(p.get("id", ""))
	var btn := Button.new()
	btn.flat = false
	btn.alignment = HORIZONTAL_ALIGNMENT_LEFT
	btn.add_theme_stylebox_override("normal", LabsUi.style_row(alt))
	btn.add_theme_stylebox_override("hover", LabsUi.style_row(not alt))
	btn.add_theme_stylebox_override("pressed", LabsUi.style_row(alt))
	btn.custom_minimum_size.y = 36

	var row := HBoxContainer.new()
	row.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	row.offset_left = 8
	row.offset_right = -8
	row.add_theme_constant_override("separation", 8)
	row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	btn.add_child(row)

	var feat_mark := "★ " if bool(p.get("featured", false)) else ""
	row.add_child(_sized_cell(feat_mark + pid, 200, false))
	row.add_child(_sized_cell(str(p.get("title", "")), 0, true))
	row.add_child(_sized_cell(str(p.get("category", "")), 100, false))
	row.add_child(_sized_cell(str(p.get("grid_label", "—")), 72, false))
	row.add_child(_sized_cell(str(p.get("base", "")).capitalize(), 72, false))

	btn.pressed.connect(_open_launch.bind(pid, p))
	return btn


func _sized_cell(text: String, width: float, expand: bool) -> Label:
	var l := LabsUi.data_cell(text, expand)
	if width > 0.0:
		l.custom_minimum_size.x = width
	if expand:
		l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return l


func _open_launch(preset_id: String, summary: Dictionary) -> void:
	LabsSession.selected_preset_id = preset_id
	LabsSession.selected_preset_summary = summary
	get_tree().change_scene_to_file(LABS_LAUNCH)


func _go_home() -> void:
	LabsSession.clear()
	get_tree().change_scene_to_file(GAME_HOME)
