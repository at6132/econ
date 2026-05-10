"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

export type ToastKind = "ok" | "warn" | "err" | "info";

type Toast = { id: number; message: string; kind: ToastKind };

type ToastContextValue = { pushToast: (t: { message: string; kind?: ToastKind }) => void };

const RealmToastContext = createContext<ToastContextValue | null>(null);

const MAX_VISIBLE = 5;
const AUTO_DISMISS_MS = 4200;

export function RealmToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seq = useRef(0);
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: number) => {
    const t = timers.current.get(id);
    if (t) clearTimeout(t);
    timers.current.delete(id);
    setToasts((xs) => xs.filter((x) => x.id !== id));
  }, []);

  useEffect(() => {
    const map = timers.current;
    return () => {
      map.forEach((t) => clearTimeout(t));
      map.clear();
    };
  }, []);

  const pushToast = useCallback(
    ({ message, kind = "info" }: { message: string; kind?: ToastKind }) => {
      const id = ++seq.current;
      setToasts((xs) => [...xs.slice(-(MAX_VISIBLE - 1)), { id, message, kind }]);
      const tm = setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
      timers.current.set(id, tm);
    },
    [dismiss],
  );

  const value = useMemo(() => ({ pushToast }), [pushToast]);

  return (
    <RealmToastContext.Provider value={value}>
      {children}
      <div className="realm-toast-stack" aria-live="polite" aria-relevant="additions text">
        {toasts.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`realm-toast realm-toast--${t.kind}`}
            onClick={() => dismiss(t.id)}
          >
            <span className="realm-toast__msg">{t.message}</span>
            <span className="realm-toast__dismiss" aria-hidden>
              ×
            </span>
          </button>
        ))}
      </div>
    </RealmToastContext.Provider>
  );
}

export function useRealmToast(): ToastContextValue {
  const c = useContext(RealmToastContext);
  if (!c) throw new Error("useRealmToast must be used within RealmToastProvider");
  return c;
}
