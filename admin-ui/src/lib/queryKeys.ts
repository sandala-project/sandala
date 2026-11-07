export const structureKeys = {
  modules: () => ["structure", "modules"] as const,
  entities: (moduleName: string) => ["structure", "entities", moduleName] as const,
  schema: (moduleName: string, entityName: string) => ["structure", "schema", moduleName, entityName] as const,
};
