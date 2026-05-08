/**
 * Command deck navigation — add groups/items here; wire new tabs in `page.tsx`.
 */
export type TabId = "world" | "market" | "logistics" | "contracts" | "log" | "codex";

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

export const FRONTIER_MENU: MenuGroup[] = [
  {
    id: "field",
    label: "Field ops",
    items: [{ id: "territory", label: "Territory & works", tab: "world", hint: "Map, recipes, builds" }],
  },
  {
    id: "commerce",
    label: "Commerce",
    items: [
      { id: "bazaar", label: "Bazaar & tape", tab: "market", hint: "Orders, depth chart" },
      { id: "caravans", label: "Caravans", tab: "logistics", hint: "Ship goods" },
    ],
  },
  {
    id: "realm",
    label: "Realm",
    items: [
      { id: "pacts", label: "Pacts & hires", tab: "contracts", hint: "Stubs today" },
      { id: "chronicle", label: "Chronicle", tab: "log", hint: "Log + save/load" },
      { id: "atlas", label: "Atlas", tab: "codex", hint: "What works / next" },
    ],
  },
];
