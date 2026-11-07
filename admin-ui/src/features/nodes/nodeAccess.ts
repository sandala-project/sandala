import type { AuthenticatedUser } from "../../lib/session";
import type { NodeDocument } from "./api";
import { getNodeReferenceId } from "./nodeFieldUtils";

export function canWriteNodeDocument(node: NodeDocument, user: AuthenticatedUser | null) {
  if (user === null) {
    return false;
  }

  if (user.role === "superuser" || Boolean(user.superuser)) {
    return true;
  }

  if (!isRecord(node.perm)) {
    return false;
  }

  const owner = getNodeReferenceId(node.owner) || null;
  const group = getNodeReferenceId(node.group) || null;
  const actorGroups = new Set(
    (Array.isArray(user.groups) ? user.groups : [])
      .map((item) => getNodeReferenceId(item))
      .filter((item) => item.length > 0),
  );

  if (owner !== null && user.id === owner) {
    return hasWritePermission(node.perm.owner);
  }
  if (group !== null && actorGroups.has(group)) {
    return hasWritePermission(node.perm.group);
  }
  return hasWritePermission(node.perm.others);
}

export function getNodeAclEditCapabilities(node: NodeDocument, user: AuthenticatedUser | null) {
  const isSuperuser = user?.role === "superuser" || Boolean(user?.superuser);
  const canWriteNode = canWriteNodeDocument(node, user);
  const isOwner = user !== null && user.id === getNodeReferenceId(node.owner);

  return {
    canEditGroup: isSuperuser || (isOwner && canWriteNode),
    canEditOwner: isSuperuser,
    canEditPerm: isSuperuser || (isOwner && canWriteNode),
  };
}

function hasWritePermission(value: unknown) {
  return isRecord(value) && value.w === true;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
