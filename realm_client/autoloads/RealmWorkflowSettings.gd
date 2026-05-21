extends Node
## Production routing + warehouse replenish — local cache synced to engine ``/workflow``.

const FILE_PATH := "user://realm_workflow.cfg"
const SECTION_BUILDING := "building_routing"
const SECTION_WAREHOUSE := "warehouse_replenish"

var _server_loaded: bool = false


func _cfg() -> ConfigFile:
	var f := ConfigFile.new()
	f.load(FILE_PATH)
	return f


func apply_server_snapshot(wf: Dictionary) -> void:
	if wf.is_empty():
		return
	_server_loaded = true
	var f := ConfigFile.new()
	var br: Variant = wf.get("building_routing", {})
	if br is Dictionary:
		for iid in (br as Dictionary).keys():
			var routes: Variant = br[iid]
			if not (routes is Dictionary):
				continue
			var rd: Dictionary = routes as Dictionary
			for mat in (rd.get("input", {}) as Dictionary).keys():
				f.set_value(SECTION_BUILDING, "%s/input/%s" % [iid, mat], rd["input"][mat])
			for mat in (rd.get("output", {}) as Dictionary).keys():
				f.set_value(SECTION_BUILDING, "%s/output/%s" % [iid, mat], rd["output"][mat])
	var wr: Variant = wf.get("warehouse_replenish", {})
	if wr is Dictionary:
		for key in (wr as Dictionary).keys():
			var rule: Variant = wr[key]
			if rule is Dictionary:
				var r: Dictionary = rule as Dictionary
				var parts: PackedStringArray = str(key).split("/")
				if parts.size() >= 2:
					var base := "%s/%s" % [parts[0], parts[1]]
					f.set_value(SECTION_WAREHOUSE, "%s/enabled" % base, bool(r.get("enabled", false)))
					f.set_value(SECTION_WAREHOUSE, "%s/target_qty" % base, int(r.get("target_qty", 0)))
					f.set_value(
						SECTION_WAREHOUSE,
						"%s/max_price_cents" % base,
						int(r.get("max_price_cents", 0)),
					)
	f.save(FILE_PATH)


func get_input_source(instance_id: String, material: String, _default_plot_id: String = "") -> String:
	if instance_id.is_empty():
		return "stash_this"
	if _server_loaded and WorldState.workflow_settings.has("building_routing"):
		var br: Variant = WorldState.workflow_settings["building_routing"]
		if br is Dictionary and (br as Dictionary).has(instance_id):
			var routes: Variant = br[instance_id]
			if routes is Dictionary:
				var inp: Variant = (routes as Dictionary).get("input", {})
				if inp is Dictionary and (inp as Dictionary).has(material):
					return str(inp[material])
	var f := _cfg()
	return str(
		f.get_value(
			SECTION_BUILDING,
			"%s/input/%s" % [instance_id, material],
			"stash_this",
		)
	)


func set_input_source(instance_id: String, material: String, source_id: String) -> void:
	if instance_id.is_empty():
		return
	var f := _cfg()
	f.set_value(SECTION_BUILDING, "%s/input/%s" % [instance_id, material], source_id)
	f.save(FILE_PATH)
	_push_building_routing(instance_id)


func get_output_dest(instance_id: String, material: String, _default_plot_id: String = "") -> String:
	if instance_id.is_empty():
		return "stash_this"
	if _server_loaded and WorldState.workflow_settings.has("building_routing"):
		var br: Variant = WorldState.workflow_settings["building_routing"]
		if br is Dictionary and (br as Dictionary).has(instance_id):
			var routes: Variant = br[instance_id]
			if routes is Dictionary:
				var out: Variant = (routes as Dictionary).get("output", {})
				if out is Dictionary and (out as Dictionary).has(material):
					return str(out[material])
	var f := _cfg()
	return str(
		f.get_value(
			SECTION_BUILDING,
			"%s/output/%s" % [instance_id, material],
			"stash_this",
		)
	)


func set_output_dest(instance_id: String, material: String, dest_id: String) -> void:
	if instance_id.is_empty():
		return
	var f := _cfg()
	f.set_value(SECTION_BUILDING, "%s/output/%s" % [instance_id, material], dest_id)
	f.save(FILE_PATH)
	_push_building_routing(instance_id)


func get_warehouse_rule(plot_id: String, material: String) -> Dictionary:
	if _server_loaded and WorldState.workflow_settings.has("warehouse_replenish"):
		var wr: Variant = WorldState.workflow_settings["warehouse_replenish"]
		var key := "%s/%s" % [plot_id, material]
		if wr is Dictionary and (wr as Dictionary).has(key):
			var r: Variant = wr[key]
			if r is Dictionary:
				return {
					"enabled": bool(r.get("enabled", false)),
					"target_qty": int(r.get("target_qty", 0)),
					"max_price_cents": int(r.get("max_price_cents", 0)),
				}
	var f := _cfg()
	var base := "%s/%s" % [plot_id, material]
	return {
		"enabled": bool(f.get_value(SECTION_WAREHOUSE, "%s/enabled" % base, false)),
		"target_qty": int(f.get_value(SECTION_WAREHOUSE, "%s/target_qty" % base, 0)),
		"max_price_cents": int(f.get_value(SECTION_WAREHOUSE, "%s/max_price_cents" % base, 0)),
	}


func set_warehouse_rule(plot_id: String, material: String, rule: Dictionary) -> void:
	var f := _cfg()
	var base := "%s/%s" % [plot_id, material]
	f.set_value(SECTION_WAREHOUSE, "%s/enabled" % base, bool(rule.get("enabled", false)))
	f.set_value(SECTION_WAREHOUSE, "%s/target_qty" % base, int(rule.get("target_qty", 0)))
	f.set_value(
		SECTION_WAREHOUSE,
		"%s/max_price_cents" % base,
		int(rule.get("max_price_cents", 0)),
	)
	f.save(FILE_PATH)
	API.post_workflow_warehouse(plot_id, material, rule, Callable())


func _building_routing_dict(instance_id: String) -> Dictionary:
	var f := _cfg()
	var inp: Dictionary = {}
	var out: Dictionary = {}
	for section_key in [SECTION_BUILDING]:
		if not f.has_section(section_key):
			continue
		for key in f.get_section_keys(section_key):
			var ks := str(key)
			if not ks.begins_with(instance_id + "/"):
				continue
			var rest := ks.substr(instance_id.length() + 1)
			var parts := rest.split("/")
			if parts.size() != 2:
				continue
			var kind := parts[0]
			var mat := parts[1]
			if kind == "input":
				inp[mat] = str(f.get_value(section_key, key, ""))
			elif kind == "output":
				out[mat] = str(f.get_value(section_key, key, ""))
	return {"input": inp, "output": out}


func _push_building_routing(instance_id: String) -> void:
	var routes := _building_routing_dict(instance_id)
	API.post_workflow_building(instance_id, routes["input"], routes["output"], Callable())
