import type { MouseEvent } from "react";
import { Icon, type IconName } from "./Icon";

type TreeNavAction = {
  ariaLabel: string;
  icon: IconName;
  onClick: (event: MouseEvent<HTMLButtonElement>) => void;
  title: string;
};

export type TreeNavItem = {
  actionAriaLabel?: string;
  actionIcon?: "plus";
  actionTitle?: string;
  actions?: TreeNavAction[];
  onActionClick?: (event: MouseEvent<HTMLButtonElement>) => void;
  children?: TreeNavItem[];
  hasChildren?: boolean;
  id: string;
  isActive?: boolean;
  isExpanded?: boolean;
  isLoading?: boolean;
  onClick?: () => void;
  onToggle?: () => void;
  title: string;
};

export function TreeNav({ items }: { items: TreeNavItem[] }) {
  return (
    <div className="tree-nav" role="tree">
      {items.map((item) => (
        <TreeNavNode depth={0} item={item} key={item.id} />
      ))}
    </div>
  );
}

function TreeNavNode({ depth, item }: { depth: number; item: TreeNavItem }) {
  const hasChildren = item.hasChildren === true;
  const canToggle = hasChildren && item.onToggle !== undefined;
  const actions = item.actions ?? (item.onActionClick ? [{
    ariaLabel: item.actionAriaLabel ?? item.actionTitle ?? "",
    icon: item.actionIcon ?? "plus",
    onClick: item.onActionClick,
    title: item.actionTitle ?? "",
  }] : []);

  return (
    <div className="tree-nav-node">
      <div
        aria-expanded={hasChildren ? item.isExpanded : undefined}
        className={`tree-nav-item ${item.isActive ? "is-active" : ""}`}
        role="treeitem"
        style={{ paddingLeft: "8px" }}
      >
        {canToggle ? (
          <button
            aria-expanded={item.isExpanded}
            className="tree-nav-toggle"
            onMouseDown={preventMouseFocus}
            onClick={item.onToggle}
            type="button"
          >
            <TreeChevron expanded={item.isExpanded === true} visible />
          </button>
        ) : (
          <span className="tree-nav-toggle tree-nav-toggle-static" aria-hidden="true">
            <TreeChevron expanded={item.isExpanded === true} visible={hasChildren} />
          </span>
        )}

        <button
          className="tree-nav-select"
          onMouseDown={preventMouseFocus}
          onClick={item.onClick}
          type="button"
        >
          <div className="tree-nav-title-row">
            <span className="tree-nav-title">{item.title}</span>
            {item.isLoading ? <span className="tree-nav-loading-dot" aria-hidden="true" /> : null}
          </div>
        </button>
      </div>

      {actions.length > 0 ? <div className="tree-nav-actions">
        {actions.map((action) => (
          <button
            aria-label={action.ariaLabel}
            className="tree-nav-action"
            key={action.ariaLabel}
            onMouseDown={preventMouseFocus}
            onClick={(event) => {
              event.stopPropagation();
              action.onClick(event);
            }}
            title={action.title}
            type="button"
          >
            <Icon name={action.icon} size="tiny" />
          </button>
        ))}
      </div> : null}

      {item.isExpanded && (item.children?.length ?? 0) > 0 ? (
        <div className="tree-nav-children" role="group">
          {item.children?.map((child) => (
            <TreeNavNode depth={depth + 1} item={child} key={child.id} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function preventMouseFocus(event: MouseEvent<HTMLButtonElement>) {
  event.preventDefault();
}

function TreeChevron({ expanded, visible }: { expanded?: boolean; visible: boolean }) {
  return (
    <span className={`tree-nav-chevron ${visible ? "" : "is-hidden"}`.trim()} aria-hidden="true">
      <Icon className={`tree-nav-chevron-icon ${expanded ? "is-expanded" : ""}`} name="chevron-right" size="tiny" weight="strong" />
    </span>
  );
}
