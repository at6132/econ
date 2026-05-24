/** Labs API DTO shapes (engine /labs/*). */

export type LabCategory =
  | "Strategy"
  | "Markets"
  | "Social"
  | "Production"
  | "Stress"
  | "Tutorial";

export type LabPresetSummary = {
  id: string;
  title: string;
  description: string;
  category: LabCategory;
  tags: string[];
  base: "frontier" | "genesis";
  grid_label: string;
  featured: boolean;
  default_seed: number;
  default_sim_speed: number;
};

export type LabOverrideSchema = Record<
  string,
  { type: string; min?: number; max?: number; default?: number; step?: number }
>;

export type LabPresetDetail = LabPresetSummary & {
  params: Record<string, unknown>;
  overlays: Record<string, boolean>;
  override_schema: LabOverrideSchema;
};

export type LabsPresetsResponse = {
  ok: boolean;
  presets: LabPresetSummary[];
  total: number;
  offset: number;
  limit: number;
  categories: LabCategory[];
  stats: { total: number; featured: number };
};
