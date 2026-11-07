import type { PropsWithChildren } from "react";

export function Panel({ children }: PropsWithChildren) {
  return <div className="panel">{children}</div>;
}
