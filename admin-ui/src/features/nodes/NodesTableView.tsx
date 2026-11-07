import { useState } from "react";
import { EmptyState } from "../../components/EmptyState";
import { OverlayDialog } from "../../components/OverlayDialog";
import { OverlayCloseButton } from "../../components/OverlayCloseButton";
import { Spinner } from "../../components/Spinner";
import { useI18n } from "../../providers/I18nProvider";
import { useAuth } from "../../providers/AuthProvider";
import type { JsonSchema } from "../entities/api";
import type { NodeDocument } from "./api";
import { NodeEditorLoader } from "./NodeEditorLoader";
import { NodeEditorOverlay } from "./NodeEditorOverlay";
import { NodeDeleteOverlay } from "./NodeDeleteOverlay";
import { NodeTableFilterOverlay } from "./NodeTableFilterOverlay";
import { NodeTableSortOverlay } from "./NodeTableSortOverlay";
import { NodeTableColumnsOverlay } from "./NodeTableColumnsOverlay";
import { NodeTablePermissionsOverlay } from "./NodeTablePermissionsOverlay";
import { NodeAclOverlay } from "./NodeAclOverlay";
import { NodeTableFieldOverlay } from "./NodeTableEditing";
import { getAppliedNodeTableFilterPaths } from "./nodeTableFilter";
import { getAppliedNodeTableSortPaths } from "./nodeTableSort";
import { canWriteNodeDocument, getNodeAclEditCapabilities } from "./nodeAccess";
import { resolveNodeDisplayLabel } from "./presentation";
import { NodesTableHeader } from "./NodesTableHeader";
import { NodesTableRow } from "./NodesTableRow";
import type { NodesTableState } from "./useNodeTableState";
import { useVirtualizedNodeTable } from "./useVirtualizedNodeTable";

export function NodesTableView(args: {
  moduleName: string;
  state: NodesTableState;
  tableSchema: JsonSchema | null;
}) {
  const { locale, t } = useI18n();
  const auth = useAuth();
  const [deletingNode, setDeletingNode] = useState<NodeDocument | null>(null);
  const [linkedNode, setLinkedNode] = useState<{
    moduleName: string;
    nodeId: string;
    onUpdated?: (node: NodeDocument) => void;
  } | null>(null);
  const {
    columnSizing,
    hiddenColumnKeys,
    tableFilterDefinition,
    editingCell,
    editingCellField,
    editingFieldOverlay,
    editingNodeId,
    editingOverlayField,
    editingOverlayNode,
    gridTemplateColumns,
    hoveredRowId,
    isFilterOpen,
    isColumnsOpen,
    isSortOpen,
    rowDensity,
    rowHeight,
    reconcileTableAfterMutation,
    rows,
    rowsById,
    selectedRowId,
    setEditingCell,
    setEditingFieldOverlay,
    setEditingNodeId,
    setHoveredRowId,
    setSelectedRowId,
    setColumnSizing,
    setHiddenColumnKeys,
    setTableFilterDefinition,
    setIsFilterOpen,
    setIsColumnsOpen,
    setIsSortOpen,
    setTableSortDefinition,
    tableColumns,
    tableFields,
    tableFilterFields,
    tableSortDefinition,
    tableSortFields,
    tableNodesQuery,
    setTableScrollElement,
    tableScrollElement,
  } = args.state;
  const { bodyHeight, virtualRows } = useVirtualizedNodeTable({
    count: rows.length,
    hasNextPage: tableNodesQuery.hasNextPage ?? false,
    isFetchingNextPage: tableNodesQuery.isFetchingNextPage,
    onEndReached: () => {
      void tableNodesQuery.fetchNextPage();
    },
    rowHeight,
    scrollElement: tableScrollElement,
  });
  const filterPaths = getAppliedNodeTableFilterPaths(tableFilterDefinition);
  const sortPaths = getAppliedNodeTableSortPaths(tableSortDefinition);

  return (
    <div className="nodes-table-layout">
      {args.tableSchema === null ? (
        <div className="nodes-table-surface nodes-table-surface-empty">
          <EmptyState
            description={t("pages.nodes.table.emptyEntity.description")}
            title={t("pages.nodes.table.emptyEntity.title")}
          />
        </div>
      ) : tableNodesQuery.isPending ? (
        <div className="nodes-table-surface nodes-table-surface-empty">
          <div className="panel panel-centered">
            <Spinner />
          </div>
        </div>
      ) : rows.length === 0 ? (
        <div className="nodes-table-surface nodes-table-surface-empty">
          <EmptyState
            description={t("pages.nodes.table.emptyRows.description")}
            title={t("pages.nodes.table.emptyRows.title")}
          />
        </div>
      ) : (
        <div className="nodes-table-surface">
          <div
            className="nodes-table-wrap"
            data-row-density={rowDensity}
            ref={setTableScrollElement}
            style={{ ["--nodes-table-row-height" as string]: `${rowHeight}px` }}
          >
            <div className="nodes-table-grid">
              <NodesTableHeader
                columnSizing={columnSizing}
                columns={tableColumns}
                filterPaths={filterPaths}
                gridTemplateColumns={gridTemplateColumns}
                onOpenFilter={() => setIsFilterOpen(true)}
                onOpenSort={() => setIsSortOpen(true)}
                onColumnResize={(columnKey, width) => {
                  setColumnSizing((current) => ({ ...current, [columnKey]: width }));
                }}
                onColumnResizeReset={(columnKey) => {
                  const column = tableColumns.find((item) => item.key === columnKey);
                  if (column === undefined) {
                    return;
                  }
                  setColumnSizing((current) => ({ ...current, [columnKey]: column.defaultWidth }));
                }}
                sortPaths={sortPaths}
              />

              <div className="nodes-table-body-viewport">
                <div className="nodes-table-body" style={{ height: `${bodyHeight}px` }}>
                  {virtualRows.map((virtualRow) => {
                    const node = rows[virtualRow.index];
                    if (node === undefined) {
                      return null;
                    }

                    const nodeId = typeof node.id === "string" ? node.id : "";
                    const rowNode = rowsById[nodeId] ?? node;
                    const aclCapabilities = getNodeAclEditCapabilities(rowNode, auth.user);

                    return (
                      <div
                        className={`nodes-table-virtual-row ${editingCell !== null && editingCell.nodeId === nodeId ? "is-inline-editing" : ""}`.trim()}
                        key={nodeId || `${virtualRow.index}`}
                        style={{ transform: `translateY(${virtualRow.start}px)` }}
                      >
                        <NodesTableRow
                          editingCell={editingCell}
                          editingCellField={editingCellField}
                          canWriteNode={canWriteNodeDocument(rowNode, auth.user)}
                          canEditGroup={aclCapabilities.canEditGroup}
                          canEditOwner={aclCapabilities.canEditOwner}
                          gridTemplateColumns={gridTemplateColumns}
                          hovered={hoveredRowId !== null && hoveredRowId === nodeId}
                          moduleName={args.moduleName}
                          node={rowNode}
                          nodeId={nodeId}
                          locale={locale}
                          onDelete={(targetNode) => {
                            setEditingCell(null);
                            setEditingFieldOverlay(null);
                            setEditingNodeId(null);
                            setDeletingNode(targetNode);
                          }}
                          onHoverChange={(hovered) => {
                            if (hovered) {
                              setHoveredRowId(nodeId);
                              return;
                            }

                            setHoveredRowId((current) => (current === nodeId ? null : current));
                          }}
                          onOpenFullEditor={() => {
                            setEditingCell(null);
                            setEditingFieldOverlay(null);
                            setSelectedRowId(nodeId);
                            setEditingNodeId(nodeId);
                          }}
                          onOpenLinkedNode={(linked, linkedModuleName, onUpdated) => {
                            if (typeof linked.id === "string" && linked.id.length > 0) {
                              setLinkedNode({ moduleName: linkedModuleName, nodeId: linked.id, onUpdated });
                            }
                          }}
                          onOpenInlineEditor={(fieldKey, targetNodeId) => {
                            setEditingFieldOverlay(null);
                            setEditingNodeId(null);
                            setSelectedRowId(targetNodeId);
                            setEditingCell({ fieldKey, nodeId: targetNodeId });
                          }}
                          onOpenOverlayEditor={(fieldKey, targetNodeId) => {
                            setEditingCell(null);
                            setEditingNodeId(null);
                            setSelectedRowId(targetNodeId);
                            setEditingFieldOverlay({ fieldKey, nodeId: targetNodeId });
                          }}
                          onSaved={async (nextNode) => {
                            setEditingCell(null);
                            await reconcileTableAfterMutation(nextNode);
                          }}
                          onStopInlineEdit={() => setEditingCell(null)}
                          selected={selectedRowId !== null && selectedRowId === nodeId}
                          t={t}
                          tableColumns={tableColumns}
                        />
                      </div>
                    );
                  })}

                  {tableNodesQuery.isFetchingNextPage ? (
                    <div className="nodes-table-loading-more" style={{ transform: `translateY(${bodyHeight}px)` }}>
                      <Spinner />
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {editingNodeId !== null ? (
        <OverlayDialog
          ariaLabel={t("common.edit")}
          className="overlay-dialog-editor"
          onClose={() => setEditingNodeId(null)}
        >
            <div className="editor-overlay-header">
              <strong>{t("common.edit")}</strong>
              <OverlayCloseButton onClick={() => setEditingNodeId(null)} />
            </div>
            {args.tableSchema === null ? (
              <div className="panel panel-centered">
                <Spinner />
              </div>
            ) : (
              <NodeEditorLoader
                moduleName={args.moduleName}
                nodeId={editingNodeId}
                onUpdated={() => {
                  void reconcileTableAfterMutation();
                }}
                onSaved={(nextNode) => {
                  void reconcileTableAfterMutation(nextNode);
                }}
                schema={args.tableSchema}
              />
            )}
        </OverlayDialog>
      ) : null}

      {linkedNode !== null ? (
        <NodeEditorOverlay
          moduleName={linkedNode.moduleName}
          nodeId={linkedNode.nodeId}
          onClose={() => setLinkedNode(null)}
          onUpdated={(nextNode) => {
            linkedNode.onUpdated?.(nextNode);
            void reconcileTableAfterMutation();
          }}
        />
      ) : null}

      {isFilterOpen ? (
        <NodeTableFilterOverlay
          filter={tableFilterDefinition}
          fields={tableFilterFields}
          moduleName={args.moduleName}
          onApply={setTableFilterDefinition}
          onClose={() => setIsFilterOpen(false)}
        />
      ) : null}

      {isSortOpen ? (
        <NodeTableSortOverlay
          fields={tableSortFields}
          onApply={setTableSortDefinition}
          onClose={() => setIsSortOpen(false)}
          sort={tableSortDefinition}
        />
      ) : null}

      {isColumnsOpen ? (
        <NodeTableColumnsOverlay
          fields={tableFields}
          hiddenColumnKeys={hiddenColumnKeys}
          onClose={() => setIsColumnsOpen(false)}
          onSetAllVisible={(visible) => {
            setHiddenColumnKeys(visible ? [] : tableFields.map((field) => field.path.join(".")));
          }}
          onVisibilityChange={(fieldKey, visible) => {
            setHiddenColumnKeys((current) => visible
              ? current.filter((key) => key !== fieldKey)
              : current.includes(fieldKey) ? current : [...current, fieldKey]);
          }}
        />
      ) : null}

      {deletingNode !== null ? (
        <NodeDeleteOverlay
          moduleName={args.moduleName}
          node={deletingNode}
          nodeTitle={resolveNodeDisplayLabel(deletingNode) || t("pages.nodes.tree.unnamed")}
          onClose={() => setDeletingNode(null)}
          onDeleted={() => {
            setDeletingNode(null);
            setSelectedRowId(null);
            setHoveredRowId(null);
            void reconcileTableAfterMutation();
          }}
        />
      ) : null}

      {editingFieldOverlay !== null && (editingOverlayField?.semanticType === "SystemOwner" || editingOverlayField?.semanticType === "SystemGroup") && editingOverlayNode !== null ? (
        <NodeAclOverlay
          canEditGroup={getNodeAclEditCapabilities(editingOverlayNode, auth.user).canEditGroup}
          canEditOwner={getNodeAclEditCapabilities(editingOverlayNode, auth.user).canEditOwner}
          canEditPerm={false}
          moduleName={args.moduleName}
          node={editingOverlayNode}
          onClose={() => setEditingFieldOverlay(null)}
          onOpenLinkedNode={(linked, linkedModuleName) => {
            if (typeof linked.id === "string" && linked.id.length > 0) {
              setLinkedNode({ moduleName: linkedModuleName, nodeId: linked.id });
            }
          }}
          onSaved={async (nextNode) => {
            setEditingFieldOverlay(null);
            await reconcileTableAfterMutation(nextNode);
          }}
          visibleField={editingOverlayField.semanticType === "SystemOwner" ? "owner" : "group"}
        />
      ) : editingFieldOverlay !== null && editingOverlayField?.semanticType === "SystemPerm" && editingOverlayNode !== null ? (
        <NodeTablePermissionsOverlay
          canEdit={getNodeAclEditCapabilities(editingOverlayNode, auth.user).canEditPerm}
          moduleName={args.moduleName}
          node={editingOverlayNode}
          onClose={() => setEditingFieldOverlay(null)}
          onSaved={async (nextNode) => {
            setEditingFieldOverlay(null);
            await reconcileTableAfterMutation(nextNode);
          }}
        />
      ) : editingFieldOverlay !== null && editingOverlayField !== null && editingOverlayNode !== null && args.tableSchema !== null ? (
        <NodeTableFieldOverlay
          canWriteNode={canWriteNodeDocument(editingOverlayNode, auth.user)}
          field={editingOverlayField}
          moduleName={args.moduleName}
          node={editingOverlayNode}
          onClose={() => setEditingFieldOverlay(null)}
          onOpenLinkedNode={(linked, linkedModuleName, onUpdated) => {
            if (typeof linked.id === "string" && linked.id.length > 0) {
              setLinkedNode({ moduleName: linkedModuleName, nodeId: linked.id, onUpdated });
            }
          }}
          onSaved={async (nextNode) => {
            setEditingFieldOverlay(null);
            await reconcileTableAfterMutation(nextNode);
          }}
          schema={args.tableSchema}
        />
      ) : null}
    </div>
  );
}
