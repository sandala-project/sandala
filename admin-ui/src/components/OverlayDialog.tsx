import type { PropsWithChildren } from "react";

type OverlayDialogProps = PropsWithChildren<{
  ariaLabel: string;
  className?: string;
  layer?: "base" | "nested" | "details";
  onClose: () => void;
}>;

export function OverlayDialog({ ariaLabel, children, className = "", layer = "base", onClose }: OverlayDialogProps) {
  return (
    <div className={`overlay-backdrop overlay-backdrop-${layer}`} onClick={onClose} role="presentation">
      <div
        aria-label={ariaLabel}
        aria-modal="true"
        className={`overlay-dialog ${className}`.trim()}
        onClick={(event) => event.stopPropagation()}
        role="dialog"
      >
        {children}
      </div>
    </div>
  );
}
