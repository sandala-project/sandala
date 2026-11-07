import { useMutation } from "@tanstack/react-query";
import { Button } from "../../components/Button";
import { ApiErrorBanner } from "../../components/Form";
import { OverlayDialog } from "../../components/OverlayDialog";
import { ApiError } from "../../lib/api";
import { localizeUnknownError } from "../../lib/errors";
import { OverlayCloseButton } from "../../components/OverlayCloseButton";
import { useI18n } from "../../providers/I18nProvider";
import { deleteNode, type NodeDocument } from "./api";

export function NodeDeleteOverlay(args: {
  moduleName: string;
  node: NodeDocument;
  nodeTitle: string;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const { t } = useI18n();
  const nodeId = typeof args.node.id === "string" ? args.node.id : "";
  const deleteMutation = useMutation({
    mutationFn: () => deleteNode(args.moduleName, nodeId),
    onSuccess: args.onDeleted,
  });
  const apiError = deleteMutation.error instanceof ApiError ? deleteMutation.error : undefined;
  const error = deleteMutation.error instanceof Error
    ? localizeUnknownError(deleteMutation.error, t)
    : deleteMutation.error === null
      ? null
      : t("pages.nodes.delete.error");

  return <OverlayDialog ariaLabel={t("pages.nodes.delete.title")} className="overlay-dialog-field" onClose={args.onClose}>
    <div className="field-overlay-header">
      <strong>{t("pages.nodes.delete.title")}</strong>
      <OverlayCloseButton onClick={args.onClose} />
    </div>
    <div className="field-overlay-body">
      <p>{t("pages.nodes.delete.confirm")} <strong>{args.nodeTitle}</strong></p>
      <p className="node-delete-warning">{t("pages.nodes.delete.descendantsWarning")}</p>
    </div>
    <div className="field-overlay-footer">
      {error ? <ApiErrorBanner error={apiError} message={error} /> : null}
      <div className="field-overlay-actions">
        <Button disabled={deleteMutation.isPending} kind="ghost" onClick={args.onClose} type="button">{t("common.cancel")}</Button>
        <Button className="ui-button-danger" disabled={nodeId.length === 0 || deleteMutation.isPending} onClick={() => deleteMutation.mutate()} type="button">
          {deleteMutation.isPending ? t("pages.nodes.delete.deleting") : t("common.delete")}
        </Button>
      </div>
    </div>
  </OverlayDialog>;
}
