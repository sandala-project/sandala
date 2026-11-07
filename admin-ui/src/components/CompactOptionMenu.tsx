import { createPortal } from "react-dom";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Icon, type IconName } from "./Icon";
import { usePopover } from "./usePopover";

export type CompactOption<T extends string> = {
  icon?: IconName;
  label: string;
  value: T;
};

type CompactOptionMenuProps<T extends string> = {
  buttonLabel: string;
  className?: string;
  options: CompactOption<T>[];
  portal?: boolean;
  showSelectedLabel?: boolean;
  triggerContent?: ReactNode;
  value: T;
  onChange: (value: T) => void;
};

export function CompactOptionMenu<T extends string>({
  buttonLabel,
  className = "",
  onChange,
  options,
  portal = false,
  showSelectedLabel = true,
  triggerContent,
  value,
}: CompactOptionMenuProps<T>) {
  const [isOpen, setIsOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const selectedOption = options.find((option) => option.value === value) ?? options[0];
  const popoverPosition = usePopover({
    anchorRef: triggerRef,
    contentRef: popoverRef,
    isOpen: portal && isOpen,
    minWidth: 148,
    onClose: () => setIsOpen(false),
  });

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    function handlePointerDown(event: MouseEvent) {
      if (portal) {
        return;
      }

      if (!rootRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, portal]);

  if (selectedOption === undefined) {
    return null;
  }

  return (
    <div className={`compact-option-menu ${className}`.trim()} ref={rootRef}>
      <button
        aria-expanded={isOpen}
        aria-haspopup="menu"
        aria-label={buttonLabel}
        className="compact-option-menu-trigger"
        onClick={() => setIsOpen((current) => !current)}
        ref={triggerRef}
        title={buttonLabel}
        type="button"
      >
        {triggerContent ?? (
          <>
            {selectedOption.icon ? <Icon name={selectedOption.icon} /> : null}
            {showSelectedLabel ? <span>{selectedOption.label}</span> : null}
          </>
        )}
        <Icon className="compact-option-menu-chevron" name="chevron-down" size="small" weight="strong" />
      </button>
      {isOpen && (!portal || popoverPosition)
        ? (() => {
            const popover = (
              <div
                className={`compact-option-menu-popover ${portal ? `is-${popoverPosition?.placement ?? "bottom"}` : ""}`.trim()}
                ref={popoverRef}
                role="menu"
                style={portal && popoverPosition
                  ? {
                      left: `${popoverPosition.left}px`,
                      maxHeight: `${popoverPosition.maxHeight}px`,
                      top: `${popoverPosition.top}px`,
                      width: `${popoverPosition.width}px`,
                    }
                  : undefined}
                onMouseDown={portal ? (event) => event.stopPropagation() : undefined}
              >
                {options.map((option) => (
                  <button
                    aria-checked={option.value === value}
                    className={`compact-option-menu-item ${option.value === value ? "is-active" : ""}`.trim()}
                    key={option.value}
                    onClick={() => {
                      setIsOpen(false);
                      onChange(option.value);
                    }}
                    role="menuitemradio"
                    type="button"
                  >
                    {option.icon ? <Icon name={option.icon} /> : null}
                    <span>{option.label}</span>
                  </button>
                ))}
              </div>
            );

            return portal ? createPortal(popover, document.body) : popover;
          })()
        : null}
    </div>
  );
}
