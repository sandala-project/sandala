import { useMemo, useRef, useState, type ReactNode } from "react";
import { ChipRemoveButton } from "./ChipRemoveButton";

type StringListInputProps = {
  disabled?: boolean;
  error?: string;
  label: ReactNode;
  onChange: (values: string[]) => void;
  placeholder?: string;
  values: string[];
};

export function StringListInput({
  disabled = false,
  error,
  label,
  onChange,
  placeholder,
  values,
}: StringListInputProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [draftValue, setDraftValue] = useState("");

  const normalizedValues = useMemo(
    () => values.filter((value, index, source) => value.length > 0 && source.indexOf(value) === index),
    [values],
  );

  function commitDraftValue() {
    const nextValue = draftValue.trim();
    if (nextValue.length === 0 || normalizedValues.includes(nextValue)) {
      setDraftValue("");
      return;
    }

    onChange([...normalizedValues, nextValue]);
    setDraftValue("");
  }

  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <div
        className={`string-list-input ${disabled ? "is-disabled" : ""}`.trim()}
        onClick={() => {
          if (!disabled) {
            inputRef.current?.focus();
          }
        }}
        role="presentation"
      >
        <div className="multi-value-control">
          {normalizedValues.map((value) => (
            <span className="multi-value-chip" key={value}>
              <span>{value}</span>
              {!disabled ? (
                <ChipRemoveButton
                  onClick={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    onChange(normalizedValues.filter((item) => item !== value));
                  }}
                />
              ) : null}
            </span>
          ))}
          <input
            className="multi-value-input"
            disabled={disabled}
            onChange={(event) => {
              setDraftValue(event.target.value);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                commitDraftValue();
              }

              if (event.key === "Backspace" && draftValue.length === 0 && normalizedValues.length > 0) {
                event.preventDefault();
                onChange(normalizedValues.slice(0, -1));
              }
            }}
            placeholder={normalizedValues.length === 0 ? placeholder : ""}
            ref={inputRef}
            value={draftValue}
          />
        </div>
      </div>
      {error ? <span className="field-error">{error}</span> : null}
    </label>
  );
}
