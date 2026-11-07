import { getSchemaDefaultPerm } from "../entities/schema";
import type { JsonSchema } from "../entities/api";
import type { AuthenticatedUser } from "../../lib/session";
import { getReferenceId, isRecord } from "../../lib/references";
import type { NodeDocument, NodeReference } from "./api";
import type { NodeEditorField } from "./editorSchema";
import { buildNodeEditorFields } from "./editorSchema";
import { getNodeReferenceId } from "./nodeFieldUtils";
import { asString, normalizeNodeFieldValue, type NodeDraft } from "./useNodeDraft";

export function createInitialNodeDraft(args: {
  entityName: string;
  parentId: string | null | undefined;
  schema: JsonSchema;
  user: AuthenticatedUser | null;
}): NodeDocument {
  const defaultPerm = getSchemaDefaultPerm(args.schema);

  const draft: NodeDocument = {
    entity: args.entityName,
    group: createReferenceValue(args.user?.primary_group),
    owner: createCurrentUserReference(args.user),
    parent: args.parentId,
    perm: defaultPerm,
  };

  applyBooleanDefaults(draft, buildNodeEditorFields(args.schema, args.user));
  return draft;
}

function applyBooleanDefaults(draft: NodeDraft, fields: NodeEditorField[], insideArray = false) {
  fields.forEach((field) => {
    const fieldInsideArray = insideArray || field.inputKind === "array-object";
    if (!fieldInsideArray && field.inputKind === "boolean" && field.writable && getValueAtPath(draft, field.path) === undefined) {
      setValueAtPath(draft, field.path, false);
    }

    applyBooleanDefaults(draft, field.children, fieldInsideArray);
  });
}

function setValueAtPath(target: Record<string, unknown>, path: string[], value: unknown) {
  const lastSegment = path.at(-1);
  if (lastSegment === undefined) {
    return;
  }

  let current = target;
  path.slice(0, -1).forEach((segment) => {
    const next = current[segment];
    if (!isRecord(next)) {
      current[segment] = {};
    }
    current = current[segment] as Record<string, unknown>;
  });
  current[lastSegment] = value;
}

function createCurrentUserReference(user: AuthenticatedUser | null): NodeReference | string {
  const id = getReferenceId(user?.id);
  const username = asString(user?.username) || asString(user?.login);

  return id.length > 0 && username.length > 0 ? { id, username } : id;
}

function createReferenceValue(value: unknown): NodeReference | string {
  if (isRecord(value)) {
    return { ...value };
  }

  return getReferenceId(value);
}

export function buildCreatePayload(args: {
  canEditGroup: boolean;
  canEditOwner: boolean;
  canEditPerm: boolean;
  draft: NodeDraft;
  fields: NodeEditorField[];
}) {
  const payload: Record<string, unknown> = {};

  const entityName = asString(args.draft.entity).trim();
  if (entityName.length > 0) {
    payload.entity = entityName;
  }

  const parentValue = args.draft.parent;
  payload.parent = typeof parentValue === "string" && parentValue.trim().length > 0 ? parentValue : null;

  for (const field of args.fields) {
    if (!field.writable) {
      continue;
    }

    const draftValue = normalizeNodeFieldValue(field, getValueAtPath(args.draft, field.path));
    if (draftValue !== undefined) {
      payload[field.name] = draftValue;
    }
  }

  if (args.canEditOwner) {
    const owner = getNodeReferenceId(args.draft.owner);
    if (owner.length > 0) {
      payload.owner = owner;
    }
  }

  if (args.canEditGroup) {
    const group = getNodeReferenceId(args.draft.group);
    if (group.length > 0) {
      payload.group = group;
    }
  }

  if (args.canEditPerm && isRecord(args.draft.perm)) {
    payload.perm = args.draft.perm;
  }

  return payload;
}

function getValueAtPath(source: unknown, path: Array<string | number>): unknown {
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
