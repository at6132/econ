extends Node
## Cached display state from the last successful API responses (read-only mirror; no game rules).

# ── Player state ─────────────────────────────────────────────────────────────
var player_cash_cents: int = 0
var player_net_worth_cents: int = 0
var party_id: String = "player"
var display_name: String = "Player"

# ── Time scale (from ``GET /world``; default matches engine ``TICKS_PER_GAME_DAY``) ──
var ticks_per_game_day: int = 1440
## Canon (Law 2): 1 in-game day = 1 real hour at 1× speed.
var real_seconds_per_game_day: int = 3600

# ── Time (derived from tick + ticks_per_game_day) ───────────────────────────
var current_tick: int = 0
var game_day: int = 1
var game_season: String = "Spring"
var game_year: int = 1

# ── Sim clock (host-side pacing — pushed by the engine, no client metronome) ──
var sim_paused: bool = false
var sim_speed: float = 1.0
var sim_effective_speed: float = 1.0
var sim_seconds_per_tick: float = 2.5
var sim_speed_presets: Array = [0.0, 1.0, 2.0, 4.0]

signal sim_clock_updated

# ── HUD counters ─────────────────────────────────────────────────────────────
var active_production_count: int = 0
var maintenance_warning_count: int = 0
var active_contracts_count: int = 0
var unread_feed_count: int = 0
var unread_npc_messages: int = 0
var cpi_current: float = 100.0

# ── World data ───────────────────────────────────────────────────────────────
var plots: Dictionary = {} # plot_id str → plot dict
## ``"gx,gy"`` world map coordinates → plot_id (multi-tile parcels).
var world_cell_to_plot: Dictionary = {}
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
var event_log: Array = []
var active_world_events: Array = []
var in_transit: Array = []
var forward_contracts: Array = []
var player_price_alerts: Array = []
var road_segments: Array = []
var population_density_map: Dictionary = {}
var regional_advantage: Dictionary = {}

## Matches ``realm.actions.plot_actions.SURVEY_COST_CENTS`` (engine source of truth).
const SURVEY_COST_CENTS: int = 50_000

# ── Market (optional cache; not populated in Phase 1 unless you call an API) ─
var market_asks: Dictionary = {}
var market_bids: Dictionary = {}
var price_history: Dictionary = {}

## Latest tick observed in any of the feed/event/npc tails. Used as the
## ``since_tick`` high-water mark on the next ``/world/feed`` poll so the
## server only sends new rows.
var feed_seen_tick: int = -1

## True once ``apply_static`` has populated the read-once tables.
var static_loaded: bool = false

signal summary_updated
signal world_updated
signal feed_updated
signal market_updated
signal map_updated
signal player_updated
signal static_updated


## Updates HUD time fields from an authoritative engine tick (e.g. ``POST /tick`` body).
## Emits ``summary_updated`` so CommandShell refreshes even when GET polling fails.
func apply_engine_tick_hint(tick: int) -> void:
	current_tick = tick
	_update_time_from_tick()
	summary_updated.emit()


## Apply a server push frame (kind == "tick"). Auth source for clock + calendar:
## the engine already computed game_day/season/year, so we trust it instead of
## re-deriving on the client (avoids drift when the engine changes the calendar).
func apply_tick_frame(data: Dictionary) -> void:
	if data.is_empty():
		return
	current_tick = int(data.get("tick", current_tick))
	game_day = int(data.get("game_day", game_day))
	game_year = int(data.get("game_year", game_year))
	var season_v: Variant = data.get("season", null)
	if season_v is String and not (season_v as String).is_empty():
		game_season = String(season_v)
	# Pause / speed are pushed along with each tick so the HUD never falls
	# behind a control change made elsewhere.
	if data.has("paused"):
		sim_paused = bool(data.get("paused", sim_paused))
	if data.has("speed"):
		sim_speed = float(data.get("speed", sim_speed))
	if data.has("effective_speed"):
		sim_effective_speed = float(data.get("effective_speed", sim_effective_speed))
	summary_updated.emit()
	sim_clock_updated.emit()


## Apply a server push frame (kind == "sim_status") — pause / speed / pacing.
func apply_sim_status(data: Dictionary) -> void:
	if data.is_empty():
		return
	sim_paused = bool(data.get("paused", sim_paused))
	sim_speed = float(data.get("speed", sim_speed))
	sim_effective_speed = float(data.get("effective_speed", sim_effective_speed))
	var spt: Variant = data.get("seconds_per_tick", null)
	if spt != null:
		sim_seconds_per_tick = float(spt)
	if data.has("ticks_per_game_day"):
		ticks_per_game_day = int(data.get("ticks_per_game_day", ticks_per_game_day))
	if data.has("real_seconds_per_game_day"):
		real_seconds_per_game_day = int(data.get("real_seconds_per_game_day", real_seconds_per_game_day))
	if data.has("speed_presets"):
		var presets: Variant = data.get("speed_presets", null)
		if presets is Array:
			sim_speed_presets = (presets as Array).duplicate()
	sim_clock_updated.emit()


func apply_summary(data: Dictionary) -> void:
	if data.is_empty():
		return
	player_cash_cents = int(data.get("cash", 0))
	player_net_worth_cents = int(data.get("net_worth_estimate", 0))
	# Summary polls must not rewind the clock below the last push frame.
	var summary_tick := int(data.get("tick", current_tick))
	current_tick = maxi(current_tick, summary_tick)
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

	var wc: Variant = data.get("world_cell_to_plot", {})
	world_cell_to_plot = wc if wc is Dictionary else {}
	_ensure_world_cell_index()

	_rebuild_town_markers_from_world(data)

	businesses = data.get("business_entities", data.get("businesses", []))
	if not (businesses is Array):
		businesses = []
	world_feed_log = data.get("world_feed_log", [])
	if not (world_feed_log is Array):
		world_feed_log = []
	var npc_raw: Variant = data.get("npc_messages_to_player", data.get("npc_messages", []))
	npc_messages = npc_raw if npc_raw is Array else []
	var el: Variant = data.get("event_log", [])
	event_log = el if el is Array else []
	var awe: Variant = data.get("active_world_events", [])
	active_world_events = awe if awe is Array else []
	var it: Variant = data.get("in_transit", [])
	in_transit = it if it is Array else []
	var fc: Variant = data.get("forward_contracts", [])
	forward_contracts = fc if fc is Array else []
	var pa: Variant = data.get("player_price_alerts", [])
	player_price_alerts = pa if pa is Array else []
	var rs: Variant = data.get("road_segments", [])
	road_segments = rs if rs is Array else []
	var adv: Variant = data.get("regional_advantage", data.get("landmass_advantage", {}))
	regional_advantage = adv if adv is Dictionary else {}
	population_density_map.clear()
	for pid in plots.keys():
		var pd: Dictionary = plots[pid]
		population_density_map[str(pid)] = float(pd.get("population_density", 0.0))
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


## Load the read-once tables from ``GET /world/static``. Safe to call
## repeatedly (after ``/dev/reset`` for example) — overwrites the cached
## catalogs and constants in place without touching plot or feed state.
func apply_static(data: Dictionary) -> void:
	if data.is_empty():
		return
	ticks_per_game_day = int(data.get("ticks_per_game_day", ticks_per_game_day))
	real_seconds_per_game_day = int(data.get("real_seconds_per_game_day", real_seconds_per_game_day))
	if data.has("sim_speed_presets"):
		var presets: Variant = data.get("sim_speed_presets", null)
		if presets is Array:
			sim_speed_presets = (presets as Array).duplicate()
	market_history_free_window_ticks = int(data.get("market_history_free_window_ticks", market_history_free_window_ticks))
	world_seed = int(data.get("seed", world_seed))
	scenario_id = str(data.get("scenario_id", scenario_id))
	var pdn: Variant = data.get("party_display_names", {})
	if pdn is Dictionary:
		party_display_names = pdn
	var rec_raw: Variant = data.get("recipes", [])
	if rec_raw is Array:
		recipes = rec_raw
	var bc_raw: Variant = data.get("building_catalog", [])
	if bc_raw is Array:
		building_catalog = bc_raw
	static_loaded = true
	static_updated.emit()


## Per-party realtime view from ``GET /world/player``. Populates cash,
## inventory, owned plots (and their subsurface/recipe_ids), placed
## buildings, active production, in-transit, forward contracts, bank
## rates/loans, owned reports, price alerts. Does NOT touch the map.
func _merge_server_tick(server_tick: int) -> void:
	# Poll responses can finish after a newer tick push — never rewind the HUD.
	current_tick = maxi(current_tick, server_tick)


func apply_player(data: Dictionary) -> void:
	if data.is_empty():
		return
	_merge_server_tick(int(data.get("tick", current_tick)))
	player_cash_cents = int(data.get("cash_cents", player_cash_cents))
	var inv: Variant = data.get("inventory", {})
	player_inventory = inv if inv is Dictionary else {}
	var own_raw: Variant = data.get("owned_plots", [])
	if own_raw is Array:
		for entry in own_raw:
			if not (entry is Dictionary):
				continue
			var pid := str(entry.get("id", ""))
			if pid == "":
				continue
			# Merge the rich (subsurface + recipe_ids) view onto whatever
			# the map endpoint left us — don't replace, the map dict has
			# the canonical (x, y) and population_density even for plots
			# we don't own.
			var merged: Dictionary = (plots.get(pid, {}) as Dictionary).duplicate(true)
			for k in (entry as Dictionary).keys():
				merged[k] = entry[k]
			plots[pid] = merged
	var pb_raw: Variant = data.get("plot_buildings", [])
	plot_buildings = pb_raw if pb_raw is Array else []
	var ap_raw: Variant = data.get("active_production", [])
	active_production = ap_raw if ap_raw is Array else []
	var it: Variant = data.get("in_transit", [])
	in_transit = it if it is Array else []
	var fc: Variant = data.get("forward_contracts", [])
	forward_contracts = fc if fc is Array else []
	var por: Variant = data.get("owned_reports", [])
	player_owned_reports = por if por is Array else []
	var pa: Variant = data.get("price_alerts", [])
	player_price_alerts = pa if pa is Array else []
	_update_time_from_tick()
	player_updated.emit()
	# DELIBERATELY does NOT emit world_updated — that signal triggers a
	# full ``_rebuild_cell_cache`` in WorldMap (76800 cells on Genesis).
	# Panels that need to react to per-tick player-state changes (owned
	# plots, in_transit, active production) should listen to
	# ``player_updated`` instead.


## Lean map view from ``GET /world/map``. Replaces the ``plots`` cache
## with the canonical map state, then rebuilds the world-cell index.
## Call only after world-load or a structural action — not on the 2 s tick.
func is_api_error_payload(data: Dictionary) -> bool:
	return data.has("ok") and not bool(data.get("ok", true))


func apply_map(data: Dictionary) -> void:
	if data.is_empty():
		return
	if is_api_error_payload(data):
		push_warning("WorldState.apply_map: %s" % str(data.get("reason", "request failed")))
		return
	var raw_plots: Variant = data.get("plots", [])
	if not (raw_plots is Array) or (raw_plots as Array).is_empty():
		# Socket error envelopes and failed requests often omit plots — never
		# wipe a good map that Main already applied.
		if not plots.is_empty():
			return
		push_warning("WorldState.apply_map: payload had no plots")
		return
	_merge_server_tick(int(data.get("tick", current_tick)))
	var uniform := bool(data.get("uniform_plots", false))
	if uniform:
		push_warning(
			"World map is uniform 1×1 plots — run dev reset for varied parcel shapes (L, zigzag, multi-hectare)."
		)
	var grid_w := int(data.get("grid_width", 0))
	var grid_h := int(data.get("grid_height", 0))
	# Preserve subsurface + recipe_ids from any prior player payload so a
	# map refresh after a build action doesn't blank out per-owned-plot
	# detail the player can already see.
	var preserved: Dictionary = {}
	for pid in plots.keys():
		var existing: Dictionary = plots[pid]
		if existing.has("subsurface") or existing.has("recipe_ids") or existing.has("output_stock"):
			preserved[pid] = existing
	plots.clear()
	if raw_plots is Array:
		for p in raw_plots:
			if p is Dictionary:
				var pid_s := str(p.get("id", ""))
				if pid_s == "":
					continue
				if preserved.has(pid_s):
					var merged: Dictionary = (p as Dictionary).duplicate(true)
					var prior: Dictionary = preserved[pid_s]
					for k in ["subsurface", "recipe_ids", "output_stock"]:
						if prior.has(k):
							merged[k] = prior[k]
					plots[pid_s] = merged
				else:
					# Genesis map payloads are huge — avoid deep-copying every plot on first load.
					plots[pid_s] = p as Dictionary
	# /world/map omits world_cell_to_plot on uniform grids — rebuild it.
	world_cell_to_plot.clear()
	var wc: Variant = data.get("world_cell_to_plot", {})
	if wc is Dictionary and not (wc as Dictionary).is_empty():
		world_cell_to_plot = wc
	else:
		if uniform:
			for pid in plots.keys():
				var pd: Dictionary = plots[pid]
				world_cell_to_plot["%d,%d" % [int(pd.get("x", 0)), int(pd.get("y", 0))]] = str(pid)
		else:
			_ensure_world_cell_index()
	population_density_map.clear()
	for pid in plots.keys():
		var pd2: Dictionary = plots[pid]
		population_density_map[str(pid)] = float(pd2.get("population_density", 0.0))
	# Surface grid dims for the map renderer (used by Phase 2 LOD cache).
	if grid_w > 0 and grid_h > 0:
		set_meta("grid_width", grid_w)
		set_meta("grid_height", grid_h)
	_update_time_from_tick()
	map_updated.emit()
	world_updated.emit()


## Feed / event / npc-message deltas from ``GET /world/feed``. With
## ``since_tick=-1`` the server returns legacy tails (used on first load);
## subsequent polls pass ``feed_seen_tick`` so the server only sends new
## rows, which we append in place (keeping the last 2000 events / 4000
## feed rows / 200 npc messages to bound memory growth).
func apply_feed(data: Dictionary) -> void:
	if data.is_empty():
		return
	_merge_server_tick(int(data.get("tick", current_tick)))
	var since: int = int(data.get("since_tick", -1))
	var events: Variant = data.get("event_log", [])
	var feed: Variant = data.get("world_feed_log", [])
	var npc: Variant = data.get("npc_messages", [])
	if since < 0:
		event_log = events if events is Array else []
		world_feed_log = feed if feed is Array else []
		npc_messages = npc if npc is Array else []
	else:
		if events is Array:
			event_log.append_array(events)
		if feed is Array:
			world_feed_log.append_array(feed)
		if npc is Array:
			npc_messages.append_array(npc)
	_trim_feed_caches()
	_advance_feed_seen_tick()
	_update_time_from_tick()
	feed_updated.emit()


func _trim_feed_caches() -> void:
	if event_log.size() > 2000:
		event_log = event_log.slice(event_log.size() - 2000)
	if world_feed_log.size() > 4000:
		world_feed_log = world_feed_log.slice(world_feed_log.size() - 4000)
	if npc_messages.size() > 200:
		npc_messages = npc_messages.slice(npc_messages.size() - 200)


func _advance_feed_seen_tick() -> void:
	# We push the high-water mark forward to current_tick (any rows added
	# in this batch had tick <= current_tick on the server) so the next
	# /world/feed call only returns strictly-newer rows.
	if current_tick > feed_seen_tick:
		feed_seen_tick = current_tick


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


func _ensure_world_cell_index() -> void:
	## Solo/API may omit the index on older saves; rebuild from per-plot ``world_cells``.
	if not world_cell_to_plot.is_empty():
		return
	for pid in plots.keys():
		var p: Dictionary = plots[pid]
		var cells: Variant = p.get("world_cells", [])
		if cells is Array and not (cells as Array).is_empty():
			for c in cells as Array:
				if c is Dictionary:
					var d: Dictionary = c as Dictionary
					var key := "%d,%d" % [int(d.get("x", 0)), int(d.get("y", 0))]
					world_cell_to_plot[key] = str(pid)
		else:
			world_cell_to_plot["%d,%d" % [int(p.get("x", 0)), int(p.get("y", 0))]] = str(pid)


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
