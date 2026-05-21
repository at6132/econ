class_name MaterialIcons
extends RefCounted
## PNG icons for inventory, bazaar, and shipping (materials + boat aliases).


static func texture_for(material_id: String) -> Texture2D:
	if material_id.is_empty():
		return null
	var path := "res://assets/icons/materials/%s.png" % material_id
	if ResourceLoader.exists(path):
		return load(path) as Texture2D
	# Boat aliases: generic boat → cargo ship art
	if material_id in ("boat", "cargo_ship") and ResourceLoader.exists(
		"res://assets/icons/materials/vessel.png"
	):
		return load("res://assets/icons/materials/vessel.png") as Texture2D
	if material_id == "fishing_boat" and ResourceLoader.exists(
		"res://assets/icons/materials/small_vessel.png"
	):
		return load("res://assets/icons/materials/small_vessel.png") as Texture2D
	return null
