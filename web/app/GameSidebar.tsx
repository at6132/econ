"use client";

import { FRONTIER_MENU, type TabId } from "./frontierMenu";

type Props = {
  active: TabId;
  onSelect: (t: TabId) => void;
};

export function GameSidebar({ active, onSelect }: Props) {
  return (
    <aside className="realm-sidebar" aria-label="Game menu">
      <div className="realm-sidebar__brand">
        <span className="realm-sidebar__brand-mark">◇</span>
        <div>
          <div className="realm-sidebar__brand-title">Realm</div>
          <div className="realm-sidebar__brand-sub">Frontier</div>
        </div>
      </div>
      {FRONTIER_MENU.map((g) => (
        <div key={g.id} className="realm-sidebar__group">
          <div className="realm-sidebar__group-head">{g.label}</div>
          <ul className="realm-sidebar__list">
            {g.items.map((it) => {
              const on = active === it.tab;
              return (
                <li key={it.id}>
                  <button
                    type="button"
                    className={`realm-sidebar__item${on ? " realm-sidebar__item--on" : ""}`}
                    onClick={() => onSelect(it.tab)}
                  >
                    <span className="realm-sidebar__item-label">{it.label}</span>
                    {it.hint ? <span className="realm-sidebar__item-hint">{it.hint}</span> : null}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </aside>
  );
}
