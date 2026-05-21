extends Node
## Semantic API wrapper over ``Transport`` (solo socket or multiplayer HTTP).
## Endpoint paths match ``engine/realm/api/routes_*.py``.

func get_request(endpoint: String, callback: Callable) -> void:
	Transport.get_request(endpoint, callback)


func post_request(endpoint: String, payload: Dictionary = {}, callback: Callable = Callable(), require_dict_ok: bool = true) -> void:
	if not callback.is_valid():
		Transport.post_request(endpoint, payload, Callable())
		return
	Transport.post_request(
		endpoint,
		payload,
		func(data: Dictionary) -> void:
			if require_dict_ok and not bool(data.get("ok", false)):
				push_warning("API POST %s failed: %s" % [endpoint, str(data)])
			if callback.is_valid():
				callback.call(data)
	)


func delete_request(endpoint: String, callback: Callable = Callable()) -> void:
	Transport.delete_request(endpoint, callback)


# ── World ───────────────────────────────────────────────────────────────────

## Engine build identity. Lets the menu refuse to start when an old realm_solo.py
## is still bound to :9000 (Windows allows multiple SO_REUSEADDR listeners).
func get_version(cb: Callable) -> void:
	get_request("/version", cb)


func get_world_summary(party: String = "player", cb: Callable = Callable()) -> void:
	get_request("/world/summary?party=%s" % party.uri_encode(), cb)


## Read-once tables (building/hire/chemistry catalogs, scenario constants, grid size).
## Fetched on boot + after /dev/reset. Recipe rows: ``get_recipes``.
func get_world_static(cb: Callable) -> void:
	get_request("/world/static", cb)


## Seeded recipe catalog (workshop ids, inputs/outputs, terrain/subsurface gates).
func get_recipes(cb: Callable) -> void:
	get_request("/recipes", cb)


## Per-party realtime view (cash, inventory, owned plots, in-transit,
## forward contracts, bank rates/loans, active production). Cheap.
func get_world_player(cb: Callable, party: String = "player") -> void:
	get_request("/world/player?party=%s" % party.uri_encode(), cb)


## Lean map-only view (terrain/owner/surveyed/powered/density/claim cost).
## Fetched on world-load and after structural actions only.
func get_world_map(cb: Callable) -> void:
	get_request("/world/map", cb)


## Event log + world feed + npc messages. Pass ``since_tick=-1`` for the
## legacy tails; pass a high-water tick to only fetch deltas.
func get_world_feed(cb: Callable, since_tick: int = -1) -> void:
	get_request("/world/feed?since_tick=%d" % int(since_tick), cb)


## Legacy "everything in one shot" payload. Heavy (~27 MB on Genesis).
## Prefer the split endpoints above; keep this only for panels that
## haven't been migrated yet.
func get_world(cb: Callable) -> void:
	get_request("/world", cb)


## Legacy single-tick poke. The host now owns the clock — this is kept only for
## tests, dev tools, and emergency "advance once" buttons. Game UI should NOT
## call this anymore (the engine pushes ``kind: "tick"`` frames automatically).
func tick_once(cb: Callable = Callable()) -> void:
	post_request("/tick", {}, cb)


## Advance N ticks in one round-trip. Dev / automation only.
func tick_batch(n: int, cb: Callable = Callable()) -> void:
	post_request("/tick/batch?count=%d" % int(n), {}, cb)


# ── Sim control (host clock pause / speed) ──────────────────────────────────

## Read pause + speed + pacing constants.
func get_sim_status(cb: Callable) -> void:
	get_request("/sim/status", cb)


## Set ``paused`` and/or ``speed`` in one round-trip. Either field is optional.
## Speed snaps to the nearest preset (``0`` pauses, ``1.0`` / ``2.0`` / ``4.0``).
func sim_control(body: Dictionary, cb: Callable = Callable()) -> void:
	post_request("/sim/control", body, cb)


# ── Plots ───────────────────────────────────────────────────────────────────

func claim_plot(plot_id: String, cb: Callable, party: String = "player") -> void:
	post_request("/plots/%s/claim?party=%s" % [plot_id.uri_encode(), party.uri_encode()], {}, cb)


func survey_plot(plot_id: String, cb: Callable, party: String = "player") -> void:
	post_request("/plots/%s/survey?party=%s" % [plot_id.uri_encode(), party.uri_encode()], {}, cb)


func buy_plot(plot_id: String, cb: Callable, party: String = "player") -> void:
	post_request(
		"/plots/%s/buy" % plot_id.uri_encode(),
		{"party": party},
		cb,
	)


func assay_mineral(plot_id: String, mineral_id: String, cb: Callable, party: String = "player") -> void:
	post_request(
		"/assay?party=%s&plot_id=%s&mineral_id=%s"
		% [party.uri_encode(), plot_id.uri_encode(), mineral_id.uri_encode()],
		{},
		cb,
	)


func get_assay_status(cb: Callable, party: String = "player") -> void:
	get_request("/assay/status?party=%s" % party.uri_encode(), cb)


func get_assay_book(cb: Callable, party: String = "player") -> void:
	get_request("/assay/book?party=%s" % party.uri_encode(), cb)


func deep_survey_plot(plot_id: String, cb: Callable, party: String = "player") -> void:
	post_request(
		"/deep_survey?party=%s&plot_id=%s" % [party.uri_encode(), plot_id.uri_encode()],
		{},
		cb,
	)


func get_deep_survey_status(cb: Callable, party: String = "player") -> void:
	get_request("/deep_survey/status?party=%s" % party.uri_encode(), cb)


func get_blueprints(cb: Callable, party: String = "player") -> void:
	get_request("/blueprints?party=%s" % party.uri_encode(), cb)


func get_workflow(cb: Callable, party: String = "player") -> void:
	get_request("/workflow?party=%s" % party.uri_encode(), cb)


func post_workflow_building(
	instance_id: String,
	input_routes: Dictionary,
	output_routes: Dictionary,
	cb: Callable,
	party: String = "player",
) -> void:
	post_request(
		"/workflow/building",
		{
			"party": party,
			"instance_id": instance_id,
			"input": input_routes,
			"output": output_routes,
		},
		cb,
	)


func post_workflow_warehouse(
	plot_id: String,
	material: String,
	rule: Dictionary,
	cb: Callable,
	party: String = "player",
) -> void:
	post_request(
		"/workflow/warehouse",
		{
			"party": party,
			"plot_id": plot_id,
			"material": material,
			"enabled": bool(rule.get("enabled", false)),
			"target_qty": int(rule.get("target_qty", 0)),
			"max_price_cents": int(rule.get("max_price_cents", 0)),
		},
		cb,
	)


## NPC/script auto-place only — players use ``place_blueprint`` from the build panel.
func build_on_plot(plot_id: String, building_id: String, mode: String, cb: Callable, party: String = "player") -> void:
	var q := "/plots/%s/build?party=%s&building_id=%s" % [
		plot_id.uri_encode(), party.uri_encode(), building_id.uri_encode()]
	if mode != "":
		q += "&build_mode=%s" % mode.uri_encode()
	post_request(q, {}, cb)


func start_production(plot_id: String, recipe_id: String, run_count: int, cb: Callable, party: String = "player") -> void:
	post_request(
		"/plots/%s/produce?party=%s&recipe_id=%s&run_count=%d"
		% [plot_id.uri_encode(), party.uri_encode(), recipe_id.uri_encode(), int(run_count)],
		{},
		cb,
	)


func maintain_building(plot_id: String, instance_id: String, cb: Callable, party: String = "player") -> void:
	post_request(
		"/plots/%s/maintain?party=%s&instance_id=%s"
		% [plot_id.uri_encode(), party.uri_encode(), instance_id.uri_encode()],
		{},
		cb,
	)


func post_building_auto_list(instance_id: String, enabled: bool, cb: Callable, party: String = "player") -> void:
	post_request(
		"/buildings/%s/auto_list" % instance_id.uri_encode(),
		{"party": party, "enabled": enabled},
		cb,
	)


func demolish_building(instance_id: String, cb: Callable, party: String = "player") -> void:
	post_request(
		"/buildings/%s/demolish?party=%s" % [instance_id.uri_encode(), party.uri_encode()],
		{},
		cb,
	)


func get_plot_energy(plot_id: String, cb: Callable) -> void:
	get_request("/plots/%s/energy" % plot_id.uri_encode(), cb)


func get_plot_grid(plot_id: String, cb: Callable) -> void:
	get_request("/plots/%s/grid" % plot_id.uri_encode(), cb)


func get_plot_value(plot_id: String, cb: Callable) -> void:
	get_request("/plots/%s/value" % plot_id.uri_encode(), cb)


func get_plot_sub_plots(plot_id: String, cb: Callable) -> void:
	get_request("/plots/%s/sub-plots" % plot_id.uri_encode(), cb)


func place_blueprint(
	plot_id: String,
	blueprint_id: String,
	grid_x: int,
	grid_y: int,
	build_mode: String,
	cb: Callable,
	party: String = "player",
	sub_plot_id: String = "",
) -> void:
	var body := {
		"party": party,
		"blueprint_id": blueprint_id,
		"grid_x": grid_x,
		"grid_y": grid_y,
		"build_mode": build_mode,
	}
	if sub_plot_id != "":
		body["sub_plot_id"] = sub_plot_id
	post_request("/plots/%s/place" % plot_id.uri_encode(), body, cb)


func place_road_path(
	plot_id: String,
	cells: Array,
	build_mode: String,
	cb: Callable,
	party: String = "player",
) -> void:
	var cell_rows: Array = []
	for c in cells:
		if c is Vector2i:
			var v := c as Vector2i
			cell_rows.append({"grid_x": v.x, "grid_y": v.y})
		elif c is Dictionary:
			cell_rows.append(c)
	var body := {
		"party": party,
		"build_mode": build_mode,
		"cells": cell_rows,
	}
	post_request("/plots/%s/place-roads" % plot_id.uri_encode(), body, cb)


func build_road(
	from_plot_id: String,
	to_plot_id: String,
	cb: Callable,
	party: String = "player",
) -> void:
	post_request(
		"/roads/build",
		{"party": party, "from_plot": from_plot_id, "to_plot": to_plot_id},
		cb,
	)


func list_plot_for_sale(plot_id: String, ask_price_cents: int, cb: Callable, party: String = "player") -> void:
	var body := {"party": party}
	if ask_price_cents > 0:
		body["ask_price_cents"] = ask_price_cents
	post_request("/plots/%s/list-for-sale" % plot_id.uri_encode(), body, cb)


func get_plot_throughput(plot_id: String, recipe_id: String, cb: Callable, party: String = "player") -> void:
	get_request(
		"/plots/%s/throughput?party=%s&recipe_id=%s"
		% [plot_id.uri_encode(), party.uri_encode(), recipe_id.uri_encode()],
		cb,
	)


func create_blueprint(body: Dictionary, cb: Callable) -> void:
	post_request("/blueprints/create", body, cb)


func register_custom_material(
	display_name: String,
	category: String,
	material_id: String,
	cb: Callable,
	party: String = "player",
) -> void:
	post_request(
		"/materials/register",
		{
			"party": party,
			"display_name": display_name,
			"category": category,
			"material_id": material_id,
		},
		cb,
	)


func create_custom_recipe(
	display_name: String,
	inputs: Dictionary,
	outputs: Dictionary,
	duration_ticks: int,
	labor_cents: int,
	requires_building_id: String,
	cb: Callable,
	party: String = "player",
) -> void:
	post_request(
		"/recipes/create",
		{
			"party": party,
			"display_name": display_name,
			"inputs": inputs,
			"outputs": outputs,
			"duration_ticks": int(duration_ticks),
			"labor_cents": int(labor_cents),
			"requires_building_id": requires_building_id,
		},
		cb,
	)


func validate_plot_schematic(plot_id: String, recipe_ids: Array, cb: Callable, party: String = "player") -> void:
	post_request(
		"/plots/%s/schematic/validate?party=%s" % [plot_id.uri_encode(), party.uri_encode()],
		{"recipe_ids": recipe_ids},
		cb,
		false,
	)


func accept_construction_quote(body: Dictionary, cb: Callable) -> void:
	post_request("/construction/accept", body, cb)


# ── Market ──────────────────────────────────────────────────────────────────

func market_buy(
	material: String,
	qty: int,
	min_seller_honored: int,
	cb: Callable,
	party: String = "player",
	max_price_per_unit_cents: int = -1,
) -> void:
	var q := "/market/buy?party=%s&material=%s&max_qty=%d&min_seller_honored=%d" % [
		party.uri_encode(),
		material.uri_encode(),
		int(qty),
		maxi(0, int(min_seller_honored)),
	]
	if max_price_per_unit_cents > 0:
		q += "&max_price_per_unit_cents=%d" % int(max_price_per_unit_cents)
	post_request(q, {}, cb)


func market_sell(
	material: String,
	qty: int,
	price_per_unit_cents: int,
	cb: Callable,
	party: String = "player",
	from_plot: String = "",
) -> void:
	var q := (
		"/market/sell?party=%s&material=%s&qty=%d&price_per_unit_cents=%d"
		% [party.uri_encode(), material.uri_encode(), int(qty), int(price_per_unit_cents)]
	)
	if not from_plot.is_empty():
		q += "&from_plot=%s" % from_plot.uri_encode()
	post_request(q, {}, cb)


func market_cancel(order_id: String, cb: Callable, party: String = "player") -> void:
	post_request("/market/cancel?party=%s&order_id=%s" % [party.uri_encode(), order_id.uri_encode()], {}, cb)


func get_market_signals(cb: Callable) -> void:
	get_request("/market/signals", cb)


func market_bid(
	material: String,
	qty: int,
	max_price_per_unit_cents: int,
	cb: Callable,
	party: String = "player",
) -> void:
	post_request(
		"/market/bid?party=%s&material=%s&qty=%d&max_price_per_unit_cents=%d"
		% [party.uri_encode(), material.uri_encode(), int(qty), int(max_price_per_unit_cents)],
		{},
		cb,
	)


func market_cancel_bid(order_id: String, cb: Callable, party: String = "player") -> void:
	post_request(
		"/market/cancel_bid?party=%s&order_id=%s" % [party.uri_encode(), order_id.uri_encode()],
		{},
		cb,
	)


func get_price_alerts(cb: Callable, party: String = "player") -> void:
	get_request("/alerts/price?party=%s" % party.uri_encode(), cb)


func post_price_alert(
	material: String,
	condition: String,
	threshold_cents: int,
	cb: Callable,
	party: String = "player",
) -> void:
	post_request(
		"/alerts/price",
		{"party": party, "material": material, "condition": condition, "threshold_cents": int(threshold_cents)},
		cb,
	)


func delete_price_alert(alert_id: String, cb: Callable) -> void:
	delete_request("/alerts/price/%s" % alert_id.uri_encode(), cb)


func get_intel_listings(cb: Callable, party: String = "player") -> void:
	get_request("/intel/listings?party=%s" % party.uri_encode(), cb)


func intel_buy(listing_id: String, cb: Callable, party: String = "player") -> void:
	post_request("/intel/buy?party=%s&listing_id=%s" % [party.uri_encode(), listing_id.uri_encode()], {}, cb)


func intel_list_report(report_id: String, ask_price_cents: int, cb: Callable, party: String = "player") -> void:
	post_request(
		"/intel/list?party=%s&report_id=%s&ask_price_cents=%d"
		% [party.uri_encode(), report_id.uri_encode(), int(ask_price_cents)],
		{},
		cb,
	)


func analytics_purchase(product: String, params: Dictionary, cb: Callable, party: String = "player") -> void:
	post_request("/analytics/purchase", {"product": product, "party": party, "params": params}, cb)


func get_analytics_history(cb: Callable, party: String = "player") -> void:
	get_request("/analytics/history?party=%s" % party.uri_encode(), cb)


func get_voyage_history(cb: Callable) -> void:
	get_request("/routes/history", cb)


# ── Labor ───────────────────────────────────────────────────────────────────

func get_laborers(cb: Callable) -> void:
	get_request("/laborers", cb)


func hire_laborer(laborer_id: String, bonus: int, wage: int, cb: Callable, employer: String = "player") -> void:
	post_request(
		"/hire?employer=%s&employee=%s&signing_bonus_cents=%d&wage_per_tick_cents=%d"
		% [employer.uri_encode(), laborer_id.uri_encode(), int(bonus), int(wage)],
		{},
		cb,
	)


func fire_laborer(laborer_id: String, cb: Callable, employer: String = "player") -> void:
	post_request("/hire/fire?employer=%s&laborer_id=%s" % [employer.uri_encode(), laborer_id.uri_encode()], {}, cb)


func post_job_opening(plot_id: String, skill_min: int, wage: int, cb: Callable, employer: String = "player") -> void:
	post_request(
		"/jobs/openings?employer=%s&plot_id=%s&skill_min=%d&wage_per_day_cents=%d"
		% [employer.uri_encode(), plot_id.uri_encode(), int(skill_min), int(wage)],
		{},
		cb,
	)


# ── Shipping / routes ────────────────────────────────────────────────────────

func get_shipping_estimate(from_plot: String, to_plot: String, qty: int, cb: Callable) -> void:
	get_request(
		"/shipping/estimate?from_plot=%s&to_plot=%s&qty=%d"
		% [from_plot.uri_encode(), to_plot.uri_encode(), int(qty)],
		cb,
	)


func ship(from_plot: String, to_plot: String, material: String, qty: int, cb: Callable, party: String = "player") -> void:
	post_request(
		"/ship?party=%s&material=%s&qty=%d&from_plot=%s&to_plot=%s"
		% [party.uri_encode(), material.uri_encode(), int(qty), from_plot.uri_encode(), to_plot.uri_encode()],
		{},
		cb,
	)


func harvest_plot_output(plot_id: String, material: String, qty: int, cb: Callable, party: String = "player") -> void:
	post_request(
		"/plot/harvest?party=%s&plot_id=%s&material=%s&qty=%d"
		% [party.uri_encode(), plot_id.uri_encode(), material.uri_encode(), int(qty)],
		{},
		cb,
	)


func get_routes(cb: Callable) -> void:
	get_request("/routes", cb)


func register_route(from_region: String, to_region: String, fee: int, plot_id: String, cb: Callable, party: String = "player") -> void:
	post_request(
		"/routes/register",
		{
			"party": party,
			"plot_id": plot_id,
			"from_region": from_region,
			"to_region": to_region,
			"fee_per_tile_cents": int(fee),
		},
		cb,
	)


# ── Finance ───────────────────────────────────────────────────────────────────

func get_accounts(cb: Callable) -> void:
	get_request("/accounts", cb)


func get_bank_rates(cb: Callable, party: String = "player") -> void:
	get_request("/bank/rates?party=%s" % party.uri_encode(), cb)


func apply_for_loan(principal_cents: int, cycles: int, cb: Callable, party: String = "player", collateral_plot_id: String = "") -> void:
	var body := {"party": party, "principal_cents": int(principal_cents), "num_cycles": int(cycles)}
	if collateral_plot_id != "":
		body["collateral_plot_id"] = collateral_plot_id
	post_request("/bank/loan/apply", body, cb)


func get_trade_balance(cb: Callable) -> void:
	get_request("/economy/trade-balance", cb)


func get_cpi(cb: Callable) -> void:
	get_request("/economy/cpi", cb)


func get_fx_rates(cb: Callable) -> void:
	get_request("/fx/rates", cb)


func get_fx_orders(cb: Callable) -> void:
	get_request("/fx/orders", cb)


func get_fx_mine(party: String, cb: Callable) -> void:
	get_request("/fx/mine?party=%s" % party.uri_encode(), cb)


func get_fx_history(pair: String, cb: Callable) -> void:
	get_request("/fx/history/%s" % pair.uri_encode(), cb)


func post_fx_order(
	sell_material: String,
	sell_qty: int,
	buy_material: String,
	buy_qty_min: int,
	cb: Callable,
	party: String = "player",
) -> void:
	post_request(
		"/fx/orders?party=%s&sell_material=%s&sell_qty=%d&buy_material=%s&buy_qty_min=%d"
		% [party.uri_encode(), sell_material.uri_encode(), int(sell_qty), buy_material.uri_encode(), int(buy_qty_min)],
		{},
		cb,
	)


func delete_fx_order(order_id: String, party: String, cb: Callable) -> void:
	delete_request("/fx/orders/%s?party=%s" % [order_id.uri_encode(), party.uri_encode()], cb)


func get_futures_orders(cb: Callable) -> void:
	get_request("/futures/orders", cb)


func get_futures_mine(party: String, cb: Callable) -> void:
	get_request("/futures/mine?party=%s" % party.uri_encode(), cb)


func get_futures_curve(material: String, cb: Callable) -> void:
	get_request("/futures/curve/%s" % material.uri_encode(), cb)


func post_futures_order(params: Dictionary, cb: Callable) -> void:
	var q := "/futures/orders?"
	var parts: PackedStringArray = []
	for k in params.keys():
		parts.append("%s=%s" % [str(k), str(params[k]).uri_encode()])
	post_request(q + "&".join(parts), {}, cb)


func delete_futures_order(order_id: String, party: String, cb: Callable) -> void:
	delete_request("/futures/orders/%s?party=%s" % [order_id.uri_encode(), party.uri_encode()], cb)


func get_bank_loans(cb: Callable, party: String = "player") -> void:
	get_request("/bank/loans?party=%s" % party.uri_encode(), cb)


func repay_bank_loan(loan_id: String, cb: Callable, party: String = "player") -> void:
	post_request("/bank/loan/%s/repay?party=%s" % [loan_id.uri_encode(), party.uri_encode()], {}, cb)


func get_account_history(label: String, cb: Callable, party: String = "player") -> void:
	get_request("/accounts/%s/history?party=%s" % [label.uri_encode(), party.uri_encode()], cb)


func create_account(label: String, cb: Callable, party: String = "player") -> void:
	post_request("/accounts/create", {"party": party, "label": label}, cb)


func transfer_accounts(from_label: String, to_label: String, amount_cents: int, cb: Callable, party: String = "player") -> void:
	post_request(
		"/accounts/transfer",
		{"party": party, "from_label": from_label, "to_label": to_label, "amount_cents": int(amount_cents)},
		cb,
	)


func get_banks_currencies(cb: Callable) -> void:
	get_request("/banks/currencies", cb)


func get_loans_market(cb: Callable) -> void:
	get_request("/loans/market", cb)


func list_loan_for_sale(contract_id: String, ask_cents: int, cb: Callable, party: String = "player") -> void:
	post_request(
		"/loans/market/list?party=%s&contract_id=%s&ask_cents=%d"
		% [party.uri_encode(), contract_id.uri_encode(), int(ask_cents)],
		{},
		cb,
	)


func buy_loan_on_market(contract_id: String, cb: Callable, party: String = "player") -> void:
	post_request(
		"/loans/market/%s/buy?party=%s" % [contract_id.uri_encode(), party.uri_encode()], {}, cb
	)


func get_npc_messages(cb: Callable) -> void:
	get_world(func(d: Dictionary) -> void:
		var msgs: Variant = d.get("npc_messages_to_player", d.get("npc_messages", []))
		cb.call(msgs if msgs is Array else [])
	)


func get_insurance_mine(party: String, cb: Callable) -> void:
	get_request("/contracts/insurance/mine?party=%s" % party.uri_encode(), cb)


func get_lease_mine(party: String, cb: Callable) -> void:
	get_request("/contracts/lease/mine?party=%s" % party.uri_encode(), cb)


func get_forward_contracts(cb: Callable) -> void:
	get_request("/contracts/forward", cb)


func get_construction_orders(party: String, cb: Callable) -> void:
	get_request("/construction/orders?party=%s" % party.uri_encode(), cb)


func post_construction_quotes(body: Dictionary, cb: Callable) -> void:
	post_request("/construction/quotes", body, cb)


func post_construction_order(body: Dictionary, cb: Callable) -> void:
	post_request("/construction/order", body, cb)


func get_businesses_mine(party: String, cb: Callable) -> void:
	get_request("/businesses/mine?party=%s" % party.uri_encode(), cb)


func get_businesses_public(cb: Callable) -> void:
	get_request("/businesses", cb)


func get_business_templates(cb: Callable) -> void:
	get_request("/businesses/templates", cb)


func register_business(body: Dictionary, cb: Callable) -> void:
	post_request("/businesses/register", body, cb)


func get_job_openings(employer: String, cb: Callable) -> void:
	get_request("/jobs/openings?employer=%s" % employer.uri_encode(), cb)


func delete_job_opening(opening_id: String, employer: String, cb: Callable) -> void:
	delete_request("/jobs/openings/%s?employer=%s" % [opening_id.uri_encode(), employer.uri_encode()], cb)


func get_laborers_filtered(query: String, cb: Callable) -> void:
	get_request("/laborers%s" % query, cb)


func get_routes_uncharted(cb: Callable) -> void:
	get_request("/routes/uncharted", cb)


func revise_route_fee(route_key: String, fee: int, plot_id: String, cb: Callable, party: String = "player") -> void:
	post_request(
		"/routes/revise_fee",
		{"party": party, "plot_id": plot_id, "route_key": route_key, "fee_per_tile_cents": int(fee)},
		cb,
	)


func get_roads(cb: Callable) -> void:
	get_request("/roads", cb)


func set_road_toll(segment_id: String, toll_bps: int, cb: Callable, party: String = "player") -> void:
	post_request(
		"/roads/%s/toll?party=%s&toll_bps=%d" % [segment_id.uri_encode(), party.uri_encode(), int(toll_bps)],
		{},
		cb,
	)


func p2p_trade(body: Dictionary, cb: Callable) -> void:
	post_request("/trade/p2p", body, cb)


func propose_insurance(params: Dictionary, cb: Callable) -> void:
	var pairs: PackedStringArray = []
	for k in params.keys():
		pairs.append("%s=%s" % [str(k), str(params[k]).uri_encode()])
	post_request("/contracts/insurance/propose?" + "&".join(pairs), {}, cb)


func accept_insurance(contract_id: String, insured: String, cb: Callable) -> void:
	post_request(
		"/contracts/insurance/accept?insured=%s&contract_id=%s"
		% [insured.uri_encode(), contract_id.uri_encode()],
		{},
		cb,
	)


func propose_lease(params: Dictionary, cb: Callable) -> void:
	var pairs: PackedStringArray = []
	for k in params.keys():
		pairs.append("%s=%s" % [str(k), str(params[k]).uri_encode()])
	post_request("/contracts/lease/propose?" + "&".join(pairs), {}, cb)


func accept_lease(contract_id: String, lessee: String, cb: Callable) -> void:
	post_request(
		"/contracts/lease/accept?lessee=%s&contract_id=%s" % [lessee.uri_encode(), contract_id.uri_encode()],
		{},
		cb,
	)


func propose_forward(params: Dictionary, cb: Callable) -> void:
	var pairs: PackedStringArray = []
	for k in params.keys():
		pairs.append("%s=%s" % [str(k), str(params[k]).uri_encode()])
	post_request("/contracts/forward/propose?" + "&".join(pairs), {}, cb)


func accept_forward(contract_id: String, party: String, cb: Callable) -> void:
	post_request(
		"/contracts/forward/%s/accept?party=%s" % [contract_id.uri_encode(), party.uri_encode()], {}, cb
	)


func deliver_forward(contract_id: String, party: String, cb: Callable) -> void:
	post_request(
		"/contracts/forward/%s/deliver?party=%s" % [contract_id.uri_encode(), party.uri_encode()], {}, cb
	)


func propose_equity_stake(params: Dictionary, cb: Callable) -> void:
	var pairs: PackedStringArray = []
	for k in params.keys():
		pairs.append("%s=%s" % [str(k), str(params[k]).uri_encode()])
	post_request("/contracts/equity/stake/propose?" + "&".join(pairs), {}, cb)


func accept_equity_stake(contract_id: String, investor: String, cb: Callable) -> void:
	post_request(
		"/contracts/equity/stake/accept?investor=%s&contract_id=%s"
		% [investor.uri_encode(), contract_id.uri_encode()],
		{},
		cb,
	)


func propose_service_contract(params: Dictionary, cb: Callable) -> void:
	var pairs: PackedStringArray = []
	for k in params.keys():
		pairs.append("%s=%s" % [str(k), str(params[k]).uri_encode()])
	post_request("/contracts/service/propose?" + "&".join(pairs), {}, cb)


func accept_service_contract(contract_id: String, subscriber: String, cb: Callable) -> void:
	post_request(
		"/contracts/service/accept?subscriber=%s&contract_id=%s"
		% [subscriber.uri_encode(), contract_id.uri_encode()],
		{},
		cb,
	)


func get_science_elements(cb: Callable) -> void:
	get_request("/science/elements", cb)


func get_science_reactions(cb: Callable) -> void:
	get_request("/science/reactions/discovered", cb)


func post_science_experiment(body: Dictionary, cb: Callable) -> void:
	post_request("/science/experiment", body, cb)


func get_cpi_components(cb: Callable) -> void:
	get_request("/economy/cpi/components", cb)


func get_tenders(cb: Callable) -> void:
	get_request("/tenders", cb)


func post_tender_bid(tender_id: String, price_cents: int, cb: Callable, party: String = "player") -> void:
	post_request(
		"/tenders/bid?tender_id=%s&party=%s&price_per_unit_cents=%d"
		% [tender_id.uri_encode(), party.uri_encode(), int(price_cents)],
		{},
		cb,
	)


# ── Contracts ───────────────────────────────────────────────────────────────

func propose_supply_contract(params: Dictionary, cb: Callable) -> void:
	var pairs: PackedStringArray = []
	for k in params.keys():
		pairs.append("%s=%s" % [str(k), str(params[k]).uri_encode()])
	post_request("/contracts/supply/propose?" + "&".join(pairs), {}, cb)


func accept_supply_contract(contract_id: String, cb: Callable, buyer: String = "player") -> void:
	post_request(
		"/contracts/supply/accept?buyer=%s&contract_id=%s" % [buyer.uri_encode(), contract_id.uri_encode()], {}, cb
	)


func fulfill_supply_contract(contract_id: String, cb: Callable, supplier: String = "player") -> void:
	post_request(
		"/contracts/supply/fulfill?supplier=%s&contract_id=%s" % [supplier.uri_encode(), contract_id.uri_encode()],
		{},
		cb,
	)


# ── Persistence ─────────────────────────────────────────────────────────────

## Saves the live world to ``saves/<slot>.sqlite``. Empty slot → engine uses this world's id.
func save_game(cb: Callable = Callable(), slot: String = "") -> void:
	var s := slot.strip_edges()
	if s.is_empty():
		s = _default_save_slot()
	var q := "/persistence/save?slot=%s" % s.uri_encode()
	post_request(q, {}, cb)


func _default_save_slot() -> String:
	var wid := WorldState.world_id.strip_edges()
	if not wid.is_empty():
		return wid
	var custom := RealmSettings.default_save_slot.strip_edges()
	if custom.is_empty() or custom == "current":
		return "current"
	return custom


func load_game(cb: Callable = Callable(), slot: String = "current") -> void:
	var q := "/persistence/load"
	if slot != "":
		q += "?slot=%s" % slot.uri_encode()
	post_request(q, {}, cb)


func persistence_list(cb: Callable) -> void:
	get_request("/persistence/list", cb)


func persistence_status(cb: Callable) -> void:
	get_request("/persistence/status", cb)


func persistence_load_path(relative_path: String, cb: Callable) -> void:
	post_request("/persistence/load?path=%s" % relative_path.uri_encode(), {}, cb)


func persistence_clear_all(cb: Callable) -> void:
	post_request("/persistence/clear-all", {}, cb)


func set_world_name(name: String, cb: Callable) -> void:
	post_request("/dev/world-name?name=%s" % name.uri_encode(), {}, cb)


func dev_reset(
	seed: int,
	scenario: String,
	cb: Callable,
	world_name: String = "",
	world_id: String = "",
) -> void:
	var q := "/dev/reset?seed=%d&scenario=%s" % [int(seed), scenario.uri_encode()]
	if not world_name.is_empty():
		q += "&name=%s" % world_name.uri_encode()
	if not world_id.is_empty():
		q += "&world_id=%s" % world_id.uri_encode()
	post_request(q, {}, cb)
