import type { NodeEditorField } from "./editorSchema";
import {
  buildNodeTableFields,
  getNodeTableFieldPath,
  type NodeTableField,
} from "./nodeTableFields";

export type NodeTableFilterCombination = "and" | "or" | "not";
export type NodeTableFilterOperator =
  | "eq"
  | "neq"
  | "gt"
  | "gte"
  | "lt"
  | "lte"
  | "in"
  | "nin"
  | "exists"
  | "size"
  | "regex";

export type NodeTableFilterField = NodeTableField;

export type NodeTableFilterScalarKind = "boolean" | "date" | "datetime" | "number" | "string";

export type NodeTableFilterCondition = {
  fieldPath: string;
  id: string;
  operator: NodeTableFilterOperator;
  rawFieldPath: string;
  value: boolean | number | string | null | Array<boolean | number | string>;
};

export type NodeTableFilterGroup = {
  children: NodeTableFilterItem[];
  combination: NodeTableFilterCombination;
  id: string;
};

export type NodeTableFilterItem = NodeTableFilterCondition | NodeTableFilterGroup;
export type NodeTableFilterDefinition = NodeTableFilterGroup;
export type NodeTableFilter =
  | { definition: NodeTableFilterDefinition; mode: "visual" }
  | { filter: Record<string, unknown>; mode: "json"; raw: string };

export type NodeTableFilterValidationIssue = {
  itemId: string;
  kind: "invalid-regex" | "invalid-size" | "invalid-value" | "missing-field" | "missing-value";
};

export function buildNodeTableFilterFields(fields: NodeEditorField[], options: { includePermissions: boolean }) {
  return buildNodeTableFields(fields, options);
}

export function createEmptyNodeTableFilterDefinition(fields: NodeTableFilterField[]): NodeTableFilterDefinition {
  return {
    children: fields.length === 0 ? [] : [createNodeTableFilterCondition(fields[0]!)],
    combination: "and",
    id: "root",
  };
}

export function createBlankNodeTableFilterDefinition(): NodeTableFilterDefinition {
  return { children: [], combination: "and", id: "root" };
}

export function createNodeTableFilterGroup(fields: NodeTableFilterField[]): NodeTableFilterGroup {
  return {
    children: fields.length === 0 ? [] : [createNodeTableFilterCondition(fields[0]!)],
    combination: "and",
    id: createGroupId(),
  };
}

export function createNodeTableFilterCondition(field: NodeTableFilterField): NodeTableFilterCondition {
  const operator = getNodeTableFilterOperators(field)[0] ?? "exists";
  return {
    fieldPath: getNodeTableFilterFieldPath(field),
    id: createConditionId(),
    operator,
    rawFieldPath: field.path.join("."),
    value: getDefaultFilterValue(field, operator),
  };
}

export function getNodeTableFilterOperators(field: NodeTableFilterField): NodeTableFilterOperator[] {
  switch (field.kind) {
    case "string":
      return ["eq", "neq", "regex", "exists"];
    case "number":
      return ["eq", "neq", "gt", "gte", "lt", "lte", "exists"];
    case "date":
    case "datetime":
      return ["eq", "neq", "gt", "gte", "lt", "lte", "exists"];
    case "boolean":
      return ["eq", "neq", "exists"];
    case "link":
      return ["eq", "neq"];
    case "link-array":
      return ["in", "nin"];
    case "array":
      return ["eq", "neq", "size", "exists"];
    case "array-object":
      return ["size", "exists", "eq", "neq"];
    case "asset-array":
      return ["size", "exists", "eq", "neq"];
    case "object":
      return ["exists", "eq", "neq"];
    case "asset":
      return ["exists", "eq", "neq"];
  }
}

export function getDefaultFilterValue(field: NodeTableFilterField, operator: NodeTableFilterOperator) {
  if (operator === "exists") {
    return true;
  }
  if (operator === "size") {
    return 0;
  }
  if (operator === "in" || operator === "nin") {
    return [];
  }
  if ((operator === "eq" || operator === "neq") && !supportsLiteralFilterValue(field)) {
    return null;
  }
  if (getNodeTableFilterScalarKind(field) === "boolean") {
    return true;
  }
  return "";
}

export function validateNodeTableFilterDefinition(
  definition: NodeTableFilterDefinition,
  fields: NodeTableFilterField[],
): NodeTableFilterValidationIssue[] {
  const fieldsByPath = new Map(fields.map((field) => [getNodeTableFilterFieldPath(field), field]));

  return validateFilterGroup(definition, fieldsByPath, true);
}

export function compileNodeTableFilter(definition: NodeTableFilterDefinition) {
  return compileFilterGroup(definition);
}

export function compileAppliedNodeTableFilter(filter: NodeTableFilter | null) {
  if (filter === null) {
    return {};
  }
  return filter.mode === "visual" ? compileNodeTableFilter(filter.definition) : filter.filter;
}

export function hasNodeTableFilter(filter: NodeTableFilter | null) {
  return Object.keys(compileAppliedNodeTableFilter(filter)).length > 0;
}

export function getAppliedNodeTableFilterPaths(filter: NodeTableFilter | null) {
  const paths = new Set<string>();
  collectFilterPaths(compileAppliedNodeTableFilter(filter), paths);
  return [...paths];
}

export function getNodeTableFilterConditionCount(definition: NodeTableFilterDefinition | null): number {
  if (definition === null) {
    return 0;
  }
  return definition.children.reduce((count, item) => (
    count + (isNodeTableFilterGroup(item) ? getNodeTableFilterConditionCount(item) : 1)
  ), 0);
}

export function parseNodeTableFilterDefinition(
  value: unknown,
  fields: NodeTableFilterField[],
): NodeTableFilterDefinition | null {
  const fieldIndex = createFilterFieldIndex(fields);
  const definition = parseFilterGroup(value, true, fieldIndex);
  if (definition === null || validateNodeTableFilterDefinition(definition, fields).length > 0) {
    return null;
  }
  return definition;
}

export function appendNodeTableFilterCondition(
  definition: NodeTableFilterDefinition,
  groupId: string,
  field: NodeTableFilterField,
) {
  return updateFilterGroup(definition, groupId, (group) => ({
    ...group,
    children: [...group.children, createNodeTableFilterCondition(field)],
  }));
}

export function appendNodeTableFilterGroup(
  definition: NodeTableFilterDefinition,
  groupId: string,
  fields: NodeTableFilterField[],
) {
  return updateFilterGroup(definition, groupId, (group) => ({
    ...group,
    children: [...group.children, createNodeTableFilterGroup(fields)],
  }));
}

export function removeNodeTableFilterItem(definition: NodeTableFilterDefinition, itemId: string) {
  return removeFilterItem(definition, itemId, true) ?? createBlankNodeTableFilterDefinition();
}

export function updateNodeTableFilterCombination(
  definition: NodeTableFilterDefinition,
  groupId: string,
  combination: NodeTableFilterCombination,
) {
  return updateFilterGroup(definition, groupId, (group) => ({ ...group, combination }));
}

export function updateNodeTableFilterCondition(
  definition: NodeTableFilterDefinition,
  conditionId: string,
  update: Partial<NodeTableFilterCondition>,
) {
  return updateFilterCondition(definition, conditionId, update);
}

export function isNodeTableFilterGroup(item: NodeTableFilterItem): item is NodeTableFilterGroup {
  return "children" in item;
}

function validateFilterGroup(
  group: NodeTableFilterGroup,
  fieldsByPath: Map<string, NodeTableFilterField>,
  isRoot: boolean,
): NodeTableFilterValidationIssue[] {
  if (!isRoot && group.children.length === 0) {
    return [{ itemId: group.id, kind: "missing-value" }];
  }

  return group.children.flatMap((item) => {
    if (isNodeTableFilterGroup(item)) {
      return validateFilterGroup(item, fieldsByPath, false);
    }

    const condition = item;
    const field = fieldsByPath.get(condition.fieldPath);
    if (field === undefined) {
      return [{ itemId: condition.id, kind: "missing-field" }];
    }

    if (!getNodeTableFilterOperators(field).includes(condition.operator)) {
      return [{ itemId: condition.id, kind: "missing-value" }];
    }

    if (condition.operator === "exists") {
      return [];
    }

    if (condition.value === null) {
      if (field.kind === "link") {
        return [{ itemId: condition.id, kind: "invalid-value" }];
      }
      return condition.operator === "eq" || condition.operator === "neq"
        ? []
        : [{ itemId: condition.id, kind: "invalid-value" }];
    }

    if ((condition.operator === "eq" || condition.operator === "neq") && !supportsLiteralFilterValue(field)) {
      return [{ itemId: condition.id, kind: "invalid-value" }];
    }

    if (condition.operator === "size") {
      return typeof condition.value === "number" && Number.isInteger(condition.value) && condition.value >= 0
        ? []
        : [{ itemId: condition.id, kind: "invalid-size" }];
    }

    if (condition.operator === "in" || condition.operator === "nin") {
      if (!Array.isArray(condition.value) || condition.value.length === 0) {
        return [{ itemId: condition.id, kind: "missing-value" }];
      }
      if (field.kind === "array" && (field.itemKind === "number" || field.itemKind === "integer")) {
        const valid = condition.value.every((value) => (
          typeof value === "number" && Number.isFinite(value) && (field.itemKind !== "integer" || Number.isInteger(value))
        ));
        return valid ? [] : [{ itemId: condition.id, kind: "invalid-value" }];
      }
      return [];
    }

    const scalarKind = getNodeTableFilterScalarKind(field);
    if (scalarKind === "boolean") {
      return typeof condition.value === "boolean"
        ? []
        : [{ itemId: condition.id, kind: "missing-value" }];
    }

    if (scalarKind === "number") {
      const isInteger = field.inputKind === "integer" || field.itemKind === "integer";
      const valid =
        typeof condition.value === "number" &&
        Number.isFinite(condition.value) &&
        (!isInteger || Number.isInteger(condition.value));
      return valid ? [] : [{ itemId: condition.id, kind: "invalid-value" }];
    }

    if (typeof condition.value !== "string") {
      return [{ itemId: condition.id, kind: "missing-value" }];
    }

    if (condition.value.length === 0 && scalarKind === "string" && (condition.operator === "eq" || condition.operator === "neq")) {
      return [];
    }

    if (condition.value.trim().length === 0) {
      return [{ itemId: condition.id, kind: "missing-value" }];
    }

    if (condition.operator === "regex") {
      try {
        new RegExp(condition.value);
      } catch {
        return [{ itemId: condition.id, kind: "invalid-regex" }];
      }
    }

    return [];
  });
}

function collectFilterPaths(value: Record<string, unknown>, paths: Set<string>) {
  for (const [key, child] of Object.entries(value)) {
    if (key === "and" || key === "or" || key === "not") {
      if (Array.isArray(child)) {
        child.forEach((item) => {
          if (isRecord(item)) {
            collectFilterPaths(item, paths);
          }
        });
      }
      continue;
    }
    paths.add(key);
  }
}

function compileFilterGroup(group: NodeTableFilterGroup): Record<string, unknown> {
  const children: Array<Record<string, unknown>> = group.children
    .map((item) => isNodeTableFilterGroup(item) ? compileFilterGroup(item) : compileFilterCondition(item))
    .filter((item) => Object.keys(item).length > 0);

  if (children.length === 0) {
    return {};
  }

  if (children.length === 1 && group.combination !== "not") {
    return children[0] ?? {};
  }

  return { [group.combination]: children };
}

function compileFilterCondition(condition: NodeTableFilterCondition) {
  const fieldPath = condition.operator === "size" || condition.value === null
    ? condition.rawFieldPath
    : condition.fieldPath;
  return {
    [fieldPath]: { [condition.operator]: condition.value },
  };
}

type FilterFieldIndex = {
  byFilterPath: Map<string, NodeTableFilterField>;
  byRawPath: Map<string, NodeTableFilterField>;
};

function createFilterFieldIndex(fields: NodeTableFilterField[]): FilterFieldIndex {
  return {
    byFilterPath: new Map(fields.map((field) => [getNodeTableFilterFieldPath(field), field])),
    byRawPath: new Map(fields.map((field) => [field.path.join("."), field])),
  };
}

function parseFilterGroup(value: unknown, isRoot: boolean, fieldIndex: FilterFieldIndex): NodeTableFilterGroup | null {
  if (!isRecord(value)) {
    return null;
  }

  const entries = Object.entries(value);
  if (entries.length === 0) {
    return isRoot ? createBlankNodeTableFilterDefinition() : null;
  }

  const firstEntry = entries[0];
  if (entries.length === 1 && firstEntry !== undefined && isNodeTableFilterCombination(firstEntry[0])) {
    const [combination, rawChildren] = firstEntry;
    if (!Array.isArray(rawChildren) || rawChildren.length === 0) {
      return null;
    }

    const children = rawChildren.map((child) => parseFilterItem(child, fieldIndex)).filter((child): child is NodeTableFilterItem => child !== null);
    if (children.length !== rawChildren.length) {
      return null;
    }

    return {
      children,
      combination,
      id: isRoot ? "root" : createGroupId(),
    };
  }

  const children = entries.map(([fieldPath, condition]) => parseFilterCondition(fieldPath, condition, fieldIndex));
  if (children.some((child) => child === null)) {
    return null;
  }

  return {
    children: children.filter((child): child is NodeTableFilterCondition => child !== null),
    combination: "and",
    id: isRoot ? "root" : createGroupId(),
  };
}

function parseFilterItem(value: unknown, fieldIndex: FilterFieldIndex): NodeTableFilterItem | null {
  if (!isRecord(value) || Object.keys(value).length !== 1) {
    return null;
  }
  const [fieldPath, condition] = Object.entries(value)[0] ?? [];
  if (typeof fieldPath !== "string") {
    return null;
  }
  if (!isNodeTableFilterCombination(fieldPath)) {
    return parseFilterCondition(fieldPath, condition, fieldIndex);
  }
  return parseFilterGroup(value, false, fieldIndex);
}

function parseFilterCondition(
  fieldPath: string,
  value: unknown,
  fieldIndex: FilterFieldIndex,
): NodeTableFilterCondition | null {
  if (isNodeTableFilterCombination(fieldPath) || fieldPath.length === 0) {
    return null;
  }

  if (isFilterValue(value)) {
    return createParsedFilterCondition(fieldPath, "eq", value, fieldIndex);
  }

  if (!isRecord(value) || Object.keys(value).length !== 1) {
    return null;
  }

  const entry = Object.entries(value)[0];
  if (entry === undefined) {
    return null;
  }
  const [operator, operand] = entry;
  if (!isBackendNodeTableFilterOperator(operator) || !isFilterValue(operand)) {
    return null;
  }
  return createParsedFilterCondition(fieldPath, operator, operand, fieldIndex);
}

function createParsedFilterCondition(
  fieldPath: string,
  operator: NodeTableFilterOperator,
  value: NodeTableFilterCondition["value"],
  fieldIndex: FilterFieldIndex,
): NodeTableFilterCondition | null {
  const field = fieldIndex.byFilterPath.get(fieldPath);
  const rawField = fieldIndex.byRawPath.get(fieldPath);
  if (operator === "size" && rawField !== undefined && getNodeTableFilterOperators(rawField).includes("size")) {
    return {
      fieldPath: getNodeTableFilterFieldPath(rawField),
      id: createConditionId(),
      operator,
      rawFieldPath: rawField.path.join("."),
      value,
    };
  }

  if (value === null && (operator === "eq" || operator === "neq")) {
    if (rawField === undefined) {
      return null;
    }
    return {
      fieldPath: getNodeTableFilterFieldPath(rawField),
      id: createConditionId(),
      operator,
      rawFieldPath: rawField.path.join("."),
      value,
    };
  }

  return {
    fieldPath,
    id: createConditionId(),
    operator,
    rawFieldPath: field?.path.join(".") ?? fieldPath,
    value,
  };
}

function isBackendNodeTableFilterOperator(value: string): value is NodeTableFilterOperator {
  return ["eq", "neq", "gt", "gte", "lt", "lte", "in", "nin", "exists", "size", "regex"].includes(value);
}

function isFilterValue(value: unknown): value is NodeTableFilterCondition["value"] {
  if (value === null) {
    return true;
  }
  if (typeof value === "boolean" || typeof value === "number" || typeof value === "string") {
    return true;
  }
  return Array.isArray(value) && value.every((item) => typeof item === "boolean" || typeof item === "number" || typeof item === "string");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNodeTableFilterCombination(value: string): value is NodeTableFilterCombination {
  return value === "and" || value === "or" || value === "not";
}

export function supportsLiteralFilterValue(field: NodeTableFilterField) {
  return getNodeTableFilterScalarKind(field) !== null || field.kind === "link";
}

export function getNodeTableFilterScalarKind(field: NodeTableFilterField): NodeTableFilterScalarKind | null {
  if (field.kind === "array") {
    switch (field.itemKind) {
      case "boolean":
        return "boolean";
      case "date":
        return "date";
      case "datetime":
        return "datetime";
      case "number":
      case "integer":
        return "number";
      case "string":
      case "text":
        return "string";
      default:
        return null;
    }
  }

  switch (field.kind) {
    case "boolean":
    case "date":
    case "datetime":
    case "number":
    case "string":
      return field.kind;
    default:
      return null;
  }
}

function updateFilterGroup(
  group: NodeTableFilterGroup,
  groupId: string,
  update: (group: NodeTableFilterGroup) => NodeTableFilterGroup,
): NodeTableFilterGroup {
  if (group.id === groupId) {
    return update(group);
  }

  return {
    ...group,
    children: group.children.map((item) => (
      isNodeTableFilterGroup(item) ? updateFilterGroup(item, groupId, update) : item
    )),
  };
}

function updateFilterCondition(
  group: NodeTableFilterGroup,
  conditionId: string,
  update: Partial<NodeTableFilterCondition>,
): NodeTableFilterGroup {
  return {
    ...group,
    children: group.children.map((item) => {
      if (isNodeTableFilterGroup(item)) {
        return updateFilterCondition(item, conditionId, update);
      }
      return item.id === conditionId ? { ...item, ...update } : item;
    }),
  };
}

function removeFilterItem(
  group: NodeTableFilterGroup,
  itemId: string,
  isRoot: boolean,
): NodeTableFilterGroup | null {
  if (group.id === itemId && !isRoot) {
    return null;
  }

  const children: NodeTableFilterItem[] = [];
  for (const item of group.children) {
    if (item.id === itemId) {
      continue;
    }
    if (!isNodeTableFilterGroup(item)) {
      children.push(item);
      continue;
    }
    const nextGroup = removeFilterItem(item, itemId, false);
    if (nextGroup !== null && nextGroup.children.length > 0) {
      children.push(nextGroup);
    }
  }

  if (!isRoot && children.length === 0) {
    return null;
  }
  return { ...group, children };
}

export function getNodeTableFilterFieldPath(field: NodeTableFilterField) {
  return getNodeTableFieldPath(field);
}

function createConditionId() {
  return `filter-${crypto.randomUUID()}`;
}

function createGroupId() {
  return `filter-group-${crypto.randomUUID()}`;
}
