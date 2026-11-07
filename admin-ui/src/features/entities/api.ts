import { apiClient } from "../../lib/api";

export type ModuleDocument = {
  description: string;
  name: string;
  root_children_entities: string[];
  root_group: string;
  root_owner: string;
  root_perm: RootPermissionDocument;
};

export type RootPermissionDocument = {
  group: { p: boolean };
  others: { p: boolean };
  owner: { p: boolean };
};

export type EntityDefaultPermissionDocument = {
  group: { p: boolean; r: boolean; w: boolean };
  others: { p: boolean; r: boolean; w: boolean };
  owner: { p: boolean; r: boolean; w: boolean };
};

export type EntityListItem = {
  description: string;
  title: string;
};

export type JsonSchema = {
  additionalProperties?: boolean;
  anyOf?: JsonSchema[];
  description?: string;
  enum?: string[];
  exclusiveMaximum?: number;
  exclusiveMinimum?: number;
  format?: string;
  items?: JsonSchema;
  maximum?: number;
  maxItems?: number;
  maxLength?: number;
  minimum?: number;
  minItems?: number;
  minLength?: number;
  multipleOf?: number;
  pattern?: string;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  title?: string;
  type?: string;
  ["x-meta"]?: Record<string, unknown>;
  ["x-ui"]?: Record<string, unknown>;
};

type ModulesResponse = {
  modules: ModuleDocument[];
};

type ModuleResponse = {
  module: ModuleDocument;
};

type EntitiesResponse = {
  entities: EntityListItem[];
};

type EntityResponse = {
  entity: JsonSchema;
};

type DeleteResponse = {
  status: "ok";
};

export function getModules(signal?: AbortSignal) {
  return apiClient.get<ModulesResponse>("/modules/", { signal }).then((payload) => payload.modules);
}

export function updateModule(moduleName: string, module: Partial<ModuleDocument>) {
  return apiClient
    .patch<ModuleResponse>(
      `/modules/${encodeURIComponent(moduleName)}/`,
      { module },
    )
    .then((payload) => payload.module);
}

export function createModule(module: ModuleDocument) {
  return apiClient
    .post<ModuleResponse>("/modules/", { module })
    .then((payload) => payload.module);
}

export function deleteModule(moduleName: string) {
  return apiClient.delete<DeleteResponse>(`/modules/${encodeURIComponent(moduleName)}/`);
}

export function getEntities(moduleName: string, signal?: AbortSignal) {
  return apiClient
    .get<EntitiesResponse>(`/modules/${encodeURIComponent(moduleName)}/entities/`, { signal })
    .then((payload) => payload.entities);
}

export function getEntitySchema(moduleName: string, entityName: string, signal?: AbortSignal) {
  return apiClient
    .get<EntityResponse>(`/modules/${encodeURIComponent(moduleName)}/entities/${encodeURIComponent(entityName)}/`, { signal })
    .then((payload) => payload.entity);
}

export function updateEntitySchema(moduleName: string, entityName: string, entity: JsonSchema) {
  return apiClient
    .put<EntityResponse>(
      `/modules/${encodeURIComponent(moduleName)}/entities/${encodeURIComponent(entityName)}/`,
      { entity },
    )
    .then((payload) => payload.entity);
}

export function createEntitySchema(moduleName: string, entityName: string, entity: JsonSchema) {
  return apiClient
    .post<EntityResponse>(
      `/modules/${encodeURIComponent(moduleName)}/entities/${encodeURIComponent(entityName)}/`,
      { entity },
    )
    .then((payload) => payload.entity);
}

export function deleteEntitySchema(moduleName: string, entityName: string) {
  return apiClient.delete<DeleteResponse>(
    `/modules/${encodeURIComponent(moduleName)}/entities/${encodeURIComponent(entityName)}/`,
  );
}
