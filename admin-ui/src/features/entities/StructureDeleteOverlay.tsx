import { useMutation } from "@tanstack/react-query";
import { Button } from "../../components/Button";
import { ApiErrorBanner } from "../../components/Form";
import { OverlayCloseButton } from "../../components/OverlayCloseButton";
import { OverlayDialog } from "../../components/OverlayDialog";
import { ApiError } from "../../lib/api";
import { localizeUnknownError } from "../../lib/errors";
import { useI18n } from "../../providers/I18nProvider";
import { deleteEntitySchema, deleteModule } from "./api";

type StructureDeleteTarget =
  | { entityName: string; kind: "entity"; moduleName: string; resourceLabel?: string }
  | { kind: "module"; moduleName: string; resourceLabel?: string };

export function StructureDeleteOverlay({ onClose, onDeleted, target }: {
  onClose: () => void;
  onDeleted: () => void;
  target: StructureDeleteTarget;
}) {
  const { t } = useI18n();
  const isModule = target.kind === "module";
  const deleteMutation = useMutation({
    mutationFn: () => isModule
      ? deleteModule(target.moduleName)
      : deleteEntitySchema(target.moduleName, target.entityName),
    onSuccess: onDeleted,
  });
  const apiError = deleteMutation.error instanceof ApiError ? deleteMutation.error : undefined;
  const error = deleteMutation.error instanceof Error
    ? localizeUnknownError(deleteMutation.error, t)
    : deleteMutation.error === null
      ? null
      : t("pages.entities.delete.error");
  const resourceTechnicalName = isModule ? target.moduleName : target.entityName;
  const resourceName = target.resourceLabel !== undefined && target.resourceLabel !== resourceTechnicalName
    ? `${target.resourceLabel} (${resourceTechnicalName})`
    : resourceTechnicalName;
  const title = t(isModule ? "pages.entities.delete.module.title" : "pages.entities.delete.entity.title");
  const confirm = t(isModule ? "pages.entities.delete.module.confirm" : "pages.entities.delete.entity.confirm");

  return <OverlayDialog ariaLabel={title} className="overlay-dialog-field" onClose={onClose}>
    <div className="field-overlay-header">
      <strong>{title}</strong>
      <OverlayCloseButton onClick={onClose} />
    </div>
    <div className="field-overlay-body">
      <p>{confirm} <strong>{resourceName}</strong></p>
      <p className="node-delete-warning">{t("pages.entities.delete.warning")}</p>
    </div>
    <div className="field-overlay-footer">
      {error ? <ApiErrorBanner error={apiError} message={error} /> : null}
      <div className="field-overlay-actions">
        <Button disabled={deleteMutation.isPending} kind="ghost" onClick={onClose} type="button">{t("common.cancel")}</Button>
        <Button className="ui-button-danger" disabled={deleteMutation.isPending} onClick={() => deleteMutation.mutate()} type="button">
          {deleteMutation.isPending ? t("pages.entities.delete.deleting") : t("common.delete")}
        </Button>
      </div>
    </div>
  </OverlayDialog>;
}

export type { StructureDeleteTarget };
