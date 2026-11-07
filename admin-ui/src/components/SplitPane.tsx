import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { useI18n } from "../providers/I18nProvider";
import { Icon } from "./Icon";

type SplitPaneState = {
  collapsed: boolean;
  width: number;
};

type SplitPaneProps = {
  children: [ReactNode, ReactNode];
  className?: string;
  defaultSidebarWidth?: number;
  maxSidebarWidth?: number;
  minMainWidth?: number;
  minSidebarWidth?: number;
  storageKey: string;
};

const DEFAULT_SIDEBAR_WIDTH = 320;
const DEFAULT_MIN_MAIN_WIDTH = 560;
const DEFAULT_MIN_SIDEBAR_WIDTH = 180;
const DEFAULT_MAX_SIDEBAR_WIDTH = 600;

export function SplitPane({
  children,
  className = "",
  defaultSidebarWidth = DEFAULT_SIDEBAR_WIDTH,
  maxSidebarWidth = DEFAULT_MAX_SIDEBAR_WIDTH,
  minMainWidth = DEFAULT_MIN_MAIN_WIDTH,
  minSidebarWidth = DEFAULT_MIN_SIDEBAR_WIDTH,
  storageKey,
}: SplitPaneProps) {
  const { t } = useI18n();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [state, setState] = useState<SplitPaneState>(() => readState(storageKey, defaultSidebarWidth));

  function constrainWidth(width: number) {
    const availableWidth = containerRef.current?.clientWidth;
    const maximumByMain = availableWidth === undefined
      ? maxSidebarWidth
      : Math.max(minSidebarWidth, availableWidth - minMainWidth);
    const maximum = Math.min(maxSidebarWidth, maximumByMain);
    return Math.min(Math.max(width, minSidebarWidth), maximum);
  }

  useEffect(() => {
    setState((current) => {
      const width = constrainWidth(current.width);
      return width === current.width ? current : { ...current, width };
    });
    const container = containerRef.current;
    if (container === null) {
      return;
    }

    const resizeObserver = new ResizeObserver(() => {
      setState((current) => {
        const width = constrainWidth(current.width);
        return width === current.width ? current : { ...current, width };
      });
    });
    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, [maxSidebarWidth, minMainWidth, minSidebarWidth]);

  useEffect(() => {
    window.localStorage.setItem(storageKey, JSON.stringify(state));
  }, [state, storageKey]);

  function updateWidth(width: number) {
    setState({ collapsed: false, width: constrainWidth(width) });
  }

  function startResize(event: React.PointerEvent<HTMLDivElement>) {
    if (event.button !== 0 || state.collapsed) {
      return;
    }
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
  }

  function resize(event: React.PointerEvent<HTMLDivElement>) {
    if (!event.currentTarget.hasPointerCapture(event.pointerId)) {
      return;
    }
    const container = containerRef.current;
    if (container === null) {
      return;
    }
    updateWidth(event.clientX - container.getBoundingClientRect().left);
  }

  function stopResize(event: React.PointerEvent<HTMLDivElement>) {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  const [sidebar, main] = children;
  return (
    <div
      className={`split-pane ${state.collapsed ? "is-collapsed" : ""} ${className}`.trim()}
      ref={containerRef}
      style={{ "--split-pane-sidebar-width": `${state.width}px` } as CSSProperties}
    >
      <div className="split-pane-sidebar">{sidebar}</div>
      <div className="split-pane-divider">
        <div
          aria-label={t("components.splitPane.resize")}
          aria-orientation="vertical"
          aria-valuemax={maxSidebarWidth}
          aria-valuemin={minSidebarWidth}
          aria-valuenow={state.collapsed ? 0 : state.width}
          className="split-pane-resize-target"
          onKeyDown={(event) => {
            if (state.collapsed) {
              return;
            }
            if (event.key === "ArrowLeft") {
              event.preventDefault();
              updateWidth(state.width - 20);
            } else if (event.key === "ArrowRight") {
              event.preventDefault();
              updateWidth(state.width + 20);
            }
          }}
          onPointerDown={startResize}
          onPointerMove={resize}
          onPointerUp={stopResize}
          role="separator"
          tabIndex={state.collapsed ? -1 : 0}
        />
        <button
          aria-label={state.collapsed ? t("components.splitPane.expand") : t("components.splitPane.collapse")}
          className="split-pane-toggle"
          onClick={() => setState((current) => ({ ...current, collapsed: !current.collapsed }))}
          title={state.collapsed ? t("components.splitPane.expand") : t("components.splitPane.collapse")}
          type="button"
        >
          <Icon
            className="split-pane-toggle-icon"
            name={state.collapsed ? "chevron-right" : "chevron-left"}
            size="small"
            weight="strong"
          />
        </button>
      </div>
      <div className="split-pane-main">{main}</div>
    </div>
  );
}

function readState(storageKey: string, defaultSidebarWidth: number): SplitPaneState {
  const fallback = { collapsed: false, width: defaultSidebarWidth };
  try {
    const rawState = window.localStorage.getItem(storageKey);
    if (rawState === null) {
      return fallback;
    }
    const parsed = JSON.parse(rawState) as Partial<SplitPaneState>;
    return {
      collapsed: parsed.collapsed === true,
      width: typeof parsed.width === "number" && Number.isFinite(parsed.width) ? parsed.width : fallback.width,
    };
  } catch {
    return fallback;
  }
}
