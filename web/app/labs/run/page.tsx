"use client";

import { useEffect } from "react";

import FrontierGameShell from "../../FrontierGameShell";
import { REALM_LAST_MODE_STORAGE_KEY } from "../../labsConstants";

export default function LabsRunPage() {
  useEffect(() => {
    try {
      localStorage.setItem(REALM_LAST_MODE_STORAGE_KEY, "lab");
    } catch {
      /* ignore */
    }
  }, []);

  return <FrontierGameShell mode="lab" />;
}
