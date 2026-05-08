export type MapFxKind =
  | "claim"
  | "survey"
  | "build"
  | "trade"
  | "produce"
  | "tick"
  | "ship"
  | "hire"
  | "contract";

export type MapFxEvent = {
  id: number;
  kind: MapFxKind;
  gx: number;
  gy: number;
  label?: string;
};
