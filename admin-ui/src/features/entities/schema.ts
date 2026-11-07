import type { JsonSchema } from "./api";
import type { EntityDefaultPermissionDocument } from "./api";

const systemFieldNames = new Set([
  "id",
  "entity",
  "parent",
  "owner",
  "group",
  "perm",
  "depth",
  "ancestors",
  "deleted",
  "cdate",
  "mdate",
]);

const STRUCTURED_ASSET_TYPES = new Set(["File", "Image", "Video"]);
const STRUCTURED_ASSET_SEMANTIC_TYPES = new Set([
  ...STRUCTURED_ASSET_TYPES,
  ...Array.from(STRUCTURED_ASSET_TYPES, (assetType) => `Array<${assetType}>`),
]);
const USER_MODULE = "users";
const USER_ENTITY = "user";
const GROUP_ENTITY = "group";
const USER_PROTECTED_FIELDS = new Set([
  "username",
  "email",
  "primary_group",
  "groups",
  "password",
  "password_hash",
  "role",
  "active",
]);
const GROUP_PROTECTED_FIELDS = new Set([
  "groupname",
  "is_default",
]);

export type SchemaFieldNode = {
  canAddNested: boolean;
  canDelete: boolean;
  canEditDescription: boolean;
  canEditStructure: boolean;
  canReorder: boolean;
  children: SchemaFieldNode[];
  description: string;
  fieldSchema: JsonSchema;
  isNullable: boolean;
  isRequired: boolean;
  linkTargetEntities: string[];
  linkTargetModule: string | null;
  name: string;
  path: string[];
  semanticType: string;
  showAccessModes: boolean;
  visibilityMode: string | null;
  writeMode: string | null;
};

type SchemaSections = {
  customFields: SchemaFieldNode[];
  systemFields: SchemaFieldNode[];
};

type SchemaContext = {
  entityName?: string;
  moduleName?: string;
};

type UnwrappedSchema = {
  isNullable: boolean;
  schema: JsonSchema;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function unwrapNullable(schema: JsonSchema): UnwrappedSchema {
  if (!Array.isArray(schema.anyOf)) {
    return { isNullable: false, schema };
  }

  const variants = schema.anyOf;
  const hasNull = variants.some((item) => item.type === "null");
  const primary = variants.find((item) => item.type !== "null");

  if (!hasNull || primary === undefined) {
    return { isNullable: false, schema };
  }

  return { isNullable: true, schema: primary };
}

function getMeta(schema: JsonSchema) {
  const meta = schema["x-meta"];
  return isRecord(meta) ? meta : null;
}

function getSemanticType(schema: JsonSchema): string {
  const meta = getMeta(schema);
  const semanticType = meta?.["semantic-type"];

  if (typeof semanticType === "string" && semanticType.length > 0) {
    if (semanticType === "Array" && schema.type === "array" && schema.items !== undefined) {
      const itemSchema = unwrapNullable(schema.items).schema;
      return `Array<${getSemanticType(itemSchema)}>`;
    }

    return semanticType;
  }

  if (schema.type === "object") {
    return "Object";
  }

  if (schema.type === "array" && schema.items !== undefined) {
    const itemSchema = unwrapNullable(schema.items).schema;
    return `Array<${getSemanticType(itemSchema)}>`;
  }

  if (typeof schema.type === "string" && schema.type.length > 0) {
    return schema.type.charAt(0).toUpperCase() + schema.type.slice(1);
  }

  return "Unknown";
}

function isStructuredAssetSemanticType(semanticType: string): boolean {
  return STRUCTURED_ASSET_SEMANTIC_TYPES.has(semanticType);
}

function getTarget(schema: JsonSchema): { entities: string[]; module: string | null } | null {
  const meta = getMeta(schema);
  const link = meta?.link;

  if (!isRecord(link)) {
    return null;
  }

  const moduleName = typeof link.module === "string" ? link.module : "";
  const entities = Array.isArray(link.entities) ? link.entities.filter((item): item is string => typeof item === "string") : [];

  if (moduleName.length === 0 && entities.length === 0) {
    return null;
  }

  return {
    entities,
    module: moduleName.length > 0 ? moduleName : null,
  };
}

function getChildStructure(schema: JsonSchema) {
  if (schema.type === "object") {
    return {
      properties: isRecord(schema.properties) ? schema.properties : {},
      requiredFields: Array.isArray(schema.required)
        ? schema.required.filter((item): item is string => typeof item === "string")
        : [],
    };
  }

  if (schema.type === "array" && schema.items !== undefined) {
    const itemSchema = unwrapNullable(schema.items).schema;
    if (itemSchema.type === "object") {
      return {
        properties: isRecord(itemSchema.properties) ? itemSchema.properties : {},
        requiredFields: Array.isArray(itemSchema.required)
          ? itemSchema.required.filter((item): item is string => typeof item === "string")
          : [],
      };
    }
  }

  return {
    properties: {},
    requiredFields: [],
  };
}

function buildFieldNode(
  name: string,
  rawSchema: JsonSchema,
  requiredFields: string[],
  path: string[],
  context: SchemaContext,
  parentLocks: { insideStructuredAsset: boolean },
): SchemaFieldNode {
  const { isNullable, schema } = unwrapNullable(rawSchema);
  const meta = getMeta(schema);
  const { properties, requiredFields: childRequired } = getChildStructure(schema);
  const target = getTarget(schema);
  const semanticType = getSemanticType(schema);
  const insideStructuredAsset = parentLocks.insideStructuredAsset;
  const isProtectedUsersField = isProtectedUsersFieldName(name, path, context);
  const canEditStructure = !insideStructuredAsset && !isProtectedUsersField;
  const canEditDescription = !insideStructuredAsset;
  const canDelete = !insideStructuredAsset && !isProtectedUsersField;
  const canReorder = !insideStructuredAsset && !isProtectedUsersField;
  const canAddNested =
    canEditStructure &&
    (semanticType === "Object" || semanticType === "Array<Object>") &&
    !isStructuredAssetSemanticType(semanticType);
  const childLocks = {
    insideStructuredAsset: insideStructuredAsset || isStructuredAssetSemanticType(semanticType),
  };

  return {
    canAddNested,
    canDelete,
    canEditDescription,
    canEditStructure,
    canReorder,
    children: Object.entries(properties).map(([childName, childSchema]) =>
      buildFieldNode(childName, childSchema as JsonSchema, childRequired, [...path, childName], context, childLocks),
    ),
    description: typeof schema.description === "string" ? schema.description : "",
    fieldSchema: rawSchema,
    isNullable,
    isRequired: requiredFields.includes(name),
    linkTargetEntities: target?.entities ?? [],
    linkTargetModule: target?.module ?? null,
    name,
    path,
    semanticType,
    showAccessModes: !insideStructuredAsset,
    visibilityMode: typeof meta?.["visibility-mode"] === "string" ? (meta["visibility-mode"] as string) : null,
    writeMode: typeof meta?.["write-mode"] === "string" ? (meta["write-mode"] as string) : null,
  };
}

export function splitSchemaFields(schema: JsonSchema, context: SchemaContext = {}): SchemaSections {
  const requiredFields = Array.isArray(schema.required)
    ? schema.required.filter((item): item is string => typeof item === "string")
    : [];
  const properties = isRecord(schema.properties) ? schema.properties : {};
  const allFields = Object.entries(properties).map(([name, fieldSchema]) =>
    buildFieldNode(name, fieldSchema as JsonSchema, requiredFields, [name], context, { insideStructuredAsset: false }),
  );

  return {
    customFields: allFields.filter((field) => !systemFieldNames.has(field.name)),
    systemFields: allFields.filter((field) => systemFieldNames.has(field.name)),
  };
}

function isProtectedUsersFieldName(name: string, path: string[], context: SchemaContext) {
  if (context.moduleName !== USER_MODULE || path.length !== 1) {
    return false;
  }

  if (context.entityName === USER_ENTITY) {
    return USER_PROTECTED_FIELDS.has(name);
  }

  if (context.entityName === GROUP_ENTITY) {
    return GROUP_PROTECTED_FIELDS.has(name);
  }

  return false;
}

export function getSchemaChildrenEntities(schema: JsonSchema): string[] {
  const meta = getMeta(schema);
  const children = isRecord(meta?.children) ? meta.children : null;
  const entities = Array.isArray(children?.entities) ? children.entities : [];

  return entities.filter((item): item is string => typeof item === "string");
}

export function getSchemaLabelTemplates(schema: JsonSchema) {
  const ui = isRecord(schema["x-ui"]) ? schema["x-ui"] : null;
  const labels = isRecord(ui?.labels) ? ui.labels : null;

  return {
    reference: typeof labels?.reference === "string" ? labels.reference : "",
    tree: typeof labels?.tree === "string" ? labels.tree : "",
  };
}

export function buildEntitySchemaWithRootEdits(
  schema: JsonSchema,
  updates: {
    childrenEntities: string[];
    defaultPerm: EntityDefaultPermissionDocument;
    description: string;
    referenceLabelTemplate: string;
    title: string;
    treeLabelTemplate: string;
  },
): JsonSchema {
  const nextMeta = isRecord(schema["x-meta"]) ? { ...schema["x-meta"] } : {};
  const nextChildren = isRecord(nextMeta.children) ? { ...nextMeta.children } : {};
  const nextPerm = isRecord(nextMeta.perm) ? { ...nextMeta.perm } : {};
  nextChildren.entities = updates.childrenEntities;
  nextPerm.default = updates.defaultPerm;
  nextMeta.children = nextChildren;
  nextMeta.perm = nextPerm;

  const nextUi = isRecord(schema["x-ui"]) ? { ...schema["x-ui"] } : {};
  const nextLabels = isRecord(nextUi.labels) ? { ...nextUi.labels } : {};
  if (updates.treeLabelTemplate.trim().length > 0) {
    nextLabels.tree = updates.treeLabelTemplate;
  } else {
    delete nextLabels.tree;
  }
  if (updates.referenceLabelTemplate.trim().length > 0) {
    nextLabels.reference = updates.referenceLabelTemplate;
  } else {
    delete nextLabels.reference;
  }
  if (Object.keys(nextLabels).length > 0) {
    nextUi.labels = nextLabels;
  } else {
    delete nextUi.labels;
  }

  const nextSchema: JsonSchema = {
    ...schema,
    description: updates.description.length > 0 ? updates.description : undefined,
    title: updates.title,
    ["x-meta"]: nextMeta,
  };
  if (Object.keys(nextUi).length > 0) {
    nextSchema["x-ui"] = nextUi;
  } else {
    delete nextSchema["x-ui"];
  }
  return nextSchema;
}

export function getSchemaDefaultPerm(schema: JsonSchema): EntityDefaultPermissionDocument {
  const meta = getMeta(schema);
  const perm = isRecord(meta?.perm) ? meta.perm : null;
  const defaultPerm = isRecord(perm?.default) ? perm.default : null;

  return {
    owner: {
      r: Boolean(isRecord(defaultPerm?.owner) ? defaultPerm.owner.r : true),
      w: Boolean(isRecord(defaultPerm?.owner) ? defaultPerm.owner.w : true),
      p: Boolean(isRecord(defaultPerm?.owner) ? defaultPerm.owner.p : true),
    },
    group: {
      r: Boolean(isRecord(defaultPerm?.group) ? defaultPerm.group.r : false),
      w: Boolean(isRecord(defaultPerm?.group) ? defaultPerm.group.w : false),
      p: Boolean(isRecord(defaultPerm?.group) ? defaultPerm.group.p : false),
    },
    others: {
      r: Boolean(isRecord(defaultPerm?.others) ? defaultPerm.others.r : false),
      w: Boolean(isRecord(defaultPerm?.others) ? defaultPerm.others.w : false),
      p: Boolean(isRecord(defaultPerm?.others) ? defaultPerm.others.p : false),
    },
  };
}

export function createEmptyEntitySchema(title = ""): JsonSchema {
  return {
    title,
    type: "object",
    additionalProperties: false,
    properties: {},
    ["x-meta"]: {
      children: { entities: [] },
      perm: {
        default: {
          owner: { r: true, w: true, p: true },
          group: { r: false, w: false, p: false },
          others: { r: false, w: false, p: false },
        },
      },
    },
  };
}

export function getSchemaFieldNodeAtPath(schema: JsonSchema, path: string[]): SchemaFieldNode | null {
  if (path.length === 0) {
    return null;
  }

  const requiredFields = Array.isArray(schema.required)
    ? schema.required.filter((item): item is string => typeof item === "string")
    : [];
  const properties = isRecord(schema.properties) ? schema.properties : {};
  const fieldName = path[0];
  if (fieldName === undefined) {
    return null;
  }

  const fieldSchema = properties[fieldName];
  if (fieldSchema === undefined) {
    return null;
  }

  let currentNode = buildFieldNode(
    fieldName,
    fieldSchema as JsonSchema,
    requiredFields,
    [fieldName],
    {},
    { insideStructuredAsset: false },
  );
  for (const segment of path.slice(1)) {
    const nextNode = currentNode.children.find((child) => child.name === segment);
    if (nextNode === undefined) {
      return null;
    }
    currentNode = nextNode;
  }

  return currentNode;
}

export function getSchemaSiblingFieldNames(schema: JsonSchema, parentPath: string[]) {
  if (parentPath.length === 0) {
    const properties = isRecord(schema.properties) ? schema.properties : {};
    return Object.keys(properties).filter((name) => !systemFieldNames.has(name));
  }

  const parentNode = getSchemaFieldNodeAtPath(schema, parentPath);
  if (parentNode === null) {
    return [];
  }

  return parentNode.children.map((child) => child.name);
}
