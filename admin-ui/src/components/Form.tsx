import type { MouseEvent, PropsWithChildren, ReactNode, RefObject } from "react";
import type { ApiError } from "../lib/errors";
import { ApiErrorDetailsButton } from "./ApiErrorDetailsOverlay";

export function FormSection({ actions, children, title }: PropsWithChildren<{ actions?: ReactNode; title: ReactNode }>) {
  return (
    <section className="form-section">
      <div className="form-section-header">
        <div className="form-section-title">{title}</div>
        {actions}
      </div>
      <div className="form-section-body">{children}</div>
    </section>
  );
}

export function ApiErrorBanner({ error, message }: { error?: ApiError; message: string }) {
  return (
    <div className="form-error-banner api-error-banner" role="alert">
      <span>{message}</span>
      {error ? <ApiErrorDetailsButton error={error} /> : null}
    </div>
  );
}

export function FormErrorSummary({ apiError, hasFieldErrors, message, scrollContainerRef }: {
  apiError?: ApiError;
  hasFieldErrors: boolean;
  message: string;
  scrollContainerRef?: RefObject<HTMLElement | null>;
}) {
  const handleClick = (event: MouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    const container = scrollContainerRef?.current;
    const target = container?.querySelector<HTMLElement>(".field-error");
    if (container === null || container === undefined || target === null || target === undefined) {
      return;
    }

    const containerRect = container.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    const targetTop = container.scrollTop + targetRect.top - containerRect.top;
    const centeredTop = targetTop - (container.clientHeight - target.offsetHeight) / 2;
    const maxScrollTop = Math.max(0, container.scrollHeight - container.clientHeight);

    container.scrollTo({
      behavior: "smooth",
      top: Math.min(Math.max(0, centeredTop), maxScrollTop),
    });
  };

  return (
    <div aria-live="assertive" className="form-error-banner form-error-summary" role="alert">
      {hasFieldErrors ? (
        <button className="form-error-summary-message" onClick={handleClick} type="button">
          {message}
        </button>
      ) : <span>{message}</span>}
      {apiError ? <ApiErrorDetailsButton error={apiError} /> : null}
    </div>
  );
}
