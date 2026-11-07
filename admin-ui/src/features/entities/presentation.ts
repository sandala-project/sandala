import type { EntityListItem, ModuleDocument } from "./api";

export function getModuleDisplayLabel(module: Pick<ModuleDocument, "description" | "name">) {
  const description = module.description.trim();
  return description.length > 0 ? description : module.name;
}

export function getEntityDisplayLabel(entity: Pick<EntityListItem, "description" | "title">) {
  const description = entity.description.trim();
  return description.length > 0 ? description : entity.title;
}
