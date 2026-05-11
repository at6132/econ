/**
 * Copy when a surveyed plot lists zero runnable recipes — usually “no workshop yet”, not “broken terrain”.
 * Dry land only; water is handled in the UI separately.
 */
export function terrainWorkshopEmptyHint(terrain: string): string {
  switch (terrain) {
    case "desert":
      return "Desert still supports power plants, mineral routes, glass, brick, pottery, and similar chains — pick a workshop under Build that matches the recipe you want.";
    case "plains":
      return "Plains suit mills, farms, wire drawing, and many general chains once the matching workshop exists on this plot.";
    case "forest":
      return "Forest unlocks sawmills, charcoal, rope, and timber-adjacent chains once you install the correct workshop.";
    case "mountain":
      return "Mountain hosts smelting, ore work, and alloys — build the workshop each recipe requires before it appears here.";
    case "swamp":
      return "Swamp allows rope, flour, bread, kilns, and other terrain-gated chains once the proper workshop is built.";
    case "tundra":
      return "Tundra supports a subset of chains (e.g. flour, rope, charcoal) where rules permit — build the matching workshop first.";
    default:
      return "This terrain can host industry once you build the workshop each recipe lists — see Build below.";
  }
}
