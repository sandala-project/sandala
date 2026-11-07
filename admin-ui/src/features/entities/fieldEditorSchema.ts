import type { JsonSchema } from "./api";
import type { SchemaFieldNode } from "./schema";
import type { TranslationKey } from "../../locales";

export const FIELD_SEMANTIC_TYPES = [
  "String",
  "Text",
  "RichText",
  "Number",
  "Integer",
  "Boolean",
  "Date",
  "DateTime",
  "File",
  "Image",
  "Video",
  "Array",
  "Object",
  "Link",
  "LinkArray",
  "Password",
] as const;

export const ARRAY_ITEM_TYPES = [
  "String",
  "Text",
  "RichText",
  "Number",
  "Integer",
  "Boolean",
  "Date",
  "DateTime",
  "File",
  "Image",
  "Video",
  "Object",
] as const;

export const ACCESS_MODES = ["all", "admin", "superuser", "none"] as const;

export type FieldSemanticType = (typeof FIELD_SEMANTIC_TYPES)[number];
// Password is accepted when reading an API-created Array<Password>, but the editor does not offer creating it.
export type ArrayItemType = (typeof ARRAY_ITEM_TYPES)[number] | "Password";
export type AccessMode = (typeof ACCESS_MODES)[number];
type Translator = (key: TranslationKey) => string;

export const FIELD_NAME_PATTERN = /^[A-Za-z0-9_-]+$/;
const ACCESS_MODE_RANK: Record<AccessMode, number> = {
  all: 0,
  admin: 1,
  superuser: 2,
  none: 3,
};

export type FieldEditorValues = {
  arrayItemType: ArrayItemType;
  description: string;
  enumValues: string[];
  exclusiveMaximum: string;
  exclusiveMinimum: string;
  isNullable: boolean;
  isRequired: boolean;
  linkEntities: string[];
  linkModule: string;
  maxItems: string;
  maxLength: string;
  maximum: string;
  minItems: string;
  minLength: string;
  minimum: string;
  multipleOf: string;
  name: string;
  pattern: string;
  semanticType: FieldSemanticType;
  visibilityMode: AccessMode;
  writeMode: AccessMode;
};

export type FieldEditorValidationContext = {
  currentName?: string;
  fieldSchema: JsonSchema;
  parentVisibilityMode?: AccessMode | null;
  parentWriteMode?: AccessMode | null;
  siblingNames: string[];
};

export function canRequireField(values: Pick<FieldEditorValues, "semanticType" | "arrayItemType">): boolean {
  return values.semanticType !== "Password"
    && (values.semanticType !== "Array" || values.arrayItemType !== "Password");
}

type ContainerHolder = {
  properties: Record<string, JsonSchema>;
  required: string[];
  writeBack: (properties: Record<string, JsonSchema>, required: string[]) => void;
};

export function getDefaultFieldEditorValues(currentModuleName = ""): FieldEditorValues {
  return {
    arrayItemType: "String",
    description: "",
    enumValues: [],
    exclusiveMaximum: "",
    exclusiveMinimum: "",
    isNullable: false,
    isRequired: false,
    linkEntities: [],
    linkModule: currentModuleName,
    maxItems: "",
    maxLength: "",
    maximum: "",
    minItems: "",
    minLength: "",
    minimum: "",
    multipleOf: "",
    name: "",
    pattern: "",
    semanticType: "String",
    visibilityMode: "all",
    writeMode: "all",
  };
}

export function getFieldEditorValuesFromNode(node: SchemaFieldNode): FieldEditorValues {
  const values = getDefaultFieldEditorValues();
  const source = unwrapNullable(node.fieldSchema).schema;
  const meta = getMeta(source);

  values.arrayItemType = getArrayItemType(source);
  values.description = typeof source.description === "string" ? source.description : "";
  values.enumValues = Array.isArray(source.enum) ? source.enum.filter((item): item is string => typeof item === "string") : [];
  values.exclusiveMaximum = toInputValue(source.exclusiveMaximum);
  values.exclusiveMinimum = toInputValue(source.exclusiveMinimum);
  values.isNullable = node.isNullable;
  values.isRequired = node.isRequired;
  values.linkEntities = node.linkTargetEntities;
  values.linkModule = node.linkTargetModule ?? "";
  values.maxItems = toInputValue(source.maxItems);
  values.maxLength = toInputValue(source.maxLength);
  values.maximum = toInputValue(source.maximum);
  values.minItems = toInputValue(source.minItems);
  values.minLength = toInputValue(source.minLength);
  values.minimum = toInputValue(source.minimum);
  values.multipleOf = toInputValue(source.multipleOf);
  values.name = node.name;
  values.pattern = typeof source.pattern === "string" ? source.pattern : "";
  values.semanticType = normalizeSemanticType(meta?.["semantic-type"]);
  values.visibilityMode = normalizeAccessMode(meta?.["visibility-mode"]);
  values.writeMode = normalizeAccessMode(meta?.["write-mode"]);

  return values;
}

export function buildFieldSchemaFromValues(values: FieldEditorValues, existingFieldSchema?: JsonSchema): JsonSchema {
  const xMetaBase: Record<string, unknown> = {
    "semantic-type": values.semanticType,
    "visibility-mode": values.visibilityMode,
    "write-mode": values.writeMode,
  };

  if (values.semanticType === "Link" || values.semanticType === "LinkArray") {
    xMetaBase.link = {
      module: values.linkModule.trim(),
      entities: values.linkEntities,
    };
  }

  const base = buildNonNullableFieldSchema(values, xMetaBase, existingFieldSchema);
  if (!values.isNullable) {
    return base;
  }

  return {
    anyOf: [
      base,
      { type: "null" },
    ],
  };
}

export function upsertFieldInSchema(args: {
  fieldSchema: JsonSchema;
  isRequired: boolean;
  parentPath: string[];
  previousPath?: string[];
  schema: JsonSchema;
  targetName: string;
}): JsonSchema {
  const draft = structuredClone(args.schema);
  const oldPath = args.previousPath;
  const oldParentPath = oldPath ? oldPath.slice(0, -1) : args.parentPath;
  const oldName = oldPath?.[oldPath.length - 1];

  if (oldName !== undefined && samePath(oldParentPath, args.parentPath) && oldName === args.targetName) {
    const holder = getContainerHolderAtPath(draft, args.parentPath);
    const nextProperties = { ...holder.properties, [oldName]: args.fieldSchema };
    const nextRequired = args.isRequired
      ? unique(holder.required)
      : holder.required.filter((name) => name !== oldName);

    holder.writeBack(nextProperties, nextRequired);
    return draft;
  }

  if (oldName !== undefined) {
    const oldHolder = getContainerHolderAtPath(draft, oldParentPath);
    delete oldHolder.properties[oldName];
    oldHolder.writeBack(
      oldHolder.properties,
      oldHolder.required.filter((item) => item !== oldName),
    );
  }

  const targetHolder = getContainerHolderAtPath(draft, args.parentPath);
  const nextProperties = { ...targetHolder.properties, [args.targetName]: args.fieldSchema };
  const nextRequired = args.isRequired
    ? unique([...targetHolder.required, args.targetName])
    : targetHolder.required.filter((item) => item !== args.targetName);

  targetHolder.writeBack(nextProperties, nextRequired);
  return draft;
}

function samePath(left: string[], right: string[]) {
  return left.length === right.length && left.every((segment, index) => segment === right[index]);
}

export function deleteFieldFromSchema(schema: JsonSchema, path: string[]): JsonSchema {
  const draft = structuredClone(schema);
  const parentPath = path.slice(0, -1);
  const fieldName = path[path.length - 1];

  if (fieldName === undefined) {
    return draft;
  }

  const holder = getContainerHolderAtPath(draft, parentPath);
  delete holder.properties[fieldName];
  holder.writeBack(
    holder.properties,
    holder.required.filter((item) => item !== fieldName),
  );

  return draft;
}

export function reorderFieldsInSchema(
  schema: JsonSchema,
  sourcePath: string[],
  targetPath: string[],
  position: "before" | "after",
): JsonSchema {
  const sourceParentPath = sourcePath.slice(0, -1);
  const targetParentPath = targetPath.slice(0, -1);
  const sourceName = sourcePath[sourcePath.length - 1];
  const targetName = targetPath[targetPath.length - 1];

  if (
    sourceName === undefined
    || targetName === undefined
    || sourceName === targetName
    || !samePath(sourceParentPath, targetParentPath)
  ) {
    return schema;
  }

  const draft = structuredClone(schema);
  const holder = getContainerHolderAtPath(draft, sourceParentPath);
  const entries = Object.entries(holder.properties);
  const sourceIndex = entries.findIndex(([name]) => name === sourceName);
  const targetIndex = entries.findIndex(([name]) => name === targetName);

  if (sourceIndex < 0 || targetIndex < 0) {
    return draft;
  }

  const [moved] = entries.splice(sourceIndex, 1);
  if (moved === undefined) {
    return draft;
  }

  const adjustedTargetIndex = sourceIndex < targetIndex ? targetIndex - 1 : targetIndex;
  const insertionIndex = position === "before" ? adjustedTargetIndex : adjustedTargetIndex + 1;
  entries.splice(insertionIndex, 0, moved);
  holder.writeBack(Object.fromEntries(entries), holder.required);
  return draft;
}

export function validateFieldName(value: string, t: Translator) {
  const normalizedValue = value.trim();
  if (normalizedValue.length === 0) {
    return t("entities.overlay.validation.name");
  }

  if (!FIELD_NAME_PATTERN.test(normalizedValue)) {
    return t("entities.overlay.validation.namePattern");
  }

  return true;
}

export function validateRegexPattern(value: string, t: Translator) {
  if (value.trim().length === 0) {
    return true;
  }

  try {
    new RegExp(value);
    return true;
  } catch {
    return t("entities.overlay.validation.invalidRegex");
  }
}

export function validateNumericInput(
  value: string,
  t: Translator,
  options: { integer?: boolean; nonNegative?: boolean; positive?: boolean } = {},
) {
  const normalizedValue = value.trim();
  if (normalizedValue.length === 0) {
    return true;
  }

  const parsedNumber = Number(normalizedValue);
  if (!Number.isFinite(parsedNumber)) {
    return t(options.integer ? "entities.overlay.validation.invalidInteger" : "entities.overlay.validation.invalidNumber");
  }

  if (options.integer && !Number.isInteger(parsedNumber)) {
    return t("entities.overlay.validation.invalidInteger");
  }

  if (options.nonNegative && parsedNumber < 0) {
    return t("entities.overlay.validation.nonNegative");
  }

  if (options.positive && parsedNumber <= 0) {
    return t("entities.overlay.validation.positive");
  }

  return true;
}

export function validateMutuallyExclusiveBounds(
  value: string,
  otherValue: string,
  t: Translator,
) {
  if (value.trim().length === 0 || otherValue.trim().length === 0) {
    return true;
  }

  return t("entities.overlay.validation.conflictingBounds");
}

export function validateFieldEditorSubmit(
  values: FieldEditorValues,
  context: FieldEditorValidationContext,
  t: Translator,
) {
  const errors: Partial<Record<keyof FieldEditorValues, string>> = {};
  const normalizedName = values.name.trim();

  const nameValidation = validateFieldName(values.name, t);
  if (nameValidation !== true) {
    errors.name = nameValidation;
  } else if (
    normalizedName !== context.currentName &&
    context.siblingNames.includes(normalizedName)
  ) {
    errors.name = t("entities.overlay.validation.duplicateName");
  }

  const minLength = parseOptionalNumber(values.minLength);
  const maxLength = parseOptionalNumber(values.maxLength);
  if (minLength !== null && maxLength !== null && minLength > maxLength) {
    errors.maxLength = t("entities.overlay.validation.rangeOrder");
  }

  const minimum = parseOptionalNumber(values.minimum);
  const maximum = parseOptionalNumber(values.maximum);
  if (minimum !== null && parseOptionalNumber(values.exclusiveMinimum) !== null) {
    errors.minimum = t("entities.overlay.validation.conflictingBounds");
    errors.exclusiveMinimum = t("entities.overlay.validation.conflictingBounds");
  }
  if (maximum !== null && parseOptionalNumber(values.exclusiveMaximum) !== null) {
    errors.maximum = t("entities.overlay.validation.conflictingBounds");
    errors.exclusiveMaximum = t("entities.overlay.validation.conflictingBounds");
  }
  if (minimum !== null && maximum !== null && minimum > maximum) {
    errors.maximum = t("entities.overlay.validation.rangeOrder");
  }

  const exclusiveMinimum = parseOptionalNumber(values.exclusiveMinimum);
  const exclusiveMaximum = parseOptionalNumber(values.exclusiveMaximum);
  if (
    exclusiveMinimum !== null &&
    exclusiveMaximum !== null &&
    exclusiveMinimum > exclusiveMaximum
  ) {
    errors.exclusiveMaximum = t("entities.overlay.validation.rangeOrder");
  }

  const minItems = parseOptionalNumber(values.minItems);
  const maxItems = parseOptionalNumber(values.maxItems);
  if (minItems !== null && maxItems !== null && minItems > maxItems) {
    errors.maxItems = t("entities.overlay.validation.rangeOrder");
  }

  const multipleOf = parseOptionalNumber(values.multipleOf);
  if (
    multipleOf !== null &&
    (values.semanticType === "Number" || values.semanticType === "Integer") &&
    multipleOf <= 0
  ) {
    errors.multipleOf = t("entities.overlay.validation.positive");
  }

  if (values.semanticType === "Link" || values.semanticType === "LinkArray") {
    if (values.linkModule.trim().length === 0) {
      errors.linkModule = t("entities.overlay.validation.linkModule");
    }

    if (values.linkEntities.length === 0) {
      errors.linkEntities = t("entities.overlay.validation.linkEntities");
    }
  }

  const accessErrors = validateFieldAccessTree(
    context.fieldSchema,
    {
      parentVisibilityMode: context.parentVisibilityMode,
      parentWriteMode: context.parentWriteMode,
    },
    t,
  );
  if (accessErrors.visibilityMode !== undefined) {
    errors.visibilityMode = accessErrors.visibilityMode;
  }
  if (accessErrors.writeMode !== undefined) {
    errors.writeMode = accessErrors.writeMode;
  }

  return errors;
}

export function validateFieldAccessTree(
  fieldSchema: JsonSchema,
  context: Pick<FieldEditorValidationContext, "parentVisibilityMode" | "parentWriteMode">,
  t: Translator,
) {
  const result = validateAccessTreeNode(
    fieldSchema,
    context.parentVisibilityMode ?? null,
    context.parentWriteMode ?? null,
  );

  return {
    visibilityMode: result.visibilityInvalid ? t("entities.overlay.validation.visibilityTooWide") : undefined,
    writeMode: result.writeInvalid ? t("entities.overlay.validation.writeTooWide") : undefined,
  };
}

function buildNonNullableFieldSchema(
  values: FieldEditorValues,
  xMetaBase: Record<string, unknown>,
  existingFieldSchema?: JsonSchema,
): JsonSchema {
  switch (values.semanticType) {
    case "String":
      return withOptionalDescription({
        type: "string",
        pattern: optionalString(values.pattern),
        enum: optionalArray(values.enumValues),
        minLength: optionalInteger(values.minLength),
        maxLength: optionalInteger(values.maxLength),
        "x-meta": xMetaBase,
      }, values.description);
    case "Password":
    case "Text":
    case "RichText":
      return withOptionalDescription({
        type: "string",
        pattern: optionalString(values.pattern),
        minLength: optionalInteger(values.minLength),
        maxLength: optionalInteger(values.maxLength),
        "x-meta": xMetaBase,
      }, values.description);
    case "Number":
      return withOptionalDescription({
        type: "number",
        minimum: optionalNumber(values.minimum),
        maximum: optionalNumber(values.maximum),
        exclusiveMinimum: optionalNumber(values.exclusiveMinimum),
        exclusiveMaximum: optionalNumber(values.exclusiveMaximum),
        multipleOf: optionalNumber(values.multipleOf),
        "x-meta": xMetaBase,
      }, values.description);
    case "Integer":
      return withOptionalDescription({
        type: "integer",
        minimum: optionalInteger(values.minimum),
        maximum: optionalInteger(values.maximum),
        exclusiveMinimum: optionalInteger(values.exclusiveMinimum),
        exclusiveMaximum: optionalInteger(values.exclusiveMaximum),
        multipleOf: optionalInteger(values.multipleOf),
        "x-meta": xMetaBase,
      }, values.description);
    case "Boolean":
      return withOptionalDescription({
        type: "boolean",
        "x-meta": xMetaBase,
      }, values.description);
    case "Date":
      return withOptionalDescription({
        type: "string",
        format: "date",
        "x-meta": xMetaBase,
      }, values.description);
    case "DateTime":
      return withOptionalDescription({
        type: "string",
        format: "date-time",
        "x-meta": xMetaBase,
      }, values.description);
    case "Object":
      return withOptionalDescription(buildObjectSchema(xMetaBase, existingFieldSchema), values.description);
    case "Array":
      return withOptionalDescription({
        type: "array",
        items: buildArrayItemsSchema(values.arrayItemType, xMetaBase, existingFieldSchema),
        minItems: optionalInteger(values.minItems),
        maxItems: optionalInteger(values.maxItems),
        "x-meta": xMetaBase,
      }, values.description);
    case "Link":
      return withOptionalDescription({
        type: "string",
        format: "uuid",
        "x-meta": xMetaBase,
      }, values.description);
    case "LinkArray":
      return withOptionalDescription({
        type: "array",
        items: {
          type: "string",
          format: "uuid",
        },
        minItems: optionalInteger(values.minItems),
        maxItems: optionalInteger(values.maxItems),
        "x-meta": xMetaBase,
      }, values.description);
    case "File":
      return withOptionalDescription(buildAssetDescriptorSchema("File", xMetaBase), values.description);
    case "Image":
      return withOptionalDescription(buildAssetDescriptorSchema("Image", xMetaBase), values.description);
    case "Video":
      return withOptionalDescription(buildAssetDescriptorSchema("Video", xMetaBase), values.description);
  }
}

function buildObjectSchema(xMetaBase: Record<string, unknown>, existingFieldSchema?: JsonSchema): JsonSchema {
  const source = existingFieldSchema ? unwrapNullable(existingFieldSchema).schema : null;
  if (source?.type === "object") {
    return {
      type: "object",
      additionalProperties: false,
      properties: isRecord(source.properties) ? structuredClone(source.properties) : {},
      required: Array.isArray(source.required) ? [...source.required] : undefined,
      "x-meta": xMetaBase,
    };
  }

  return {
    type: "object",
    additionalProperties: false,
    properties: {},
    "x-meta": xMetaBase,
  };
}

function buildArrayItemsSchema(
  arrayItemType: ArrayItemType,
  parentMeta: Record<string, unknown>,
  existingFieldSchema?: JsonSchema,
): JsonSchema {
  const source = existingFieldSchema ? unwrapNullable(existingFieldSchema).schema : null;
  const existingObjectItem =
    source?.type === "array" && source.items !== undefined
      ? unwrapNullable(source.items).schema
      : null;

  const itemMeta = {
    "semantic-type": arrayItemType,
    "visibility-mode": parentMeta["visibility-mode"],
    "write-mode": parentMeta["write-mode"],
  };

  if (arrayItemType === "Object") {
    if (existingObjectItem?.type === "object") {
      return {
        type: "object",
        additionalProperties: false,
        properties: isRecord(existingObjectItem.properties) ? structuredClone(existingObjectItem.properties) : {},
        required: Array.isArray(existingObjectItem.required) ? [...existingObjectItem.required] : undefined,
        "x-meta": itemMeta,
      };
    }

    return {
      type: "object",
      additionalProperties: false,
      properties: {},
      "x-meta": itemMeta,
    };
  }

  return buildPrimitiveArrayItemSchema(arrayItemType, itemMeta);
}

function buildPrimitiveArrayItemSchema(type: ArrayItemType, itemMeta: Record<string, unknown>): JsonSchema {
  switch (type) {
    case "String":
    case "Password":
      return { type: "string", "x-meta": itemMeta };
    case "Text":
    case "RichText":
      return { type: "string", "x-meta": itemMeta };
    case "Number":
      return { type: "number", "x-meta": itemMeta };
    case "Integer":
      return { type: "integer", "x-meta": itemMeta };
    case "Boolean":
      return { type: "boolean", "x-meta": itemMeta };
    case "Date":
      return { type: "string", format: "date", "x-meta": itemMeta };
    case "DateTime":
      return { type: "string", format: "date-time", "x-meta": itemMeta };
    case "File":
      return buildAssetDescriptorSchema("File", itemMeta);
    case "Image":
      return buildAssetDescriptorSchema("Image", itemMeta);
    case "Video":
      return buildAssetDescriptorSchema("Video", itemMeta);
    case "Object":
      return {
        type: "object",
        additionalProperties: false,
        properties: {},
        "x-meta": itemMeta,
      };
  }
}

function buildAssetDescriptorSchema(kind: "File" | "Image" | "Video", xMetaBase: Record<string, unknown>): JsonSchema {
  const commonProperties: Record<string, JsonSchema> = {
    url: { type: "string" },
    "mime-type": { type: "string" },
    size: { type: "integer" },
  };

  if (kind === "Image") {
    commonProperties.width = { type: "integer" };
    commonProperties.height = { type: "integer" };
  }

  return {
    type: "object",
    additionalProperties: false,
    properties: commonProperties,
    required: ["url"],
    "x-meta": xMetaBase,
  };
}

function getContainerHolderAtPath(schema: JsonSchema, path: string[]): ContainerHolder {
  let current: JsonSchema = schema;

  for (const segment of path) {
    const holder = getChildHolder(current);
    const next = holder.properties[segment];
    if (next === undefined) {
      throw new Error(`Unknown schema path segment: ${segment}`);
    }
    current = unwrapNullable(next).schema;
  }

  return getChildHolder(current);
}

function getChildHolder(schema: JsonSchema): ContainerHolder {
  if (schema.type === "object") {
    const properties = isRecord(schema.properties) ? (schema.properties as Record<string, JsonSchema>) : {};
    const required = Array.isArray(schema.required) ? schema.required.filter((item): item is string => typeof item === "string") : [];

    return {
      properties,
      required,
      writeBack(nextProperties, nextRequired) {
        schema.properties = nextProperties;
        schema.required = nextRequired.length > 0 ? nextRequired : undefined;
      },
    };
  }

  if (schema.type === "array" && schema.items !== undefined) {
    const itemsSchema = unwrapNullable(schema.items).schema;
    if (itemsSchema.type !== "object") {
      throw new Error("Array item schema is not an object");
    }

    const properties = isRecord(itemsSchema.properties) ? (itemsSchema.properties as Record<string, JsonSchema>) : {};
    const required = Array.isArray(itemsSchema.required)
      ? itemsSchema.required.filter((item): item is string => typeof item === "string")
      : [];

    return {
      properties,
      required,
      writeBack(nextProperties, nextRequired) {
        itemsSchema.properties = nextProperties;
        itemsSchema.required = nextRequired.length > 0 ? nextRequired : undefined;
      },
    };
  }

  throw new Error("Schema does not support nested children");
}

function unwrapNullable(schema: JsonSchema): { isNullable: boolean; schema: JsonSchema } {
  if (!Array.isArray(schema.anyOf)) {
    return { isNullable: false, schema };
  }

  const primary = schema.anyOf.find((item) => item.type !== "null");
  if (primary === undefined) {
    return { isNullable: false, schema };
  }

  return {
    isNullable: true,
    schema: primary,
  };
}

function getMeta(schema: JsonSchema) {
  const meta = schema["x-meta"];
  return isRecord(meta) ? meta : null;
}

function getArrayItemType(schema: JsonSchema): ArrayItemType {
  if (schema.type !== "array" || schema.items === undefined) {
    return "String";
  }

  const itemSchema = unwrapNullable(schema.items).schema;
  const meta = getMeta(itemSchema);
  const semanticType = typeof meta?.["semantic-type"] === "string" ? meta["semantic-type"] : null;

  switch (semanticType) {
    case "Number":
    case "Integer":
    case "Boolean":
    case "Date":
    case "DateTime":
    case "File":
    case "Image":
    case "Video":
    case "Object":
    case "String":
    case "Password":
    case "Text":
    case "RichText":
      return semanticType;
    default:
      return "String";
  }
}

function normalizeSemanticType(value: unknown): FieldSemanticType {
  return FIELD_SEMANTIC_TYPES.includes(value as FieldSemanticType) ? (value as FieldSemanticType) : "String";
}

function normalizeAccessMode(value: unknown): AccessMode {
  return ACCESS_MODES.includes(value as AccessMode) ? (value as AccessMode) : "all";
}

function withOptionalDescription(schema: JsonSchema, description: string): JsonSchema {
  return {
    ...schema,
    description: description.trim().length > 0 ? description.trim() : undefined,
  };
}

function optionalArray(value: string[]) {
  return value.length > 0 ? value : undefined;
}

function optionalInteger(value: string) {
  return value.trim().length > 0 ? Number.parseInt(value, 10) : undefined;
}

function optionalNumber(value: string) {
  return value.trim().length > 0 ? Number(value) : undefined;
}

function optionalString(value: string) {
  return value.trim().length > 0 ? value.trim() : undefined;
}

function parseOptionalNumber(value: string) {
  return value.trim().length > 0 ? Number(value) : null;
}

function toInputValue(value: unknown) {
  return typeof value === "number" || typeof value === "string" ? String(value) : "";
}

function unique(values: string[]) {
  return values.filter((value, index) => values.indexOf(value) === index);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function validateAccessTreeNode(
  rawSchema: JsonSchema,
  parentVisibilityMode: AccessMode | null,
  parentWriteMode: AccessMode | null,
): { visibilityInvalid: boolean; writeInvalid: boolean } {
  const schema = unwrapNullable(rawSchema).schema;
  const meta = getMeta(schema);
  const currentVisibilityMode = normalizeAccessMode(meta?.["visibility-mode"]);
  const currentWriteMode = normalizeAccessMode(meta?.["write-mode"]);

  let visibilityInvalid =
    parentVisibilityMode !== null &&
    ACCESS_MODE_RANK[currentVisibilityMode] < ACCESS_MODE_RANK[parentVisibilityMode];
  let writeInvalid =
    parentWriteMode !== null &&
    ACCESS_MODE_RANK[currentWriteMode] < ACCESS_MODE_RANK[parentWriteMode];

  for (const childSchema of getChildSchemas(schema)) {
    const childResult = validateAccessTreeNode(
      childSchema,
      currentVisibilityMode,
      currentWriteMode,
    );
    visibilityInvalid = visibilityInvalid || childResult.visibilityInvalid;
    writeInvalid = writeInvalid || childResult.writeInvalid;
  }

  return { visibilityInvalid, writeInvalid };
}

function getChildSchemas(schema: JsonSchema) {
  if (schema.type === "object") {
    const properties = isRecord(schema.properties) ? schema.properties : {};
    return Object.values(properties) as JsonSchema[];
  }

  if (schema.type === "array" && schema.items !== undefined) {
    const itemsSchema = unwrapNullable(schema.items).schema;
    if (itemsSchema.type === "object") {
      const properties = isRecord(itemsSchema.properties) ? itemsSchema.properties : {};
      return Object.values(properties) as JsonSchema[];
    }
  }

  return [];
}
