class_name MapHash
extends RefCounted
## Deterministic 32-bit mix for map visuals (ported from ``web/app/mapHash.ts``).


static func hash32(seed: int, s: String) -> int:
	var h: int = seed ^ s.length()
	for i in range(s.length()):
		h = int((h ^ s.unicode_at(i)) * 0x9E3779B1) & 0xFFFFFFFF
	return h & 0xFFFFFFFF


static func vertex_jitter(world_seed: int, vx: int, vy: int, amp: float) -> Vector2:
	var h1: int = hash32(world_seed, "vj:%d,%d" % [vx, vy])
	var h2: int = hash32(world_seed ^ 0xDEADBEEF, "vj:%d,%d" % [vx, vy])
	var dx: float = ((h1 & 0xFFFF) / 65535.0 - 0.5) * 2.0 * amp
	var dy: float = ((h2 & 0xFFFF) / 65535.0 - 0.5) * 2.0 * amp
	return Vector2(dx, dy)


static func owner_tint_color(owner: String) -> Color:
	if owner.is_empty():
		return Color.TRANSPARENT
	var h: int = hash32(0xFEED, owner)
	var hue: float = float(h % 360) / 360.0
	return Color.from_hsv(hue, 0.55, 0.45, 0.26)


static func owner_accent_color(owner: String) -> Color:
	var h: int = hash32(0xFEED, owner)
	var hue: float = float(h % 360) / 360.0
	return Color.from_hsv(hue, 0.72, 0.58)
