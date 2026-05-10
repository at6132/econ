"use client";

import type { ReactNode } from "react";

import { RealmToastProvider } from "./realmToast";

export function RealmClientRoot({ children }: { children: ReactNode }) {
  return <RealmToastProvider>{children}</RealmToastProvider>;
}
