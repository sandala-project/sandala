import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, localizeApiFieldError, type FieldError } from "../../lib/errors";
import { normalizeUtcDateTimeValue } from "../../lib/dateTime";
import type { TranslationKey } from "../../locales";
import type { NodeDocument } from "./api";
import type { NodeEditorField } from "./editorSchema";
import { isAtomicAssetSemanticType } from "./nodeFieldUtils";
import {
  findFieldAtRuntimePath,
  validateFieldSubtree,
  validateNodeDraft,
  validateSingleField,
} from "./nodeValidation";

export type NodeDraft = Record<string, unknown>;
export type PathSegment = string | number;

export function useNodeDraft(args: {
  fields: NodeEditorField[];
  node: NodeDocument;
  t: (key: TranslationKey) => string;
}) {
  const { fields, node, t } = args;
  const [draft, setDraft] = useState<NodeDraft>(() => deepCloneObject(node));
  const draftRef = useRef<NodeDraft>(draft);
  const customFieldErrorsRef = useRef<Record<string, string>>({});
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitApiError, setSubmitApiError] = useState<ApiError | null>(null);
  const [isDirty, setIsDirty] = useState(false);

  useEffect(() => {
    const nextDraft = deepCloneObject(node);
    draftRef.current = nextDraft;
    customFieldErrorsRef.current = {};
    setDraft(nextDraft);
    setFieldErrors({});
    setSubmitError(null);
    setSubmitApiError(null);
    setIsDirty(false);
  }, [node]);

  const handleBlur = useCallback((path: PathSegment[]) => {
    setFieldErrors((current) => {
      const nextErrors = validateSingleField(fields, draftRef.current, path, t);
      return applyFieldErrorDelta(current, nextErrors);
    });
  }, [fields, t]);

  const handleChange = useCallback((path: PathSegment[], value: unknown) => {
    setDraft((current) => {
      const nextDraft = setValueAtPath(current, path, value);
      draftRef.current = nextDraft;
      return nextDraft;
    });
    setFieldErrors((current) => replaceErrorsUnderPath(current, path, {}));
    setSubmitError(null);
    setSubmitApiError(null);
    setIsDirty(true);
  }, []);

  const handleChangeAndValidate = useCallback((path: PathSegment[], value: unknown) => {
    setDraft((current) => {
      const nextDraft = setValueAtPath(current, path, value);
      draftRef.current = nextDraft;
      setFieldErrors((fieldCurrent) => {
        const nextErrors = validateSingleField(fields, nextDraft, path, t);
        return applyFieldErrorDelta(fieldCurrent, nextErrors);
      });
      return nextDraft;
    });
    setSubmitError(null);
    setSubmitApiError(null);
    setIsDirty(true);
  }, [fields, t]);

  const handleStructureChange = useCallback((path: PathSegment[], value: unknown) => {
    setDraft((current) => {
      const nextDraft = setValueAtPath(current, path, value);
      draftRef.current = nextDraft;
      const nextErrors = validateFieldSubtree(fields, nextDraft, path, t);

      setFieldErrors((fieldCurrent) => replaceErrorsUnderPath(fieldCurrent, path, nextErrors));
      return nextDraft;
    });
    setSubmitError(null);
    setSubmitApiError(null);
    setIsDirty(true);
  }, [fields, t]);

  const validateForSubmit = useCallback(() => {
    const nextErrors = {
      ...validateNodeDraft(fields, draftRef.current, t),
      ...customFieldErrorsRef.current,
    };
    setFieldErrors(nextErrors);
    return nextErrors;
  }, [fields, t]);

  const replaceWithNode = useCallback((nextNode: NodeDocument) => {
    const nextDraft = deepCloneObject(nextNode);
    draftRef.current = nextDraft;
    customFieldErrorsRef.current = {};
    setDraft(nextDraft);
    setFieldErrors({});
    setSubmitError(null);
    setSubmitApiError(null);
    setIsDirty(false);
  }, []);

  const mergeValues = useCallback((values: Record<string, unknown>) => {
    setDraft((current) => {
      const nextDraft = Object.entries(values).reduce(
        (result, [key, value]) => setValueAtPath(result, [key], value),
        current,
      );
      draftRef.current = nextDraft;
      return nextDraft;
    });
    setSubmitError(null);
    setSubmitApiError(null);
  }, []);

  const mergeLinkedNode = useCallback((nextNode: NodeDocument) => {
    setDraft((current) => {
      const nextDraft = replaceNodeReferences(current, nextNode);
      if (nextDraft === current) {
        return current;
      }
      draftRef.current = nextDraft as NodeDraft;
      return nextDraft as NodeDraft;
    });
    setSubmitError(null);
    setSubmitApiError(null);
  }, []);

  const setCustomFieldError = useCallback((path: PathSegment[], message: string | null) => {
    const key = toPathKey(path);
    if (message === null) {
      delete customFieldErrorsRef.current[key];
    } else {
      customFieldErrorsRef.current[key] = message;
    }
  }, []);

  return {
    draft,
    fieldErrors,
    isDirty,
    replaceWithNode,
    setFieldErrors,
    setCustomFieldError,
    setIsDirty,
    setSubmitError,
    setSubmitApiError,
    submitApiError,
    submitError,
    validateForSubmit,
    handleBlur,
    handleChange,
    handleChangeAndValidate,
    handleStructureChange,
    mergeValues,
    mergeLinkedNode,
  };
}

export function buildPatchPayload(args: {
  current: NodeDocument;
  draft: NodeDraft;
  fields: NodeEditorField[];
}) {
  const payload: Record<string, unknown> = {};

  for (const field of args.fields) {
    if (!field.writable) {
      continue;
    }

    const currentValue = normalizeNodeFieldValue(field, getValueAtPath(args.current, field.path));
    const draftValue = normalizeNodeFieldValue(field, getValueAtPath(args.draft, field.path));

    if (!areEqual(currentValue, draftValue)) {
      payload[field.name] = draftValue;
    }
  }

  return payload;
}

export function mapApiFieldErrors(
  error: { fieldErrors: Array<{ keyword: string; location: unknown[]; message: string }> },
  fields: NodeEditorField[],
  t: (key: TranslationKey) => string,
) {
  const nextErrors: Record<string, string> = {};

  for (const fieldError of error.fieldErrors) {
    if (fieldError.location.length === 0) {
      continue;
    }

    const path = fieldError.location.filter((segment): segment is string | number => typeof segment === "string" || typeof segment === "number");
    const pathKey = toPathKey(path);
    const normalizedFieldError: FieldError = { ...fieldError, location: path };

    if (path[0] === "owner" || path[0] === "group" || path[0] === "perm") {
      nextErrors[pathKey] = localizeApiFieldError(normalizedFieldError, t);
      continue;
    }

    const field = findFieldAtRuntimePath(fields, path);
    if (field !== null) {
      nextErrors[pathKey] = localizeApiFieldError(normalizedFieldError, t);
      continue;
    }

    for (let length = path.length - 1; length > 0; length -= 1) {
      const parentPath = path.slice(0, length);
      if (findFieldAtRuntimePath(fields, parentPath) !== null) {
        nextErrors[toPathKey(parentPath)] = localizeApiFieldError(normalizedFieldError, t);
        break;
      }
    }
  }

  return nextErrors;
}

export function normalizeNodeFieldValue(field: NodeEditorField, value: unknown): unknown {
  if (value === undefined) {
    return undefined;
  }

  if (value === null) {
    return null;
  }

  if (field.inputKind === "number" || field.inputKind === "integer") {
    if (typeof value === "number") {
      return value;
    }
    const raw = String(value).trim();
    if (raw.length === 0) {
      return "";
    }
    const numericValue = Number(raw);
    return Number.isNaN(numericValue) ? value : numericValue;
  }

  if (field.inputKind === "boolean") {
    return Boolean(value);
  }

  if (field.inputKind === "datetime") {
    return normalizeUtcDateTimeValue(value);
  }

  if (field.inputKind === "link") {
    return normalizeLinkValue(value);
  }

  if (field.inputKind === "link-array") {
    return normalizeLinkArrayValue(value);
  }

  if (field.inputKind === "object") {
    if (isAtomicAssetSemanticType(field.semanticType)) {
      return value;
    }

    if (!isRecord(value)) {
      return value;
    }
    const next: Record<string, unknown> = {};
    field.children.forEach((child) => {
      next[child.name] = normalizeNodeFieldValue(child, getValueAtPath(value, [child.name]));
    });
    return next;
  }

  if (field.inputKind === "array-primitive") {
    if (!Array.isArray(value)) {
      return value;
    }
    return value.map((item) => normalizePrimitiveItem(field, item));
  }

  if (field.inputKind === "array-object") {
    if (!Array.isArray(value)) {
      return value;
    }
    return value.map((item) => {
      const next: Record<string, unknown> = {};
      field.children.forEach((child) => {
        next[child.name] = normalizeNodeFieldValue(child, getValueAtPath(item, [child.name]));
      });
      return next;
    });
  }

  if (field.inputKind === "array-asset") {
    if (!Array.isArray(value)) {
      return value;
    }
    return value;
  }

  return value;
}

function normalizePrimitiveItem(field: NodeEditorField, value: unknown) {
  if (field.itemKind === "number" || field.itemKind === "integer") {
    if (typeof value === "number") {
      return value;
    }
    const raw = String(value).trim();
    if (raw.length === 0) {
      return "";
    }
    const numericValue = Number(raw);
    return Number.isNaN(numericValue) ? value : numericValue;
  }

  if (field.itemKind === "boolean") {
    return Boolean(value);
  }

  return value;
}

function normalizeLinkValue(value: unknown) {
  if (typeof value === "string") {
    return value.trim();
  }

  if (isRecord(value) && typeof value.id === "string") {
    return value.id.trim();
  }

  return value === null ? null : "";
}

function normalizeLinkArrayValue(value: unknown) {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((item) => normalizeLinkValue(item))
    .filter((item): item is string => typeof item === "string" && item.length > 0);
}

export function sanitizePermValue(value: unknown) {
  return {
    owner: {
      p: Boolean(getValueAtPath(value, ["owner", "p"])),
      r: Boolean(getValueAtPath(value, ["owner", "r"])),
      w: Boolean(getValueAtPath(value, ["owner", "w"])),
    },
    group: {
      p: Boolean(getValueAtPath(value, ["group", "p"])),
      r: Boolean(getValueAtPath(value, ["group", "r"])),
      w: Boolean(getValueAtPath(value, ["group", "w"])),
    },
    others: {
      p: Boolean(getValueAtPath(value, ["others", "p"])),
      r: Boolean(getValueAtPath(value, ["others", "r"])),
      w: Boolean(getValueAtPath(value, ["others", "w"])),
    },
  };
}


function setValueAtPath(root: NodeDraft, path: PathSegment[], value: unknown): NodeDraft {
  const next = deepCloneObject(root);

  if (path.length === 0) {
    return next;
  }

  let current: unknown = next;

  for (let index = 0; index < path.length - 1; index += 1) {
    const segment = path[index];
    const nextSegment = path[index + 1];
    if (segment === undefined) {
      return next;
    }

    if (typeof segment === "number") {
      if (!Array.isArray(current)) {
        return next;
      }
      const currentValue = current[segment];
      if (currentValue === undefined || currentValue === null || typeof currentValue !== "object") {
        current[segment] = typeof nextSegment === "number" ? [] : {};
      } else {
        current[segment] = deepCloneValue(currentValue);
      }
      current = current[segment];
      continue;
    }

    if (!isRecord(current)) {
      return next;
    }

    const currentValue = current[segment];
    if (currentValue === undefined || currentValue === null || typeof currentValue !== "object") {
      current[segment] = typeof nextSegment === "number" ? [] : {};
    } else {
      current[segment] = deepCloneValue(currentValue);
    }
    current = current[segment];
  }

  const finalSegment = path[path.length - 1];
  if (finalSegment === undefined) {
    return next;
  }

  if (typeof finalSegment === "number") {
    if (!Array.isArray(current)) {
      return next;
    }
    current[finalSegment] = value;
    return next;
  }

  if (!isRecord(current)) {
    return next;
  }
  current[finalSegment] = value;
  return next;
}

export function getValueAtPath(source: unknown, path: PathSegment[]): unknown {
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

function clearErrorKeys(current: Record<string, string>, keys: string[]) {
  const next: Record<string, string> = {};

  Object.entries(current).forEach(([key, value]) => {
    if (!keys.includes(key)) {
      next[key] = value;
    }
  });

  return next;
}

function applyFieldErrorDelta(
  current: Record<string, string>,
  delta: { clear: string[]; set: Record<string, string> },
) {
  return {
    ...clearErrorKeys(current, delta.clear),
    ...delta.set,
  };
}

function replaceErrorsUnderPath(
  current: Record<string, string>,
  path: PathSegment[],
  nextErrors: Record<string, string>,
) {
  const prefix = toPathKey(path);
  const remaining = Object.fromEntries(
    Object.entries(current).filter(([key]) => key !== prefix && !key.startsWith(`${prefix}.`)),
  );

  return {
    ...remaining,
    ...nextErrors,
  };
}

function toPathKey(path: PathSegment[]) {
  return path.join(".");
}

function deepCloneObject(value: unknown): Record<string, unknown> {
  return (deepCloneValue(value) as Record<string, unknown>) ?? {};
}

function deepCloneValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => deepCloneValue(item));
  }

  if (isRecord(value)) {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, deepCloneValue(item)]),
    );
  }

  return value;
}

export function replaceNodeReferences(value: unknown, nextNode: NodeDocument): unknown {
  if (Array.isArray(value)) {
    let changed = false;
    const next = value.map((item) => {
      const replacement = replaceNodeReferences(item, nextNode);
      changed = changed || replacement !== item;
      return replacement;
    });
    return changed ? next : value;
  }

  if (!isRecord(value)) {
    return value;
  }

  if (value !== nextNode && value.id === nextNode.id && typeof nextNode.id === "string") {
    return nextNode;
  }

  let changed = false;
  const next: Record<string, unknown> = {};
  Object.entries(value).forEach(([key, item]) => {
    const replacement = replaceNodeReferences(item, nextNode);
    changed = changed || replacement !== item;
    next[key] = replacement;
  });

  return changed ? next : value;
}

function areEqual(left: unknown, right: unknown) {
  return JSON.stringify(left) === JSON.stringify(right);
}

export function asString(value: unknown) {
  return typeof value === "string" ? value : "";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
