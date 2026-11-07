import { useId, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { ChipRemoveButton } from "./ChipRemoveButton";
import { usePopover } from "./usePopover";

export type MultiValueOption = {
  label: string;
  value: string;
};

type MultiValueSelectProps = {
  disabled?: boolean;
  emptyText?: string;
  error?: string;
  label: ReactNode;
  onChange: (values: string[]) => void;
  options: MultiValueOption[];
  placeholder?: string;
  values: string[];
};

export function MultiValueSelect({
  disabled = false,
  emptyText,
  error,
  label,
  onChange,
  options,
  placeholder,
  values,
}: MultiValueSelectProps) {
  const labelId = useId();
  const controlRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");

  const selectedItems = useMemo(
    () =>
      values.map((storedValue) => {
        const matchingOption = options.find((option) => getOptionValue(option) === storedValue);
        return {
          key: storedValue,
          label: matchingOption?.label ?? storedValue,
        };
      }),
    [options, values],
  );

  const filteredOptions = useMemo(() => {
    const selectedSet = new Set(values);
    const normalizedQuery = query.trim().toLowerCase();

    return options.filter((option) => {
      if (selectedSet.has(getOptionValue(option))) {
        return false;
      }

      if (normalizedQuery.length === 0) {
        return true;
      }

      return option.label.toLowerCase().includes(normalizedQuery);
    });
  }, [options, query, values]);

  const menuPosition = usePopover({
    anchorRef: controlRef,
    contentRef: menuRef,
    deps: [query, selectedItems.length],
    isOpen,
    onClose: () => setIsOpen(false),
  });

  return (
    <div className="field">
      <span className="field-label" id={labelId}>{label}</span>
      <div
        className={`multi-value-select ${disabled ? "is-disabled" : ""}`.trim()}
        ref={controlRef}
        onClick={() => {
          if (disabled) {
            return;
          }
          setIsOpen(true);
          inputRef.current?.focus();
        }}
        role="presentation"
      >
        <div className="multi-value-control">
          {selectedItems.map((item) => (
            <span className="multi-value-chip" key={item.key}>
              <span>{item.label}</span>
              {!disabled ? (
                <ChipRemoveButton
                  onClick={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    onChange(values.filter((currentValue) => currentValue !== item.key));
                  }}
                />
              ) : null}
            </span>
          ))}
          <input
            aria-labelledby={labelId}
            className="multi-value-input"
            disabled={disabled}
            onChange={(event) => {
              setQuery(event.target.value);
              if (!isOpen) {
                setIsOpen(true);
              }
            }}
            onFocus={() => {
              if (!disabled) {
                setIsOpen(true);
              }
            }}
            placeholder={selectedItems.length === 0 ? placeholder : ""}
            ref={inputRef}
            value={query}
          />
        </div>
      </div>
      {error ? <span className="field-error">{error}</span> : null}
      {isOpen && !disabled && menuPosition
        ? createPortal(
            <div
              className={`multi-value-menu multi-value-menu-${menuPosition.placement}`}
              ref={menuRef}
              style={{
                left: `${menuPosition.left}px`,
                maxHeight: `${menuPosition.maxHeight}px`,
                top: `${menuPosition.top}px`,
                width: `${menuPosition.width}px`,
              }}
            >
              {filteredOptions.length > 0 ? (
                filteredOptions.map((option) => {
                  const storedValue = getOptionValue(option);
                  return (
                    <button
                      className="multi-value-option"
                      key={storedValue}
                      onClick={(event) => {
                        event.preventDefault();
                        onChange([...values, storedValue]);
                        setQuery("");
                        inputRef.current?.focus();
                      }}
                      type="button"
                    >
                      {option.label}
                    </button>
                  );
                })
              ) : (
                <div className="multi-value-empty">{emptyText}</div>
              )}
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}

function getOptionValue(option: MultiValueOption) {
  return option.value;
}
