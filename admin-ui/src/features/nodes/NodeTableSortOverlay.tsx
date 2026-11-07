import { useMemo, useState } from "react";
import { Button } from "../../components/Button";
import { IconButton } from "../../components/IconButton";
import { OverlayDialog } from "../../components/OverlayDialog";
import { OverlayCloseButton } from "../../components/OverlayCloseButton";
import { Select } from "../../components/Select";
import { useI18n } from "../../providers/I18nProvider";
import { getNodeTableFieldPath, type NodeTableField } from "./nodeTableFields";
import {
  compileNodeTableSort,
  createEmptyNodeTableSortDefinition,
  createNodeTableSortRule,
  isNodeTableSortDirection,
  parseNodeTableSortDefinition,
  type NodeTableSort,
  type NodeTableSortDefinition,
  type NodeTableSortRule,
} from "./nodeTableSort";

export function NodeTableSortOverlay(args: {
  fields: NodeTableField[];
  onApply: (sort: NodeTableSort | null) => void;
  onClose: () => void;
  sort: NodeTableSort | null;
}) {
  const { t } = useI18n();
  const [mode, setMode] = useState<"json" | "visual">(args.sort?.mode ?? "visual");
  const [draft, setDraft] = useState(() => getInitialDefinition(args.sort, args.fields));
  const [rawJson, setRawJson] = useState(() => args.sort?.mode === "json" ? args.sort.raw : "");
  const [jsonError, setJsonError] = useState<string | null>(null);
  const fieldOptions = useMemo(() => args.fields.map((field) => ({ label: field.label, value: getNodeTableFieldPath(field) })), [args.fields]);

  function apply() {
    if (mode === "visual") {
      args.onApply(draft.rules.length === 0 ? null : { definition: draft, mode: "visual" });
      args.onClose();
      return;
    }

    const parsed = parseJsonSort(rawJson);
    if (parsed === null) {
      setJsonError(t("pages.nodes.table.sort.validation.invalidJson"));
      return;
    }
    args.onApply(Object.keys(parsed).length === 0 ? null : { mode: "json", raw: rawJson, sort: parsed });
    args.onClose();
  }

  function switchToJson() {
    if (mode === "json") {
      return;
    }
    setRawJson(JSON.stringify(compileNodeTableSort(draft), null, 2));
    setJsonError(null);
    setMode("json");
  }

  function switchToVisual() {
    const parsed = parseJsonSort(rawJson);
    if (rawJson.trim().length === 0) {
      setDraft(createEmptyNodeTableSortDefinition());
      setJsonError(null);
      setMode("visual");
      return;
    }
    if (parsed === null) {
      setJsonError(t("pages.nodes.table.sort.validation.invalidJson"));
      return;
    }
    const definition = parseNodeTableSortDefinition(parsed, args.fields);
    if (definition === null) {
      setJsonError(t("pages.nodes.table.sort.validation.unsupportedJson"));
      return;
    }
    setDraft(definition);
    setJsonError(null);
    setMode("visual");
  }

  return <OverlayDialog ariaLabel={t("pages.nodes.table.sort.title")} className="overlay-dialog-node-table-filter" onClose={args.onClose}>
    <div className="nodes-table-filter-header">
      <div className="nodes-table-filter-title">
        <strong>{t("pages.nodes.table.sort.title")}</strong>
        <div className="nodes-table-filter-mode-switch">
          <button className={mode === "visual" ? "is-active" : ""} onClick={switchToVisual} type="button">{t("pages.nodes.table.filter.visual")}</button>
          <button className={mode === "json" ? "is-active" : ""} onClick={switchToJson} type="button">{t("pages.nodes.table.filter.json")}</button>
        </div>
      </div>
      <OverlayCloseButton onClick={args.onClose} />
    </div>
    <div className="nodes-table-filter-body">
      {mode === "visual" ? <div className="nodes-table-sort-rules">
        {draft.rules.map((rule, index) => <SortRuleEditor
          fieldOptions={fieldOptions}
          key={rule.id}
          onMove={(offset) => setDraft((current) => moveRule(current, rule.id, offset))}
          onRemove={() => setDraft((current) => ({ ...current, rules: current.rules.filter((item) => item.id !== rule.id) }))}
          onUpdate={(update) => setDraft((current) => updateRule(current, rule.id, update))}
          position={index}
          rule={rule}
          total={draft.rules.length}
        />)}
        {draft.rules.length === 0 ? <div className="nodes-table-filter-empty">{t("pages.nodes.table.sort.empty")}</div> : null}
        <Button disabled={args.fields.length === 0} kind="ghost" onClick={() => {
          const field = args.fields.find((item) => !draft.rules.some((rule) => rule.fieldPath === getNodeTableFieldPath(item)));
          if (field !== undefined) setDraft((current) => ({ ...current, rules: [...current.rules, createNodeTableSortRule(field)] }));
        }} type="button">{t("pages.nodes.table.sort.addRule")}</Button>
      </div> : <label className="field nodes-table-filter-json">
        <span className="field-label">{t("pages.nodes.table.filter.json")}</span>
        <textarea className="field-control" onChange={(event) => { setRawJson(event.target.value); setJsonError(null); }} spellCheck={false} value={rawJson} />
        {jsonError ? <span className="field-error">{jsonError}</span> : null}
      </label>}
    </div>
    <div className="nodes-table-filter-footer">
      <Button disabled={mode === "visual" ? draft.rules.length === 0 : rawJson.trim().length === 0} kind="ghost" onClick={() => { args.onApply(null); args.onClose(); }} type="button">{t("pages.nodes.table.filter.clear")}</Button>
      <div className="nodes-table-filter-footer-actions">
        <Button kind="ghost" onClick={args.onClose} type="button">{t("common.cancel")}</Button>
        <Button onClick={apply} type="button">{t("common.apply")}</Button>
      </div>
    </div>
  </OverlayDialog>;
}

function SortRuleEditor(args: { fieldOptions: { label: string; value: string }[]; onMove: (offset: number) => void; onRemove: () => void; onUpdate: (update: Partial<NodeTableSortRule>) => void; position: number; rule: NodeTableSortRule; total: number }) {
  const { t } = useI18n();
  return <div className="nodes-table-sort-rule">
    <Select onChange={(fieldPath) => args.onUpdate({ fieldPath })} options={args.fieldOptions} value={args.rule.fieldPath} />
    <Select onChange={(direction) => args.onUpdate({ direction: direction as NodeTableSortRule["direction"] })} options={[{ label: t("pages.nodes.table.sort.ascending"), value: "asc" }, { label: t("pages.nodes.table.sort.descending"), value: "desc" }]} value={args.rule.direction} />
    <div className="nodes-table-sort-rule-actions">
      <IconButton disabled={args.position === 0} icon="arrow-up" label={t("pages.nodes.table.sort.moveUp")} onClick={() => args.onMove(-1)} size="regular" />
      <IconButton disabled={args.position === args.total - 1} icon="arrow-down" label={t("pages.nodes.table.sort.moveDown")} onClick={() => args.onMove(1)} size="regular" />
      <IconButton icon="x" label={t("common.remove")} onClick={args.onRemove} size="regular" />
    </div>
  </div>;
}

function getInitialDefinition(sort: NodeTableSort | null, fields: NodeTableField[]) {
  if (sort?.mode === "visual") return sort.definition;
  if (sort?.mode === "json") return parseNodeTableSortDefinition(sort.sort, fields) ?? createEmptyNodeTableSortDefinition();
  return createEmptyNodeTableSortDefinition();
}

function moveRule(definition: NodeTableSortDefinition, id: string, offset: number): NodeTableSortDefinition {
  const index = definition.rules.findIndex((rule) => rule.id === id);
  const nextIndex = index + offset;
  if (index < 0 || nextIndex < 0 || nextIndex >= definition.rules.length) return definition;
  const rules = [...definition.rules];
  [rules[index], rules[nextIndex]] = [rules[nextIndex]!, rules[index]!];
  return { ...definition, rules };
}

function updateRule(definition: NodeTableSortDefinition, id: string, update: Partial<NodeTableSortRule>): NodeTableSortDefinition {
  const nextRule = definition.rules.find((rule) => rule.id === id);
  if (nextRule === undefined) return definition;
  const nextFieldPath = update.fieldPath ?? nextRule.fieldPath;
  if (definition.rules.some((rule) => rule.id !== id && rule.fieldPath === nextFieldPath)) return definition;
  return { ...definition, rules: definition.rules.map((rule) => rule.id === id ? { ...rule, ...update } : rule) };
}

function parseJsonSort(raw: string): Record<string, "asc" | "desc"> | null {
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return null;
    if (!Object.values(parsed).every(isNodeTableSortDirection)) return null;
    return parsed as Record<string, "asc" | "desc">;
  } catch {
    return null;
  }
}
