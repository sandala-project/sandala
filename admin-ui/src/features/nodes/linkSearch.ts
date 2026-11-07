import type { AuthenticatedUser } from "../../lib/session";
import type { JsonSchema } from "../entities/api";
import { buildNodeEditorFields, type NodeEditorField } from "./editorSchema";
import { DEFAULT_NODE_LABEL_FIELDS, getNodeLabelTemplatePaths } from "./presentation";

export function buildLinkSearchFilter(args: {
  entityName: string;
  excludeIds: string[];
  query: string;
  schema: JsonSchema;
  user: AuthenticatedUser | null;
}): Record<string, unknown> {
  const filter: Record<string, unknown> = { entity: args.entityName };
  const query = args.query.trim();

  if (query.length > 0) {
    const fields = buildNodeEditorFields(args.schema, args.user);
    const searchablePaths = new Set(collectSearchablePaths(fields));
    const candidates = [...new Set([
      ...getNodeLabelTemplatePaths(args.schema, "reference"),
      ...DEFAULT_NODE_LABEL_FIELDS,
      "id",
    ])];
    const paths = candidates.filter((path) => path === "id" || searchablePaths.has(path));
    const regex = `^${query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`;
    filter.or = paths.map((path) => ({ [path]: { regex } }));
  }

  if (args.excludeIds.length > 0) {
    filter.id = { nin: args.excludeIds };
  }

  return filter;
}

function collectSearchablePaths(fields: NodeEditorField[]): string[] {
  return fields.flatMap((field) => {
    if (field.inputKind === "string" || field.inputKind === "text") {
      return [field.path.join(".")];
    }
    return field.inputKind === "object" ? collectSearchablePaths(field.children) : [];
  });
}
