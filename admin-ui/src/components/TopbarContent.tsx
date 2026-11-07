import { createContext, useContext, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

type TopbarContentContextValue = {
  container: HTMLElement | null;
  setContainer: (element: HTMLElement | null) => void;
};

const TopbarContentContext = createContext<TopbarContentContextValue | null>(null);

export function TopbarContentProvider({ children }: { children: ReactNode }) {
  const [container, setContainer] = useState<HTMLElement | null>(null);
  return <TopbarContentContext.Provider value={{ container, setContainer }}>{children}</TopbarContentContext.Provider>;
}

export function TopbarContentTarget() {
  const context = useContext(TopbarContentContext);
  return <div className="topbar-center" ref={context?.setContainer} />;
}

export function TopbarPortal({ children }: { children: ReactNode }) {
  const context = useContext(TopbarContentContext);
  return context?.container === null || context?.container === undefined
    ? null
    : createPortal(children, context.container);
}
