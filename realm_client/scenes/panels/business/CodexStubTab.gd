extends VBoxContainer
## Phase 4+ programmable services — placeholder until Lua sandbox ships.


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var title := Label.new()
	title.text = "Programmable services (Codex)"
	title.add_theme_color_override("font_color", RealmColors.ACCENT)
	add_child(title)
	var body := Label.new()
	body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	body.text = (
		"Publish Lua-style services other players subscribe to (analytics, routing, "
		+ "custom market makers). Engine hooks exist on the contract layer; the in-game "
		+ "editor and sandbox land in Phase 4. Use Service contracts in Pacts for fixed "
		+ "fee subscriptions until then."
	)
	add_child(body)
