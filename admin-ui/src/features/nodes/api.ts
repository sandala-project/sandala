import { apiClient } from "../../lib/api";
import type { ReferenceValue } from "../../lib/references";
import type { JsonSchema } from "../entities/api";

export type NodeReference = ReferenceValue;

export type NodeDocument = {
  ancestors?: string[];
  cdate?: string;
  deleted?: boolean;
  depth?: number;
  entity?: string;
  group?: NodeReference;
  id?: string;
  mdate?: string;
  owner?: NodeReference;
  parent?: string | null;
  perm?: unknown;
  [key: string]: unknown;
};

export type ImageDescriptor = {
  "mime-type"?: string;
  height?: number;
  size?: number;
  url: string;
  width?: number;
};

export type FileDescriptor = {
  "mime-type"?: string;
  size?: number;
  url: string;
};

export type VideoDescriptor = {
  "mime-type"?: string;
  size?: number;
  url: string;
};

type NodesResponse = {
  nodes: NodeDocument[];
};

type NodeResponse = {
  node: NodeDocument;
};

export type NodeAclPatchResponse = {
  node: NodeDocument;
  updated_count: number;
};

type DeleteNodeResponse = {
  deleted_count: number;
};

type ImageUploadResponse = {
  image: ImageDescriptor;
};

type FileUploadResponse = {
  file: FileDescriptor;
};

type VideoUploadResponse = {
  video: VideoDescriptor;
};

type NodeQueryPayload = {
  filter?: Record<string, unknown>;
  limit?: number;
  offset?: number;
  sort?: Record<string, "asc" | "desc">;
};

export function getRootNodes(moduleName: string, signal?: AbortSignal) {
  return queryNodes(
    moduleName,
    {
      filter: { parent: null },
    },
    signal,
  );
}

export function getChildNodes(moduleName: string, parentId: string, signal?: AbortSignal) {
  return queryNodes(
    moduleName,
    {
      filter: { parent: parentId },
    },
    signal,
  );
}

export function getNode(moduleName: string, nodeId: string, signal?: AbortSignal) {
  return apiClient
    .get<NodeResponse>(`/nodes/${encodeURIComponent(moduleName)}/${encodeURIComponent(nodeId)}/`, { signal })
    .then((payload) => payload.node);
}

export function deleteNode(moduleName: string, nodeId: string) {
  return apiClient.delete<DeleteNodeResponse>(`/nodes/${encodeURIComponent(moduleName)}/${encodeURIComponent(nodeId)}/`);
}

export function getEntityNodesPage(args: {
  entityName: string;
  filter?: Record<string, unknown>;
  limit?: number;
  moduleName: string;
  offset?: number;
  signal?: AbortSignal;
  sort?: Record<string, "asc" | "desc">;
}) {
  return apiClient
    .post<NodesResponse>(
      `/nodes/${encodeURIComponent(args.moduleName)}/entity/${encodeURIComponent(args.entityName)}/query/`,
      {
        query: {
          filter: args.filter,
          limit: args.limit,
          offset: args.offset,
          sort: args.sort,
        },
      },
      { signal: args.signal },
    )
    .then((payload) => payload.nodes);
}

export async function updateNode(moduleName: string, nodeId: string, node: Record<string, unknown>) {
  await apiClient.patch<NodeResponse>(`/nodes/${encodeURIComponent(moduleName)}/${encodeURIComponent(nodeId)}/`, { node });
  return getNode(moduleName, nodeId);
}

export function patchNodeAcl(args: {
  moduleName: string;
  nodeId: string;
  node: Record<string, unknown>;
  recursive: boolean;
}) {
  return apiClient.patch<NodeAclPatchResponse>(
    `/nodes/${encodeURIComponent(args.moduleName)}/${encodeURIComponent(args.nodeId)}/acl/`,
    { node: args.node, recursive: args.recursive },
  );
}

export function createNode(moduleName: string, node: Record<string, unknown>) {
  return apiClient
    .post<NodeResponse>(`/nodes/${encodeURIComponent(moduleName)}/`, { node })
    .then((payload) => payload.node);
}

export function uploadImageAsset(args: {
  entityName: string;
  fieldPath: string;
  file: File;
  moduleName: string;
}) {
  const form = new FormData();
  form.set("file", args.file);
  form.set(
    "target",
    JSON.stringify({
      entity: args.entityName,
      field: args.fieldPath,
      module: args.moduleName,
    }),
  );

  return apiClient
    .postForm<ImageUploadResponse>("/uploads/assets/images/", form)
    .then((payload) => payload.image);
}

export function uploadFileAsset(args: {
  entityName: string;
  fieldPath: string;
  file: File;
  moduleName: string;
}) {
  const form = new FormData();
  form.set("file", args.file);
  form.set(
    "target",
    JSON.stringify({
      entity: args.entityName,
      field: args.fieldPath,
      module: args.moduleName,
    }),
  );

  return apiClient
    .postForm<FileUploadResponse>("/uploads/assets/files/", form)
    .then((payload) => payload.file);
}

export function uploadVideoAsset(args: {
  entityName: string;
  fieldPath: string;
  file: File;
  moduleName: string;
}) {
  const form = new FormData();
  form.set("file", args.file);
  form.set(
    "target",
    JSON.stringify({
      entity: args.entityName,
      field: args.fieldPath,
      module: args.moduleName,
    }),
  );

  return apiClient
    .postForm<VideoUploadResponse>("/uploads/assets/videos/", form)
    .then((payload) => payload.video);
}

export function queryNodes(moduleName: string, query: NodeQueryPayload, signal?: AbortSignal) {
  return apiClient
    .post<NodesResponse>(`/nodes/${encodeURIComponent(moduleName)}/query/`, { query }, { signal })
    .then((payload) => payload.nodes);
}

export function getLinkableNodesByIds(args: {
  entityNames: string[];
  ids: string[];
  moduleName: string;
  signal?: AbortSignal;
}) {
  const ids = [...new Set(args.ids.filter((id) => id.trim().length > 0))];
  if (ids.length === 0) {
    return Promise.resolve([]);
  }

  const filter: Record<string, unknown> = {
    id: { in: ids },
  };
  if (args.entityNames.length > 0) {
    filter.entity = { in: args.entityNames };
  }

  return queryNodes(
    args.moduleName,
    {
      filter,
      limit: ids.length,
    },
    args.signal,
  );
}

export type { JsonSchema };
