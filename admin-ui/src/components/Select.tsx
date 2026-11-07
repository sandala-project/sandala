import { useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Icon } from "./Icon";
import { usePopover } from "./usePopover";

export type SelectOption = {
  label: string;
  value: string;
};

type SelectProps = {
  disabled?: boolean;
  error?: string;
  label?: ReactNode;
  onBlur?: () => void;
  onChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  value: string;
};

export function Select({
  disabled = false,
  error,
  label,
  onBlur,
  onChange,
  options,
  placeholder,
  value,
}: SelectProps) {
  const rootRef = useRef<HTMLLabelElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [isOpen, setIsOpen] = useState(false);

  const selectedOption = useMemo(
    () => options.find((option) => option.value === value) ?? null,
    [options, value],
  );

  const menuPosition = usePopover({
    anchorRef: triggerRef,
    contentRef: menuRef,
    isOpen,
    onClose: () => setIsOpen(false),
  });

  return (
    <label className="field" ref={rootRef}>
      {label !== undefined ? <span className="field-label">{label}</span> : null}
      <button
        aria-expanded={isOpen}
        className={`select-trigger ${disabled ? "is-disabled" : ""}`.trim()}
        onBlur={onBlur}
        onClick={() => {
          if (!disabled) {
            setIsOpen((current) => !current);
          }
        }}
        ref={triggerRef}
        type="button"
      >
        <span className={`select-trigger-value ${selectedOption === null ? "is-placeholder" : ""}`.trim()}>
          {selectedOption?.label ?? placeholder ?? value}
        </span>
        <Icon className="chevron-icon" name="chevron-down" size="small" weight="strong" />
      </button>
      {error ? <span className="field-error">{error}</span> : null}
      {isOpen && !disabled && menuPosition
        ? createPortal(
            <div
              className={`select-menu select-menu-${menuPosition.placement}`}
              ref={menuRef}
              style={{
                left: `${menuPosition.left}px`,
                maxHeight: `${menuPosition.maxHeight}px`,
                top: `${menuPosition.top}px`,
                width: `${menuPosition.width}px`,
              }}
            >
              {options.map((option) => (
                <button
                  className={`select-option ${option.value === value ? "is-selected" : ""}`.trim()}
                  key={option.value}
                  onClick={(event) => {
                    event.preventDefault();
                    onChange(option.value);
                    setIsOpen(false);
                    triggerRef.current?.focus();
                  }}
                  type="button"
                >
                  {option.label}
                </button>
              ))}
            </div>,
            document.body,
          )
        : null}
    </label>
  );
}
