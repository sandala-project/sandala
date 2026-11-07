import { useRef } from "react";
import { IconButton } from "../../components/IconButton";
import { useI18n } from "../../providers/I18nProvider";
import type { NodeTableColumn } from "./nodeTableColumns";
import { resolveNodeTableColumnWidth } from "./nodeTableColumns";

export function NodesTableHeader(args: {
  columnSizing: Record<string, number>;
  columns: NodeTableColumn[];
  filterPaths: string[];
  gridTemplateColumns: string;
  onOpenFilter: () => void;
  onOpenSort: () => void;
  onColumnResize: (columnKey: string, width: number) => void;
  onColumnResizeReset: (columnKey: string) => void;
  sortPaths: string[];
}) {
  const { t } = useI18n();
  const resizeStateRef = useRef<{
    columnKey: string;
    startWidth: number;
    startX: number;
  } | null>(null);

  return (
    <div className="nodes-table-header" style={{ gridTemplateColumns: args.gridTemplateColumns }}>
      {args.columns.map((column) => (
        <div
          className={`nodes-table-header-cell column-${column.kind}`.trim()}
          key={column.key}
        >
          <span className="nodes-table-header-label">{column.label}</span>
          {column.field !== null && hasPathForColumn(args.filterPaths, column.key) ? (
            <IconButton
              icon="filter"
              label={`${t("pages.nodes.table.filter.openForColumn")} ${column.label}`}
              onClick={(event) => {
                event.stopPropagation();
                args.onOpenFilter();
              }}
              variant="bare"
            />
          ) : null}
          {column.field !== null && hasPathForColumn(args.sortPaths, column.key) ? (
            <IconButton
              icon="arrow-down-up"
              label={`${t("pages.nodes.table.sort.openForColumn")} ${column.label}`}
              onClick={(event) => {
                event.stopPropagation();
                args.onOpenSort();
              }}
              variant="bare"
            />
          ) : null}
          {column.resizable ? (
            <button
              aria-label={`${t("pages.nodes.table.resizeColumn")} ${column.label}`.trim()}
              className="nodes-table-resize-handle"
              onDoubleClick={(event) => {
                event.preventDefault();
                event.stopPropagation();
                args.onColumnResizeReset(column.key);
              }}
              onMouseDown={(event) => {
                event.preventDefault();
                event.stopPropagation();

                resizeStateRef.current = {
                  columnKey: column.key,
                  startWidth: resolveNodeTableColumnWidth(column, args.columnSizing),
                  startX: event.clientX,
                };

                const handleMouseMove = (moveEvent: MouseEvent) => {
                  const state = resizeStateRef.current;
                  if (state === null || state.columnKey !== column.key) {
                    return;
                  }

                  const nextWidth = state.startWidth + (moveEvent.clientX - state.startX);
                  args.onColumnResize(column.key, nextWidth);
                };

                const handleMouseUp = () => {
                  resizeStateRef.current = null;
                  window.removeEventListener("mousemove", handleMouseMove);
                  window.removeEventListener("mouseup", handleMouseUp);
                };

                window.addEventListener("mousemove", handleMouseMove);
                window.addEventListener("mouseup", handleMouseUp);
              }}
              type="button"
            />
          ) : null}
        </div>
      ))}
    </div>
  );
}

function hasPathForColumn(paths: string[], columnPath: string) {
  return paths.some((path) => path === columnPath || path.startsWith(`${columnPath}.`));
}
