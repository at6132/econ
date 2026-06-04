class_name BuildingHubKnowledge
extends RefCounted
## Knowledge graph for the building hub — routes, sites, and stash edges (open-ended, deed-driven).

const COMMON_MATERIALS: Array[String] = [
	"grain",
	"coal",
	"timber",
	"stone",
	"brick",
	"lumber",
	"iron_ore",
	"electricity",
]


static func route_target_plot_id(route_id: String) -> String:
	if route_id.begins_with("stash_plot:"):
		return route_id.substr(11)
	if route_id.begins_with("ship_to:"):
		return route_id.substr(8)
	return ""


static func is_remote_site_route(route_id: String) -> bool:
	return not route_target_plot_id(route_id).is_empty()


static func all_owned_instances() -> Array:
	var out: Array = []
	for pid in WorldState.owned_plot_ids_sorted():
		var ui: Dictionary = WorldState.get_plot_ui(pid)
		for b in ui.get("buildings", []):
			if not (b is Dictionary):
				continue
			var row: Dictionary = b as Dictionary
			var inst := str(row.get("instance_id", ""))
			if inst.is_empty():
				continue
			out.append(
				{
					"plot_id": str(pid),
					"instance_id": inst,
					"building": row,
					"building_name": WorldState.building_display_name(row),
				}
			)
	return out


static func configured_materials_for_instance(instance_id: String, recipe_id: String = "") -> PackedStringArray:
	var seen: Dictionary = {}
	var out: Array = []
	if not recipe_id.is_empty():
		var row := WorldState.recipe_by_id(recipe_id)
		for bucket in ["inputs", "outputs"]:
			var block: Variant = row.get(bucket, {})
			if block is Dictionary:
				for k in (block as Dictionary).keys():
					var mid := str(k)
					if not seen.has(mid):
						seen[mid] = true
						out.append(mid)
	for mid in COMMON_MATERIALS:
		var m := str(mid)
		if seen.has(m):
			continue
		var src := RealmWorkflowSettings.get_input_source(instance_id, m, "")
		var dst := RealmWorkflowSettings.get_output_dest(instance_id, m, "")
		if (
			src != "stash_this"
			or dst != "stash_this"
			or is_remote_site_route(src)
			or is_remote_site_route(dst)
		):
			seen[m] = true
			out.append(m)
	out.sort()
	var packed := PackedStringArray()
	for m in out:
		packed.append(str(m))
	return packed


static func edge_row(
	kind: String,
	material: String,
	qty: int,
	route_id: String,
	home_plot_id: String,
) -> Dictionary:
	var peer := route_target_plot_id(route_id)
	var peer_summary := WorldState.plot_site_summary(peer) if not peer.is_empty() else ""
	return {
		"kind": kind,
		"material": material,
		"qty": qty,
		"route_id": route_id,
		"route_label": WorldState.workflow_route_label(route_id),
		"peer_plot_id": peer,
		"peer_summary": peer_summary,
		"home_plot_id": home_plot_id,
		"is_remote": not peer.is_empty(),
	}


static func material_edges(
	instance_id: String,
	home_plot_id: String,
	recipe_id: String = "",
) -> Dictionary:
	var inputs: Array = []
	var outputs: Array = []
	if instance_id.is_empty():
		return {"inputs": inputs, "outputs": outputs}
	var recipe := WorldState.recipe_by_id(recipe_id) if not recipe_id.is_empty() else {}
	var mats := configured_materials_for_instance(instance_id, recipe_id)
	for mid in mats:
		var qty_in := 0
		var qty_out := 0
		if recipe is Dictionary and not recipe.is_empty():
			var inp: Variant = recipe.get("inputs", {})
			if inp is Dictionary:
				qty_in = int((inp as Dictionary).get(mid, 0))
			var outp: Variant = recipe.get("outputs", {})
			if outp is Dictionary:
				qty_out = int((outp as Dictionary).get(mid, 0))
		var src := RealmWorkflowSettings.get_input_source(instance_id, mid, home_plot_id)
		if qty_in > 0 or src != "stash_this" or is_remote_site_route(src):
			inputs.append(edge_row("input", mid, qty_in, src, home_plot_id))
		var dest := RealmWorkflowSettings.get_output_dest(instance_id, mid, home_plot_id)
		if qty_out > 0 or dest != "stash_this" or is_remote_site_route(dest):
			outputs.append(edge_row("output", mid, qty_out, dest, home_plot_id))
	return {"inputs": inputs, "outputs": outputs}


static func inbound_edges_for_plot(target_plot_id: String) -> Array:
	if target_plot_id.is_empty():
		return []
	var out: Array = []
	for row in all_owned_instances():
		var inst := str(row.get("instance_id", ""))
		if inst.is_empty():
			continue
		var from_plot := str(row.get("plot_id", ""))
		var bname := str(row.get("building_name", "Building"))
		for kind_route in _remote_routes_for_instance(inst, from_plot):
			var verb: String = str(kind_route.get("verb", ""))
			var route_id: String = str(kind_route.get("route_id", ""))
			var mid: String = str(kind_route.get("material", ""))
			if route_target_plot_id(route_id) != target_plot_id:
				continue
			out.append({
				"verb": verb,
				"material": mid,
				"route_id": route_id,
				"route_label": WorldState.workflow_route_label(route_id),
				"from_plot_id": from_plot,
				"from_building": bname,
				"from_summary": WorldState.plot_site_summary(from_plot),
			})
	out.sort_custom(
		func(a, b) -> bool:
			var ka: String = "%s|%s" % [a["from_plot_id"], a["material"]]
			var kb: String = "%s|%s" % [b["from_plot_id"], b["material"]]
			return ka < kb
	)
	return out


static func _remote_routes_for_instance(instance_id: String, home_plot_id: String) -> Array:
	## Only configured routes that point at another deed — avoids scanning every material.
	var out: Array = []
	var seen: Dictionary = {}
	for mid in COMMON_MATERIALS:
		var m := str(mid)
		var src := RealmWorkflowSettings.get_input_source(instance_id, m, home_plot_id)
		if is_remote_site_route(src):
			var key := "in|%s|%s" % [m, src]
			if not seen.has(key):
				seen[key] = true
				out.append({"verb": "pulls", "material": m, "route_id": src})
		var dst := RealmWorkflowSettings.get_output_dest(instance_id, m, home_plot_id)
		if is_remote_site_route(dst):
			var key2 := "out|%s|%s" % [m, dst]
			if not seen.has(key2):
				seen[key2] = true
				out.append({"verb": "sends", "material": m, "route_id": dst})
	return out


static func stash_snapshot(plot_id: String, max_rows: int = 6) -> Array:
	var pd: Dictionary = WorldState.plots.get(plot_id, {})
	var stock: Variant = pd.get("output_stock", {})
	if not (stock is Dictionary):
		return []
	var rows: Array = []
	for k in (stock as Dictionary).keys():
		var qty: int = WorldState.variant_to_int((stock as Dictionary)[k], 0)
		if qty <= 0:
			continue
		rows.append({"material": str(k), "qty": qty})
	rows.sort_custom(func(a, b): return int(b["qty"]) < int(a["qty"]))
	if rows.size() > max_rows:
		return rows.slice(0, max_rows)
	return rows


static func supply_sites() -> Array:
	## Owned deeds with plot bulk storage — finite cap per site (yard vs warehouse).
	return WorldState.logistics_site_entries("")


static func physical_storage_law_blurb() -> String:
	var yard_cap := str(WorldState.PLOT_YARD_CAP_UNITS)
	var wh_cap := str(WorldState.PLOT_WAREHOUSE_CAP_UNITS)
	return (
		"Bulk on a deed is physical: finite capacity (yard ~"
		+ yard_cap
		+ " u, operational warehouse ~"
		+ wh_cap
		+ " u), perishables spoil over time on plot stash, buildings need materials + time to build "
		+ "and decay without maintenance. Routes and auto-buy do not bypass those rules."
	)


static func physical_storage_law_short() -> String:
	return (
		"Finite stash (yard or warehouse cap), spoilage on perishables, "
		+ "and build/upkeep costs still apply — routes cannot bypass those rules."
	)


static func warehouse_rules_active(plot_id: String) -> Array:
	var out: Array = []
	for mid in COMMON_MATERIALS:
		var rule := RealmWorkflowSettings.get_warehouse_rule(plot_id, str(mid))
		if bool(rule.get("enabled", false)):
			out.append(
				{
					"material": str(mid),
					"target_qty": int(rule.get("target_qty", 0)),
					"max_price_cents": int(rule.get("max_price_cents", 0)),
				}
			)
	return out


static func automation_impact_lines(instance_id: String, home_plot_id: String, recipe_id: String) -> PackedStringArray:
	var lines := PackedStringArray()
	if RealmWorkflowSettings.get_auto_maintain(instance_id):
		lines.append("• Auto-maintain this building when upkeep is due.")
	if RealmWorkflowSettings.get_auto_buy_inputs(instance_id):
		var edges := material_edges(instance_id, home_plot_id, recipe_id)
		var market_n := 0
		for e in edges["inputs"]:
			if str(e.get("route_id", "")) == "market_buy":
				market_n += 1
		if market_n > 0:
			lines.append("• Auto-buy: market purchase for %d input route(s) set to buy-from-market." % market_n)
		else:
			lines.append("• Auto-buy enabled — set input routes to “buy from market” on Logistics to use it.")
	if RealmWorkflowSettings.get_auto_replenish_warehouses(instance_id):
		var sites: Array = []
		for entry in supply_sites():
			if not (entry is Dictionary):
				continue
			var pid := str((entry as Dictionary).get("plot_id", ""))
			if warehouse_rules_active(pid).size() > 0:
				sites.append(WorldState.plot_site_summary(pid))
		if sites.is_empty():
			lines.append("• Auto-replenish: no supply rules enabled yet (Supply tab).")
		else:
			lines.append("• Auto-replenish stash targets: %s" % ", ".join(sites))
	return lines
