import type { ButtonHTMLAttributes, PropsWithChildren } from "react";

type ButtonProps = PropsWithChildren<
  ButtonHTMLAttributes<HTMLButtonElement> & {
    kind?: "ghost" | "primary";
  }
>;

export function Button({ children, className = "", kind = "primary", type = "button", ...props }: ButtonProps) {
  return (
    <button
      className={`ui-button ui-button-${kind} ${className}`.trim()}
      type={type}
      {...props}
    >
      {children}
    </button>
  );
}
