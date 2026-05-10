"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getFrontierPaletteItems, type PaletteItem, type TabId } from "./frontierMenu";

type Props = {
  open: boolean;
  onClose: () => void;
  activeTab: TabId;
  onPick: (tab: TabId) => void;
};

export function FrontierCommandPalette({ open, onClose, activeTab, onPick }: Props) {
  const items = useMemo(() => getFrontierPaletteItems(), []);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return items;
    return items.filter((it) => {
      const hay = `${it.group} ${it.label} ${it.hint ?? ""}`.toLowerCase();
      return hay.includes(s);
    });
  }, [items, q]);

  useEffect(() => {
    if (open) {
      setQ("");
      setSel(0);
      const id = window.requestAnimationFrame(() => inputRef.current?.focus());
      return () => cancelAnimationFrame(id);
    }
  }, [open]);

  useEffect(() => {
    if (filtered.length === 0) setSel(0);
    else setSel((i) => Math.min(i, filtered.length - 1));
  }, [filtered]);

  const commit = useCallback(
    (it: PaletteItem) => {
      onPick(it.tab);
      onClose();
    },
    [onClose, onPick],
  );

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (filtered.length < 1) return;
        setSel((i) => Math.min(filtered.length - 1, i + 1));
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        if (filtered.length < 1) return;
        setSel((i) => Math.max(0, i - 1));
      }
      if (e.key === "Enter" && filtered[sel]) {
        e.preventDefault();
        commit(filtered[sel]);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, filtered, sel, commit, onClose]);

  if (!open) return null;

  return (
    <div className="realm-palette-backdrop" role="presentation" onMouseDown={onClose}>
      <div
        className="realm-palette"
        role="dialog"
        aria-modal="true"
        aria-label="Go to screen"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="realm-palette__head">
          <input
            ref={inputRef}
            className="realm-input realm-palette__input"
            placeholder="Filter screens…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-autocomplete="list"
            aria-controls="realm-palette-list"
          />
          <span className="realm-palette__hint">Esc to close</span>
        </div>
        <ul id="realm-palette-list" className="realm-palette__list" role="listbox">
          {filtered.length === 0 ? (
            <li className="realm-palette__empty">No matches.</li>
          ) : (
            filtered.map((it, idx) => {
              const on = activeTab === it.tab;
              const hi = idx === sel;
              return (
                <li key={it.id} role="presentation">
                  <button
                    type="button"
                    role="option"
                    aria-selected={hi}
                    className={`realm-palette__row${hi ? " realm-palette__row--sel" : ""}`}
                    onMouseEnter={() => setSel(idx)}
                    onClick={() => commit(it)}
                  >
                    <span className="realm-palette__group">{it.group}</span>
                    <span className="realm-palette__label">
                      {it.label}
                      {on ? <span className="realm-palette__here"> · current</span> : null}
                    </span>
                    {it.hint ? <span className="realm-palette__detail">{it.hint}</span> : null}
                  </button>
                </li>
              );
            })
          )}
        </ul>
      </div>
    </div>
  );
}
