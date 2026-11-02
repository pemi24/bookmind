import type { EntityKind } from "../../types";

/** Colour per entity kind (graph nodes, glossary dots, legend). Kept apart from EntityGraph so the
 *  graph library is only downloaded when the graph is shown. */
export const KIND_COLORS: Record<EntityKind, string> = {
  character: "#3b6ef6",
  place: "#10b981",
  organization: "#f59e0b",
  term: "#8b5cf6",
  concept: "#ec4899",
  theme: "#64748b",
};
