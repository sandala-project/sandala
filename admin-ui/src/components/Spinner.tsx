import { useI18n } from "../providers/I18nProvider";

export function Spinner() {
  const { t } = useI18n();

  return <div className="spinner" aria-label={t("common.loading")} />;
}
