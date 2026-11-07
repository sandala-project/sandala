import { useMemo, useState, type ReactNode } from "react";
import { Button } from "../../components/Button";
import { ChipRemoveButton } from "../../components/ChipRemoveButton";
import { IconButton } from "../../components/IconButton";
import { OverlayDialog } from "../../components/OverlayDialog";
import { OverlayCloseButton } from "../../components/OverlayCloseButton";
import { Select } from "../../components/Select";
import { useI18n } from "../../providers/I18nProvider";
import type { NodeDocument } from "./api";
import { NodeLinkSelect } from "./NodeLinkSelect";
import {
  appendNodeTableFilterCondition,
  appendNodeTableFilterGroup,
  compileNodeTableFilter,
  createBlankNodeTableFilterDefinition,
  createEmptyNodeTableFilterDefinition,
  getNodeTableFilterFieldPath,
  getDefaultFilterValue,
  getNodeTableFilterScalarKind,
  getNodeTableFilterOperators,
  isNodeTableFilterGroup,
  parseNodeTableFilterDefinition,
  removeNodeTableFilterItem,
  supportsLiteralFilterValue,
  updateNodeTableFilterCombination,
  updateNodeTableFilterCondition,
  validateNodeTableFilterDefinition,
  type NodeTableFilterCondition,
  type NodeTableFilter,
  type NodeTableFilterDefinition,
  type NodeTableFilterField,
  type NodeTableFilterGroup,
  type NodeTableFilterOperator,
} from "./nodeTableFilter";

type NodeTableFilterOverlayProps = {
  filter: NodeTableFilter | null;
  fields: NodeTableFilterField[];
  moduleName: string;
  onApply: (filter: NodeTableFilter | null) => void;
  onClose: () => void;
};

export function NodeTableFilterOverlay({ filter, fields, moduleName, onApply, onClose }: NodeTableFilterOverlayProps) {
  const { t } = useI18n();
  const [mode, setMode] = useState<"json" | "visual">(filter?.mode ?? "visual");
  const [draft, setDraft] = useState(() => cloneDefinition(getInitialVisualDefinition(filter, fields)));
  const [rawJson, setRawJson] = useState(() => filter?.mode === "json" ? filter.raw : "");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [jsonError, setJsonError] = useState<string | null>(null);
  const fieldsByPath = useMemo(
    () => new Map(fields.map((field) => [getNodeTableFilterFieldPath(field), field])),
    [fields],
  );
  const fieldOptions = useMemo(
    () => fields.map((field) => ({ label: field.label, value: getNodeTableFilterFieldPath(field) })),
    [fields],
  );

  function updateCondition(conditionId: string, update: Partial<NodeTableFilterCondition>) {
    setDraft((current) => updateNodeTableFilterCondition(current, conditionId, update));
    setErrors((current) => {
      const next = { ...current };
      delete next[conditionId];
      return next;
    });
  }

  function handleFieldChange(condition: NodeTableFilterCondition, fieldPath: string) {
    const nextField = fieldsByPath.get(fieldPath);
    if (nextField === undefined) {
      return;
    }
    const operator = getNodeTableFilterOperators(nextField)[0] ?? "exists";
    updateCondition(condition.id, {
      fieldPath,
      operator,
      rawFieldPath: nextField.path.join("."),
      value: getDefaultFilterValue(nextField, operator),
    });
  }

  function handleApply() {
    if (mode === "json") {
      const parsed = parseJsonFilter(rawJson);
      if (parsed === null) {
        setJsonError(t("pages.nodes.table.filter.validation.invalidJson"));
        return;
      }
      onApply({ filter: parsed, mode: "json", raw: rawJson });
      onClose();
      return;
    }

    const validationIssues = validateNodeTableFilterDefinition(draft, fields);
    if (validationIssues.length > 0) {
      setErrors(Object.fromEntries(validationIssues.map((issue) => [issue.itemId, t(`pages.nodes.table.filter.validation.${issue.kind}`)])));
      return;
    }
    onApply({ definition: draft, mode: "visual" });
    onClose();
  }

  function switchToJson() {
    if (mode === "json") {
      return;
    }
    setRawJson(JSON.stringify(compileNodeTableFilter(draft), null, 2));
    setJsonError(null);
    setMode("json");
  }

  function switchToVisual() {
    if (mode === "visual") {
      return;
    }
    if (rawJson.trim().length === 0) {
      setDraft(createBlankNodeTableFilterDefinition());
      setErrors({});
      setJsonError(null);
      setMode("visual");
      return;
    }
    const parsed = parseJsonFilter(rawJson);
    if (parsed === null) {
      setJsonError(t("pages.nodes.table.filter.validation.invalidJson"));
      return;
    }

    const parsedDefinition = parseNodeTableFilterDefinition(parsed, fields);
    if (parsedDefinition === null) {
      setJsonError(t("pages.nodes.table.filter.validation.unsupportedJson"));
      return;
    }

    setDraft(parsedDefinition);
    setErrors({});
    setJsonError(null);
    setMode("visual");
  }

  return (
    <OverlayDialog
      ariaLabel={t("pages.nodes.table.filter.title")}
      className="overlay-dialog-node-table-filter"
      onClose={onClose}
    >
      <div className="nodes-table-filter-header">
        <div className="nodes-table-filter-title">
          <strong>{t("pages.nodes.table.filter.title")}</strong>
          <div className="nodes-table-filter-mode-switch">
            <button
              className={mode === "visual" ? "is-active" : ""}
              onClick={switchToVisual}
              type="button"
            >
              {t("pages.nodes.table.filter.visual")}
            </button>
            <button
              className={mode === "json" ? "is-active" : ""}
              onClick={switchToJson}
              type="button"
            >
              {t("pages.nodes.table.filter.json")}
            </button>
          </div>
        </div>
        <OverlayCloseButton onClick={onClose} />
      </div>
      <div className="nodes-table-filter-body">
        {mode === "visual" ? (
          <FilterGroupEditor
            errors={errors}
            fieldOptions={fieldOptions}
            fields={fields}
            fieldsByPath={fieldsByPath}
            group={draft}
            isRoot
            moduleName={moduleName}
            onAddCondition={(groupId) => {
              const firstField = fields[0];
              if (firstField !== undefined) {
                setDraft((current) => appendNodeTableFilterCondition(current, groupId, firstField));
              }
            }}
            onAddGroup={(groupId) => setDraft((current) => appendNodeTableFilterGroup(current, groupId, fields))}
            onRemoveItem={(itemId) => setDraft((current) => removeNodeTableFilterItem(current, itemId))}
            onUpdateCombination={(groupId, combination) => setDraft((current) => updateNodeTableFilterCombination(current, groupId, combination))}
            onUpdateCondition={updateCondition}
            onUpdateField={handleFieldChange}
          />
        ) : (
          <label className="field nodes-table-filter-json">
            <span className="field-label">{t("pages.nodes.table.filter.json")}</span>
            <textarea
              className="field-control"
              onChange={(event) => {
                setRawJson(event.target.value);
                setJsonError(null);
              }}
              spellCheck={false}
              value={rawJson}
            />
            {jsonError ? <span className="field-error">{jsonError}</span> : null}
          </label>
        )}
      </div>
      <div className="nodes-table-filter-footer">
        <Button
          disabled={mode === "visual" ? draft.children.length === 0 : rawJson.trim().length === 0}
          kind="ghost"
          onClick={() => {
            onApply(null);
            onClose();
          }}
          type="button"
        >
          {t("pages.nodes.table.filter.clear")}
        </Button>
        <div className="nodes-table-filter-footer-actions">
          <Button kind="ghost" onClick={onClose} type="button">
            {t("common.cancel")}
          </Button>
          <Button onClick={handleApply} type="button">
            {t("common.apply")}
          </Button>
        </div>
      </div>
    </OverlayDialog>
  );
}

function FilterGroupEditor(args: {
  errors: Record<string, string>;
  fieldOptions: { label: string; value: string }[];
  fields: NodeTableFilterField[];
  fieldsByPath: Map<string, NodeTableFilterField>;
  group: NodeTableFilterGroup;
  isRoot: boolean;
  moduleName: string;
  onAddCondition: (groupId: string) => void;
  onAddGroup: (groupId: string) => void;
  onRemoveItem: (itemId: string) => void;
  onUpdateCombination: (groupId: string, combination: NodeTableFilterDefinition["combination"]) => void;
  onUpdateCondition: (conditionId: string, update: Partial<NodeTableFilterCondition>) => void;
  onUpdateField: (condition: NodeTableFilterCondition, fieldPath: string) => void;
}) {
  const { t } = useI18n();
  const groupPrefix = t(args.isRoot ? "pages.nodes.table.filter.showRecords" : "pages.nodes.table.filter.matchConditions");

  return (
    <div className={`nodes-table-filter-group ${args.isRoot ? "is-root" : ""}`.trim()}>
      <div className="nodes-table-filter-group-header">
        <div className="nodes-table-filter-combination">
          <span>{groupPrefix}</span>
          <Select
            onChange={(combination) => args.onUpdateCombination(args.group.id, combination as NodeTableFilterDefinition["combination"])}
            options={[
              { label: t("pages.nodes.table.filter.allConditions"), value: "and" },
              { label: t("pages.nodes.table.filter.anyCondition"), value: "or" },
              { label: t("pages.nodes.table.filter.noConditions"), value: "not" },
            ]}
            value={args.group.combination}
          />
        </div>
        {!args.isRoot ? (
          <IconButton
            icon="trash"
            label={t("common.delete")}
            onClick={() => args.onRemoveItem(args.group.id)}
            size="regular"
          />
        ) : null}
      </div>

      {args.group.children.length === 0 ? (
        <div className="nodes-table-filter-empty">{t("pages.nodes.table.filter.empty")}</div>
      ) : (
        <div className="nodes-table-filter-items">
          {args.group.children.map((item) => (
            isNodeTableFilterGroup(item) ? (
              <FilterGroupEditor
                errors={args.errors}
                fieldOptions={args.fieldOptions}
                fields={args.fields}
                fieldsByPath={args.fieldsByPath}
                group={item}
                isRoot={false}
                key={item.id}
                moduleName={args.moduleName}
                onAddCondition={args.onAddCondition}
                onAddGroup={args.onAddGroup}
                onRemoveItem={args.onRemoveItem}
                onUpdateCombination={args.onUpdateCombination}
                onUpdateCondition={args.onUpdateCondition}
                onUpdateField={args.onUpdateField}
              />
            ) : (
              <FilterConditionEditor
                condition={item}
                error={args.errors[item.id]}
                field={args.fieldsByPath.get(item.fieldPath) ?? null}
                fieldOptions={args.fieldOptions}
                key={item.id}
                moduleName={args.moduleName}
                onRemove={() => args.onRemoveItem(item.id)}
                onUpdate={args.onUpdateCondition}
                onUpdateField={args.onUpdateField}
              />
            )
          ))}
        </div>
      )}

      <div className="nodes-table-filter-group-actions">
        <Button
          disabled={args.fields.length === 0}
          kind="ghost"
          onClick={() => args.onAddCondition(args.group.id)}
          type="button"
        >
          {t("pages.nodes.table.filter.addCondition")}
        </Button>
        <Button
          disabled={args.fields.length === 0}
          kind="ghost"
          onClick={() => args.onAddGroup(args.group.id)}
          type="button"
        >
          {t("pages.nodes.table.filter.addGroup")}
        </Button>
      </div>
    </div>
  );
}

function getInitialVisualDefinition(filter: NodeTableFilter | null, fields: NodeTableFilterField[]) {
  if (filter?.mode === "visual") {
    return filter.definition;
  }
  if (filter?.mode === "json") {
    return parseNodeTableFilterDefinition(filter.filter, fields) ?? createEmptyNodeTableFilterDefinition(fields);
  }
  return createEmptyNodeTableFilterDefinition(fields);
}

function parseJsonFilter(raw: string): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(raw);
    return typeof value === "object" && value !== null && !Array.isArray(value)
      ? value as Record<string, unknown>
      : null;
  } catch {
    return null;
  }
}

function FilterConditionEditor(args: {
  condition: NodeTableFilterCondition;
  error?: string;
  field: NodeTableFilterField | null;
  fieldOptions: { label: string; value: string }[];
  moduleName: string;
  onRemove: () => void;
  onUpdate: (conditionId: string, update: Partial<NodeTableFilterCondition>) => void;
  onUpdateField: (condition: NodeTableFilterCondition, fieldPath: string) => void;
}) {
  const { t } = useI18n();

  return (
    <div className="nodes-table-filter-condition">
      <span className="nodes-table-filter-where">{t("pages.nodes.table.filter.where")}</span>
      <Select
        onChange={(fieldPath) => args.onUpdateField(args.condition, fieldPath)}
        options={args.fieldOptions}
        placeholder={t("pages.nodes.table.filter.selectField")}
        value={args.condition.fieldPath}
      />
      {args.field === null ? null : (
        <>
          <Select
            onChange={(operator) => args.onUpdate(args.condition.id, {
              operator: operator as NodeTableFilterOperator,
              value: getDefaultFilterValue(args.field!, operator as NodeTableFilterOperator),
            })}
            options={getNodeTableFilterOperators(args.field).map((operator) => ({
              label: t(`pages.nodes.table.filter.operator.${operator}`),
              value: operator,
            }))}
            value={args.condition.operator}
          />
          <FilterValueControl
            error={args.error}
            field={args.field}
            moduleName={args.moduleName}
            onChange={(value) => args.onUpdate(args.condition.id, { value })}
            operator={args.condition.operator}
            value={args.condition.value}
          />
        </>
      )}
      <IconButton
        icon="trash"
        label={t("common.delete")}
        onClick={args.onRemove}
        size="regular"
      />
    </div>
  );
}

function FilterValueControl(args: {
  error?: string;
  field: NodeTableFilterField;
  moduleName: string;
  onChange: (value: NodeTableFilterCondition["value"]) => void;
  operator: NodeTableFilterOperator;
  value: NodeTableFilterCondition["value"];
}) {
  const { t } = useI18n();
  const valueLabel = t("pages.nodes.table.filter.value");

  if (isNullComparableOperator(args.operator) && args.value === null) {
    return (
      <NullFilterValue
        onUseValue={supportsLiteralFilterValue(args.field)
          ? () => args.onChange(getDefaultFilterValue(args.field, args.operator))
          : undefined}
      />
    );
  }

  if (args.operator === "exists") {
    return (
      <Select
        error={args.error}
        onChange={(value) => args.onChange(value === "true")}
        options={[
          { label: t("common.true"), value: "true" },
          { label: t("common.false"), value: "false" },
        ]}
        value={String(Boolean(args.value))}
      />
    );
  }

  if (args.operator === "size") {
    return (
      <label className="field">
        <input
          className="field-control"
          min="0"
          onChange={(event) => args.onChange(event.target.value === "" ? "" : Number(event.target.value))}
          type="number"
          value={typeof args.value === "number" || typeof args.value === "string" ? args.value : ""}
        />
        {args.error ? <span className="field-error">{args.error}</span> : null}
      </label>
    );
  }

  if (args.field.kind === "link" && args.field.linkTargetModule !== null) {
    return withNullValueControl(args, (
      <NodeLinkSelect
        canWrite
        error={args.error}
        hideLabel
        label={valueLabel}
        mode="single"
        onBlur={() => undefined}
        onChange={(value) => args.onChange(toSingleReferenceId(value))}
        placeholder={t("pages.nodes.table.filter.selectNode")}
        resolveSelectedReferences
        targetEntities={args.field.linkTargetEntities}
        targetModule={args.field.linkTargetModule}
        value={typeof args.value === "string" ? args.value : ""}
      />
    ));
  }

  if (args.field.kind === "link-array" && args.field.linkTargetModule !== null) {
    return (
      <NodeLinkSelect
        canWrite
        error={args.error}
        hideLabel
        label={valueLabel}
        mode="multiple"
        onBlur={() => undefined}
        onChange={(value) => args.onChange(toReferenceIds(value))}
        placeholder={t("pages.nodes.table.filter.selectNodes")}
        resolveSelectedReferences
        targetEntities={args.field.linkTargetEntities}
        targetModule={args.field.linkTargetModule}
        value={Array.isArray(args.value) ? args.value : []}
      />
    );
  }

  const scalarKind = getNodeTableFilterScalarKind(args.field);
  if (scalarKind === "boolean") {
    return withNullValueControl(args, (
      <Select
        error={args.error}
        onChange={(value) => args.onChange(value === "true")}
        options={[
          { label: t("common.true"), value: "true" },
          { label: t("common.false"), value: "false" },
        ]}
        value={String(Boolean(args.value))}
      />
    ));
  }

  const enumValues = args.field.kind === "array" ? args.field.itemEnumValues : args.field.enumValues;
  if (enumValues.length > 0 && (args.operator === "eq" || args.operator === "neq")) {
    return withNullValueControl(args, (
      <Select
        error={args.error}
        onChange={args.onChange}
        options={enumValues.map((value) => ({ label: value, value }))}
        placeholder={t("pages.nodes.table.filter.selectValue")}
        value={typeof args.value === "string" ? args.value : ""}
      />
    ));
  }

  return withNullValueControl(args, (
    <label className="field">
      <input
        className="field-control"
        onChange={(event) => args.onChange(normalizeScalarValue(args.field, event.target.value))}
        placeholder={t("pages.nodes.table.filter.enterValue")}
        type={getInputType(args.field)}
        value={toInputValue(args.field, args.value)}
      />
      {args.error ? <span className="field-error">{args.error}</span> : null}
    </label>
  ));
}

function isNullComparableOperator(operator: NodeTableFilterOperator) {
  return operator === "eq" || operator === "neq";
}

function withNullValueControl(
  args: Pick<Parameters<typeof FilterValueControl>[0], "field" | "onChange" | "operator">,
  control: ReactNode,
) {
  if (args.field.kind === "link" || !isNullComparableOperator(args.operator) || !supportsLiteralFilterValue(args.field)) {
    return control;
  }

  return (
    <div className="nodes-table-filter-value-control">
      {control}
      <Button kind="ghost" onClick={() => args.onChange(null)} type="button">null</Button>
    </div>
  );
}

function NullFilterValue({ onUseValue }: { onUseValue?: () => void }) {
  const { t } = useI18n();

  return (
    <div className="nodes-table-filter-null-value">
      <code>null</code>
      {onUseValue ? (
        <ChipRemoveButton
          aria-label={t("pages.nodes.table.filter.enterValue")}
          className="nodes-table-filter-null-clear"
          onClick={onUseValue}
          title={t("pages.nodes.table.filter.enterValue")}
        />
      ) : null}
    </div>
  );
}

function cloneDefinition(definition: NodeTableFilterDefinition): NodeTableFilterDefinition {
  return {
    children: definition.children.map(cloneFilterItem),
    combination: definition.combination,
    id: definition.id,
  };
}

function cloneFilterItem(item: NodeTableFilterDefinition["children"][number]): NodeTableFilterDefinition["children"][number] {
  if (isNodeTableFilterGroup(item)) {
    return {
      ...item,
      children: item.children.map(cloneFilterItem),
    };
  }
  return {
    ...item,
    value: Array.isArray(item.value) ? [...item.value] : item.value,
  };
}

function getInputType(field: NodeTableFilterField) {
  const scalarKind = getNodeTableFilterScalarKind(field);
  if (scalarKind === "number") {
    return "number";
  }
  if (scalarKind === "date") {
    return "date";
  }
  if (scalarKind === "datetime") {
    return "datetime-local";
  }
  return "text";
}

function normalizeScalarValue(field: NodeTableFilterField, value: string) {
  const scalarKind = getNodeTableFilterScalarKind(field);
  if (scalarKind === "number") {
    return value === "" ? "" : Number(value);
  }
  if (scalarKind === "datetime") {
    return value.length === 0 ? "" : `${value}:00Z`;
  }
  return value;
}

function toInputValue(field: NodeTableFilterField, value: NodeTableFilterCondition["value"]) {
  if (typeof value !== "string" && typeof value !== "number") {
    return "";
  }
  if (getNodeTableFilterScalarKind(field) === "datetime" && typeof value === "string") {
    return value.replace(/:00(?:\.\d+)?Z$/, "");
  }
  return value;
}

function toSingleReferenceId(value: NodeDocument | NodeDocument[] | null) {
  if (Array.isArray(value) || value === null) {
    return "";
  }
  return typeof value.id === "string" ? value.id : "";
}

function toReferenceIds(value: NodeDocument | NodeDocument[] | null) {
  return (Array.isArray(value) ? value : value === null ? [] : [value])
    .map((node) => (typeof node.id === "string" ? node.id : ""))
    .filter(Boolean);
}
