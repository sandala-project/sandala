import type { AuthenticatedUser } from "../../lib/session";
import type { JsonSchema } from "../entities/api";

const SYSTEM_FIELD_NAMES = new Set([
  "id",
  "entity",
  "parent",
  "owner",
  "group",
  "perm",
  "depth",
  "ancestors",
  "deleted",
  "cdate",
  "mdate",
]);

type AccessMode = "all" | "admin" | "superuser" | "none";

type SchemaKind =
  | "string"
  | "password"
  | "text"
  | "number"
  | "integer"
  | "boolean"
  | "date"
  | "datetime"
  | "link"
  | "link-array"
  | "object"
  | "array-asset"
  | "array-primitive"
  | "array-object"
  | "unknown";

type UnwrappedSchema = {
  isNullable: boolean;
  schema: JsonSchema;
};

type BuiltFieldResult = {
  field: NodeEditorField;
  hasUnsafeNestedState: boolean;
};

export type NodeEditorField = {
  children: NodeEditorField[];
  description: string;
  fieldSchema: JsonSchema;
  inputKind: SchemaKind;
  isNullable: boolean;
  isRequired: boolean;
  itemKind: SchemaKind | null;
  itemSchema: JsonSchema | null;
  label: string;
  linkTargetEntities: string[];
  linkTargetModule: string | null;
  name: string;
  path: string[];
  semanticType: string;
  visible: boolean;
  writable: boolean;
};

export function buildNodeEditorFields(schema: JsonSchema, user: AuthenticatedUser | null): NodeEditorField[] {
  const requiredFields = Array.isArray(schema.required)
    ? schema.required.filter((item): item is string => typeof item === "string")
    : [];
  const properties = isRecord(schema.properties) ? schema.properties : {};

  return Object.entries(properties)
    .filter(([name]) => !SYSTEM_FIELD_NAMES.has(name))
    .flatMap(([name, fieldSchema]) => {
      const result = buildNodeEditorField(name, fieldSchema as JsonSchema, requiredFields, [name], user);
      return result.field.visible && result.field.inputKind !== "unknown" ? [result.field] : [];
    });
}

function buildNodeEditorField(
  name: string,
  rawSchema: JsonSchema,
  requiredFields: string[],
  path: string[],
  user: AuthenticatedUser | null,
): BuiltFieldResult {
  const { isNullable, schema } = unwrapNullable(rawSchema);
  const meta = getMeta(schema);
  const visibilityMode = asAccessMode(meta?.["visibility-mode"]);
  const writeMode = asAccessMode(meta?.["write-mode"]);
  const semanticType = getSemanticType(schema);
  const inputKind = getInputKind(schema);
  const linkTarget = getLinkTarget(schema);
  const visible = canAccess(visibilityMode, user);
  const itemSchema = getArrayItemSchema(schema);
  const itemKind = itemSchema === null ? null : getInputKind(itemSchema);
  const isAtomicStructuredField = isAtomicStructuredSemanticType(semanticType);
  const isAtomicStructuredArrayItem =
    itemSchema !== null && isAtomicStructuredSemanticType(getSemanticType(itemSchema));
  const properties = isAtomicStructuredField || isAtomicStructuredArrayItem ? {} : getObjectProperties(schema);
  const childRequiredFields = isAtomicStructuredField || isAtomicStructuredArrayItem ? [] : getRequiredFields(schema);

  const childResults = Object.entries(properties)
    .map(([childName, childSchema]) =>
      buildNodeEditorField(childName, childSchema as JsonSchema, childRequiredFields, [...path, childName], user),
    );
  const children = childResults
    .filter((result) => result.field.visible && result.field.inputKind !== "unknown")
    .map((result) => result.field);
  const hasUnsafeNestedState = childResults.some(
    (result) => !result.field.visible || result.field.inputKind === "unknown" || result.hasUnsafeNestedState,
  );
  const writable =
    canAccess(writeMode, user) &&
    (!isStructuredContainerKind(inputKind) || !hasUnsafeNestedState);

  const field: NodeEditorField = {
    children,
    description: typeof schema.description === "string" ? schema.description : "",
    fieldSchema: schema,
    inputKind,
    isNullable,
    isRequired: requiredFields.includes(name),
    itemKind,
    itemSchema,
    label: typeof schema.description === "string" && schema.description.trim().length > 0 ? schema.description : name,
    linkTargetEntities: linkTarget?.entities ?? [],
    linkTargetModule: linkTarget?.module ?? null,
    name,
    path,
    semanticType,
    visible,
    writable,
  };

  return {
    field,
    hasUnsafeNestedState,
  };
}

function unwrapNullable(schema: JsonSchema): UnwrappedSchema {
  if (!Array.isArray(schema.anyOf)) {
    return { isNullable: false, schema };
  }

  const variants = schema.anyOf;
  const hasNull = variants.some((item) => item.type === "null");
  const primary = variants.find((item) => item.type !== "null");

  if (!hasNull || primary === undefined) {
    return { isNullable: false, schema };
  }

  return { isNullable: true, schema: primary };
}

function getMeta(schema: JsonSchema) {
  const meta = schema["x-meta"];
  return isRecord(meta) ? meta : null;
}

function getSemanticType(schema: JsonSchema): string {
  const meta = getMeta(schema);
  const semanticType = meta?.["semantic-type"];

  if (typeof semanticType === "string" && semanticType.length > 0) {
    if (semanticType === "Array" && schema.type === "array" && schema.items !== undefined) {
      const itemSchema = unwrapNullable(schema.items).schema;
      return `Array<${getSemanticType(itemSchema)}>`;
    }
    return semanticType;
  }

  if (schema.type === "array" && schema.items !== undefined) {
    const itemSchema = unwrapNullable(schema.items).schema;
    return `Array<${getSemanticType(itemSchema)}>`;
  }

  if (schema.type === "object") {
    return "Object";
  }

  if (typeof schema.type === "string" && schema.type.length > 0) {
    return schema.type.charAt(0).toUpperCase() + schema.type.slice(1);
  }

  return "Unknown";
}

function getInputKind(schema: JsonSchema): SchemaKind {
  const semanticType = getSemanticType(schema);

  if (semanticType === "Link") {
    return "link";
  }

  if (semanticType === "LinkArray") {
    return "link-array";
  }

  switch (semanticType) {
    case "String":
      return "string";
    case "Password":
      return "password";
    case "Text":
    case "RichText":
      return "text";
    case "Number":
      return "number";
    case "Integer":
      return "integer";
    case "Boolean":
      return "boolean";
    case "Date":
      return "date";
    case "DateTime":
      return "datetime";
    case "Object":
    case "File":
    case "Image":
    case "Video":
      return "object";
    default:
      break;
  }

  if (schema.type === "array" && schema.items !== undefined) {
    const itemSchema = unwrapNullable(schema.items).schema;
    const itemKind = getInputKind(itemSchema);
    if (itemKind === "object" && isAtomicStructuredSemanticType(getSemanticType(itemSchema))) {
      return "array-asset";
    }
    if (itemKind === "object") {
      return "array-object";
    }
    if (itemKind !== "unknown") {
      return "array-primitive";
    }
  }

  return "unknown";
}

function getLinkTarget(schema: JsonSchema) {
  const meta = getMeta(schema);
  const link = meta?.link;

  if (!isRecord(link)) {
    return null;
  }

  const moduleName = typeof link.module === "string" && link.module.trim().length > 0
    ? link.module.trim()
    : null;
  const entities = Array.isArray(link.entities)
    ? link.entities.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : [];

  return {
    entities,
    module: moduleName,
  };
}

function getArrayItemSchema(schema: JsonSchema): JsonSchema | null {
  if (schema.type !== "array" || schema.items === undefined) {
    return null;
  }

  return unwrapNullable(schema.items).schema;
}

function getObjectProperties(schema: JsonSchema) {
  if (schema.type === "object") {
    return isRecord(schema.properties) ? schema.properties : {};
  }

  if (schema.type === "array" && schema.items !== undefined) {
    const itemSchema = unwrapNullable(schema.items).schema;
    if (itemSchema.type === "object") {
      return isRecord(itemSchema.properties) ? itemSchema.properties : {};
    }
  }

  return {};
}

function getRequiredFields(schema: JsonSchema): string[] {
  if (schema.type === "object") {
    return Array.isArray(schema.required)
      ? schema.required.filter((item): item is string => typeof item === "string")
      : [];
  }

  if (schema.type === "array" && schema.items !== undefined) {
    const itemSchema = unwrapNullable(schema.items).schema;
    return Array.isArray(itemSchema.required)
      ? itemSchema.required.filter((item): item is string => typeof item === "string")
      : [];
  }

  return [];
}

function canAccess(mode: AccessMode, user: AuthenticatedUser | null) {
  if (mode === "none") {
    return false;
  }
  if (mode === "all") {
    return true;
  }
  if (mode === "admin") {
    return user?.role === "superuser" || user?.role === "admin" || Boolean(user?.superuser || user?.admin);
  }
  return user?.role === "superuser" || Boolean(user?.superuser);
}

function isStructuredContainerKind(kind: SchemaKind) {
  return kind === "object" || kind === "array-asset" || kind === "array-object";
}

function isAtomicStructuredSemanticType(semanticType: string) {
  return semanticType === "File" || semanticType === "Image" || semanticType === "Video";
}

function asAccessMode(value: unknown): AccessMode {
  if (value === "admin" || value === "all" || value === "none" || value === "superuser") {
    return value;
  }
  return "none";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
