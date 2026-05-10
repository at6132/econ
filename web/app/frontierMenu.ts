/**
 * Command deck navigation — wire tabs in `page.tsx`.
 */
import { SHOW_INTERNAL_ATLAS_AND_DEV_CONTRACTS } from "./realmUiFlags";

export type TabId = "world" | "schematic" | "market" | "logistics" | "hire" | "pacts" | "log" | "codex";

export type MenuItem = {
  id: string;
  label: string;
  tab: TabId;
  /** Shown under the group header in the sidebar */
  hint?: string;
};

export type MenuGroup = {
  id: string;
  label: string;
  items: MenuItem[];
};

function realmItems(): MenuItem[] {
  const items: MenuItem[] = [
    { id: "hires", label: "Hiring", tab: "hire", hint: "Employment and wages" },
    { id: "pacts", label: "Contracts", tab: "pacts", hint: "Supply deals" },
    { id: "chronicle", label: "Chronicle", tab: "log", hint: "Log and saves" },
  ];
  if (SHOW_INTERNAL_ATLAS_AND_DEV_CONTRACTS) {
    items.push({ id: "atlas", label: "Atlas", tab: "codex", hint: "Internal roadmap (dev)" });
  }
  return items;
}

export function getFrontierMenu(): MenuGroup[] {
  return [
    {
      id: "field",
      label: "Field ops",
      items: [
        { id: "territory", label: "Territory & works", tab: "world", hint: "Map, recipes, builds" },
        { id: "schematic", label: "Schematic", tab: "schematic", hint: "Drag recipe chain, validate flow" },
      ],
    },
    {
      id: "commerce",
      label: "Commerce",
      items: [
        { id: "bazaar", label: "Bazaar", tab: "market", hint: "Orders and prices" },
        { id: "caravans", label: "Caravans", tab: "logistics", hint: "Ship goods" },
      ],
    },
    {
      id: "realm",
      label: "Realm",
      items: realmItems(),
    },
  ];
}
