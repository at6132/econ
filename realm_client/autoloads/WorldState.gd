extends Node
## Cached display state from the last successful API responses (read-only mirror; no game rules).

## Godot 4.4+ rejects ``int()`` on values that are already ``int`` — use for JSON/API Variants.
static func variant_to_int(v: Variant, default_val: int = 0) -> int:
	match typeof(v):
		TYPE_INT:
			return v
		TYPE_FLOAT:
			return int(v)
		TYPE_STRING:
			var s := v as String
			return int(s) if s.is_valid_int() else default_val
		_:
			return default_val


# ── Player state ─────────────────────────────────────────────────────────────
## Must match ``engine/realm/core/player_economy.PLAYER_STARTING_CASH_CENTS``.
const PLAYER_STARTING_CASH_CENTS: int = 10_000_000
## Portable goods only — must match ``engine/realm/production/storage_caps.CARRIED_MATERIAL_IDS``.
const CARRIED_MATERIAL_IDS: Array[String] = ["mining_pick"]
var player_cash_cents: int = 0
## Canon starting balance for a fresh human (from ``GET /world/static`` / ``/dev/reset``).
var player_starting_cash_cents: int = PLAYER_STARTING_CASH_CENTS
var player_net_worth_cents: int = 0
var player_inventory_value_cents: int = 0
var player_building_book_value_cents: int = 0
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
var recipes: Array = []
var custom_recipes: Array = []
var custom_materials: Array = [] # ``recipe_public_list()`` rows
## Server-backed production routing + warehouse replenish (``workflow_settings``).
var workflow_settings: Dictionary = {}
var building_catalog: Array = []
## ``GET /blueprints`` rows keyed by ``blueprint_id`` (seeded + player-authored).
var blueprints_by_id: Dictionary = {}
var player_owned_reports: Array = []
var party_display_names: Dictionary = {}
var scenario_id: String = ""
var world_id: String = ""
var world_name: String = ""
## Labs run metadata (from ``GET /world`` / ``/world/static`` when ``lab_mode``).
var lab_mode: bool = false
var lab_preset_id: String = ""
var lab_title: String = ""
var lab_category: String = ""
var lab_seed: int = 0
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
var market_fob_pickups: Array = []
var forward_contracts: Array = []
var player_price_alerts: Array = []
var road_segments: Array = []
var population_density_map: Dictionary = {}
## Per-landmass category multipliers from ``regional_advantages`` on ``GET /world/static``.
var regional_advantages: Dictionary = {}
## Legacy flat view (first landmass) for economics panels.
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
## True once ``GET /recipes`` has populated ``recipes``.
var recipes_catalog_loaded: bool = false

signal summary_updated
signal world_updated
signal feed_updated
signal market_updated
signal recipes_updated
## ``instance_id``, ``enabled`` — auto-list output toggle synced across panels.
signal building_auto_list_changed(instance_id: String, enabled: bool)
signal map_updated
## Single-plot owner change (claim, purchase) — cheap map tint refresh only.
signal plot_owner_changed(plot_id: String)
signal player_updated
signal static_updated
signal world_name_changed


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
	current_tick = variant_to_int(data.get("tick", current_tick), current_tick)
	game_day = variant_to_int(data.get("game_day", game_day), game_day)
	game_year = variant_to_int(data.get("game_year", game_year), game_year)
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
		ticks_per_game_day = variant_to_int(data.get("ticks_per_game_day", ticks_per_game_day), ticks_per_game_day)
	if data.has("real_seconds_per_game_day"):
		real_seconds_per_game_day = variant_to_int(data.get("real_seconds_per_game_day", real_seconds_per_game_day), real_seconds_per_game_day)
	if data.has("speed_presets"):
		var presets: Variant = data.get("speed_presets", null)
		if presets is Array:
			sim_speed_presets = (presets as Array).duplicate()
	sim_clock_updated.emit()


func apply_summary(data: Dictionary) -> void:
	if data.is_empty():
		return
	player_cash_cents = variant_to_int(data.get("cash", 0), 0)
	player_inventory_value_cents = variant_to_int(
		data.get("inventory_value_estimate", 0), 0
	)
	player_building_book_value_cents = variant_to_int(
		data.get("building_book_value_cents", 0), 0
	)
	player_net_worth_cents = variant_to_int(data.get("net_worth_estimate", 0), 0)
	# Summary polls must not rewind the clock below the last push frame.
	var summary_tick := variant_to_int(data.get("tick", current_tick), current_tick)
	current_tick = maxi(current_tick, summary_tick)
	var ap: Variant = data.get("active_production", [])
	active_production_count = ap.size() if ap is Array else 0
	var mw: Variant = data.get("maintenance_warnings", [])
	maintenance_warning_count = mw.size() if mw is Array else 0
	active_contracts_count = variant_to_int(data.get("active_contracts", 0), 0)
	unread_feed_count = variant_to_int(data.get("unread_feed_entries", 0), 0)
	unread_npc_messages = variant_to_int(data.get("unread_npc_messages", 0), 0)
	if data.has("world_id"):
		world_id = str(data.get("world_id", ""))
	if data.has("world_name"):
		world_name = str(data.get("world_name", ""))
		world_name_changed.emit()
	if data.has("scenario_id"):
		var sid := str(data.get("scenario_id", ""))
		if not sid.is_empty():
			scenario_id = sid
	_update_time_from_tick()
	summary_updated.emit()


func apply_world(data: Dictionary) -> void:
	if data.is_empty():
		return
	ticks_per_game_day = variant_to_int(data.get("ticks_per_game_day", ticks_per_game_day), ticks_per_game_day)
	current_tick = variant_to_int(data.get("tick", current_tick), current_tick)
	world_seed = variant_to_int(data.get("seed", world_seed), world_seed)
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
	_apply_regional_advantages_payload(data)
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
	_apply_lab_fields(data)
	if data.has("world_id"):
		world_id = str(data.get("world_id", ""))
	if data.has("world_name"):
		world_name = str(data.get("world_name", ""))
		world_name_changed.emit()
	var contracts_raw: Variant = data.get("contracts", [])
	active_contracts = contracts_raw if contracts_raw is Array else []

	var ma: Variant = data.get("market_asks", [])
	market_asks_rows = ma if ma is Array else []
	var mb: Variant = data.get("market_bids", [])
	market_bids_rows = mb if mb is Array else []
	var mh: Variant = data.get("market_history", [])
	market_history_rows = mh if mh is Array else []
	market_history_free_window_ticks = variant_to_int(data.get("market_history_free_window_ticks", 48), 48)

	var inv_root: Variant = data.get("inventory", {})
	if inv_root is Dictionary:
		var ply: Variant = (inv_root as Dictionary).get(party_id, {})
		player_inventory = ply if ply is Dictionary else {}
	else:
		player_inventory.clear()

	world_updated.emit()
	feed_updated.emit()


## Load pacing + building/hire/chemistry catalogs from ``GET /world/static``.
## Seeded recipes: ``apply_recipes_catalog`` / ``GET /recipes`` only.
func apply_static(data: Dictionary) -> void:
	if data.is_empty():
		return
	# Legacy servers may still send recipes on static — never use them here.
	if data.has("recipes"):
		data = data.duplicate(true)
		data.erase("recipes")
	player_starting_cash_cents = variant_to_int(
		data.get("player_starting_cash_cents", player_starting_cash_cents),
		player_starting_cash_cents,
	)
	ticks_per_game_day = variant_to_int(data.get("ticks_per_game_day", ticks_per_game_day), ticks_per_game_day)
	real_seconds_per_game_day = variant_to_int(data.get("real_seconds_per_game_day", real_seconds_per_game_day), real_seconds_per_game_day)
	if data.has("sim_speed_presets"):
		var presets: Variant = data.get("sim_speed_presets", null)
		if presets is Array:
			sim_speed_presets = (presets as Array).duplicate()
	market_history_free_window_ticks = variant_to_int(data.get("market_history_free_window_ticks", market_history_free_window_ticks), market_history_free_window_ticks)
	world_seed = variant_to_int(data.get("seed", world_seed), world_seed)
	scenario_id = str(data.get("scenario_id", scenario_id))
	_apply_lab_fields(data)
	if data.has("world_id"):
		world_id = str(data.get("world_id", ""))
	if data.has("world_name"):
		world_name = str(data.get("world_name", ""))
		world_name_changed.emit()
	var pdn: Variant = data.get("party_display_names", {})
	if pdn is Dictionary:
		party_display_names = pdn
	var bc_raw: Variant = data.get("building_catalog", [])
	if bc_raw is Array:
		building_catalog = bc_raw
	_apply_regional_advantages_payload(data)
	static_loaded = true
	static_updated.emit()


## Load seeded recipe rows from ``GET /recipes``.
func apply_recipes_catalog(data: Dictionary) -> void:
	if data.is_empty():
		return
	var rec_raw: Variant = data.get("recipes", [])
	if rec_raw is Array:
		recipes = rec_raw
	recipes_catalog_loaded = true
	recipes_updated.emit()


## Fetch ``GET /recipes`` when the catalog is missing (e.g. map-only boot).
func ensure_recipes_catalog(on_ready: Callable = Callable()) -> void:
	if recipes_catalog_loaded and not recipes.is_empty():
		if on_ready.is_valid():
			on_ready.call()
		return
	API.get_recipes(func(data: Dictionary) -> void:
		if not data.is_empty():
			apply_recipes_catalog(data)
		if on_ready.is_valid():
			on_ready.call()
	)


## Fetch ``GET /world/static`` when pacing/catalog constants are missing.
func ensure_static_tables(on_ready: Callable = Callable()) -> void:
	if static_loaded:
		if on_ready.is_valid():
			on_ready.call()
		return
	API.get_world_static(func(data: Dictionary) -> void:
		if not data.is_empty():
			apply_static(data)
		if on_ready.is_valid():
			on_ready.call()
	)


## Per-party realtime view from ``GET /world/player``. Populates cash,
## inventory, owned plots (and their subsurface/recipe_ids), placed
## buildings, active production, in-transit, forward contracts, bank
## rates/loans, owned reports, price alerts. Does NOT touch the map.
func _merge_server_tick(server_tick: Variant) -> void:
	# Poll responses can finish after a newer tick push — never rewind the HUD.
	current_tick = maxi(current_tick, variant_to_int(server_tick, current_tick))


func _apply_regional_advantages_payload(data: Dictionary) -> void:
	var ra: Variant = data.get("regional_advantages", data.get("regional_advantage", data.get("landmass_advantage", null)))
	if ra is Dictionary and not (ra as Dictionary).is_empty():
		regional_advantages = (ra as Dictionary).duplicate(true)
		var keys := regional_advantages.keys()
		if keys.size() > 0:
			var row: Variant = regional_advantages[keys[0]]
			regional_advantage = row if row is Dictionary else {}
		else:
			regional_advantage = {}


func apply_player(data: Dictionary) -> void:
	if data.is_empty():
		return
	_merge_server_tick(data.get("tick", current_tick))
	player_cash_cents = variant_to_int(data.get("cash_cents", player_cash_cents), player_cash_cents)
	player_inventory_value_cents = variant_to_int(
		data.get("inventory_value_estimate", player_inventory_value_cents),
		player_inventory_value_cents,
	)
	player_building_book_value_cents = variant_to_int(
		data.get("building_book_value_cents", player_building_book_value_cents),
		player_building_book_value_cents,
	)
	player_net_worth_cents = variant_to_int(
		data.get("net_worth_estimate", player_net_worth_cents),
		player_net_worth_cents,
	)
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
	var cr_raw: Variant = data.get("custom_recipes", [])
	custom_recipes = cr_raw if cr_raw is Array else []
	var cm_raw: Variant = data.get("custom_materials", [])
	custom_materials = cm_raw if cm_raw is Array else []
	var wf: Variant = data.get("workflow_settings", {})
	workflow_settings = wf if wf is Dictionary else {}
	if not workflow_settings.is_empty():
		RealmWorkflowSettings.apply_server_snapshot(workflow_settings)
	var it: Variant = data.get("in_transit", [])
	in_transit = it if it is Array else []
	var mp: Variant = data.get("market_fob_pickups", [])
	market_fob_pickups = mp if mp is Array else []
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
	_merge_server_tick(data.get("tick", current_tick))
	var uniform := bool(data.get("uniform_plots", false))
	if uniform:
		push_warning(
			"World map is uniform 1×1 plots — run dev reset for varied parcel shapes (L, zigzag, multi-hectare)."
		)
	var grid_w := variant_to_int(data.get("grid_width", 0), 0)
	var grid_h := variant_to_int(data.get("grid_height", 0), 0)
	# Preserve subsurface + recipe_ids from any prior player payload so a
	# map refresh after a build action doesn't blank out per-owned-plot
	# detail the player can already see.
	var preserved: Dictionary = {}
	for pid in plots.keys():
		var existing: Dictionary = plots[pid]
		if (
			existing.has("subsurface")
			or existing.has("recipe_ids")
			or existing.has("output_stock")
			or bool(existing.get("surveyed", false))
		):
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
					for k in ["subsurface", "recipe_ids", "output_stock", "surveyed"]:
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
				world_cell_to_plot["%d,%d" % [variant_to_int(pd.get("x", 0), 0), variant_to_int(pd.get("y", 0), 0)]] = str(pid)
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
	_merge_server_tick(data.get("tick", current_tick))
	var since: int = variant_to_int(data.get("since_tick", -1), -1)
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
					var key := "%d,%d" % [variant_to_int(d.get("x", 0), 0), variant_to_int(d.get("y", 0), 0)]
					world_cell_to_plot[key] = str(pid)
		else:
			world_cell_to_plot["%d,%d" % [variant_to_int(p.get("x", 0), 0), variant_to_int(p.get("y", 0), 0)]] = str(pid)


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
				var gx := variant_to_int(pd.get("x", 0), 0)
				var gy := variant_to_int(pd.get("y", 0), 0)
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
					"center_x": variant_to_int(pd.get("x", 0), 0),
					"center_y": variant_to_int(pd.get("y", 0), 0),
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
	var ac := absi(cents)
	var dollars := ac / 100
	var c := ac % 100
	var sign := "-" if cents < 0 else ""
	return "%s$%s.%02d" % [sign, _format_int_commas(dollars), c]


func player_material_total(material_id: String) -> int:
	var row: Variant = player_inventory.get(material_id, 0)
	if row is Dictionary:
		return variant_to_int((row as Dictionary).get("total", 0), 0)
	return variant_to_int(row, 0)


func player_material_qty(material_id: String, quality: String = "standard") -> int:
	var row: Variant = player_inventory.get(material_id, 0)
	if row is Dictionary:
		var d: Dictionary = row as Dictionary
		if quality == "any":
			return player_material_total(material_id)
		var by_q: Variant = d.get("by_quality", {})
		if by_q is Dictionary:
			return variant_to_int((by_q as Dictionary).get(quality, 0), 0)
		return variant_to_int(d.get("total", 0), 0)
	if quality == "any" or quality == "standard":
		return variant_to_int(row, 0)
	return 0


func player_has_material(material_id: String, qty_needed: int) -> bool:
	return player_material_total(material_id) >= qty_needed


func player_has_substitute(recipe_id: String, primary_material_id: String) -> bool:
	var recipe := recipe_by_id(recipe_id)
	var subs: Variant = recipe.get("input_substitutes", {})
	if not (subs is Dictionary):
		return false
	var entries: Variant = (subs as Dictionary).get(primary_material_id, [])
	if not (entries is Array):
		return false
	var primary_qty := 1
	var inputs: Variant = recipe.get("inputs", {})
	if inputs is Dictionary and (inputs as Dictionary).has(primary_material_id):
		primary_qty = variant_to_int((inputs as Dictionary)[primary_material_id], 1)
	for entry in entries as Array:
		if not (entry is Array) or (entry as Array).size() < 2:
			continue
		var sub_id := str((entry as Array)[0])
		var ratio := float((entry as Array)[1])
		var sub_need := int(ceil(float(primary_qty) * ratio))
		if player_material_total(sub_id) >= sub_need:
			return true
	return false


func recipe_by_id(recipe_id: String) -> Dictionary:
	for r in recipes:
		if r is Dictionary and str(r.get("id", "")) == recipe_id:
			return r
	for row in custom_recipes:
		if row is Dictionary and str((row as Dictionary).get("recipe_id", "")) == recipe_id:
			var d: Dictionary = (row as Dictionary).duplicate(true)
			d["id"] = recipe_id
			return d
	return {}


func building_catalog_entry(building_id: String) -> Dictionary:
	for row in building_catalog:
		if row is Dictionary and str((row as Dictionary).get("id", "")) == building_id:
			return (row as Dictionary).duplicate(true)
	return {}


func recipes_for_building(building_id: String) -> Array:
	var out: Array = []
	for r in recipes:
		if not (r is Dictionary):
			continue
		if str((r as Dictionary).get("requires_building_id", "")) == building_id:
			out.append(r)
	return out


func merge_blueprints_list(items: Variant) -> void:
	if not (items is Array):
		return
	for item in items:
		if not (item is Dictionary):
			continue
		var bid := str((item as Dictionary).get("blueprint_id", ""))
		if bid.is_empty():
			continue
		blueprints_by_id[bid] = (item as Dictionary).duplicate(true)


func workshop_id_for_building(building: Dictionary) -> String:
	var bp := str(building.get("blueprint_id", ""))
	if not bp.is_empty():
		return bp
	return str(building.get("building_id", ""))


func blueprint_dict(workshop_id: String) -> Dictionary:
	if blueprints_by_id.has(workshop_id):
		return (blueprints_by_id[workshop_id] as Dictionary).duplicate(true)
	var cat := building_catalog_entry(workshop_id)
	var enabled: Array = []
	for row in recipes_for_building(workshop_id):
		if row is Dictionary:
			var rid := str((row as Dictionary).get("id", ""))
			if not rid.is_empty():
				enabled.append(rid)
	if cat.is_empty() and enabled.is_empty():
		return {}
	return {
		"blueprint_id": workshop_id,
		"name": str(cat.get("label", workshop_id)),
		"description": str(cat.get("description", cat.get("label", ""))),
		"category": "processing",
		"enabled_recipe_ids": enabled,
		"footprint_w": 3,
		"footprint_h": 3,
	}


func building_display_name(building: Dictionary) -> String:
	var label := str(building.get("label", ""))
	if not label.is_empty():
		return label
	var wid := workshop_id_for_building(building)
	var bp := blueprint_dict(wid)
	var nm := str(bp.get("name", ""))
	if not nm.is_empty():
		return nm
	return wid if not wid.is_empty() else "Building"


func recipes_for_workshop_building(building: Dictionary) -> Array:
	var wid := workshop_id_for_building(building)
	if wid.is_empty():
		return []
	var bp := blueprint_dict(wid)
	var enabled: Variant = bp.get("enabled_recipe_ids", [])
	var out: Array = []
	var seen: Dictionary = {}
	if enabled is Array:
		for rid in enabled as Array:
			var rid_s := str(rid)
			if rid_s.is_empty() or seen.has(rid_s):
				continue
			var row := recipe_by_id(rid_s)
			if row.is_empty():
				continue
			out.append(row)
			seen[rid_s] = true
	for r in recipes_for_building(wid):
		if not (r is Dictionary):
			continue
		var id_s := str((r as Dictionary).get("id", ""))
		if id_s.is_empty() or seen.has(id_s):
			continue
		out.append(r)
		seen[id_s] = true
	for row in custom_recipes:
		if not (row is Dictionary):
			continue
		if str((row as Dictionary).get("requires_building_id", "")) != wid:
			continue
		var crid := str((row as Dictionary).get("recipe_id", ""))
		if crid.is_empty() or seen.has(crid):
			continue
		var dup: Dictionary = (row as Dictionary).duplicate(true)
		dup["id"] = crid
		out.append(dup)
		seen[crid] = true
	return out


## Seeded workshop ids that run recipes (mirrors engine employment / genesis sets).
const PRODUCTION_WORKSHOP_IDS: Dictionary = {
	"strip_mine": true,
	"timber_yard": true,
	"grain_row": true,
	"drill_rig": true,
	"power_shed": true,
	"tidal_mill": true,
	"wood_shop": true,
	"gristmill": true,
	"kiln_shed": true,
	"foundry": true,
	"stone_works": true,
	"blast_furnace": true,
	"chemical_works": true,
	"forge_press": true,
	"tool_workshop": true,
	"machine_shop": true,
	"shipyard": true,
	"assay_lab": true,
	"laboratory": true,
	"apothecary": true,
	"dock": true,
	"warehouse": true,
}


func building_supports_production(building: Dictionary) -> bool:
	var wid := workshop_id_for_building(building)
	if wid.is_empty() or wid == "road_segment":
		return false
	if building_is_warehouse(building):
		return true
	if PRODUCTION_WORKSHOP_IDS.has(wid):
		return true
	var bp := blueprint_dict(wid)
	var cat := str(bp.get("category", "")).to_lower()
	if cat in ["extraction", "processing", "research"]:
		return true
	if cat == "infrastructure" and wid in ["power_shed", "tidal_mill"]:
		return true
	if cat == "custom":
		var er: Variant = bp.get("enabled_recipe_ids", [])
		if er is Array and not (er as Array).is_empty():
			return true
	return not recipes_for_workshop_building(building).is_empty()


func building_is_warehouse(building: Dictionary) -> bool:
	return workshop_id_for_building(building) == "warehouse"


func find_game_shell() -> Node:
	var tree := get_tree()
	if tree == null:
		return null
	var scene := tree.current_scene
	if scene != null and scene.has_method("open_production_workflow"):
		return scene
	var root := tree.root
	if root == null:
		return scene
	for child in root.get_children():
		if child.has_method("open_production_workflow"):
			return child
	return scene


func patch_building_auto_list(instance_id: String, enabled: bool) -> void:
	if instance_id.is_empty():
		return
	for b in plot_buildings:
		if b is Dictionary and str((b as Dictionary).get("instance_id", "")) == instance_id:
			(b as Dictionary)["auto_list_output"] = enabled
			break
	building_auto_list_changed.emit(instance_id, enabled)


func set_building_auto_list_enabled(instance_id: String, enabled: bool) -> void:
	if instance_id.is_empty():
		return
	API.post_building_auto_list(
		instance_id,
		enabled,
		func(res: Dictionary) -> void:
			if bool(res.get("ok", false)):
				patch_building_auto_list(instance_id, bool(res.get("enabled", enabled)))
	)


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


func set_plot_owner(plot_id: String, owner: String) -> void:
	if plot_id.is_empty():
		return
	var row: Dictionary
	if plots.has(plot_id):
		row = (plots[plot_id] as Dictionary).duplicate(true)
	else:
		row = {"id": plot_id}
	row["owner"] = owner
	plots[plot_id] = row
	plot_owner_changed.emit(plot_id)


func set_plot_surveyed(plot_id: String, surveyed: bool) -> void:
	if plot_id.is_empty():
		return
	var row: Dictionary
	if plots.has(plot_id):
		row = (plots[plot_id] as Dictionary).duplicate(true)
	else:
		row = {"id": plot_id}
	row["surveyed"] = surveyed
	plots[plot_id] = row


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
			b["_efficiency_pct"] = variant_to_int(m.get("efficiency_pct", 100), 100)
			b["_missed_cycles"] = variant_to_int(m.get("missed_cycles", 0), 0)
			var due_at: int = variant_to_int(m.get("due_at_tick", 0), 0)
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


func active_production_run_for_building(plot_id: String, building: Variant) -> Dictionary:
	var workshop_id := ""
	var enabled_ids: Dictionary = {}
	if building is Dictionary:
		var b: Dictionary = building as Dictionary
		workshop_id = workshop_id_for_building(b)
		for row in recipes_for_workshop_building(b):
			if row is Dictionary:
				var rid := str((row as Dictionary).get("id", ""))
				if not rid.is_empty():
					enabled_ids[rid] = true
	elif building is String:
		workshop_id = str(building)
		for row in recipes_for_building(workshop_id):
			if row is Dictionary:
				var rid := str((row as Dictionary).get("id", ""))
				if not rid.is_empty():
					enabled_ids[rid] = true
	for run in active_production:
		if not (run is Dictionary):
			continue
		if str(run.get("plot_id", "")) != plot_id:
			continue
		if str(run.get("party", "")) != party_id:
			continue
		var rid: String = str(run.get("recipe_id", ""))
		if enabled_ids.has(rid):
			return run
		var req: String = str(recipe_by_id(rid).get("requires_building_id", ""))
		if req == workshop_id:
			return run
	return {}


func party_label(pid: String) -> String:
	if pid == party_id:
		return "You"
	if pid == "genesis_exchange":
		return "Exchange"
	return str(party_display_names.get(pid, pid))


func material_display_name(material_id: String) -> String:
	var parts: PackedStringArray = str(material_id).split("_")
	for i in parts.size():
		var p := str(parts[i])
		if p.length() > 0:
			parts[i] = p.substr(0, 1).to_upper() + p.substr(1)
	return " ".join(parts)


func owned_plot_ids_sorted() -> PackedStringArray:
	var ids: Array = []
	var party := party_id
	for pid in plots.keys():
		var row: Dictionary = plots[pid] as Dictionary
		if str(row.get("owner", "")) == party:
			ids.append(str(pid))
	ids.sort()
	var out := PackedStringArray()
	for pid in ids:
		out.append(str(pid))
	return out


func plot_site_tags(plot_id: String) -> PackedStringArray:
	var tags: PackedStringArray = PackedStringArray()
	var ui := get_plot_ui(plot_id)
	for b in ui.get("buildings", []):
		if not (b is Dictionary):
			continue
		var bid := str((b as Dictionary).get("building_id", ""))
		if bid == "warehouse" and not tags.has("warehouse"):
			tags.append("warehouse")
		elif bid == "store" and not tags.has("store"):
			tags.append("store")
		elif bid != "road_segment" and recipes_for_building(bid).size() > 0 and not tags.has("factory"):
			tags.append("factory")
	return tags


func plot_site_label(plot_id: String) -> String:
	var tags := plot_site_tags(plot_id)
	if tags.is_empty():
		return plot_id
	var tag_list: Array = []
	for t in tags:
		tag_list.append(str(t))
	return "%s · %s" % [plot_id, ", ".join(tag_list)]


func is_carried_material(material_id: String) -> bool:
	return material_id in CARRIED_MATERIAL_IDS


func player_plot_stash_total(material_id: String) -> int:
	var total := 0
	for pid in owned_plot_ids_sorted():
		total += plot_output_stock_qty(pid, material_id)
	return total


func player_material_held_total(material_id: String) -> int:
	return player_material_total(material_id) + player_plot_stash_total(material_id)


func plots_with_material(material_id: String, min_qty: int = 1) -> Array:
	var out: Array = []
	for pid in owned_plot_ids_sorted():
		var q: int = plot_output_stock_qty(pid, material_id)
		if q >= min_qty:
			out.append(
				{"plot_id": pid, "qty": q, "label": plot_site_label(pid)}
			)
	return out


func plot_output_stock_qty(plot_id: String, material_id: String) -> int:
	var pd: Dictionary = plots.get(plot_id, {})
	var stock: Variant = pd.get("output_stock", {})
	if not (stock is Dictionary):
		return 0
	return variant_to_int((stock as Dictionary).get(material_id, 0), 0)


func inventory_ledger_rows() -> Array:
	var rows: Array = []
	for mat in player_inventory.keys():
		var mid := str(mat)
		var qty := player_material_total(mid)
		if qty <= 0:
			continue
		rows.append({
			"material": mid,
			"qty": qty,
			"location": "Personal carry",
			"status": "Portable",
			"kind": "carried",
			"plot_id": "",
			"can_ship": is_carried_material(mid),
			"can_harvest": false,
		})
	for pid in owned_plot_ids_sorted():
		var pd: Dictionary = plots[pid] as Dictionary
		var stock: Variant = pd.get("output_stock", {})
		if not (stock is Dictionary):
			continue
		for mat in (stock as Dictionary).keys():
			var mid := str(mat)
			var qty: int = variant_to_int((stock as Dictionary)[mid], 0)
			if qty <= 0:
				continue
			rows.append({
				"material": mid,
				"qty": qty,
				"location": plot_site_label(pid),
				"status": "On site",
				"kind": "stash",
				"plot_id": pid,
				"can_ship": true,
				"can_harvest": is_carried_material(mid),
			})
	for ship in in_transit:
		if not (ship is Dictionary):
			continue
		var s: Dictionary = ship
		var mid := str(s.get("material", ""))
		var qty: int = variant_to_int(s.get("qty", 0), 0)
		if mid.is_empty() or qty <= 0:
			continue
		var from_p := str(s.get("from_plot_id", ""))
		var dest := str(s.get("dest_plot_id", ""))
		var arrive: int = variant_to_int(s.get("arrive_tick", 0), 0)
		var eta := maxi(0, arrive - current_tick)
		var consignee := str(s.get("consignee", ""))
		var market_ship := bool(s.get("escrowed_market", false))
		var status := "In transit · %s" % format_ticks_as_gametime(eta)
		if market_ship and consignee == party_id:
			status = "Market delivery · %s" % format_ticks_as_gametime(eta)
		rows.append({
			"material": mid,
			"qty": qty,
			"location": "%s → %s" % [from_p if not from_p.is_empty() else "?", dest],
			"status": status,
			"kind": "transit",
			"plot_id": dest,
			"can_ship": false,
			"can_harvest": false,
		})
	for pick in market_fob_pickups:
		if not (pick is Dictionary):
			continue
		var pk: Dictionary = pick
		if str(pk.get("role", "")) != "buyer":
			continue
		var mid2 := str(pk.get("material", ""))
		var q2: int = variant_to_int(pk.get("qty", 0), 0)
		if mid2.is_empty() or q2 <= 0:
			continue
		var seller_lbl := party_label(str(pk.get("seller", "?")))
		rows.append({
			"material": mid2,
			"qty": q2,
			"location": plot_site_label(str(pk.get("from_plot_id", ""))),
			"status": "FOB — collect at seller (%s)" % seller_lbl,
			"kind": "pickup",
			"plot_id": str(pk.get("from_plot_id", "")),
			"pickup_id": str(pk.get("pickup_id", "")),
			"can_ship": false,
			"can_harvest": false,
			"can_pickup": true,
		})
	rows.sort_custom(func(a, b) -> bool:
		var ka: String = "%s|%s|%s" % [a["kind"], a["location"], a["material"]]
		var kb: String = "%s|%s|%s" % [b["kind"], b["location"], b["material"]]
		return ka < kb
	)
	return rows


func default_delivery_plot_id() -> String:
	for entry in ship_destination_options():
		if entry is Dictionary:
			return str((entry as Dictionary).get("plot_id", ""))
	return ""


func ship_destination_options() -> Array:
	## Each entry: ``{plot_id, label, group}`` where group is warehouse|store|factory|other.
	var buckets: Dictionary = {
		"warehouse": [],
		"store": [],
		"factory": [],
		"other": [],
	}
	for pid in owned_plot_ids_sorted():
		var tags := plot_site_tags(pid)
		var group := "other"
		if tags.has("warehouse"):
			group = "warehouse"
		elif tags.has("store"):
			group = "store"
		elif tags.has("factory"):
			group = "factory"
		buckets[group].append({"plot_id": pid, "label": plot_site_label(pid), "group": group})
	var order := ["warehouse", "store", "factory", "other"]
	var out: Array = []
	for g in order:
		for row in buckets[g]:
			out.append(row)
	return out


func _apply_lab_fields(data: Dictionary) -> void:
	if not data.has("lab_mode"):
		return
	lab_mode = bool(data.get("lab_mode", false))
	if lab_mode:
		lab_preset_id = str(data.get("lab_preset_id", lab_preset_id))
		lab_title = str(data.get("lab_title", lab_title))
		lab_category = str(data.get("lab_category", lab_category))
		lab_seed = variant_to_int(data.get("lab_seed", data.get("seed", lab_seed)), lab_seed)
	else:
		lab_preset_id = ""
		lab_title = ""
		lab_category = ""
		lab_seed = 0


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
