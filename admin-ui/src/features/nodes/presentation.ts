import type { JsonSchema } from "../entities/api";
import type { NodeDocument } from "./api";

export const DEFAULT_NODE_LABEL_FIELDS = ["name", "title", "caption", "code", "description"] as const;
const LABEL_TEMPLATE_FIELD_PATTERN = /\{\{\s*([A-Za-z0-9_\-\u0080-\u{10FFFF}]+(?:\.[A-Za-z0-9_\-\u0080-\u{10FFFF}]+)*)\s*\}\}/gu;

export type NodeEntityPresentation = {
  canHaveChildren: boolean;
  labelFieldCandidates: string[];
  referenceLabelTemplate: string | null;
  treeLabelTemplate: string | null;
};

export type NodeEntityPresentationRegistry = Record<string, NodeEntityPresentation>;

export function buildNodeEntityPresentation(schema: JsonSchema): NodeEntityPresentation {
  const properties = isRecord(schema.properties) ? schema.properties : {};
  const childrenEntities = getChildrenEntities(schema);

  return {
    canHaveChildren: childrenEntities.length > 0,
    labelFieldCandidates: DEFAULT_NODE_LABEL_FIELDS.filter((fieldName) => fieldName in properties),
    referenceLabelTemplate: getLabelTemplate(schema, "reference"),
    treeLabelTemplate: getLabelTemplate(schema, "tree"),
  };
}

export function resolveNodeDisplayLabel(
  node: NodeDocument,
  presentation?: NodeEntityPresentation | null,
  purpose: "reference" | "tree" = "reference",
): string {
  const template = purpose === "tree"
    ? presentation?.treeLabelTemplate
    : presentation?.referenceLabelTemplate;
  if (template !== null && template !== undefined) {
    return renderLabelTemplate(template, node);
  }

  const candidateFields = presentation?.labelFieldCandidates.length
    ? presentation.labelFieldCandidates
    : DEFAULT_NODE_LABEL_FIELDS;

  for (const fieldName of candidateFields) {
    const value = node[fieldName];
    if (typeof value === "string" && value.trim().length > 0) {
      return value.trim();
    }
  }

  if (typeof node.id === "string" && node.id.trim().length > 0) {
    return node.id;
  }

  return "";
}

export function getNodeLabelTemplatePaths(schema: JsonSchema, purpose: "reference" | "tree"): string[] {
  const template = getLabelTemplate(schema, purpose);
  return [...new Set(
    [...(template ?? "").matchAll(LABEL_TEMPLATE_FIELD_PATTERN)]
      .flatMap((match) => match[1] === undefined ? [] : [match[1]]),
  )];
}

function getLabelTemplate(schema: JsonSchema, purpose: "reference" | "tree") {
  const ui = isRecord(schema["x-ui"]) ? schema["x-ui"] : null;
  const labels = isRecord(ui?.labels) ? ui.labels : null;
  const value = labels?.[purpose];
  return typeof value === "string" ? value : null;
}

function renderLabelTemplate(template: string, node: NodeDocument) {
  return template.replace(LABEL_TEMPLATE_FIELD_PATTERN, (_match, path: string) => {
    const value = getObjectPathValue(node, path.split("."));
    return typeof value === "string" || typeof value === "number" || typeof value === "boolean"
      ? String(value)
      : "";
  });
}

function getObjectPathValue(value: unknown, path: string[]): unknown {
  let current: unknown = value;
  for (const segment of path) {
    if (!isRecord(current) || Array.isArray(current)) {
      return undefined;
    }
    current = current[segment];
  }
  return current;
}

function getChildrenEntities(schema: JsonSchema): string[] {
  const meta = isRecord(schema["x-meta"]) ? schema["x-meta"] : null;
  const children = meta !== null && isRecord(meta.children) ? meta.children : null;
  const entities = children !== null && Array.isArray(children.entities) ? children.entities : [];

  return entities.filter((item): item is string => typeof item === "string");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
