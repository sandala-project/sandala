import type { ButtonHTMLAttributes } from "react";
import { useI18n } from "../providers/I18nProvider";
import { Icon } from "./Icon";

type ChipRemoveButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children" | "type">;

export function ChipRemoveButton({ className = "", ...props }: ChipRemoveButtonProps) {
  const { t } = useI18n();
  const label = t("common.remove");

  return (
    <button
      aria-label={label}
      className={`multi-value-remove ${className}`.trim()}
      title={label}
      type="button"
      {...props}
    >
      <Icon name="x" size="tiny" weight="strong" />
    </button>
  );
}
