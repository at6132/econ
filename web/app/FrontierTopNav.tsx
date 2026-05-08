"use client";

import { FRONTIER_MENU, type TabId } from "./frontierMenu";

type Props = {
  active: TabId;
  onSelect: (t: TabId) => void;
};

export function FrontierTopNav({ active, onSelect }: Props) {
  return (
    <nav className="realm-top-nav" aria-label="Command screens">
      {FRONTIER_MENU.map((g) => (
        <div key={g.id} className="realm-top-nav__group">
          <span className="realm-top-nav__group-label">{g.label}</span>
          <div className="realm-top-nav__chips">
            {g.items.map((it) => {
              const on = active === it.tab;
              return (
                <button
                  key={it.id}
                  type="button"
                  className={`realm-top-nav__chip${on ? " realm-top-nav__chip--on" : ""}`}
                  onClick={() => onSelect(it.tab)}
                  title={it.hint ?? it.label}
                >
                  {it.label}
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );
}
