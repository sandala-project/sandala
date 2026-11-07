import { useState } from "react";
import type { ApiError } from "../lib/errors";
import { useI18n } from "../providers/I18nProvider";
import { Button } from "./Button";
import { IconButton } from "./IconButton";
import { OverlayCloseButton } from "./OverlayCloseButton";
import { OverlayDialog } from "./OverlayDialog";

export function ApiErrorDetailsButton({ error }: { error: ApiError }) {
  const { t } = useI18n();
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);

  return (
    <>
      <IconButton
        className="api-error-details-button"
        icon="error-details"
        label={t("errors.api.details.open")}
        onClick={() => setIsDetailsOpen(true)}
        variant="bare"
      />
      {isDetailsOpen ? <ApiErrorDetailsOverlay error={error} onClose={() => setIsDetailsOpen(false)} /> : null}
    </>
  );
}

export function ApiErrorDetailsOverlay({ error, onClose }: { error: ApiError; onClose: () => void }) {
  const { t } = useI18n();
  const payload = JSON.stringify(error.payload, null, 2) ?? String(error.payload);

  return (
    <OverlayDialog ariaLabel={t("errors.api.details.title")} className="overlay-dialog-api-error" layer="details" onClose={onClose}>
      <div className="field-overlay-header">
        <strong>{t("errors.api.details.title")}</strong>
        <OverlayCloseButton onClick={onClose} />
      </div>
      <div className="api-error-details-body">
        <div className="api-error-details-meta">
          <span><strong>{t("errors.api.details.status")}:</strong> {error.status}</span>
          <span><strong>{t("errors.api.details.code")}:</strong> {error.code}</span>
        </div>
        <pre className="api-error-details-json">{payload}</pre>
      </div>
      <div className="field-overlay-footer">
        <div className="field-overlay-actions">
          <Button onClick={onClose} type="button">{t("common.close")}</Button>
        </div>
      </div>
    </OverlayDialog>
  );
}
