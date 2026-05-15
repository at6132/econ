extends Node
## Cached display state from the last successful API responses (read-only mirror; no game rules).

# ── Player state ─────────────────────────────────────────────────────────────
var player_cash_cents: int = 0
var player_net_worth_cents: int = 0
var party_id: String = "player"
var display_name: String = "Player"

# ── Time scale (from ``GET /world``; default matches engine ``TICKS_PER_GAME_DAY``) ──
var ticks_per_game_day: int = 1440

# ── Time (derived from tick + ticks_per_game_day) ───────────────────────────
var current_tick: int = 0
var game_day: int = 1
var game_season: String = "Spring"
var game_year: int = 1

# ── HUD counters ─────────────────────────────────────────────────────────────
var active_production_count: int = 0
var maintenance_warning_count: int = 0
var active_contracts_count: int = 0
var unread_feed_count: int = 0
var unread_npc_messages: int = 0
var cpi_current: float = 100.0

# ── World data ───────────────────────────────────────────────────────────────
var plots: Dictionary = {} # plot_id str → plot dict
var plot_buildings: Array = []
var active_production: Array = [] # engine ``active_production`` list (plot-level runs)
var recipes: Array = [] # ``recipe_public_list()`` rows
var building_catalog: Array = []
var player_owned_reports: Array = []
var party_display_names: Dictionary = {}
var scenario_id: String = ""
## RNG seed from ``GET /world`` (for HUD / map parity with engine).
var world_seed: int = 42
## Flattened ``market_asks`` / ``market_bids`` / ``market_history`` from ``GET /world``.
var market_asks_rows: Array = []
var market_bids_rows: Array = []
var market_history_rows: Array = []
var market_history_free_window_ticks: int = 48
## ``inventory[party_id]`` material → qty.
var player_inventory: Dictionary = {}
var towns: Array = [] # synthetic markers (e.g. nascent settlements) for the map
var businesses: Array = []
var active_contracts: Array = []
var world_feed_log: Array = []
var npc_messages: Array = []

## Matches ``realm.actions.plot_actions.SURVEY_COST_CENTS`` (engine source of truth).
const SURVEY_COST_CENTS: int = 50_000

# ── Market (optional cache; not populated in Phase 1 unless you call an API) ─
var market_asks: Dictionary = {}
var market_bids: Dictionary = {}
var price_history: Dictionary = {}

signal summary_updated
signal world_updated
signal feed_updated
signal market_updated


## Updates HUD time fields from an authoritative engine tick (e.g. ``POST /tick`` body).
## Emits ``summary_updated`` so CommandShell refreshes even when GET polling fails.
func apply_engine_tick_hint(tick: int) -> void:
	current_tick = tick
	_update_time_from_tick()
	summary_updated.emit()


func apply_summary(data: Dictionary) -> void:
	if data.is_empty():
		return
	player_cash_cents = int(data.get("cash", 0))
	player_net_worth_cents = int(data.get("net_worth_estimate", 0))
	current_tick = int(data.get("tick", current_tick))
	var ap: Variant = data.get("active_production", [])
	active_production_count = int(ap.size()) if ap is Array else 0
	var mw: Variant = data.get("maintenance_warnings", [])
	maintenance_warning_count = int(mw.size()) if mw is Array else 0
	active_contracts_count = int(data.get("active_contracts", 0))
	unread_feed_count = int(data.get("unread_feed_entries", 0))
	unread_npc_messages = int(data.get("unread_npc_messages", 0))
	_update_time_from_tick()
	summary_updated.emit()


func apply_world(data: Dictionary) -> void:
	if data.is_empty():
		return
	ticks_per_game_day = int(data.get("ticks_per_game_day", ticks_per_game_day))
	current_tick = int(data.get("tick", current_tick))
	world_seed = int(data.get("seed", world_seed))
	var raw_plots: Variant = data.get("plots", [])
	plots.clear()
	if raw_plots is Array:
		for p in raw_plots:
			if p is Dictionary:
				var pid := str(p.get("id", ""))
				if pid != "":
					plots[pid] = p
	elif raw_plots is Dictionary:
		for k in raw_plots.keys():
			plots[str(k)] = raw_plots[k]

	_rebuild_town_markers_from_world(data)

	businesses = data.get("business_entities", data.get("businesses", []))
	if not (businesses is Array):
		businesses = []
	world_feed_log = data.get("world_feed_log", [])
	if not (world_feed_log is Array):
		world_feed_log = []
	npc_messages = data.get("npc_messages", [])
	if not (npc_messages is Array):
		npc_messages = []
	plot_buildings = data.get("plot_buildings", [])
	if not (plot_buildings is Array):
		plot_buildings = []
	var ap_raw: Variant = data.get("active_production", [])
	active_production = ap_raw if ap_raw is Array else []
	var rec_raw: Variant = data.get("recipes", [])
	recipes = rec_raw if rec_raw is Array else []
	var bc_raw: Variant = data.get("building_catalog", [])
	building_catalog = bc_raw if bc_raw is Array else []
	var por_raw: Variant = data.get("player_owned_reports", [])
	player_owned_reports = por_raw if por_raw is Array else []
	var pdn: Variant = data.get("party_display_names", {})
	party_display_names = pdn if pdn is Dictionary else {}
	scenario_id = str(data.get("scenario_id", scenario_id))
	var contracts_raw: Variant = data.get("contracts", [])
	active_contracts = contracts_raw if contracts_raw is Array else []

	var ma: Variant = data.get("market_asks", [])
	market_asks_rows = ma if ma is Array else []
	var mb: Variant = data.get("market_bids", [])
	market_bids_rows = mb if mb is Array else []
	var mh: Variant = data.get("market_history", [])
	market_history_rows = mh if mh is Array else []
	market_history_free_window_ticks = int(data.get("market_history_free_window_ticks", 48))

	var inv_root: Variant = data.get("inventory", {})
	if inv_root is Dictionary:
		var ply: Variant = (inv_root as Dictionary).get(party_id, {})
		player_inventory = ply if ply is Dictionary else {}
	else:
		player_inventory.clear()

	world_updated.emit()
	feed_updated.emit()


func apply_market(data: Dictionary) -> void:
	if data.is_empty():
		return
	market_asks = data.get("asks_by_material", data.get("market_asks", {}))
	market_bids = data.get("bids_by_material", data.get("market_bids", {}))
	market_updated.emit()


func apply_cpi(data: Dictionary) -> void:
	if data.is_empty():
		return
	cpi_current = float(data.get("current", 100.0))
	summary_updated.emit()


func _rebuild_town_markers_from_world(data: Dictionary) -> void:
	towns.clear()
	var tw: Variant = data.get("towns", {})
	if tw is Dictionary:
		for _tid in tw.keys():
			var row: Variant = tw[_tid]
			if not (row is Dictionary):
				continue
			var d: Dictionary = row as Dictionary
			var rp: Variant = d.get("residential_plots", [])
			if not (rp is Array) or rp.is_empty():
				continue
			var min_x := 2147483647
			var min_y := 2147483647
			var max_x := -2147483648
			var max_y := -2147483648
			var saw := false
			for pid in rp:
				var ps := str(pid)
				if not plots.has(ps):
					continue
				var pd: Dictionary = plots[ps]
				var gx := int(pd.get("x", 0))
				var gy := int(pd.get("y", 0))
				min_x = mini(min_x, gx)
				min_y = mini(min_y, gy)
				max_x = maxi(max_x, gx)
				max_y = maxi(max_y, gy)
				saw = true
			if not saw or max_x < min_x:
				continue
			towns.append(
				{
					"kind": "town",
					"name": str(d.get("name", _tid)),
					"town_id": str(d.get("town_id", _tid)),
					"bound_min_x": min_x,
					"bound_min_y": min_y,
					"bound_max_x": max_x,
					"bound_max_y": max_y,
				}
			)
	var ns: Variant = data.get("nascent_settlements", [])
	if ns is Array:
		for row in ns:
			if not (row is Dictionary):
				continue
			var anchor := str(row.get("anchor_plot_id", ""))
			if anchor == "" or not plots.has(anchor):
				continue
			var pd: Dictionary = plots[anchor]
			towns.append(
				{
					"kind": "nascent",
					"name": str(row.get("nascent_id", "settlement")),
					"center_x": int(pd.get("x", 0)),
					"center_y": int(pd.get("y", 0)),
				}
			)


func _update_time_from_tick() -> void:
	var tpd := maxi(1, ticks_per_game_day)
	game_day = (current_tick / tpd) + 1
	var day_of_year: int = (game_day - 1) % 365
	if day_of_year < 91:
		game_season = "Spring"
	elif day_of_year < 182:
		game_season = "Summer"
	elif day_of_year < 273:
		game_season = "Autumn"
	else:
		game_season = "Winter"
	game_year = ((game_day - 1) / 365) + 1


func format_money(cents: int) -> String:
	var dollars := int(abs(cents)) / 100
	var c := int(abs(cents)) % 100
	var sign := "-" if cents < 0 else ""
	return "%s$%s.%02d" % [sign, _format_int_commas(dollars), c]


func recipe_by_id(recipe_id: String) -> Dictionary:
	for r in recipes:
		if r is Dictionary and str(r.get("id", "")) == recipe_id:
			return r
	return {}


func player_has_survey_report_for_plot(plot_id: String) -> bool:
	for rep in player_owned_reports:
		if rep is Dictionary and str(rep.get("plot_id", "")) == plot_id:
			return true
	return false


func subsurface_for_plot_ui(plot_id: String, plot_dict: Dictionary) -> Dictionary:
	if bool(plot_dict.get("surveyed", false)) and str(plot_dict.get("owner", "")) == party_id:
		var sub: Variant = plot_dict.get("subsurface", {})
		return sub if sub is Dictionary else {}
	for rep in player_owned_reports:
		if not (rep is Dictionary):
			continue
		if str(rep.get("plot_id", "")) != plot_id:
			continue
		var g: Variant = rep.get("grades", {})
		return g if g is Dictionary else {}
	return {}


func get_plot_ui(plot_id: String) -> Dictionary:
	var base: Dictionary = plots.get(plot_id, {}).duplicate(true)
	if not base.has("id") or str(base.get("id", "")).is_empty():
		base["id"] = plot_id
	var blds: Array = []
	for row in plot_buildings:
		if not (row is Dictionary):
			continue
		if str(row.get("plot_id", "")) != plot_id:
			continue
		var b: Dictionary = (row as Dictionary).duplicate(true)
		var m: Variant = b.get("maintenance", {})
		if m is Dictionary:
			b["_efficiency_pct"] = int(m.get("efficiency_pct", 100))
			b["_missed_cycles"] = int(m.get("missed_cycles", 0))
			var due_at: int = int(m.get("due_at_tick", 0))
			b["_due_in_ticks"] = maxi(0, due_at - current_tick)
			var mats: Variant = m.get("materials", {})
			b["_maintenance_materials"] = mats if mats is Dictionary else {}
		else:
			b["_efficiency_pct"] = 100
			b["_missed_cycles"] = 0
			b["_due_in_ticks"] = 99_999
			b["_maintenance_materials"] = {}
		blds.append(b)
	base["buildings"] = blds
	return base


func active_production_run_for_building(plot_id: String, building_id: String) -> Dictionary:
	for run in active_production:
		if not (run is Dictionary):
			continue
		if str(run.get("plot_id", "")) != plot_id:
			continue
		if str(run.get("party", "")) != party_id:
			continue
		var rid: String = str(run.get("recipe_id", ""))
		var req: String = str(recipe_by_id(rid).get("requires_building_id", ""))
		if req == building_id:
			return run
	return {}


func party_label(pid: String) -> String:
	if pid == party_id:
		return "You"
	if pid == "genesis_exchange":
		return "Exchange"
	return str(party_display_names.get(pid, pid))


func format_ticks_as_gametime(ticks: int) -> String:
	var minutes := ticks
	var hours := minutes / 60
	var days := hours / 24
	if days > 0:
		return "%d game-day%s" % [days, "s" if days > 1 else ""]
	if hours > 0:
		return "%dh %dm" % [hours, minutes % 60]
	return "%dm" % minutes


func _format_int_commas(n: int) -> String:
	var s := str(abs(n))
	var result := ""
	var count := 0
	for i in range(s.length() - 1, -1, -1):
		if count > 0 and count % 3 == 0:
			result = "," + result
		result = s[i] + result
		count += 1
	if n < 0:
		return "-" + result
	return result
