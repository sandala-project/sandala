import { useI18n } from "../providers/I18nProvider";
import { IconButton } from "./IconButton";

export function OverlayCloseButton({ onClick }: { onClick: () => void }) {
  const { t } = useI18n();

  return <IconButton icon="x" label={t("common.close")} onClick={onClick} variant="bare" />;
}
