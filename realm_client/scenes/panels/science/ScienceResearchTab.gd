extends VBoxContainer

## Technology tree — start research when a lab exists anywhere on your deeds.


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var row := HBoxContainer.new()
	var node_opt := OptionButton.new()
	node_opt.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(node_opt)
	var start_btn := Button.new()
	start_btn.text = "Start research"
	start_btn.pressed.connect(func() -> void:
		if node_opt.selected < 0:
			return
		var nid: String = str(node_opt.get_item_metadata(node_opt.selected))
		API.start_research(nid, func(data: Dictionary) -> void:
			if bool(data.get("ok", false)):
				MainFeedback.toast("Research started: %s" % nid)
				_load_catalog(node_opt)
			else:
				MainFeedback.toast(str(data.get("reason", "Failed")), true)
		)
	)
	row.add_child(start_btn)
	add_child(row)
	var status_lbl := Label.new()
	status_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(status_lbl)
	var sc := PanelUI.make_scroll_list()
	var list := PanelUI.list_inner(sc)
	add_child(sc)
	_load_catalog(node_opt)
	API.get_research_status(func(st: Dictionary) -> void:
		var active: Variant = st.get("active")
		if active is Dictionary and not active.is_empty():
			status_lbl.text = "Active: %s — %.1f / %s days" % [str(active.get("node_id", "")), float(active.get("progress_days", 0)), str(active.get("research_cost_days", "?"))]
		else:
			status_lbl.text = "No active research project"
	)


func _load_catalog(node_opt: OptionButton) -> void:
	API.get_research_catalog(func(cat: Dictionary) -> void:
		node_opt.clear()
		var nodes: Dictionary = cat.get("nodes", {})
		for nid in nodes.keys():
			var spec: Dictionary = nodes[nid] if nodes[nid] is Dictionary else {}
			if not bool(spec.get("can_start", false)):
				continue
			var label: String = str(nid).replace("_", " ")
			node_opt.add_item(label)
			node_opt.set_item_metadata(node_opt.item_count - 1, nid)
		if node_opt.item_count == 0:
			node_opt.add_item("(none available)")
		if not bool(cat.get("has_research_lab", false)):
			MainFeedback.toast("Build a research lab to start projects")
	)
