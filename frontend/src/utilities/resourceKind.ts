import type { Equipment } from "./api";

export type ResourceKind = "equipment" | "lab-station" | "kit";

export function resourceKind(item: Pick<Equipment, "kind" | "category">): ResourceKind {
  if (item.kind === "lab-station" || item.kind === "kit" || item.kind === "equipment") {
    return item.kind;
  }
  if (item.category === "kit") {
    return "kit";
  }
  if (item.category === "lab-station" || item.category === "workspace") {
    return "lab-station";
  }
  return "equipment";
}

export function resourceKindLabel(kind: ResourceKind): string {
  if (kind === "lab-station") {
    return "Lab station";
  }
  if (kind === "kit") {
    return "Kit";
  }
  return "Equipment";
}
