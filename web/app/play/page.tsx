"use client";

import { useEffect } from "react";

import FrontierGameShell from "../FrontierGameShell";
import { REALM_LAST_MODE_STORAGE_KEY } from "../labsConstants";

export default function PlayPage() {
  useEffect(() => {
    try {
      localStorage.setItem(REALM_LAST_MODE_STORAGE_KEY, "frontier");
    } catch {
      /* ignore */
    }
  }, []);

  return <FrontierGameShell mode="frontier" />;
}
