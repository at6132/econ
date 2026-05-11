"use client";

type Props = {
  /** When true, overlays are filtered to the human player only. */
  mineLogisticsActive: boolean;
};

/**
 * Compact key for map glyphs — fixed position inside the map viewport (not world-scaled).
 */
export function RealmMapLegendPanel({ mineLogisticsActive }: Props) {
  return (
    <div className="realm-map-legend" role="region" aria-label="Map legend">
      <div className="realm-map-legend__title">Map key</div>
      <ul className="realm-map-legend__list">
        <li className="realm-map-legend__row">
          <span className="realm-map-legend__swatch realm-map-legend__swatch--claim" aria-hidden />
          <span>Colored chip — plot owner (party id)</span>
        </li>
        <li className="realm-map-legend__row">
          <span className="realm-map-legend__glyph" aria-hidden>
            ▣
          </span>
          <span>Workshop / building count on plot</span>
        </li>
        <li className="realm-map-legend__row">
          <span className="realm-map-legend__glyph realm-map-legend__glyph--prod" aria-hidden>
            ⚙
          </span>
          <span>Active production run (count if multiple)</span>
        </li>
        <li className="realm-map-legend__row">
          <span className="realm-map-legend__swatch realm-map-legend__swatch--ship" aria-hidden />
          <span>Dashed arc — shipment in transit (origin → destination)</span>
        </li>
      </ul>
      <p className="realm-map-legend__note">
        {mineLogisticsActive
          ? "Mine is on: only your workshops, production, and shipment arcs are drawn; other parties’ claim chips and route lines are hidden. Terrain tint still shows who owns each plot."
          : "Turn on Mine to hide NPC agents’ logistics overlays when the map feels busy."}
      </p>
    </div>
  );
}
