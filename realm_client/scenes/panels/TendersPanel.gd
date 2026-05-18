extends CanvasLayer

const WIDTH_PCT := 0.50
const HUD_TOP := 96.0

@onready var panel: Panel = %Panel
@onready var close_btn: Button = %CloseBtn
@onready var list_box: VBoxContainer = %ListBox


func _ready() -> void:
	PanelUI.style_panel(panel)
	SlidePanelAnim.layout_panel(panel, WIDTH_PCT, HUD_TOP)
	PanelUI.style_btn(close_btn)
	close_btn.pressed.connect(close)
	SlidePanelAnim.slide_in(self, panel, WIDTH_PCT, true)
	_refresh()
	API.get_tenders(_on_tenders)


func _refresh() -> void:
	PanelUI.clear_children(list_box)


func _on_tenders(data: Dictionary) -> void:
	_refresh()
	var rows: Variant = data.get("tenders", data.get("open", []))
	if not (rows is Array):
		return
	for row in rows as Array:
		if row is Dictionary:
			list_box.add_child(_tender_row(row as Dictionary))


func _tender_row(d: Dictionary) -> VBoxContainer:
	var v := VBoxContainer.new()
	var title := Label.new()
	title.text = str(d.get("title", d.get("tender_id", "Tender")))
	title.add_theme_color_override("font_color", RealmColors.ACCENT)
	v.add_child(title)
	var need := Label.new()
	need.text = str(d.get("need_summary", d.get("material", "")))
	need.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	v.add_child(need)
	var spin := SpinBox.new()
	spin.min_value = 1
	spin.value = int(d.get("lowest_bid_cents", 100))
	var tid: String = str(d.get("tender_id", d.get("id", "")))
	var bid_btn := Button.new()
	bid_btn.text = "Submit bid"
	bid_btn.pressed.connect(func() -> void:
		API.post_tender_bid(tid, int(spin.value), func(r: Dictionary) -> void:
			if bool(r.get("ok", false)):
				MainFeedback.toast("Bid submitted")
			else:
				MainFeedback.toast(str(r.get("reason", "Failed")), true)
		)
	)
	v.add_child(spin)
	v.add_child(bid_btn)
	return v


func close() -> void:
	SlidePanelAnim.slide_out(self, panel, WIDTH_PCT, queue_free, true)
