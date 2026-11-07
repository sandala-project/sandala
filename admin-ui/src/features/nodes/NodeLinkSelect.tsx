import { useId, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { createPortal } from "react-dom";
import { ChipRemoveButton } from "../../components/ChipRemoveButton";
import { EPHEMERAL_NODE_QUERY_OPTIONS, SCHEMA_QUERY_OPTIONS } from "../../lib/queryOptions";
import { structureKeys } from "../../lib/queryKeys";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { localizeUnknownError } from "../../lib/errors";
import { usePopover, type PopoverPosition } from "../../components/usePopover";
import { resolveNodeDisplayLabel } from "./presentation";
import { NodeDisplayLabel } from "./NodeDisplayLabel";
import { getEntitySchema } from "../entities/api";
import { getLinkableNodesByIds, queryNodes, type NodeDocument } from "./api";
import { buildLinkSearchFilter } from "./linkSearch";

type NodeLinkSelectProps = {
  canWrite: boolean;
  error?: string;
  hideLabel?: boolean;
  label: ReactNode;
  mode: "multiple" | "single";
  onBlur: () => void;
  onChange: (value: NodeDocument | NodeDocument[] | null) => void;
  onOpenNode?: (node: NodeDocument, moduleName: string) => void;
  placeholder?: string;
  resolveSelectedReferences?: boolean;
  targetEntities: string[];
  targetModule: string;
  value: unknown;
};

export function NodeLinkSelect({
  canWrite,
  error,
  hideLabel = false,
  label,
  mode,
  onBlur,
  onChange,
  onOpenNode,
  placeholder,
  resolveSelectedReferences = false,
  targetEntities,
  targetModule,
  value,
}: NodeLinkSelectProps) {
  const labelId = useId();
  const controlRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const rawSelectedNodes = useMemo(
    () => coerceSelectedNodes(value, mode),
    [mode, value],
  );
  const unresolvedSelectedIds = useMemo(
    () => rawSelectedNodes
      .filter(isUnresolvedReference)
      .map((node) => (typeof node.id === "string" ? node.id : ""))
      .filter(Boolean),
    [rawSelectedNodes],
  );
  const selectedReferencesQuery = useQuery({
    ...EPHEMERAL_NODE_QUERY_OPTIONS,
    enabled:
      resolveSelectedReferences &&
      unresolvedSelectedIds.length > 0 &&
      targetModule.trim().length > 0,
    queryKey: [
      "nodes",
      "link-selected-references",
      targetModule,
      [...targetEntities].sort().join("|"),
      [...unresolvedSelectedIds].sort().join("|"),
    ],
    queryFn: ({ signal }) =>
      getLinkableNodesByIds({
        entityNames: targetEntities,
        ids: unresolvedSelectedIds,
        moduleName: targetModule,
        signal,
      }),
  });
  const selectedNodes = useMemo(
    () => mergeSelectedNodes(rawSelectedNodes, selectedReferencesQuery.data ?? []),
    [rawSelectedNodes, selectedReferencesQuery.data],
  );
  const selectedIds = useMemo(
    () => new Set(selectedNodes.map((node) => (typeof node.id === "string" ? node.id : "")).filter(Boolean)),
    [selectedNodes],
  );
  const selectedNodeIds = useMemo(() => [...selectedIds].sort(), [selectedIds]);

  const menuPosition = usePopover({
    anchorRef: controlRef,
    contentRef: menuRef,
    deps: [query, selectedNodes.length],
    isOpen,
    onClose: () => {
      setIsOpen(false);
      setQuery("");
      onBlur();
    },
  });

  return (
    <div className="field">
      {!hideLabel ? <span className="field-label" id={labelId}>{label}</span> : null}
      <div
        className={`multi-value-select ${!canWrite ? "is-disabled" : ""}`.trim()}
        ref={controlRef}
        onClick={() => {
          if (!canWrite) {
            return;
          }
          setIsOpen(true);
          inputRef.current?.focus();
        }}
        role="presentation"
      >
        <div className="multi-value-control">
          {selectedNodes.map((node, index) => {
            const nodeId = typeof node.id === "string" ? node.id : "";
            const nodeLabel = resolveNodeDisplayLabel(node);
            return (
              <span className="multi-value-chip multi-value-chip-link" key={nodeId || `${nodeLabel}:${index}`}>
                {onOpenNode !== undefined && isResolvedNode(node) ? (
                  <button
                    className="multi-value-link"
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      onOpenNode(node, targetModule);
                    }}
                    type="button"
                  ><NodeDisplayLabel moduleName={targetModule} node={node} purpose="reference" /></button>
                ) : <span><NodeDisplayLabel moduleName={targetModule} node={node} purpose="reference" /></span>}
                {canWrite ? (
                  <ChipRemoveButton
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      removeSelectedNode({ mode, nodeId, onChange, selectedNodes });
                    }}
                  />
                ) : null}
              </span>
            );
          })}
          <input
            aria-labelledby={labelId}
            className="multi-value-input"
            disabled={!canWrite}
            onChange={(event) => {
              setQuery(event.target.value);
              if (!isOpen) {
                setIsOpen(true);
              }
            }}
            onFocus={() => {
              if (canWrite) {
                setIsOpen(true);
              }
            }}
            placeholder={selectedNodes.length === 0 ? placeholder : ""}
            ref={inputRef}
            value={query}
          />
        </div>
      </div>
      {error ? <span className="field-error">{error}</span> : null}
      {isOpen && canWrite && menuPosition
        ? <NodeLinkSearchMenu
            inputRef={inputRef}
            menuPosition={menuPosition}
            menuRef={menuRef}
            mode={mode}
            onBlur={onBlur}
            onChange={onChange}
            onClose={() => {
              setQuery("");
              setIsOpen(false);
            }}
            query={query}
            selectedIds={selectedIds}
            selectedNodeIds={selectedNodeIds}
            selectedNodes={selectedNodes}
            setQuery={setQuery}
            targetEntities={targetEntities}
            targetModule={targetModule}
          />
        : null}
    </div>
  );
}

function NodeLinkSearchMenu(args: {
  inputRef: RefObject<HTMLInputElement | null>;
  menuPosition: PopoverPosition;
  menuRef: RefObject<HTMLDivElement | null>;
  mode: "multiple" | "single";
  onBlur: () => void;
  onChange: (value: NodeDocument | NodeDocument[] | null) => void;
  onClose: () => void;
  query: string;
  selectedIds: Set<string>;
  selectedNodeIds: string[];
  selectedNodes: NodeDocument[];
  setQuery: (value: string) => void;
  targetEntities: string[];
  targetModule: string;
}) {
  const { t } = useI18n();
  const { user } = useAuth();
  const entityNames = [...new Set(args.targetEntities)].sort();
  const hasTargetModule = args.targetModule.trim().length > 0;
  const schemaQueries = useQueries({
    queries: entityNames.map((entityName) => ({
      ...SCHEMA_QUERY_OPTIONS,
      enabled: hasTargetModule,
      queryKey: structureKeys.schema(args.targetModule, entityName),
      queryFn: ({ signal }: { signal: AbortSignal }) => getEntitySchema(args.targetModule, entityName, signal),
    })),
  });
  const searchQueries = useQueries({
    queries: entityNames.map((entityName, index) => {
      const schema = schemaQueries[index]?.data;
      const filter = schema === undefined ? undefined : buildLinkSearchFilter({
        entityName,
        excludeIds: args.selectedNodeIds,
        query: args.query,
        schema,
        user,
      });

      return {
        ...EPHEMERAL_NODE_QUERY_OPTIONS,
        enabled: hasTargetModule && filter !== undefined,
        queryKey: ["nodes", "link-search", args.targetModule, entityName, filter],
        queryFn: ({ signal }: { signal: AbortSignal }) => queryNodes(args.targetModule, { filter, limit: 10 }, signal),
      };
    }),
  });
  const searchError = schemaQueries.find((query) => query.error !== null)?.error
    ?? searchQueries.find((query) => query.error !== null)?.error
    ?? null;
  const isPending = hasTargetModule && searchError === null
    && (schemaQueries.some((query) => query.isPending) || searchQueries.some((query) => query.isPending));
  const filteredOptions = searchQueries.flatMap((query) => query.data ?? []).filter((node) => {
    const nodeId = typeof node.id === "string" ? node.id : "";
    return nodeId.length > 0 && !args.selectedIds.has(nodeId);
  });

  return createPortal(
    <div
      className={`multi-value-menu multi-value-menu-${args.menuPosition.placement}`}
      ref={args.menuRef}
      style={{
        left: `${args.menuPosition.left}px`,
        maxHeight: `${args.menuPosition.maxHeight}px`,
        top: `${args.menuPosition.top}px`,
        width: `${args.menuPosition.width}px`,
      }}
    >
      {isPending ? (
        <div className="multi-value-empty">{t("common.loading")}</div>
      ) : searchError !== null ? (
        <div className="multi-value-empty">{localizeUnknownError(searchError, t)}</div>
      ) : filteredOptions.length > 0 ? (
        filteredOptions.map((node) => {
          const nodeId = typeof node.id === "string" ? node.id : "";
          return (
            <button
              className="multi-value-option"
              key={nodeId}
              onClick={(event) => {
                event.preventDefault();
                if (args.mode === "multiple") {
                  args.onChange([...args.selectedNodes, node]);
                  args.setQuery("");
                  args.inputRef.current?.focus();
                  return;
                }

                args.onChange(node);
                args.onClose();
                args.onBlur();
              }}
              type="button"
            >
              <NodeDisplayLabel moduleName={args.targetModule} node={node} purpose="reference" />
            </button>
          );
        })
      ) : (
        <div className="multi-value-empty">
          {t("pages.nodes.editor.linkEmpty")}
        </div>
      )}
    </div>,
    document.body,
  );
}

function coerceSelectedNodes(value: unknown, mode: "multiple" | "single") {
  if (mode === "multiple") {
    return Array.isArray(value)
      ? value.flatMap(coerceNodeDocument)
      : [];
  }

  return coerceNodeDocument(value);
}

function coerceNodeDocument(value: unknown): NodeDocument[] {
  if (isNodeDocument(value)) {
    return [value];
  }
  if (typeof value === "string" && value.trim().length > 0) {
    return [{ id: value.trim() }];
  }
  return [];
}

function removeSelectedNode(args: {
  mode: "multiple" | "single";
  nodeId: string;
  onChange: (value: NodeDocument | NodeDocument[] | null) => void;
  selectedNodes: NodeDocument[];
}) {
  if (args.mode === "single") {
    args.onChange(null);
    return;
  }

  args.onChange(
    args.selectedNodes.filter((node) => node.id !== args.nodeId),
  );
}

function isNodeDocument(value: unknown): value is NodeDocument {
  return typeof value === "object" && value !== null;
}

function isUnresolvedReference(node: NodeDocument) {
  return typeof node.id === "string" && Object.keys(node).every((key) => key === "id");
}

function isResolvedNode(node: NodeDocument) {
  return !isUnresolvedReference(node) && typeof node.id === "string" && node.id.length > 0;
}

function mergeSelectedNodes(selectedNodes: NodeDocument[], resolvedNodes: NodeDocument[]) {
  const resolvedById = new Map(
    resolvedNodes
      .filter((node) => typeof node.id === "string" && node.id.length > 0)
      .map((node) => [node.id as string, node]),
  );

  return selectedNodes.map((node) => {
    if (!isUnresolvedReference(node) || typeof node.id !== "string") {
      return node;
    }
    return resolvedById.get(node.id) ?? node;
  });
}
