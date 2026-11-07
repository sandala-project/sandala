import { IconButton } from "../../components/IconButton";
import type { TranslationKey } from "../../locales";
import type { NodeDocument } from "./api";
import { NodeTableInlineEditor } from "./NodeTableEditing";
import { getNodeTableColumnEditMode, type NodeTableColumn } from "./nodeTableColumns";
import { renderNodeTableCell } from "./nodeTablePresenters";

export function NodesTableRow(args: {
  editingCell: { fieldKey: string; nodeId: string } | null;
  editingCellField: NodeTableColumn["field"];
  canWriteNode: boolean;
  canEditGroup: boolean;
  canEditOwner: boolean;
  gridTemplateColumns: string;
  hovered: boolean;
  moduleName: string;
  node: NodeDocument;
  nodeId: string;
  locale: string;
  onDelete: (node: NodeDocument) => void;
  onHoverChange: (hovered: boolean) => void;
  onOpenFullEditor: () => void;
  onOpenLinkedNode: (node: NodeDocument, moduleName: string, onUpdated?: (node: NodeDocument) => void) => void;
  onOpenInlineEditor: (fieldKey: string, nodeId: string) => void;
  onOpenOverlayEditor: (fieldKey: string, nodeId: string) => void;
  onSaved: (node: NodeDocument) => Promise<void> | void;
  onStopInlineEdit: () => void;
  selected: boolean;
  t: (key: TranslationKey) => string;
  tableColumns: NodeTableColumn[];
}) {
  return (
    <div
      className={`nodes-table-row ${args.selected ? "is-selected" : ""} ${inlineEditingRowClass(args.editingCell, args.nodeId)}`.trim()}
      style={{ gridTemplateColumns: args.gridTemplateColumns }}
      onMouseEnter={() => args.onHoverChange(true)}
      onMouseLeave={() => args.onHoverChange(false)}
    >
      {args.tableColumns.map((column) => {
        if (column.kind === "actions") {
          return (
            <div className="nodes-table-cell column-actions" key={column.key}>
              {args.canWriteNode ? (
                <>
                  <IconButton
                    className={`table-action-button ${(args.hovered || args.selected) ? "is-visible" : ""}`.trim()}
                    icon="trash"
                    label={args.t("pages.nodes.delete.action")}
                    onClick={(event) => {
                      event.stopPropagation();
                      if (args.nodeId.length === 0) {
                        return;
                      }
                      args.onDelete(args.node);
                    }}
                  />
                </>
              ) : null}
              <IconButton
                className={`table-action-button ${(args.hovered || args.selected) ? "is-visible" : ""}`.trim()}
                icon="maximize"
                label={args.t("common.open")}
                onClick={(event) => {
                  event.stopPropagation();
                  if (args.nodeId.length === 0) {
                    return;
                  }
                  args.onOpenFullEditor();
                }}
              />
            </div>
          );
        }

        const editMode = getNodeTableColumnEditMode(column.field, args.canWriteNode);
        const isOwnerField = column.field?.semanticType === "SystemOwner";
        const isGroupField = column.field?.semanticType === "SystemGroup";
        const isPermField = column.field?.semanticType === "SystemPerm";
        const isEditingInline =
          args.editingCell !== null
          && args.editingCell.nodeId === args.nodeId
          && args.editingCell.fieldKey === column.key
          && args.editingCellField !== null;
        const inlineEditingField = isEditingInline ? args.editingCellField : null;

        return (
          <div
            className={`nodes-table-cell column-${column.kind} ${(editMode === "inline" || editMode === "overlay" || editMode === "view-overlay") ? "is-editable" : ""} ${inlineEditingField !== null ? "is-inline-editing-cell" : ""}`.trim()}
            key={column.key}
            onClick={(event) => {
              if (column.field === null || args.nodeId.length === 0) {
                return;
              }

              if ((isOwnerField && args.canEditOwner) || (isGroupField && args.canEditGroup)) {
                event.stopPropagation();
                args.onOpenOverlayEditor(column.key, args.nodeId);
                return;
              }

              if (isPermField) {
                event.stopPropagation();
                args.onOpenOverlayEditor(column.key, args.nodeId);
                return;
              }

              if (editMode === "inline") {
                event.stopPropagation();
                args.onOpenInlineEditor(column.key, args.nodeId);
                return;
              }

              if (editMode === "overlay" || editMode === "view-overlay") {
                event.stopPropagation();
                args.onOpenOverlayEditor(column.key, args.nodeId);
              }
            }}
            role="presentation"
          >
            {renderNodeTableCell({
              field: column.field,
              locale: args.locale,
              node: args.node,
              onOpenLinkedNode: args.onOpenLinkedNode,
              t: args.t,
            })}
            {inlineEditingField !== null ? (
              <NodeTableInlineEditor
                field={inlineEditingField}
                moduleName={args.moduleName}
                node={args.node}
                onCancel={args.onStopInlineEdit}
                onOpenLinkedNode={args.onOpenLinkedNode}
                onSaved={args.onSaved}
              />
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function inlineEditingRowClass(
  editingCell: { fieldKey: string; nodeId: string } | null,
  nodeId: string,
) {
  return editingCell !== null && editingCell.nodeId === nodeId ? "is-inline-editing" : "";
}
