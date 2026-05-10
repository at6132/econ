/**
 * Production builds hide internal / dev-only UI. Enable full tools with `next dev`
 * or set `NEXT_PUBLIC_REALM_INTERNAL_TOOLS=1` on the build.
 */
export const SHOW_INTERNAL_ATLAS_AND_DEV_CONTRACTS =
  process.env.NEXT_PUBLIC_REALM_INTERNAL_TOOLS === "1" || process.env.NODE_ENV !== "production";
