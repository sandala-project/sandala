import { Button } from "../../components/Button";
import { CheckboxField } from "../../components/Field";
import { OverlayDialog } from "../../components/OverlayDialog";
import { OverlayCloseButton } from "../../components/OverlayCloseButton";
import { useI18n } from "../../providers/I18nProvider";
import type { NodeEditorField } from "./editorSchema";

export function NodeTableColumnsOverlay(args: {
  fields: NodeEditorField[];
  hiddenColumnKeys: string[];
  onClose: () => void;
  onSetAllVisible: (visible: boolean) => void;
  onVisibilityChange: (fieldKey: string, visible: boolean) => void;
}) {
  const { t } = useI18n();
  const hiddenKeys = new Set(args.hiddenColumnKeys);

  return <OverlayDialog ariaLabel={t("pages.nodes.table.columns.title")} className="overlay-dialog-node-table-columns" onClose={args.onClose}>
    <div className="nodes-table-filter-header nodes-table-columns-header">
      <div className="nodes-table-columns-title">
        <strong>{t("pages.nodes.table.columns.title")}</strong>
        <div className="nodes-table-columns-actions">
          <Button kind="ghost" onClick={() => args.onSetAllVisible(true)} type="button">{t("pages.nodes.table.columns.showAll")}</Button>
          <Button kind="ghost" onClick={() => args.onSetAllVisible(false)} type="button">{t("pages.nodes.table.columns.hideAll")}</Button>
        </div>
      </div>
      <OverlayCloseButton onClick={args.onClose} />
    </div>
    <div className="nodes-table-columns-body">
      {args.fields.map((field) => {
        const key = field.path.join(".");
        return <CheckboxField
          checked={!hiddenKeys.has(key)}
          key={key}
          label={field.label}
          onChange={(event) => args.onVisibilityChange(key, event.target.checked)}
        />;
      })}
    </div>
  </OverlayDialog>;
}
