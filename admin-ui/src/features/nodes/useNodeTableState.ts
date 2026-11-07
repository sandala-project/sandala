import { useInfiniteQuery, useQueryClient, type InfiniteData } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import { EPHEMERAL_NODE_QUERY_OPTIONS } from "../../lib/queryOptions";
import type { EntityListItem, JsonSchema } from "../entities/api";
import { getEntityDisplayLabel } from "../entities/presentation";
import { getEntityNodesPage, type NodeDocument } from "./api";
import { buildNodeEditorFields } from "./editorSchema";
import { buildNodeTableSystemFields } from "./nodeTableSystemFields";
import {
  buildNodeTableColumns,
  buildNodeTableGridTemplateColumns,
  getDefaultNodeTableColumnSizing,
} from "./nodeTableColumns";
import {
  buildNodeTableFilterFields,
  compileAppliedNodeTableFilter,
  type NodeTableFilter,
} from "./nodeTableFilter";
import {
  buildNodeTableSortFields,
  compileAppliedNodeTableSort,
  type NodeTableSort,
} from "./nodeTableSort";

const TABLE_PAGE_SIZE = 100;
const ROW_DENSITY_HEIGHTS = {
  comfortable: 76,
  expanded: 132,
} as const;

export type NodesTableState = ReturnType<typeof useNodesTableState>;
export type NodeTableRowDensity = keyof typeof ROW_DENSITY_HEIGHTS;

export function useNodesTableState(args: {
  entitiesInModule: EntityListItem[];
  entityNamesInModule: string[];
  moduleName: string;
  selectedEntity: string;
  setSelectedEntity: (entityName: string) => void;
  tableSchema: JsonSchema | null;
}) {
  const auth = useAuth();
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [editingNodeId, setEditingNodeId] = useState<string | null>(null);
  const [editingCell, setEditingCell] = useState<{ fieldKey: string; nodeId: string } | null>(null);
  const [editingFieldOverlay, setEditingFieldOverlay] = useState<{ fieldKey: string; nodeId: string } | null>(null);
  const [selectedRowId, setSelectedRowId] = useState<string | null>(null);
  const [hoveredRowId, setHoveredRowId] = useState<string | null>(null);
  const [columnSizing, setColumnSizing] = useState<Record<string, number>>({});
  const [hiddenColumnKeys, setHiddenColumnKeys] = useState<string[]>([]);
  const [tableFilterDefinition, setTableFilterDefinition] = useState<NodeTableFilter | null>(null);
  const [isColumnsOpen, setIsColumnsOpen] = useState(false);
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [isSortOpen, setIsSortOpen] = useState(false);
  const [tableSortDefinition, setTableSortDefinition] = useState<NodeTableSort | null>(null);
  const [rowDensity, setRowDensity] = useState<NodeTableRowDensity>("comfortable");
  const [tableScrollElement, setTableScrollElement] = useState<HTMLDivElement | null>(null);

  useEffect(() => {
    if (args.entityNamesInModule.length === 0) {
      if (args.selectedEntity.length > 0) {
        args.setSelectedEntity("");
      }
      return;
    }

    if (args.selectedEntity.length === 0 || !args.entityNamesInModule.includes(args.selectedEntity)) {
      const firstEntity = args.entityNamesInModule[0];
      if (firstEntity !== undefined) {
        args.setSelectedEntity(firstEntity);
      }
    }
  }, [args.entityNamesInModule, args.selectedEntity, args.setSelectedEntity]);

  useEffect(() => {
    setEditingNodeId(null);
    setEditingCell(null);
    setEditingFieldOverlay(null);
    setSelectedRowId(null);
    setHoveredRowId(null);
    setHiddenColumnKeys([]);
    setTableFilterDefinition(null);
    setIsColumnsOpen(false);
    setIsFilterOpen(false);
    setTableSortDefinition(null);
    setIsSortOpen(false);
  }, [args.moduleName, args.selectedEntity]);

  const userTableFields = useMemo(
    () => (args.tableSchema === null ? [] : buildNodeEditorFields(args.tableSchema, auth.user)),
    [args.tableSchema, auth.user],
  );
  const tableFields = useMemo(
    () => [...userTableFields, ...buildNodeTableSystemFields(t)],
    [t, userTableFields],
  );
  const visibleColumnFields = useMemo(
    () => tableFields.filter((field) => !hiddenColumnKeys.includes(field.path.join("."))),
    [hiddenColumnKeys, tableFields],
  );
  const tableColumns = useMemo(
    () => buildNodeTableColumns({ fields: visibleColumnFields }),
    [visibleColumnFields],
  );
  const tableFilterFields = useMemo(
    () => buildNodeTableFilterFields(tableFields, { includePermissions: auth.user?.role === "superuser" || Boolean(auth.user?.superuser) }),
    [auth.user, tableFields],
  );
  const tableFilter = useMemo(
    () => compileAppliedNodeTableFilter(tableFilterDefinition),
    [tableFilterDefinition],
  );
  const tableFilterKey = JSON.stringify(tableFilter);
  const tableSortFields = useMemo(
    () => buildNodeTableSortFields(tableFields),
    [tableFields],
  );
  const tableSort = useMemo(
    () => compileAppliedNodeTableSort(tableSortDefinition),
    [tableSortDefinition],
  );
  const tableSortKey = JSON.stringify(tableSort);
  useEffect(() => {
    setColumnSizing((current) => {
      const defaults = getDefaultNodeTableColumnSizing(tableColumns);
      const next: Record<string, number> = {};

      tableColumns.forEach((column) => {
        next[column.key] = current[column.key] ?? defaults[column.key] ?? column.defaultWidth;
      });

      return next;
    });
  }, [tableColumns]);
  const gridTemplateColumns = useMemo(
    () => buildNodeTableGridTemplateColumns(tableColumns, columnSizing),
    [columnSizing, tableColumns],
  );

  const tableQueryKey = ["nodes", "table", args.moduleName, args.selectedEntity, tableFilterKey, tableSortKey] as const;
  const tableNodesQuery = useInfiniteQuery({
    ...EPHEMERAL_NODE_QUERY_OPTIONS,
    enabled: args.moduleName.length > 0 && args.selectedEntity.length > 0 && args.tableSchema !== null,
    initialPageParam: 0,
    queryKey: tableQueryKey,
    queryFn: ({ pageParam, signal }) =>
      getEntityNodesPage({
        entityName: args.selectedEntity,
        filter: tableFilter,
        limit: TABLE_PAGE_SIZE,
        moduleName: args.moduleName,
        offset: pageParam,
        signal,
        sort: Object.keys(tableSort).length > 0 ? tableSort : undefined,
      }),
    getNextPageParam: (lastPage, allPages) =>
      lastPage.length < TABLE_PAGE_SIZE ? undefined : allPages.length * TABLE_PAGE_SIZE,
  });

  useEffect(() => {
    tableScrollElement?.scrollTo({ top: 0 });
  }, [args.moduleName, args.selectedEntity, tableFilterKey, tableSortKey, tableScrollElement]);
  function replaceTableNode(nextNode: NodeDocument) {
    const nodeId = typeof nextNode.id === "string" ? nextNode.id : "";
    if (nodeId.length === 0) {
      return;
    }

    queryClient.setQueryData<InfiniteData<NodeDocument[]>>(tableQueryKey, (current) => {
      if (current === undefined) {
        return current;
      }

      let changed = false;
      const pages = current.pages.map((page) => page.map((node) => {
        if (node.id !== nodeId) {
          return node;
        }

        changed = true;
        return nextNode;
      }));

      return changed ? { ...current, pages } : current;
    });
  }

  async function reconcileTableAfterMutation(nextNode?: NodeDocument) {
    if (nextNode !== undefined) {
      replaceTableNode(nextNode);
    }
    await tableNodesQuery.refetch();
  }

  const rows = useMemo(
    () => tableNodesQuery.data?.pages.flatMap((page) => page) ?? [],
    [tableNodesQuery.data],
  );
  const rowsById = useMemo(() => {
    const next: Record<string, NodeDocument> = {};
    rows.forEach((node) => {
      if (typeof node.id === "string" && node.id.length > 0) {
        next[node.id] = node;
      }
    });
    return next;
  }, [rows]);

  useEffect(() => {
    if (tableNodesQuery.isFetching) {
      return;
    }

    if (selectedRowId !== null && rowsById[selectedRowId] === undefined) {
      setSelectedRowId(null);
    }
    if (editingNodeId !== null && rowsById[editingNodeId] === undefined) {
      setEditingNodeId(null);
    }
    if (editingCell !== null && rowsById[editingCell.nodeId] === undefined) {
      setEditingCell(null);
    }
    if (editingFieldOverlay !== null && rowsById[editingFieldOverlay.nodeId] === undefined) {
      setEditingFieldOverlay(null);
    }
  }, [editingCell, editingFieldOverlay, editingNodeId, rowsById, selectedRowId, tableNodesQuery.isFetching]);

  const editingCellField = editingCell === null
    ? null
    : tableColumns.find((column) => column.key === editingCell.fieldKey)?.field ?? null;
  const editingCellNode = editingCell === null ? null : rowsById[editingCell.nodeId] ?? null;
  const editingOverlayField = editingFieldOverlay === null
    ? null
    : tableColumns.find((column) => column.key === editingFieldOverlay.fieldKey)?.field ?? null;
  const editingOverlayNode = editingFieldOverlay === null ? null : rowsById[editingFieldOverlay.nodeId] ?? null;

  const entityOptions = useMemo(
    () => args.entitiesInModule.map((entity) => ({ label: getEntityDisplayLabel(entity), value: entity.title })),
    [args.entitiesInModule],
  );

  return {
    editingCell,
    editingCellField,
    editingCellNode,
    editingFieldOverlay,
    editingNodeId,
    editingOverlayField,
    editingOverlayNode,
    columnSizing,
    hiddenColumnKeys,
    tableFilterDefinition,
    tableSortDefinition,
    entityOptions,
    gridTemplateColumns,
    hoveredRowId,
    isColumnsOpen,
    isFilterOpen,
    isSortOpen,
    rowDensity,
    rowHeight: ROW_DENSITY_HEIGHTS[rowDensity],
    reconcileTableAfterMutation,
    rows,
    rowsById,
    selectedRowId,
    setEditingCell,
    setEditingFieldOverlay,
    setEditingNodeId,
    setHoveredRowId,
    setSelectedRowId,
    setColumnSizing,
    setHiddenColumnKeys,
    setTableFilterDefinition,
    setIsColumnsOpen,
    setIsFilterOpen,
    setTableSortDefinition,
    setIsSortOpen,
    setRowDensity,
    tableColumns,
    tableFields,
    tableFilterFields,
    tableSortFields,
    tableNodesQuery,
    setTableScrollElement,
    tableScrollElement,
  };
}
