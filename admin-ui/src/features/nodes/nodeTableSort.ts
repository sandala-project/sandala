import type { NodeEditorField } from "./editorSchema";
import { buildNodeTableFields, getNodeTableFieldPath, type NodeTableField } from "./nodeTableFields";

export type NodeTableSortDirection = "asc" | "desc";
export type NodeTableSortRule = {
  direction: NodeTableSortDirection;
  fieldPath: string;
  id: string;
};
export type NodeTableSortDefinition = { rules: NodeTableSortRule[] };
export type NodeTableSort =
  | { definition: NodeTableSortDefinition; mode: "visual" }
  | { mode: "json"; raw: string; sort: Record<string, NodeTableSortDirection> };

export function buildNodeTableSortFields(fields: NodeEditorField[]) {
  return buildNodeTableFields(fields);
}

export function createNodeTableSortRule(field: NodeTableField): NodeTableSortRule {
  return {
    direction: "asc",
    fieldPath: getNodeTableFieldPath(field),
    id: `sort-${crypto.randomUUID()}`,
  };
}

export function createEmptyNodeTableSortDefinition(): NodeTableSortDefinition {
  return { rules: [] };
}

export function compileNodeTableSort(definition: NodeTableSortDefinition) {
  return Object.fromEntries(definition.rules.map((rule) => [rule.fieldPath, rule.direction]));
}

export function compileAppliedNodeTableSort(sort: NodeTableSort | null) {
  return sort === null ? {} : sort.mode === "visual" ? compileNodeTableSort(sort.definition) : sort.sort;
}

export function hasNodeTableSort(sort: NodeTableSort | null) {
  return Object.keys(sort === null ? {} : sort.mode === "visual" ? compileNodeTableSort(sort.definition) : sort.sort).length > 0;
}

export function getAppliedNodeTableSortPaths(sort: NodeTableSort | null) {
  return Object.keys(sort === null ? {} : sort.mode === "visual" ? compileNodeTableSort(sort.definition) : sort.sort);
}

export function parseNodeTableSortDefinition(value: unknown, fields: NodeTableField[]): NodeTableSortDefinition | null {
  if (!isRecord(value)) {
    return null;
  }

  const fieldsByPath = new Map(fields.map((field) => [getNodeTableFieldPath(field), field]));
  const rules: NodeTableSortRule[] = [];
  for (const [fieldPath, direction] of Object.entries(value)) {
    const field = fieldsByPath.get(fieldPath);
    if (field === undefined || !isDirection(direction)) {
      return null;
    }
    rules.push({ ...createNodeTableSortRule(field), direction });
  }
  return { rules };
}

export function isNodeTableSortDirection(value: unknown): value is NodeTableSortDirection {
  return value === "asc" || value === "desc";
}

function isDirection(value: unknown): value is NodeTableSortDirection {
  return isNodeTableSortDirection(value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
