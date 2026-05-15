extends Node
## Single entry point for HTTP calls to the Realm FastAPI server.
## Endpoints and query shapes match ``engine/realm/api/routes_*.py`` (not legacy stubs).

const BASE := "http://127.0.0.1:8000"
## Not ``const``: ``PackedStringArray([...])`` is not a constant expression in GDScript.
var HEADERS: PackedStringArray = PackedStringArray(["Content-Type: application/json"])

func _http_done(h: HTTPRequest, callback: Callable, require_ok: bool, body_text: String) -> void:
	h.queue_free()
	var parsed: Variant = JSON.parse_string(body_text)
	if parsed == null:
		parsed = {}
	if require_ok and parsed is Dictionary and not bool(parsed.get("ok", true)):
		push_warning("API rejected response: %s" % str(parsed))
	callback.call(parsed if parsed is Dictionary else {})


func get_request(endpoint: String, callback: Callable) -> void:
	var h := HTTPRequest.new()
	add_child(h)
	h.request_completed.connect(
		func(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
			if result != HTTPRequest.RESULT_SUCCESS:
				push_warning(
					"Realm API GET %s — network error result=%s (need uvicorn at %s?)" % [endpoint, result, BASE]
				)
				callback.call({})
				h.queue_free()
				return
			if response_code != 200:
				push_warning("API GET %s → HTTP %d" % [endpoint, response_code])
				callback.call({})
				h.queue_free()
				return
			var body_text := body.get_string_from_utf8()
			if JSON.parse_string(body_text) == null and not body_text.is_empty():
				push_warning("API GET %s — JSON parse failed (response length %d)" % [endpoint, body_text.length()])
			_http_done(h, callback, false, body_text)
	)
	var err := h.request(BASE + endpoint, HEADERS, HTTPClient.METHOD_GET)
	if err != OK:
		push_warning("API GET request failed to start: %d %s" % [err, endpoint])
		h.queue_free()
		callback.call({})


func post_request(endpoint: String, payload: Dictionary = {}, callback: Callable = Callable(), require_dict_ok: bool = true) -> void:
	var h := HTTPRequest.new()
	add_child(h)
	h.request_completed.connect(
		func(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
			var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
			if parsed == null:
				parsed = {}
			if result != HTTPRequest.RESULT_SUCCESS:
				push_warning(
					"Realm API POST %s — network error result=%s (need uvicorn at %s?)" % [endpoint, result, BASE]
				)
			elif response_code < 200 or response_code >= 300:
				push_warning("API POST %s → HTTP %d %s" % [endpoint, response_code, str(parsed)])
			elif require_dict_ok and parsed is Dictionary and not bool(parsed.get("ok", true)):
				push_warning("API POST %s failed: %s" % [endpoint, str(parsed)])
			h.queue_free()
			if callback.is_valid():
				callback.call(parsed if parsed is Dictionary else {})
	)
	var body_str := "{}" if payload.is_empty() else JSON.stringify(payload)
	var err := h.request(BASE + endpoint, HEADERS, HTTPClient.METHOD_POST, body_str)
	if err != OK:
		push_warning("API POST request failed to start: %d %s" % [err, endpoint])
		h.queue_free()
		if callback.is_valid():
			callback.call({})


func delete_request(endpoint: String, callback: Callable = Callable()) -> void:
	var h := HTTPRequest.new()
	add_child(h)
	h.request_completed.connect(
		func(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
			h.queue_free()
			var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
			if callback.is_valid():
				callback.call(parsed if parsed is Dictionary else {})
	)
	var err := h.request(BASE + endpoint, HEADERS, HTTPClient.METHOD_DELETE)
	if err != OK:
		push_warning("API DELETE failed to start: %d" % err)
		h.queue_free()
		if callback.is_valid():
			callback.call({})


# ── World ───────────────────────────────────────────────────────────────────

func get_world_summary(party: String = "player", cb: Callable = Callable()) -> void:
	get_request("/world/summary?party=%s" % party.uri_encode(), cb)


func get_world(cb: Callable) -> void:
	get_request("/world", cb)


func tick_once(cb: Callable = Callable()) -> void:
	post_request("/tick", {}, cb)


func tick_batch(n: int, cb: Callable = Callable()) -> void:
	post_request("/tick/batch?count=%d" % int(n), {}, cb)


# ── Plots ───────────────────────────────────────────────────────────────────

func claim_plot(plot_id: String, cb: Callable, party: String = "player") -> void:
	post_request("/plots/%s/claim?party=%s" % [plot_id.uri_encode(), party.uri_encode()], {}, cb)


func survey_plot(plot_id: String, cb: Callable, party: String = "player") -> void:
	post_request("/plots/%s/survey?party=%s" % [plot_id.uri_encode(), party.uri_encode()], {}, cb)


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


func get_plot_energy(plot_id: String, cb: Callable) -> void:
	get_request("/plots/%s/energy" % plot_id.uri_encode(), cb)


func get_plot_throughput(plot_id: String, recipe_id: String, cb: Callable, party: String = "player") -> void:
	get_request(
		"/plots/%s/throughput?party=%s&recipe_id=%s"
		% [plot_id.uri_encode(), party.uri_encode(), recipe_id.uri_encode()],
		cb,
	)


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


func market_sell(material: String, qty: int, price_per_unit_cents: int, cb: Callable, party: String = "player") -> void:
	post_request(
		"/market/sell?party=%s&material=%s&qty=%d&price_per_unit_cents=%d"
		% [party.uri_encode(), material.uri_encode(), int(qty), int(price_per_unit_cents)],
		{},
		cb,
	)


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

func ship(from_plot: String, to_plot: String, material: String, qty: int, cb: Callable, party: String = "player") -> void:
	post_request(
		"/ship?party=%s&material=%s&qty=%d&from_plot=%s&to_plot=%s"
		% [party.uri_encode(), material.uri_encode(), int(qty), from_plot.uri_encode(), to_plot.uri_encode()],
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


func get_cpi(cb: Callable) -> void:
	get_request("/economy/cpi", cb)


func get_fx_rates(cb: Callable) -> void:
	get_request("/fx/rates", cb)


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

## Saves the live world to ``saves/<slot>.sqlite`` (slot defaults to ``current``).
func save_game(cb: Callable = Callable(), slot: String = "current") -> void:
	var q := "/persistence/save"
	if slot != "":
		q += "?slot=%s" % slot.uri_encode()
	post_request(q, {}, cb)


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


func dev_reset(seed: int, scenario: String, cb: Callable) -> void:
	post_request("/dev/reset?seed=%d&scenario=%s" % [int(seed), scenario.uri_encode()], {}, cb)
