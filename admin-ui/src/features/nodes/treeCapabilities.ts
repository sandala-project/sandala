import type { AuthenticatedUser } from "../../lib/session";
import type { JsonSchema, ModuleDocument } from "../entities/api";
import type { NodeDocument } from "./api";
import { getNodeReferenceId } from "./nodeFieldUtils";
import { getValueAtPath } from "./useNodeDraft";

export function canPopulateNodeDocument(node: NodeDocument, user: AuthenticatedUser | null) {
  if (user === null) {
    return false;
  }

  if (user.role === "superuser" || Boolean(user.superuser)) {
    return true;
  }

  if (!isRecord(node.perm)) {
    return false;
  }

  const actorId = user.id;
  const actorGroups = new Set(
    Array.isArray(user.groups)
      ? user.groups.map((group) => getNodeReferenceId(group)).filter((group) => group.length > 0)
      : [],
  );
  const owner = getNodeReferenceId(node.owner) || null;
  const group = getNodeReferenceId(node.group) || null;

  if (owner !== null && actorId === owner) {
    return Boolean(getValueAtPath(node.perm, ["owner", "p"]));
  }
  if (group !== null && actorGroups.has(group)) {
    return Boolean(getValueAtPath(node.perm, ["group", "p"]));
  }
  return Boolean(getValueAtPath(node.perm, ["others", "p"]));
}

export function canPopulateModuleRoot(moduleDoc: ModuleDocument, user: AuthenticatedUser | null) {
  if (user === null) {
    return false;
  }

  if (user.role === "superuser" || Boolean(user.superuser)) {
    return true;
  }

  const actorId = user.id;
  const actorGroups = new Set(
    Array.isArray(user.groups)
      ? user.groups.map((group) => getNodeReferenceId(group)).filter((group) => group.length > 0)
      : [],
  );

  if (typeof moduleDoc.root_owner === "string" && moduleDoc.root_owner === actorId) {
    return Boolean(moduleDoc.root_perm.owner?.p);
  }
  if (typeof moduleDoc.root_group === "string" && actorGroups.has(moduleDoc.root_group)) {
    return Boolean(moduleDoc.root_perm.group?.p);
  }
  return Boolean(moduleDoc.root_perm.others?.p);
}

export function resolveRootCreateTargets(moduleDoc: ModuleDocument, entityNamesInModule: string[]) {
  const allowed = Array.isArray(moduleDoc.root_children_entities)
    ? moduleDoc.root_children_entities.filter((item): item is string => typeof item === "string" && item.length > 0)
    : [];

  if (allowed.length === 0) {
    return entityNamesInModule;
  }

  const allowedSet = new Set(allowed);
  return entityNamesInModule.filter((entityName) => allowedSet.has(entityName));
}

export function resolveNodeCreateTargets(schema: JsonSchema | null | undefined, entityNamesInModule: string[]) {
  if (schema === null || schema === undefined) {
    return [];
  }

  const meta = isRecord(schema["x-meta"]) ? schema["x-meta"] : null;
  const children = meta !== null && isRecord(meta.children) ? meta.children : null;
  const entities = children !== null && Array.isArray(children.entities) ? children.entities : [];
  const allowed = entities.filter((item): item is string => typeof item === "string" && item.length > 0);

  if (allowed.length === 0) {
    return [];
  }

  const allowedSet = new Set(allowed);
  return entityNamesInModule.filter((entityName) => allowedSet.has(entityName));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
