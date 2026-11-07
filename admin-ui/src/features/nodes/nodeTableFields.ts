import type { NodeEditorField } from "./editorSchema";
import { getSemanticTypeFromSchema } from "./nodeFieldUtils";

export type NodeTableFieldKind =
  | "array"
  | "asset-array"
  | "array-object"
  | "asset"
  | "boolean"
  | "date"
  | "datetime"
  | "link"
  | "link-array"
  | "number"
  | "object"
  | "string";

export type NodeTableField = {
  enumValues: string[];
  inputKind: NodeEditorField["inputKind"];
  itemEnumValues: string[];
  itemKind: NodeEditorField["itemKind"];
  kind: NodeTableFieldKind;
  label: string;
  linkTargetEntities: string[];
  linkTargetModule: string | null;
  path: string[];
};

export function buildNodeTableFields(fields: NodeEditorField[], options: { includePermissions?: boolean } = {}) {
  return fields.flatMap((field) => collectNodeTableFields(field, [], options.includePermissions ?? true));
}

export function getNodeTableFieldPath(field: NodeTableField) {
  const path = field.path.join(".");
  return field.kind === "link" || field.kind === "link-array" ? `${path}.id` : path;
}

function collectNodeTableFields(field: NodeEditorField, labelPath: string[] = [], includePermissions: boolean): NodeTableField[] {
  if (field.semanticType === "SystemPerm" && !includePermissions) {
    return [];
  }
  const nextLabelPath = [...labelPath, field.label];
  const ownField = containsPassword(field) ? null : toNodeTableField(field, nextLabelPath.join(" / "));
  const nestedFields = field.inputKind === "object" || field.inputKind === "array-object"
    ? field.children.flatMap((child) => collectNodeTableFields(child, nextLabelPath, includePermissions))
    : [];

  return ownField === null ? nestedFields : [ownField, ...nestedFields];
}

function containsPassword(field: NodeEditorField) {
  return field.semanticType === "Password"
    || getSemanticTypeFromSchema(field.itemSchema) === "Password"
    || field.children.some(containsPassword);
}

function toNodeTableField(field: NodeEditorField, label: string): NodeTableField | null {
  if (field.semanticType === "SystemPerm" || field.semanticType === "SystemPermissionGroup") {
    return null;
  }
  const kind = getNodeTableFieldKind(field);
  if (kind === null) {
    return null;
  }

  return {
    enumValues: Array.isArray(field.fieldSchema.enum)
      ? field.fieldSchema.enum.filter((value): value is string => typeof value === "string")
      : [],
    inputKind: field.inputKind,
    itemEnumValues: Array.isArray(field.itemSchema?.enum)
      ? field.itemSchema.enum.filter((value): value is string => typeof value === "string")
      : [],
    itemKind: field.itemKind,
    kind,
    label,
    linkTargetEntities: field.linkTargetEntities,
    linkTargetModule: field.linkTargetModule,
    path: field.path,
  };
}

function getNodeTableFieldKind(field: NodeEditorField): NodeTableFieldKind | null {
  switch (field.inputKind) {
    case "password":
      return null;
    case "string":
    case "text":
      return "string";
    case "number":
    case "integer":
      return "number";
    case "boolean":
      return "boolean";
    case "date":
      return "date";
    case "datetime":
      return "datetime";
    case "link":
      return "link";
    case "link-array":
      return "link-array";
    case "array-primitive":
      return "array";
    case "array-object":
      return "array-object";
    case "array-asset":
      return "asset-array";
    case "object":
      return field.semanticType === "File" || field.semanticType === "Image" || field.semanticType === "Video"
        ? "asset"
        : "object";
    case "unknown":
      return null;
  }
}
