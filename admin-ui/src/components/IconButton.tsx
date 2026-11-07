import type { ButtonHTMLAttributes } from "react";
import { Icon, type IconName } from "./Icon";

type IconButtonSize = "compact" | "regular";
type IconButtonVariant = "bare" | "outline";

type IconButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children" | "type"> & {
  hasIndicator?: boolean;
  icon: IconName;
  label: string;
  size?: IconButtonSize;
  variant?: IconButtonVariant;
};

export function IconButton({ className = "", hasIndicator = false, icon, label, size = "compact", variant = "outline", ...props }: IconButtonProps) {
  return (
    <button
      aria-label={label}
      className={`icon-button icon-button-${size} icon-button-${variant} ${hasIndicator ? "has-indicator" : ""} ${className}`.trim()}
      title={label}
      type="button"
      {...props}
    >
      <Icon name={icon} />
      {hasIndicator ? <span aria-hidden="true" className="icon-button-indicator" /> : null}
    </button>
  );
}
