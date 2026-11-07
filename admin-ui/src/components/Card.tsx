import type { PropsWithChildren, ReactNode } from "react";

export function Card({ children, title, tone = "default" }: PropsWithChildren<{ title?: ReactNode; tone?: "default" | "muted" }>) {
  return (
    <section className={`card card-${tone}`}>
      {title ? <header className="card-header">{title}</header> : null}
      <div className="card-body">{children}</div>
    </section>
  );
}
