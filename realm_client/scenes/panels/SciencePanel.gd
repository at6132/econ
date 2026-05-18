extends "res://scenes/panels/TabbedSlidePanel.gd"


func _init() -> void:
	width_pct = 0.68
	panel_title = "🔬 Science Lab"


func _build_tabs() -> void:
	_add_api_tab("Elements", func(cb): API.get_science_elements(cb))
	_add_api_tab("Reactions", func(cb): API.get_science_reactions(cb))
	_add_experiment_tab()


func _add_api_tab(tab_title: String, fetcher: Callable) -> void:
	var tab := preload("res://scenes/panels/GenericListTab.gd").new() as VBoxContainer
	tab.title = tab_title
	tab.fetch_callable = fetcher
	add_tab(tab, tab_title)


func _add_experiment_tab() -> void:
	var tab := VBoxContainer.new()
	tab.size_flags_vertical = Control.SIZE_EXPAND_FILL
	var a := OptionButton.new()
	var b := OptionButton.new()
	for i in range(20):
		a.add_item("Element %d" % i)
		b.add_item("Element %d" % i)
	tab.add_child(Label.new())
	(tab.get_child(0) as Label).text = "Run experiment (requires laboratory)"
	var btn := Button.new()
	btn.text = "Run experiment"
	btn.pressed.connect(func() -> void:
		API.post_science_experiment(
			{"party": WorldState.party_id, "element_a": "fe", "element_b": "c", "conditions": ["heat_1200c"]},
			func(d: Dictionary) -> void:
				if bool(d.get("ok", false)):
					MainFeedback.toast("Experiment started")
				else:
					MainFeedback.toast(str(d.get("reason", "Failed")), true)
		)
	)
	tab.add_child(a)
	tab.add_child(b)
	tab.add_child(btn)
	add_tab(tab, "Experiment")
