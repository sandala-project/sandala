import type { InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";

export function TextField({
  error,
  label,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { error?: string; label: ReactNode }) {
  const className = ["field-control", props.readOnly ? "is-readonly" : "", props.className ?? ""]
    .filter(Boolean)
    .join(" ");

  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <input
        {...props}
        className={className}
        onMouseDown={(event) => {
          if (props.readOnly) {
            event.preventDefault();
          }
          props.onMouseDown?.(event);
        }}
        tabIndex={props.readOnly ? -1 : props.tabIndex}
      />
      {error ? <span className="field-error">{error}</span> : null}
    </label>
  );
}

export function TextAreaField({
  error,
  label,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement> & { error?: string; label: ReactNode }) {
  const className = ["field-control", "field-control-textarea", props.readOnly ? "is-readonly" : "", props.className ?? ""]
    .filter(Boolean)
    .join(" ");

  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <textarea
        {...props}
        className={className}
        onMouseDown={(event) => {
          if (props.readOnly) {
            event.preventDefault();
          }
          props.onMouseDown?.(event);
        }}
        tabIndex={props.readOnly ? -1 : props.tabIndex}
      />
      {error ? <span className="field-error">{error}</span> : null}
    </label>
  );
}

export function CheckboxField({
  label,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: ReactNode }) {
  return (
    <label className="checkbox-field">
      <input className="checkbox-input" type="checkbox" {...props} />
      {label ? <span>{label}</span> : null}
    </label>
  );
}
