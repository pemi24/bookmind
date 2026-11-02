import cytoscape from "cytoscape";
import { useEffect, useRef } from "react";
import type { Entity, Relation } from "../../types";
import { KIND_COLORS } from "./kindColors";

/** Relationship graph (fiction) / concept map (non-fiction). Node size = importance. */
export default function EntityGraph({
  entities,
  relations,
  selectedId,
  onSelect,
  dark,
}: {
  entities: Entity[];
  relations: Relation[];
  selectedId: number | null;
  onSelect: (id: number | null) => void;
  dark: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    if (!ref.current) return;
    const ids = new Set(entities.map((e) => e.id));
    // Only entities that take part in a relation, plus the most important ones, to keep it readable.
    const linked = new Set(relations.flatMap((r) => [r.source, r.target]));
    const nodes = entities.filter((e) => linked.has(e.id) || e.importance >= 4);
    const text = dark ? "#e7e5e4" : "#1c1917";
    const cy = cytoscape({
      container: ref.current,
      elements: [
        ...nodes.map((e) => ({
          data: { id: String(e.id), label: e.name, color: KIND_COLORS[e.kind] ?? "#64748b", size: 18 + e.importance * 9 },
        })),
        ...relations
          .filter((r) => ids.has(r.source) && ids.has(r.target))
          .map((r) => ({ data: { id: `r${r.id}`, source: String(r.source), target: String(r.target), label: r.relation } })),
      ],
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            label: "data(label)",
            width: "data(size)",
            height: "data(size)",
            color: text,
            "font-size": 11,
            "text-valign": "bottom",
            "text-margin-y": 4,
            "text-outline-color": dark ? "#0c0a09" : "#fafaf9",
            "text-outline-width": 2,
          },
        },
        {
          selector: "edge",
          style: {
            width: 1.5,
            "line-color": dark ? "#57534e" : "#d6d3d1",
            "target-arrow-color": dark ? "#57534e" : "#d6d3d1",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            label: "data(label)",
            "font-size": 9,
            color: dark ? "#a8a29e" : "#78716c",
            "text-rotation": "autorotate",
            "text-background-color": dark ? "#1c1917" : "#ffffff",
            "text-background-opacity": 0.85,
            "text-background-padding": "2px",
          },
        },
        { selector: "node:selected", style: { "border-width": 3, "border-color": "#f97316" } },
        { selector: ".faded", style: { opacity: 0.15 } },
      ],
      layout: { name: "cose", animate: false, nodeRepulsion: () => 9000, idealEdgeLength: () => 90, padding: 20 },
      wheelSensitivity: 0.3,
    });
    cy.on("tap", "node", (evt) => onSelectRef.current(Number(evt.target.id())));
    cy.on("tap", (evt) => {
      if (evt.target === cy) onSelectRef.current(null);
    });
    cyRef.current = cy;
    return () => cy.destroy();
  }, [entities, relations, dark]);

  // Highlight the selected entity's neighbourhood.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.elements().removeClass("faded").unselect();
    if (selectedId === null) return;
    const node = cy.getElementById(String(selectedId));
    if (node.empty()) return;
    node.select();
    cy.elements().difference(node.closedNeighborhood()).addClass("faded");
  }, [selectedId, entities, relations, dark]);

  return <div ref={ref} className="h-full w-full" role="img" aria-label="Relationship graph" />;
}
