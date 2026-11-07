import type { TranslationKey } from "../../locales";
import type { JsonSchema } from "../entities/api";
import type { NodeEditorField } from "./editorSchema";
import {
  asFileDescriptor,
  asImageDescriptor,
  asVideoDescriptor,
  getSemanticTypeFromSchema,
} from "./nodeFieldUtils";

type PathSegment = string | number;
type ScalarInputKind = Exclude<
  NodeEditorField["inputKind"],
  "array-asset" | "array-object" | "array-primitive" | "link" | "link-array" | "object" | "unknown"
>;

export function validateNodeDraft(
  fields: NodeEditorField[],
  draft: Record<string, unknown>,
  t: (key: TranslationKey) => string,
) {
  const errors: Record<string, string> = {};

  for (const field of fields) {
    if (!field.writable) {
      continue;
    }
    validateFieldRecursively(field, getValueAtPath(draft, field.path), field.path, errors, t);
  }

  return errors;
}

export function validateSingleField(
  fields: NodeEditorField[],
  draft: Record<string, unknown>,
  path: PathSegment[],
  t: (key: TranslationKey) => string,
) {
  const set: Record<string, string> = {};
  const field = findFieldAtRuntimePath(fields, path);
  if (field === null || !field.writable) {
    return { clear: [], set };
  }

  if (path.some((segment) => typeof segment === "number")) {
    if (isScalarInputKind(field.inputKind)) {
      validateScalarValue({
        errors: set,
        kind: field.inputKind,
        pathKey: toPathKey(path),
        required: field.isRequired,
        schema: field.fieldSchema,
        t,
        value: getValueAtPath(draft, path),
      });
      return { clear: [toPathKey(path)], set };
    }

    if (field.inputKind === "array-primitive") {
      validateArrayPrimitiveItem(field, getValueAtPath(draft, path), path, set, t);
      return { clear: [toPathKey(path)], set };
    }

    if (field.inputKind === "array-asset") {
      validateAssetArrayItem(field, getValueAtPath(draft, path), path, set, t);
      return { clear: [toPathKey(path)], set };
    }

    return { clear: [toPathKey(path)], set };
  }

  const clear: string[] = [];
  collectPathKeys(field, path, clear);
  validateFieldRecursively(field, getValueAtPath(draft, path), path, set, t);

  return { clear, set };
}

export function validateFieldSubtree(
  fields: NodeEditorField[],
  draft: Record<string, unknown>,
  path: PathSegment[],
  t: (key: TranslationKey) => string,
) {
  const field = findFieldAtRuntimePath(fields, path);
  if (field === null || !field.writable) {
    return {};
  }

  const errors: Record<string, string> = {};
  validateFieldRecursively(field, getValueAtPath(draft, path), path, errors, t);
  return errors;
}

export function findFieldAtRuntimePath(fields: NodeEditorField[], path: PathSegment[]): NodeEditorField | null {
  if (path.length === 0 || typeof path[0] !== "string") {
    return null;
  }

  let currentField = fields.find((field) => field.name === path[0]) ?? null;
  let index = 1;

  while (currentField !== null && index < path.length) {
    const segment = path[index];
    if (typeof segment === "number") {
      index += 1;
      continue;
    }

    currentField = currentField.children.find((child) => child.name === segment) ?? null;
    index += 1;
  }

  return currentField;
}

function validateFieldRecursively(
  field: NodeEditorField,
  value: unknown,
  path: PathSegment[],
  errors: Record<string, string>,
  t: (key: TranslationKey) => string,
) {
  const pathKey = toPathKey(path);

  if (isScalarInputKind(field.inputKind)) {
    validateScalarValue({
      errors,
      kind: field.inputKind,
      pathKey,
      required: field.isRequired,
      schema: field.fieldSchema,
      t,
      value,
    });
    return;
  }

  if (field.inputKind === "array-primitive" || field.inputKind === "array-object" || field.inputKind === "array-asset") {
    if (value === undefined) {
      if (field.isRequired) {
        errors[pathKey] = t("pages.nodes.editor.validation.required");
      }
      return;
    }

    const items = Array.isArray(value) ? value : [];
    const minItems = typeof field.fieldSchema.minItems === "number" ? field.fieldSchema.minItems : null;
    const maxItems = typeof field.fieldSchema.maxItems === "number" ? field.fieldSchema.maxItems : null;

    if (minItems !== null && items.length < minItems) {
      errors[pathKey] = t("pages.nodes.editor.minItems");
    }
    if (maxItems !== null && items.length > maxItems) {
      errors[pathKey] = t("pages.nodes.editor.maxItems");
    }

    if (field.inputKind === "array-object") {
      items.forEach((item, index) => {
        field.children.forEach((child) => {
          validateFieldRecursively(child, getValueAtPath(item, [child.name]), [...path, index, child.name], errors, t);
        });
      });
      return;
    }

    if (field.inputKind === "array-asset") {
      items.forEach((item, index) => {
        validateAssetArrayItem(field, item, [...path, index], errors, t);
      });
      return;
    }

    items.forEach((item, index) => {
      validateArrayPrimitiveItem(field, item, [...path, index], errors, t);
    });
    return;
  }

  if (field.inputKind === "link") {
    validateLinkValue(field, value, pathKey, errors, t);
    return;
  }

  if (field.inputKind === "link-array") {
    validateLinkArrayValue(field, value, pathKey, errors, t);
    return;
  }

  if (field.inputKind === "object") {
    if (value === undefined || value === null) {
      if (field.isRequired) {
        errors[pathKey] = t("pages.nodes.editor.validation.required");
      }
      return;
    }

    field.children.forEach((child) => {
      validateFieldRecursively(child, getValueAtPath(value, [child.name]), [...path, child.name], errors, t);
    });
  }
}

function validateLinkValue(
  field: NodeEditorField,
  value: unknown,
  pathKey: string,
  errors: Record<string, string>,
  t: (key: TranslationKey) => string,
) {
  if (isMissingValue(value)) {
    if (field.isRequired) {
      errors[pathKey] = t("pages.nodes.editor.validation.required");
    }
    return;
  }

  const linkId = extractLinkId(value);
  if (linkId.length === 0) {
    errors[pathKey] = t("pages.nodes.editor.validation.required");
  }
}

function validateLinkArrayValue(
  field: NodeEditorField,
  value: unknown,
  pathKey: string,
  errors: Record<string, string>,
  t: (key: TranslationKey) => string,
) {
  if (value === undefined) {
    if (field.isRequired) {
      errors[pathKey] = t("pages.nodes.editor.validation.required");
    }
    return;
  }

  const items = Array.isArray(value) ? value : [];
  const minItems = typeof field.fieldSchema.minItems === "number" ? field.fieldSchema.minItems : null;
  const maxItems = typeof field.fieldSchema.maxItems === "number" ? field.fieldSchema.maxItems : null;

  if (minItems !== null && items.length < minItems) {
    errors[pathKey] = t("pages.nodes.editor.minItems");
    return;
  }

  if (maxItems !== null && items.length > maxItems) {
    errors[pathKey] = t("pages.nodes.editor.maxItems");
    return;
  }

  if (items.some((item) => extractLinkId(item).length === 0)) {
    errors[pathKey] = t("pages.nodes.editor.validation.required");
  }
}

function validateArrayPrimitiveItem(
  field: NodeEditorField,
  value: unknown,
  path: PathSegment[],
  errors: Record<string, string>,
  t: (key: TranslationKey) => string,
) {
  if (field.itemKind !== null && isScalarInputKind(field.itemKind)) {
    validateScalarValue({
      errors,
      kind: field.itemKind,
      pathKey: toPathKey(path),
      required: true,
      schema: field.itemSchema ?? {},
      t,
      value,
    });
  }
}

function validateAssetArrayItem(
  field: NodeEditorField,
  value: unknown,
  path: PathSegment[],
  errors: Record<string, string>,
  t: (key: TranslationKey) => string,
) {
  const itemSemanticType = getSemanticTypeFromSchema(field.itemSchema);
  const pathKey = toPathKey(path);

  if (value === undefined || value === null) {
    errors[pathKey] = t("pages.nodes.editor.validation.required");
    return;
  }

  if (itemSemanticType === "Image") {
    if (asImageDescriptor(value) === null) {
      errors[pathKey] = t("pages.nodes.editor.validation.required");
    }
    return;
  }

  if (itemSemanticType === "File") {
    if (asFileDescriptor(value) === null) {
      errors[pathKey] = t("pages.nodes.editor.validation.required");
    }
    return;
  }

  if (itemSemanticType === "Video" && asVideoDescriptor(value) === null) {
    errors[pathKey] = t("pages.nodes.editor.validation.required");
  }
}

function validateScalarValue(args: {
  errors: Record<string, string>;
  kind: ScalarInputKind;
  pathKey: string;
  required: boolean;
  schema: JsonSchema;
  t: (key: TranslationKey) => string;
  value: unknown;
}) {
  if (args.kind === "boolean") {
    if (args.required && args.value === undefined) {
      args.errors[args.pathKey] = args.t("pages.nodes.editor.validation.required");
    }
    return;
  }

  if (isMissingValue(args.value)) {
    if (args.required) {
      args.errors[args.pathKey] = args.t("pages.nodes.editor.validation.required");
    }
    return;
  }

  if (args.kind === "date") {
    if (!isValidDateString(args.value)) {
      args.errors[args.pathKey] = args.t("pages.nodes.editor.validation.invalidDate");
    }
    return;
  }

  if (args.kind === "datetime") {
    if (!isValidDateTimeString(args.value)) {
      args.errors[args.pathKey] = args.t("pages.nodes.editor.validation.invalidDateTime");
    }
    return;
  }

  if (args.kind === "password" || args.kind === "string" || args.kind === "text") {
    validateStringValue({
      errors: args.errors,
      pathKey: args.pathKey,
      schema: args.schema,
      t: args.t,
      value: args.value,
    });
    return;
  }

  validateNumericValue({
    errors: args.errors,
    kind: args.kind,
    pathKey: args.pathKey,
    schema: args.schema,
    t: args.t,
    value: args.value,
  });
}

function validateStringValue(args: {
  errors: Record<string, string>;
  pathKey: string;
  schema: JsonSchema;
  t: (key: TranslationKey) => string;
  value: unknown;
}) {
  const value = typeof args.value === "string" ? args.value : String(args.value);

  const minLength = typeof args.schema.minLength === "number" ? args.schema.minLength : null;
  if (minLength !== null && value.length < minLength) {
    args.errors[args.pathKey] = args.t("pages.nodes.editor.validation.minLength");
    return;
  }

  const maxLength = typeof args.schema.maxLength === "number" ? args.schema.maxLength : null;
  if (maxLength !== null && value.length > maxLength) {
    args.errors[args.pathKey] = args.t("pages.nodes.editor.validation.maxLength");
    return;
  }

  if (typeof args.schema.pattern === "string" && args.schema.pattern.length > 0) {
    try {
      const pattern = new RegExp(args.schema.pattern);
      if (!pattern.test(value)) {
        args.errors[args.pathKey] = args.t("pages.nodes.editor.validation.pattern");
        return;
      }
    } catch {
      return;
    }
  }

  if (Array.isArray(args.schema.enum)) {
    const allowed = args.schema.enum.filter((item): item is string => typeof item === "string");
    if (allowed.length > 0 && !allowed.includes(value)) {
      args.errors[args.pathKey] = args.t("pages.nodes.editor.validation.enum");
    }
  }
}

function validateNumericValue(args: {
  errors: Record<string, string>;
  kind: "integer" | "number";
  pathKey: string;
  schema: JsonSchema;
  t: (key: TranslationKey) => string;
  value: unknown;
}) {
  const numericValue = parseNumericValue(args.value, args.kind);
  if (numericValue === null) {
    args.errors[args.pathKey] = args.t(
      args.kind === "integer"
        ? "entities.overlay.validation.invalidInteger"
        : "entities.overlay.validation.invalidNumber",
    );
    return;
  }

  const minimum = typeof args.schema.minimum === "number" ? args.schema.minimum : null;
  if (minimum !== null && numericValue < minimum) {
    args.errors[args.pathKey] = args.t("pages.nodes.editor.validation.minimum");
    return;
  }

  const maximum = typeof args.schema.maximum === "number" ? args.schema.maximum : null;
  if (maximum !== null && numericValue > maximum) {
    args.errors[args.pathKey] = args.t("pages.nodes.editor.validation.maximum");
    return;
  }

  const exclusiveMinimum = typeof args.schema.exclusiveMinimum === "number" ? args.schema.exclusiveMinimum : null;
  if (exclusiveMinimum !== null && numericValue <= exclusiveMinimum) {
    args.errors[args.pathKey] = args.t("pages.nodes.editor.validation.exclusiveMinimum");
    return;
  }

  const exclusiveMaximum = typeof args.schema.exclusiveMaximum === "number" ? args.schema.exclusiveMaximum : null;
  if (exclusiveMaximum !== null && numericValue >= exclusiveMaximum) {
    args.errors[args.pathKey] = args.t("pages.nodes.editor.validation.exclusiveMaximum");
    return;
  }

  const multipleOf = typeof args.schema.multipleOf === "number" ? args.schema.multipleOf : null;
  if (multipleOf !== null && !isMultipleOf(numericValue, multipleOf)) {
    args.errors[args.pathKey] = args.t("pages.nodes.editor.validation.multipleOf");
  }
}

function parseNumericValue(value: unknown, kind: "integer" | "number") {
  if (typeof value === "number") {
    if (Number.isNaN(value) || (kind === "integer" && !Number.isInteger(value))) {
      return null;
    }
    return value;
  }

  const raw = String(value).trim();
  if (raw.length === 0) {
    return null;
  }

  const numericValue = Number(raw);
  if (Number.isNaN(numericValue) || (kind === "integer" && !Number.isInteger(numericValue))) {
    return null;
  }

  return numericValue;
}

function isMultipleOf(value: number, divisor: number) {
  if (divisor === 0) {
    return false;
  }

  const quotient = value / divisor;
  return Math.abs(quotient - Math.round(quotient)) < 1e-9;
}

function collectPathKeys(field: NodeEditorField, path: PathSegment[], bucket: string[]) {
  bucket.push(toPathKey(path));

  if (field.inputKind === "object" || field.inputKind === "array-object") {
    field.children.forEach((child) => {
      collectPathKeys(child, [...path, child.name], bucket);
    });
  }
}

function isScalarInputKind(kind: NodeEditorField["inputKind"] | NodeEditorField["itemKind"]): kind is ScalarInputKind {
  return kind === "boolean" || kind === "date" || kind === "datetime" || kind === "integer" || kind === "number" || kind === "password" || kind === "string" || kind === "text";
}

function isValidDateString(value: unknown) {
  if (typeof value !== "string") {
    return false;
  }

  const trimmed = value.trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    return false;
  }

  const [year = NaN, month = NaN, day = NaN] = trimmed.split("-").map(Number);
  const candidate = new Date(Date.UTC(year, month - 1, day));

  return (
    !Number.isNaN(candidate.getTime()) &&
    candidate.getUTCFullYear() === year &&
    candidate.getUTCMonth() === month - 1 &&
    candidate.getUTCDate() === day
  );
}

function isValidDateTimeString(value: unknown) {
  if (typeof value !== "string") {
    return false;
  }

  const trimmed = value.trim();
  const match = trimmed.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})(?::(\d{2})(?:\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/);

  if (!match) {
    return false;
  }

  const datePart = match[1] ?? "";
  const timePart = match[2] ?? "";
  const [hours = NaN, minutes = NaN] = timePart.split(":").map(Number);
  const seconds = Number(match[3] ?? "0");

  return (
    isValidDateString(datePart) &&
    Number.isInteger(hours) &&
    hours >= 0 &&
    hours <= 23 &&
    Number.isInteger(minutes) &&
    minutes >= 0 &&
    minutes <= 59 &&
    Number.isInteger(seconds) &&
    seconds >= 0 &&
    seconds <= 59
  );
}

function isMissingValue(value: unknown) {
  return value === undefined || value === null || (typeof value === "string" && value.trim().length === 0);
}

function extractLinkId(value: unknown) {
  if (typeof value === "string") {
    return value.trim();
  }

  if (isRecord(value) && typeof value.id === "string") {
    return value.id.trim();
  }

  return "";
}

function getValueAtPath(source: unknown, path: PathSegment[]): unknown {
  let current = source;

  for (const segment of path) {
    if (typeof segment === "number") {
      if (!Array.isArray(current)) {
        return undefined;
      }
      current = current[segment];
      continue;
    }

    if (!isRecord(current)) {
      return undefined;
    }
    current = current[segment];
  }

  return current;
}

function toPathKey(path: PathSegment[]) {
  return path.join(".");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
