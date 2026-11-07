import { useQueries, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Button } from "../../components/Button";
import { Icon } from "../../components/Icon";
import { OverlayCloseButton } from "../../components/OverlayCloseButton";
import { OverlayDialog } from "../../components/OverlayDialog";
import { Spinner } from "../../components/Spinner";
import { EPHEMERAL_NODE_QUERY_OPTIONS } from "../../lib/queryOptions";
import { useI18n } from "../../providers/I18nProvider";
import { getChildNodes, getNode, getRootNodes, type NodeDocument } from "./api";
import { NodeDisplayLabel } from "./NodeDisplayLabel";

type NodeTreePickerOption = {
  isSelectable: boolean;
  label: string;
  value: null;
};

export function NodeTreePicker(args: {
  disabled?: boolean;
  emptyLabel: string;
  error?: string;
  isNodeSelectable: (node: NodeDocument) => boolean;
  label: string;
  moduleName: string;
  onChange: (value: string | null) => void;
  placeholder: string;
  rootOption?: NodeTreePickerOption;
  toggleLabel: string;
  value: string | null | undefined;
}) {
  const { t } = useI18n();
  const [isOpen, setIsOpen] = useState(false);
  const [selectedNode, setSelectedNode] = useState<{ moduleName: string; node: NodeDocument } | null>(null);
  const selectedNodeQuery = useQuery({
    ...EPHEMERAL_NODE_QUERY_OPTIONS,
    enabled:
      typeof args.value === "string" &&
      args.value.length > 0 &&
      (selectedNode?.moduleName !== args.moduleName || selectedNode.node.id !== args.value),
    queryKey: ["nodes", "tree-picker-selected", args.moduleName, args.value],
    queryFn: ({ signal }) => getNode(args.moduleName, args.value!, signal),
  });
  const selectedLabel = args.value === null
    ? args.rootOption?.label ?? args.placeholder
    : typeof args.value === "string"
      ? <NodeDisplayLabel moduleName={args.moduleName} node={selectedNode?.node ?? selectedNodeQuery.data ?? { id: args.value }} purpose="tree" />
      : args.placeholder;

  useEffect(() => {
    if (
      typeof args.value !== "string" ||
      selectedNode?.moduleName !== args.moduleName ||
      selectedNode.node.id !== args.value
    ) {
      setSelectedNode(null);
    }
  }, [args.moduleName, args.value, selectedNode]);

  return (
    <div className="field">
      <span className="field-label">{args.label}</span>
      <button className={`node-tree-picker-input ${args.disabled ? "is-disabled" : ""}`.trim()} disabled={args.disabled} onClick={() => setIsOpen(true)} type="button">
        {args.value === undefined ? selectedLabel : <span className="multi-value-chip multi-value-chip-link"><span>{selectedLabel}</span></span>}
      </button>
      {args.error ? <span className="field-error">{args.error}</span> : null}
      {isOpen ? (
        <NodeTreePickerDialog
          {...args}
          onClose={() => setIsOpen(false)}
          onSelect={(node) => {
            setSelectedNode(node === null ? null : { moduleName: args.moduleName, node });
            args.onChange(node === null ? null : String(node.id));
            setIsOpen(false);
          }}
          t={t}
        />
      ) : null}
    </div>
  );
}

function NodeTreePickerDialog(args: Parameters<typeof NodeTreePicker>[0] & {
  onClose: () => void;
  onSelect: (node: NodeDocument | null) => void;
  t: ReturnType<typeof useI18n>["t"];
}) {
  const [expandedNodeIds, setExpandedNodeIds] = useState<string[]>([]);
  const rootNodesQuery = useQuery({
    ...EPHEMERAL_NODE_QUERY_OPTIONS,
    queryKey: ["nodes", "tree-picker", args.moduleName, "root"],
    queryFn: ({ signal }) => getRootNodes(args.moduleName, signal),
  });
  const childQueries = useQueries({
    queries: expandedNodeIds.map((nodeId) => ({
      ...EPHEMERAL_NODE_QUERY_OPTIONS,
      queryKey: ["nodes", "tree-picker", args.moduleName, nodeId],
      queryFn: ({ signal }: { signal: AbortSignal }) => getChildNodes(args.moduleName, nodeId, signal),
    })),
  });
  const childrenByParentId = useMemo(
    () => new Map(expandedNodeIds.map((nodeId, index) => [nodeId, childQueries[index]?.data ?? []])),
    [childQueries, expandedNodeIds],
  );

  function toggle(nodeId: string) {
    setExpandedNodeIds((current) => {
      if (!current.includes(nodeId)) {
        return [...current, nodeId];
      }

      const collapsedIds = new Set([nodeId]);
      const pendingIds = [nodeId];
      while (pendingIds.length > 0) {
        const parentId = pendingIds.pop()!;
        for (const child of childrenByParentId.get(parentId) ?? []) {
          const childId = typeof child.id === "string" ? child.id : "";
          if (childId.length > 0 && !collapsedIds.has(childId)) {
            collapsedIds.add(childId);
            pendingIds.push(childId);
          }
        }
      }
      return current.filter((item) => !collapsedIds.has(item));
    });
  }

  return (
    <OverlayDialog ariaLabel={args.label} className="overlay-dialog-node-tree-picker" onClose={args.onClose}>
      <div className="field-overlay-header">
        <strong>{args.label}</strong>
        <OverlayCloseButton onClick={args.onClose} />
      </div>
      <div className="node-tree-picker-body">
        {args.rootOption !== undefined ? <PickerOptionRow option={args.rootOption} onSelect={() => args.onSelect(null)} selected={args.value === null} /> : null}
        {rootNodesQuery.isPending ? <div className="list-loading"><Spinner /></div> : null}
        {(rootNodesQuery.data ?? []).map((node) => (
          <TreePickerNode
            childrenByParentId={childrenByParentId}
            expandedNodeIds={expandedNodeIds}
            isNodeSelectable={args.isNodeSelectable}
            key={typeof node.id === "string" ? node.id : String(node.entity ?? "node")}
            moduleName={args.moduleName}
            node={node}
            onSelect={args.onSelect}
            onToggle={toggle}
            selectedId={typeof args.value === "string" ? args.value : null}
            toggleLabel={args.toggleLabel}
          />
        ))}
        {!rootNodesQuery.isPending && (rootNodesQuery.data ?? []).length === 0 ? <div className="node-tree-picker-empty">{args.emptyLabel}</div> : null}
      </div>
      <div className="field-overlay-footer">
        <div className="field-overlay-actions">
          <Button kind="ghost" onClick={args.onClose} type="button">{args.t("common.cancel")}</Button>
        </div>
      </div>
    </OverlayDialog>
  );
}

function PickerOptionRow(args: { onSelect: () => void; option: NodeTreePickerOption; selected: boolean }) {
  return <button
    className={`node-tree-picker-row ${args.option.isSelectable ? "" : "is-disabled"} ${args.selected ? "is-selected" : ""}`.trim()}
    disabled={!args.option.isSelectable}
    onClick={args.onSelect}
    type="button"
  >{args.option.label}</button>;
}

function TreePickerNode(args: {
  childrenByParentId: Map<string, NodeDocument[]>;
  expandedNodeIds: string[];
  isNodeSelectable: (node: NodeDocument) => boolean;
  moduleName: string;
  node: NodeDocument;
  onSelect: (node: NodeDocument) => void;
  onToggle: (nodeId: string) => void;
  selectedId: string | null;
  toggleLabel: string;
}) {
  const nodeId = typeof args.node.id === "string" ? args.node.id : "";
  const isExpanded = nodeId.length > 0 && args.expandedNodeIds.includes(nodeId);
  const children = nodeId.length > 0 ? args.childrenByParentId.get(nodeId) ?? [] : [];
  const eligible = nodeId.length > 0 && args.isNodeSelectable(args.node);

  return <div className="node-tree-picker-node">
    <div className="node-tree-picker-node-line">
      <button aria-label={args.toggleLabel} className="node-tree-picker-toggle" disabled={nodeId.length === 0} onClick={() => args.onToggle(nodeId)} type="button">
        <Icon className={`node-tree-picker-chevron ${isExpanded ? "is-expanded" : ""}`.trim()} name="chevron-right" size="tiny" weight="strong" />
      </button>
      <button
        className={`node-tree-picker-row ${eligible ? "" : "is-disabled"} ${args.selectedId === nodeId ? "is-selected" : ""}`.trim()}
        disabled={!eligible}
        onClick={() => args.onSelect(args.node)}
        type="button"
      ><NodeDisplayLabel moduleName={args.moduleName} node={args.node} purpose="tree" /></button>
    </div>
    {isExpanded ? <div className="node-tree-picker-children">{children.map((child, index) => <TreePickerNode {...args} key={typeof child.id === "string" ? child.id : `${String(child.entity ?? "node")}:${index}`} node={child} />)}</div> : null}
  </div>;
}
