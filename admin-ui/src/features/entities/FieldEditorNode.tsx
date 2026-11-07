import { useEffect, useState, type DragEvent } from "react";
import { Button } from "../../components/Button";
import { IconButton } from "../../components/IconButton";
import { useI18n } from "../../providers/I18nProvider";
import type { SchemaFieldNode } from "./schema";

type FieldEditorNodeProps = {
  canEdit: boolean;
  draggedPath: string[] | null;
  node: SchemaFieldNode;
  onAddNested: (parentPath: string[]) => void;
  onDelete: (path: string[]) => void;
  onDragEnd: () => void;
  onDragStart: (path: string[]) => void;
  onEdit: (node: SchemaFieldNode) => void;
  onReorder: (sourcePath: string[], targetPath: string[], position: "before" | "after") => void;
};

export function FieldEditorNode({
  canEdit,
  draggedPath,
  node,
  onAddNested,
  onDelete,
  onDragEnd,
  onDragStart,
  onEdit,
  onReorder,
}: FieldEditorNodeProps) {
  const { t } = useI18n();
  const [dropPosition, setDropPosition] = useState<"before" | "after" | null>(null);
  const targetLabel = node.linkTargetModule
    ? node.linkTargetEntities.length > 0
      ? `${node.linkTargetModule} / ${node.linkTargetEntities.join(", ")}`
      : node.linkTargetModule
    : node.linkTargetEntities.join(", ");
  const canOpenEditor = node.canEditStructure || node.canEditDescription;
  const canDrag = canEdit && node.canReorder;
  const canAcceptDrop = canDrag
    && draggedPath !== null
    && !samePath(draggedPath, node.path)
    && samePath(draggedPath.slice(0, -1), node.path.slice(0, -1));

  useEffect(() => {
    if (draggedPath === null) {
      setDropPosition(null);
    }
  }, [draggedPath]);

  function handleDragOver(event: DragEvent<HTMLDivElement>) {
    if (!canAcceptDrop) {
      return;
    }

    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    const bounds = event.currentTarget.getBoundingClientRect();
    setDropPosition(event.clientY < bounds.top + bounds.height / 2 ? "before" : "after");
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    if (!canAcceptDrop || draggedPath === null) {
      return;
    }

    event.preventDefault();
    const bounds = event.currentTarget.getBoundingClientRect();
    const position = event.clientY < bounds.top + bounds.height / 2 ? "before" : "after";
    onReorder(draggedPath, node.path, position);
    setDropPosition(null);
  }

  return (
    <div
      className={[
        "entity-field-node",
        dropPosition === "before" ? "is-drop-before" : "",
        dropPosition === "after" ? "is-drop-after" : "",
      ].filter(Boolean).join(" ")}
    >
      <div
        className={[
          "entity-field-row",
          draggedPath !== null && samePath(draggedPath, node.path) ? "is-dragging" : "",
        ].filter(Boolean).join(" ")}
        onDragLeave={() => setDropPosition(null)}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        <div className="entity-field-reorder-slot">
          {canDrag ? (
            <IconButton
              className="entity-field-reorder-handle"
              draggable
              icon="field-reorder"
              label={t("entities.fields.reorder")}
              onDragEnd={onDragEnd}
              onDragStart={(event) => {
                event.dataTransfer.effectAllowed = "move";
                event.dataTransfer.setData("text/plain", node.path.join("."));
                onDragStart(node.path);
              }}
              variant="bare"
            />
          ) : null}
        </div>
        <div className="entity-field-title">
          <div className="entity-field-name-row">
            <strong>{node.name}</strong>
            {node.isRequired ? <span className="schema-flag schema-flag-required">{t("schema.required")}</span> : null}
            {node.isNullable ? <span className="schema-flag">{t("schema.nullable")}</span> : <span className="schema-flag">{t("schema.nonNull")}</span>}
          </div>
          {node.description ? <div className="schema-node-description">{node.description}</div> : null}
          {targetLabel ? <div className="schema-node-description">{t("schema.target")}: {targetLabel}</div> : null}
        </div>
        <div className="entity-field-badge-wrap">
          <span className="schema-badge">{node.semanticType}</span>
        </div>
        {node.showAccessModes ? (
          <div className="entity-field-meta">{t("schema.visible")}: {translateMode(node.visibilityMode, t)}</div>
        ) : (
          <div />
        )}
        {node.showAccessModes ? (
          <div className="entity-field-meta">{t("schema.write")}: {translateMode(node.writeMode, t)}</div>
        ) : (
          <div />
        )}
        {canEdit ? (
          <div className="entity-field-actions">
            {canOpenEditor ? (
              <IconButton icon="pencil" label={t("common.edit")} onClick={() => onEdit(node)} />
            ) : null}
            {node.canDelete ? (
              <IconButton icon="trash" label={t("common.delete")} onClick={() => onDelete(node.path)} />
            ) : null}
          </div>
        ) : null}
      </div>

      {node.children.length > 0 || (canEdit && node.canAddNested) ? (
        <div className="entity-field-children">
          {node.children.map((child) => (
            <FieldEditorNode
              canEdit={canEdit}
              draggedPath={draggedPath}
              key={child.path.join(".")}
              node={child}
              onAddNested={onAddNested}
              onDelete={onDelete}
              onDragEnd={onDragEnd}
              onDragStart={onDragStart}
              onEdit={onEdit}
              onReorder={onReorder}
            />
          ))}
          {canEdit && node.canAddNested ? (
            <div className="entity-field-add-nested-action">
              <Button kind="ghost" onClick={() => onAddNested(node.path)} type="button">
                {t("entities.fields.addNested")}
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function samePath(left: string[], right: string[]) {
  return left.length === right.length && left.every((segment, index) => segment === right[index]);
}

function translateMode(mode: string | null, t: ReturnType<typeof useI18n>["t"]) {
  switch (mode) {
    case "all":
      return t("schema.mode.all");
    case "admin":
      return t("schema.mode.admin");
    case "superuser":
      return t("schema.mode.superuser");
    case "none":
      return t("schema.mode.none");
    default:
      return t("schema.unknown");
  }
}
