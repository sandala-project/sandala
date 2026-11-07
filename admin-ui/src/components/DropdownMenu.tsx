import { Link } from "@tanstack/react-router";
import { cloneElement, isValidElement, useEffect, useRef, useState, type ButtonHTMLAttributes, type ReactElement, type ReactNode } from "react";
import { Button } from "./Button";

type MenuItem =
  | { action: () => void | Promise<void>; label: string; meta?: string }
  | { divider?: boolean; label: string; meta?: string; to: string };

type DropdownMenuProps = {
  footer?: ReactNode;
  items: MenuItem[];
  label: string;
  trigger?: ReactElement<ButtonHTMLAttributes<HTMLButtonElement>>;
};

export function DropdownMenu({ footer, items, label, trigger }: DropdownMenuProps) {
  const [isOpen, setIsOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, []);

  return (
    <div className="dropdown" ref={rootRef}>
      {trigger && isValidElement(trigger)
        ? cloneElement(trigger, {
            "aria-expanded": isOpen,
            "aria-haspopup": "menu",
            onClick: () => setIsOpen((current) => !current),
          })
        : (
          <Button kind="ghost" onClick={() => setIsOpen((current) => !current)}>
            {label}
          </Button>
        )}
      {isOpen ? (
        <div className="dropdown-menu">
          {items.map((item) => {
            if ("action" in item) {
              return (
                <button
                  className="dropdown-item"
                  key={item.label}
                  onClick={async () => {
                    setIsOpen(false);
                    await item.action();
                  }}
                  type="button"
                >
                  <span>{item.label}</span>
                  {item.meta ? <span className="dropdown-meta">{item.meta}</span> : null}
                </button>
              );
            }

            return (
              <Link
                className={`dropdown-item ${item.divider ? "dropdown-divider" : ""}`.trim()}
                key={`${item.label}-${item.to}`}
                onClick={() => setIsOpen(false)}
                to={item.to}
              >
                <span>{item.label}</span>
                {item.meta ? <span className="dropdown-meta">{item.meta}</span> : null}
              </Link>
            );
          })}
          {footer ? <div className="dropdown-footer">{footer}</div> : null}
        </div>
      ) : null}
    </div>
  );
}
