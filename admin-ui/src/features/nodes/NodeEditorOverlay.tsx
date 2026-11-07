import { OverlayCloseButton } from "../../components/OverlayCloseButton";
import { OverlayDialog } from "../../components/OverlayDialog";
import { useI18n } from "../../providers/I18nProvider";
import type { JsonSchema } from "../entities/api";
import type { NodeDocument } from "./api";
import { NodeEditorLoader } from "./NodeEditorLoader";

export function NodeEditorOverlay(args: {
  moduleName: string;
  nodeId: string;
  onClose: () => void;
  onSaved?: (node: NodeDocument) => void;
  onUpdated?: (node: NodeDocument) => void;
  schema?: JsonSchema;
  title?: string;
}) {
  const { t } = useI18n();

  return (
    <OverlayDialog ariaLabel={args.title ?? t("common.edit")} className="overlay-dialog-editor" layer="nested" onClose={args.onClose}>
      <div className="editor-overlay-header">
        <strong>{args.title ?? t("common.edit")}</strong>
        <OverlayCloseButton onClick={args.onClose} />
      </div>
      <NodeEditorLoader
        moduleName={args.moduleName}
        nodeId={args.nodeId}
        onUpdated={args.onUpdated}
        onSaved={(node) => {
          args.onUpdated?.(node);
          args.onSaved?.(node);
          args.onClose();
        }}
        schema={args.schema}
      />
    </OverlayDialog>
  );
}
