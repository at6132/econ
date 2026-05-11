"use client";

import { motion, useReducedMotion } from "framer-motion";

import { getFrontierMenu, type TabId } from "./frontierMenu";

type Props = {
  active: TabId;
  onSelect: (t: TabId) => void;
};

export function FrontierTopNav({ active, onSelect }: Props) {
  const menu = getFrontierMenu();
  const reduceMotion = useReducedMotion();
  let chipStagger = 0;
  return (
    <nav className="realm-top-nav" aria-label="Command screens">
      {menu.map((g) => (
        <div key={g.id} className="realm-top-nav__group">
          <span className="realm-top-nav__group-label">{g.label}</span>
          <div className="realm-top-nav__chips">
            {g.items.map((it) => {
              const on = active === it.tab;
              const delay = chipStagger * 0.025;
              chipStagger += 1;
              return (
                <motion.button
                  key={it.id}
                  type="button"
                  className={`realm-top-nav__chip${on ? " realm-top-nav__chip--on" : ""}`}
                  onClick={() => onSelect(it.tab)}
                  title={it.hint ?? it.label}
                  initial={reduceMotion ? false : { opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={
                    reduceMotion ? { duration: 0 } : { delay, duration: 0.2, ease: [0.22, 1, 0.36, 1] }
                  }
                  whileHover={reduceMotion ? undefined : { y: -1 }}
                  whileTap={reduceMotion ? undefined : { scale: 0.98 }}
                >
                  {it.label}
                </motion.button>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );
}
