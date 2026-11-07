import { useQueries, useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useMemo, useRef, useState, type Dispatch, type MouseEvent as ReactMouseEvent, type RefObject, type SetStateAction } from "react";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { CompactOptionMenu } from "../components/CompactOptionMenu";
import { EmptyState } from "../components/EmptyState";
import { Icon } from "../components/Icon";
import { IconButton } from "../components/IconButton";
import { OverlayCloseButton } from "../components/OverlayCloseButton";
import { OverlayDialog } from "../components/OverlayDialog";
import { Select, type SelectOption } from "../components/Select";
import { SplitPane } from "../components/SplitPane";
import { Spinner } from "../components/Spinner";
import { TopbarPortal } from "../components/TopbarContent";
import { TreeNav, type TreeNavItem } from "../components/TreeNav";
import { getEntities, getEntitySchema, getModules, type JsonSchema } from "../features/entities/api";
import { getEntityDisplayLabel, getModuleDisplayLabel } from "../features/entities/presentation";
import { getChildNodes, getNode, getRootNodes, type NodeDocument } from "../features/nodes/api";
import { NodeDeleteOverlay } from "../features/nodes/NodeDeleteOverlay";
import { NodesTableScene } from "../features/nodes/NodesTableScene";
import { createInitialNodeDraft } from "../features/nodes/nodeCreate";
import { NodeEditor } from "../features/nodes/NodeEditor";
import { hasNodeTableFilter } from "../features/nodes/nodeTableFilter";
import { hasNodeTableSort } from "../features/nodes/nodeTableSort";
import { getNodeReferenceId } from "../features/nodes/nodeFieldUtils";
import { buildNodeEntityPresentation, resolveNodeDisplayLabel, type NodeEntityPresentationRegistry } from "../features/nodes/presentation";
import { canPopulateModuleRoot, canPopulateNodeDocument, resolveNodeCreateTargets, resolveRootCreateTargets } from "../features/nodes/treeCapabilities";
import { canWriteNodeDocument } from "../features/nodes/nodeAccess";
import { useNodesTableState } from "../features/nodes/useNodeTableState";
import { ApiError } from "../lib/api";
import { localizeApiError } from "../lib/errors";
import { structureKeys } from "../lib/queryKeys";
import { EPHEMERAL_NODE_QUERY_OPTIONS, SCHEMA_QUERY_OPTIONS, STRUCTURE_QUERY_OPTIONS } from "../lib/queryOptions";
import type { AuthenticatedUser } from "../lib/session";
import type { TranslationKey } from "../locales";
import { useAuth } from "../providers/AuthProvider";
import { useI18n } from "../providers/I18nProvider";
import { APP_ROUTE_PREFIX } from "../router/routeConfig";

type BranchState = {
  error: string | null;
  isLoaded: boolean;
  isLoading: boolean;
  nodeIds: string[];
};

type BranchLoadResult =
  | { nodeIds: string[]; status: "loaded" }
  | { status: "discarded" }
  | { nodeIds: string[]; status: "failed" };

const EMPTY_BRANCH_STATE: BranchState = {
  error: null,
  isLoaded: false,
  isLoading: false,
  nodeIds: [],
};

type CreateState = {
  entityName: string;
  parentId: string | null | undefined;
};

type CreateMenuState = {
  anchorLeft: number;
  anchorTop: number;
  parentId: string | null;
  targets: string[];
};

export function NodesPage({ mode }: { mode: "table" | "tree" }) {
  const auth = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();
  const params = useParams({ strict: false }) as { entity?: string; module?: string; nodeId?: string };
  const [selectedTableEntity, setSelectedTableEntity] = useState(() => mode === "table" ? params.entity ?? "" : "");
  const [expandedNodeIds, setExpandedNodeIds] = useState<string[]>([]);
  const [createState, setCreateState] = useState<CreateState | null>(null);
  const [createMenuState, setCreateMenuState] = useState<CreateMenuState | null>(null);
  const [deleteNodeState, setDeleteNodeState] = useState<NodeDocument | null>(null);
  const [savedSelectedNode, setSavedSelectedNode] = useState<NodeDocument | null>(null);
  const [branchStates, setBranchStates] = useState<Record<string, BranchState>>({});
  const [nodesByKey, setNodesByKey] = useState<Record<string, NodeDocument>>({});
  const selectedModule = params.module ?? "";
  const selectedNodeId = mode === "tree" ? params.nodeId ?? null : null;
  const branchStatesRef = useRef<Record<string, BranchState>>({});
  const branchRequestVersionsRef = useRef<Record<string, number>>({});
  const branchAbortControllersRef = useRef<Record<string, AbortController>>({});
  const nodesByKeyRef = useRef<Record<string, NodeDocument>>({});
  const skipSelectedNodeExpansionRef = useRef(false);
  const selectedModuleRef = useRef(selectedModule);
  const sidebarRef = useRef<HTMLElement | null>(null);

  function navigateToTree(moduleName: string, nodeId?: string | null) {
    if (moduleName.trim().length === 0) {
      void navigate({ to: `${APP_ROUTE_PREFIX}/nodes/tree` });
      return;
    }

    if (nodeId && nodeId.trim().length > 0) {
      void navigate({ to: `${APP_ROUTE_PREFIX}/nodes/tree/$module/$nodeId`, params: { module: moduleName, nodeId } });
      return;
    }

    void navigate({ to: `${APP_ROUTE_PREFIX}/nodes/tree/$module`, params: { module: moduleName } });
  }

  function navigateToTable(moduleName: string, entityName?: string) {
    if (moduleName.trim().length === 0) {
      void navigate({ to: `${APP_ROUTE_PREFIX}/nodes/table` });
      return;
    }

    if (entityName !== undefined && entityName.trim().length > 0) {
      void navigate({ to: `${APP_ROUTE_PREFIX}/nodes/table/$module/$entity`, params: { entity: entityName, module: moduleName } });
      return;
    }

    void navigate({ to: `${APP_ROUTE_PREFIX}/nodes/table/$module`, params: { module: moduleName } });
  }

  useEffect(() => {
    branchStatesRef.current = branchStates;
  }, [branchStates]);

  useEffect(() => {
    nodesByKeyRef.current = nodesByKey;
  }, [nodesByKey]);

  useEffect(() => () => {
    Object.values(branchAbortControllersRef.current).forEach((controller) => controller.abort());
  }, []);

  useEffect(() => {
    selectedModuleRef.current = selectedModule;
  }, [selectedModule]);

  useEffect(() => {
    skipSelectedNodeExpansionRef.current = false;
    setSavedSelectedNode(null);
  }, [selectedModule, selectedNodeId]);

  useEffect(() => {
    if (createMenuState === null) {
      return;
    }

    function handlePointerDown(event: MouseEvent) {
      const target = event.target;
      if (!(target instanceof Node)) {
        setCreateMenuState(null);
        return;
      }
      if (sidebarRef.current?.contains(target)) {
        return;
      }
      setCreateMenuState(null);
    }

    document.addEventListener("mousedown", handlePointerDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
    };
  }, [createMenuState]);

  const modulesQuery = useQuery({
    ...STRUCTURE_QUERY_OPTIONS,
    queryKey: structureKeys.modules(),
    queryFn: ({ signal }) => getModules(signal),
  });

  const moduleEntitiesQuery = useQuery({
    ...STRUCTURE_QUERY_OPTIONS,
    enabled: selectedModule.length > 0,
    queryKey: structureKeys.entities(selectedModule),
    queryFn: ({ signal }) => getEntities(selectedModule, signal),
  });

  const entitySchemaQueries = useQueries({
    queries: (moduleEntitiesQuery.data ?? []).map((entityDoc) => ({
      ...SCHEMA_QUERY_OPTIONS,
      enabled: selectedModule.length > 0,
      queryKey: structureKeys.schema(selectedModule, entityDoc.title),
      queryFn: ({ signal }: { signal: AbortSignal }) => getEntitySchema(selectedModule, entityDoc.title, signal),
    })),
  });

  useEffect(() => {
    if (modulesQuery.data === undefined || modulesQuery.data.length === 0) {
      return;
    }

    const firstModule = modulesQuery.data[0];
    if (firstModule === undefined) {
      return;
    }

    if (selectedModule.length === 0) {
      if (mode === "tree") {
        navigateToTree(firstModule.name);
      } else {
        navigateToTable(firstModule.name);
      }
      return;
    }

    if (!modulesQuery.data.some((moduleDoc) => moduleDoc.name === selectedModule)) {
      setCreateState(null);
      setCreateMenuState(null);
      if (mode === "tree") {
        navigateToTree(firstModule.name);
      } else {
        navigateToTable(firstModule.name);
      }
    }
  }, [mode, modulesQuery.data, selectedModule]);

  useEffect(() => {
    setSelectedTableEntity("");
    setCreateState(null);
    setCreateMenuState(null);
    setExpandedNodeIds([]);
    Object.values(branchAbortControllersRef.current).forEach((controller) => controller.abort());
    branchAbortControllersRef.current = {};
    branchStatesRef.current = {};
    branchRequestVersionsRef.current = {};
    nodesByKeyRef.current = {};
    setBranchStates({});
    setNodesByKey({});
  }, [selectedModule]);

  useEffect(() => {
    if (mode !== "tree" || selectedModule.length === 0) {
      return;
    }

    void ensureBranchLoaded({
      branchStatesRef,
      branchRequestVersionsRef,
      branchAbortControllersRef,
      moduleName: selectedModule,
      nodesByKeyRef,
      parentId: null,
      selectedModuleRef,
      setBranchStates,
      setExpandedNodeIds,
      setNodesByKey,
      t,
    });
  }, [mode, selectedModule, t]);

  const moduleOptions = useMemo<SelectOption[]>(
    () => (modulesQuery.data ?? []).map((moduleDoc) => ({ label: getModuleDisplayLabel(moduleDoc), value: moduleDoc.name })),
    [modulesQuery.data],
  );
  const selectedModuleDoc = useMemo(
    () => (modulesQuery.data ?? []).find((moduleDoc) => moduleDoc.name === selectedModule) ?? null,
    [modulesQuery.data, selectedModule],
  );
  const entitiesInModule = moduleEntitiesQuery.data ?? [];
  const entityNamesInModule = useMemo(
    () => entitiesInModule.map((entityDoc) => entityDoc.title),
    [entitiesInModule],
  );
  const entityDisplayLabels = useMemo(
    () => new Map(entitiesInModule.map((entityDoc) => [entityDoc.title, getEntityDisplayLabel(entityDoc)])),
    [entitiesInModule],
  );
  const routeTableEntity = mode === "table" ? params.entity ?? "" : "";

  useEffect(() => {
    if (mode !== "table" || routeTableEntity.length === 0 || !entityNamesInModule.includes(routeTableEntity)) {
      return;
    }

    if (selectedTableEntity !== routeTableEntity) {
      setSelectedTableEntity(routeTableEntity);
    }
  }, [entityNamesInModule, mode, routeTableEntity, selectedTableEntity]);
  const entityPresentationRegistry = useMemo<NodeEntityPresentationRegistry>(() => {
    const registry: NodeEntityPresentationRegistry = {};
    const entities = moduleEntitiesQuery.data ?? [];

    entities.forEach((entityDoc, index) => {
      const schema = entitySchemaQueries[index]?.data;
      if (schema === undefined) {
        return;
      }
      registry[entityDoc.title] = buildNodeEntityPresentation(schema);
    });

    return registry;
  }, [entitySchemaQueries, moduleEntitiesQuery.data]);

  const entitySchemaRegistry = useMemo<Record<string, JsonSchema>>(() => {
    const registry: Record<string, JsonSchema> = {};
    const entities = moduleEntitiesQuery.data ?? [];

    entities.forEach((entityDoc, index) => {
      const schema = entitySchemaQueries[index]?.data;
      if (schema !== undefined) {
        registry[entityDoc.title] = schema;
      }
    });

    return registry;
  }, [entitySchemaQueries, moduleEntitiesQuery.data]);
  const selectedTableSchema =
    selectedTableEntity.length > 0
      ? entitySchemaRegistry[selectedTableEntity] ?? null
      : null;
  const tableState = useNodesTableState({
    entitiesInModule,
    entityNamesInModule,
    moduleName: selectedModule,
    selectedEntity: selectedTableEntity,
    setSelectedEntity: setSelectedTableEntity,
    tableSchema: selectedTableSchema,
  });

  const rootCreateTargets = useMemo(
    () =>
      selectedModuleDoc === null
        ? []
        : resolveRootCreateTargets(selectedModuleDoc, entityNamesInModule),
    [entityNamesInModule, selectedModuleDoc],
  );
  const canCreateInRoot = selectedModuleDoc !== null
    && canPopulateModuleRoot(selectedModuleDoc, auth.user)
    && rootCreateTargets.length > 0;
  const tableParentEntityNames = useMemo(
    () => entityNamesInModule.filter((entityName) =>
      resolveNodeCreateTargets(entitySchemaRegistry[entityName], entityNamesInModule).includes(selectedTableEntity),
    ),
    [entityNamesInModule, entitySchemaRegistry, selectedTableEntity],
  );
  const canCreateTableInRoot = selectedModuleDoc !== null
    && selectedTableEntity.length > 0
    && canPopulateModuleRoot(selectedModuleDoc, auth.user)
    && rootCreateTargets.includes(selectedTableEntity);
  const canCreateTableNode = selectedTableSchema !== null
    && selectedTableEntity.length > 0
    && (canCreateTableInRoot || tableParentEntityNames.length > 0);

  const rootBranchKey = selectedModule.length > 0 ? makeBranchKey(selectedModule, null) : null;
  const rootBranchState = rootBranchKey ? branchStates[rootBranchKey] ?? EMPTY_BRANCH_STATE : EMPTY_BRANCH_STATE;

  const openCreateMenu = (args: {
    anchorElement: HTMLElement;
    parentId: string | null;
    targets: string[];
  }) => {
    if (args.targets.length === 0) {
      return;
    }

    if (args.targets.length === 1) {
      const onlyTarget = args.targets[0];
      if (onlyTarget !== undefined) {
        setCreateMenuState(null);
        setCreateState({ entityName: onlyTarget, parentId: args.parentId });
      }
      return;
    }

    const sidebarRect = sidebarRef.current?.getBoundingClientRect();
    const anchorRect = args.anchorElement.getBoundingClientRect();
    if (sidebarRect === undefined) {
      return;
    }
    const preferredWidth = 220;
    const maxLeft = Math.max(8, sidebarRect.width - preferredWidth - 8);

    setCreateMenuState({
      anchorLeft: Math.max(8, Math.min(anchorRect.left - sidebarRect.left, maxLeft)),
      anchorTop: anchorRect.bottom - sidebarRect.top + 6,
      parentId: args.parentId,
      targets: args.targets,
    });
  };

  const selectedNodeQuery = useQuery({
    ...EPHEMERAL_NODE_QUERY_OPTIONS,
    enabled: mode === "tree" && selectedModule.length > 0 && selectedNodeId !== null,
    queryKey: ["nodes", "tree-selected", selectedModule, selectedNodeId],
    queryFn: ({ signal }) => getNode(selectedModule, selectedNodeId!, signal),
  });
  const selectedNode = savedSelectedNode ?? selectedNodeQuery.data ?? null;

  useEffect(() => {
    if (mode !== "tree" || selectedModule.length === 0 || selectedNodeId === null || selectedNode === null) {
      return;
    }

    if (skipSelectedNodeExpansionRef.current) {
      skipSelectedNodeExpansionRef.current = false;
      return;
    }

    const ancestorIds = selectedNode.ancestors?.filter((ancestorId): ancestorId is string => typeof ancestorId === "string" && ancestorId.length > 0) ?? [];

    setExpandedNodeIds((current) => {
      const next = [...current];
      for (const ancestorId of ancestorIds) {
        if (!next.includes(ancestorId)) {
          next.push(ancestorId);
        }
      }
      return next;
    });

    void (async () => {
      await ensureBranchLoaded({
        branchStatesRef,
        branchRequestVersionsRef,
        branchAbortControllersRef,
        moduleName: selectedModule,
        nodesByKeyRef,
        parentId: null,
        selectedModuleRef,
        setBranchStates,
        setExpandedNodeIds,
        setNodesByKey,
        t,
      });

      for (const ancestorId of ancestorIds) {
        await ensureBranchLoaded({
          branchStatesRef,
          branchRequestVersionsRef,
          branchAbortControllersRef,
          moduleName: selectedModule,
          nodesByKeyRef,
          parentId: ancestorId,
          selectedModuleRef,
          setBranchStates,
          setExpandedNodeIds,
          setNodesByKey,
          t,
        });
      }
    })();
  }, [mode, selectedModule, selectedNode, selectedNodeId, t]);

  const treeItems = selectedModule.length > 0
    && mode === "tree"
    ? buildTreeItems({
        branchStates,
        entityNamesInModule,
        entityPresentationRegistry,
        entitySchemaRegistry,
        expandedNodeIds,
        moduleName: selectedModule,
        nodesByKey,
        user: auth.user,
        onCreateRequest: (parentId, targets, anchorElement) => {
          openCreateMenu({ anchorElement, parentId, targets });
        },
        onDeleteRequest: (node) => {
          setCreateState(null);
          setCreateMenuState(null);
          setDeleteNodeState(node);
        },
        onSelect: (nodeId) => {
          setCreateState(null);
          setCreateMenuState(null);
          navigateToTree(selectedModule, nodeId);
        },
        onToggle: (nodeId) => {
          void toggleNodeBranch({
            branchStatesRef,
            branchRequestVersionsRef,
            branchAbortControllersRef,
            expandedNodeIds,
            moduleName: selectedModule,
            nodeId,
            nodesByKeyRef,
            selectedModuleRef,
            setBranchStates,
            setExpandedNodeIds,
            setNodesByKey,
            t,
          });
        },
        rootNodeIds: rootBranchState.nodeIds,
        selectedNodeAncestorIds: new Set(
          selectedNode?.ancestors?.filter((ancestorId): ancestorId is string => typeof ancestorId === "string" && ancestorId.length > 0) ?? [],
        ),
        selectedNodeId,
        t,
      })
    : [];
  const selectedNodeSchema =
    selectedNode !== null && typeof selectedNode.entity === "string"
      ? entitySchemaRegistry[selectedNode.entity] ?? null
      : null;
  const selectedNodeForEditor = selectedNodeQuery.isFetching ? null : savedSelectedNode ?? selectedNodeQuery.data ?? null;
  const treeParentPicker = useMemo(() => {
    if (selectedNodeForEditor === null || selectedModuleDoc === null || typeof selectedNodeForEditor.entity !== "string") {
      return undefined;
    }

    const childEntityName = selectedNodeForEditor.entity;
    const parentEntityNames = entityNamesInModule.filter((entityName) =>
      resolveNodeCreateTargets(entitySchemaRegistry[entityName], entityNamesInModule).includes(childEntityName),
    );
    const nodeId = typeof selectedNodeForEditor.id === "string" ? selectedNodeForEditor.id : undefined;

    return {
      canSelectRoot:
        canPopulateModuleRoot(selectedModuleDoc, auth.user) &&
        resolveRootCreateTargets(selectedModuleDoc, entityNamesInModule).includes(childEntityName),
      excludeNodeId: nodeId,
      parentEntityNames,
    };
  }, [auth.user, entityNamesInModule, entitySchemaRegistry, selectedModuleDoc, selectedNodeForEditor]);
  const createSchema =
    createState !== null
      ? entitySchemaRegistry[createState.entityName] ?? null
      : null;
  const createDraft = useMemo(
    () =>
      createState !== null && createSchema !== null
        ? createInitialNodeDraft({
            entityName: createState.entityName,
            parentId: createState.parentId,
            schema: createSchema,
            user: auth.user,
          })
        : null,
    [auth.user, createSchema, createState],
  );
  const tableFilterError =
    mode === "table" &&
    tableState.tableFilterDefinition !== null &&
    tableState.tableNodesQuery.isError
      ? getTableFilterErrorMessage(tableState.tableNodesQuery.error, t)
      : null;
  const hasTableFilter = hasNodeTableFilter(tableState.tableFilterDefinition);
  const hasTableSort = hasNodeTableSort(tableState.tableSortDefinition);
  const hasHiddenTableColumns = tableState.hiddenColumnKeys.length > 0;
  const tableSortError =
    mode === "table" &&
    tableState.tableSortDefinition !== null &&
    tableState.tableNodesQuery.isError
      ? getTableSortErrorMessage(tableState.tableNodesQuery.error, t)
      : null;

  const nodesToolbar = (
    <div className="nodes-toolbar">
        <Select
          disabled={modulesQuery.isPending || moduleOptions.length === 0}
          onChange={(nextModule) => {
            if (mode === "tree") {
              navigateToTree(nextModule);
            } else {
              navigateToTable(nextModule);
            }
          }}
          options={moduleOptions}
          value={selectedModule}
        />

        <CompactOptionMenu
          buttonLabel={t("pages.nodes.toolbar.mode")}
          className="nodes-mode-selector"
          options={[
            { icon: "nodes-table-view", label: t("pages.nodes.mode.table"), value: "table" },
            { icon: "nodes-tree-view", label: t("pages.nodes.mode.tree"), value: "tree" },
          ]}
          value={mode}
          onChange={(nextMode) => {
            if (nextMode === "tree") {
              navigateToTree(selectedModule);
            } else {
              navigateToTable(selectedModule);
            }
          }}
        />

        {mode === "table" ? (
          <>
            <Select
              disabled={tableState.entityOptions.length === 0}
              onChange={(value) => {
                setSelectedTableEntity(value);
                navigateToTable(selectedModule, value);
              }}
              options={tableState.entityOptions}
              value={selectedTableEntity}
            />
            <div className="nodes-toolbar-spacer" />
            <IconButton
              aria-busy={tableState.tableNodesQuery.isFetching}
              className={tableState.tableNodesQuery.isFetching ? "is-loading" : ""}
              disabled={tableState.tableNodesQuery.isFetching || selectedTableEntity.length === 0}
              icon="nodes-reload"
              label={t("pages.nodes.table.reload")}
              onClick={() => {
                void tableState.tableNodesQuery.refetch();
              }}
              size="regular"
            />
            <div className="nodes-table-filter-control">
              <IconButton
                aria-pressed={hasTableFilter}
                disabled={selectedTableEntity.length === 0 || tableState.tableFilterFields.length === 0}
                hasIndicator={hasTableFilter}
                icon="nodes-filter"
                label={t("pages.nodes.table.filter.action")}
                onClick={() => tableState.setIsFilterOpen(true)}
                size="regular"
              />
              {tableFilterError ? <div className="nodes-table-filter-error" role="alert">{tableFilterError}</div> : null}
            </div>
            <div className="nodes-table-filter-control">
              <IconButton
                aria-pressed={hasTableSort}
                disabled={selectedTableEntity.length === 0 || tableState.tableSortFields.length === 0}
                hasIndicator={hasTableSort}
                icon="nodes-sort"
                label={t("pages.nodes.table.sort.action")}
                onClick={() => tableState.setIsSortOpen(true)}
                size="regular"
              />
              {tableSortError ? <div className="nodes-table-filter-error" role="alert">{tableSortError}</div> : null}
            </div>
            <div className="nodes-table-filter-control">
              <IconButton
                aria-pressed={hasHiddenTableColumns}
                disabled={selectedTableEntity.length === 0 || tableState.tableFields.length === 0}
                hasIndicator={hasHiddenTableColumns}
                icon="nodes-columns"
                label={t("pages.nodes.table.columns.action")}
                onClick={() => tableState.setIsColumnsOpen(true)}
                size="regular"
              />
            </div>
            <CompactOptionMenu
              buttonLabel={t("pages.nodes.table.density")}
              options={[
                { icon: "nodes-density-comfortable", label: t("pages.nodes.table.density.comfortable"), value: "comfortable" },
                { icon: "nodes-density-expanded", label: t("pages.nodes.table.density.expanded"), value: "expanded" },
              ]}
              showSelectedLabel={false}
              value={tableState.rowDensity}
              onChange={tableState.setRowDensity}
            />
            <Button
              aria-label={t("pages.nodes.table.create")}
              className="nodes-create-button"
              disabled={!canCreateTableNode}
              onClick={() => {
                setCreateState({
                  entityName: selectedTableEntity,
                  parentId: canCreateTableInRoot ? null : undefined,
                });
              }}
              title={t("pages.nodes.table.create")}
              type="button"
            >
              <Icon name="nodes-create" weight="strong" />
            </Button>
          </>
        ) : null}
    </div>
  );

  return (
    <>
      <TopbarPortal>{nodesToolbar}</TopbarPortal>
      <section className="nodes-screen">

      {mode === "table" ? (
        <NodesTableScene
          moduleName={selectedModule}
          state={tableState}
          tableSchema={selectedTableSchema}
        />
      ) : (
      <SplitPane className="nodes-tree-layout" storageKey="sandala.admin-ui.nodes-tree.split-pane">
        <aside className="nodes-tree-sidebar" ref={sidebarRef}>
          <Card
            title={
              <div className="panel-header-actions">
                <strong>{t("pages.nodes.tree.title")}</strong>
                {canCreateInRoot ? (
                  <IconButton
                    icon="plus"
                    label={t("pages.nodes.tree.addRoot")}
                    onClick={(event) => {
                      openCreateMenu({
                        anchorElement: event.currentTarget,
                        parentId: null,
                        targets: rootCreateTargets,
                      });
                    }}
                  />
                ) : null}
              </div>
            }
          >
            {modulesQuery.isPending ? (
              <div className="list-loading">
                <Spinner />
              </div>
            ) : moduleOptions.length === 0 ? (
              <EmptyState
                description={t("pages.nodes.empty.modules.description")}
                title={t("pages.nodes.empty.modules.title")}
              />
            ) : rootBranchState.isLoading && rootBranchState.nodeIds.length === 0 ? (
              <div className="list-loading">
                <Spinner />
              </div>
            ) : rootBranchState.error && rootBranchState.nodeIds.length === 0 ? (
              <div className="nodes-branch-message">{rootBranchState.error}</div>
            ) : treeItems.length === 0 ? (
              <EmptyState
                description={t("pages.nodes.empty.tree.description")}
                title={t("pages.nodes.empty.tree.title")}
              />
            ) : (
              <TreeNav items={treeItems} />
            )}
          </Card>

          {createMenuState !== null ? (
            <div
              className="tree-action-menu"
              style={{
                left: `${createMenuState.anchorLeft}px`,
                top: `${createMenuState.anchorTop}px`,
              }}
            >
              <div className="tree-action-menu-list">
                {createMenuState.targets.map((entityName) => (
                  <button
                    className="tree-action-menu-item"
                    key={`${createMenuState.parentId ?? "__root__"}:${entityName}`}
                    onClick={() => {
                      setCreateState({
                        entityName,
                        parentId: createMenuState.parentId,
                      });
                      setCreateMenuState(null);
                    }}
                    type="button"
                  >
                    {entityDisplayLabels.get(entityName) ?? entityName}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </aside>

        <div className="nodes-tree-main">
          {createState !== null && (createDraft === null || createSchema === null) ? (
            <div className="panel panel-centered">
              <Spinner />
            </div>
          ) : createState !== null && createDraft !== null && createSchema !== null ? (
            <NodeEditor
              mode="create"
              moduleName={selectedModule}
              node={createDraft}
              onSaved={(nextNode) => {
                const nextNodeId = typeof nextNode.id === "string" ? nextNode.id : "";
                if (nextNodeId.length === 0) {
                  return;
                }
                applyCreatedNodeToTree({
                  branchStatesRef,
                  moduleName: selectedModule,
                  nextNode,
                  nodesByKeyRef,
                  parentId: createState.parentId ?? null,
                  setBranchStates,
                  setExpandedNodeIds,
                  setNodesByKey,
                });
                navigateToTree(selectedModule, nextNodeId);
                setCreateState(null);
              }}
              schema={createSchema}
              variant="full"
            />
          ) : selectedNodeId !== null && selectedNodeQuery.isFetching ? (
            <div className="panel panel-centered">
              <Spinner />
            </div>
          ) : selectedNodeForEditor === null ? (
            <Card title={<strong>{t("pages.nodes.placeholder.title")}</strong>} tone="muted">
              <p>{t("pages.nodes.placeholder.description")}</p>
            </Card>
          ) : selectedNodeSchema === null ? (
            <div className="panel panel-centered">
              <Spinner />
            </div>
          ) : (
            <NodeEditor
              moduleName={selectedModule}
              node={selectedNodeForEditor}
              onAclUpdated={(nextNode) => {
                if (selectedNodeId === null) {
                  return;
                }
                updateNodesByKey(nodesByKeyRef, setNodesByKey, (current) => ({
                  ...current,
                  [makeNodeKey(selectedModule, selectedNodeId)]: {
                    ...(current[makeNodeKey(selectedModule, selectedNodeId)] ?? selectedNodeForEditor),
                    owner: nextNode.owner,
                    group: nextNode.group,
                    perm: nextNode.perm,
                  },
                }));
              }}
              onSaved={(nextNode) => {
                if (selectedNodeId === null) {
                  return;
                }
                updateNodesByKey(nodesByKeyRef, setNodesByKey, (current) => ({
                  ...current,
                  [makeNodeKey(selectedModule, selectedNodeId)]: nextNode,
                }));
                setSavedSelectedNode(nextNode);
                const oldParentId = getNodeReferenceId(selectedNodeForEditor.parent);
                const nextParentId = getNodeReferenceId(nextNode.parent);
                if (oldParentId !== nextParentId) {
                  skipSelectedNodeExpansionRef.current = true;
                }
                const oldBranchIsVisible = oldParentId.length === 0 || expandedNodeIds.includes(oldParentId);
                const nextBranchIsVisible = nextParentId.length === 0 || expandedNodeIds.includes(nextParentId);

                void (async () => {
                  if (oldParentId !== nextParentId && oldBranchIsVisible) {
                    await ensureBranchLoaded({
                      branchStatesRef,
                      branchRequestVersionsRef,
                      branchAbortControllersRef,
                      force: true,
                      moduleName: selectedModule,
                      nodesByKeyRef,
                      parentId: oldParentId || null,
                      selectedModuleRef,
                      setBranchStates,
                      setExpandedNodeIds,
                      setNodesByKey,
                      t,
                    });
                  }

                  if (nextBranchIsVisible) {
                    await ensureBranchLoaded({
                      branchStatesRef,
                      branchRequestVersionsRef,
                      branchAbortControllersRef,
                      force: true,
                      moduleName: selectedModule,
                      nodesByKeyRef,
                      parentId: nextParentId || null,
                      selectedModuleRef,
                      setBranchStates,
                      setExpandedNodeIds,
                      setNodesByKey,
                      t,
                    });
                  }
                })();
              }}
              parentPicker={treeParentPicker}
              schema={selectedNodeSchema}
              variant="full"
            />
          )}
        </div>
      </SplitPane>
      )}
      {mode === "table" && createState !== null && createSchema !== null && createDraft !== null && selectedModuleDoc !== null ? (
        <OverlayDialog ariaLabel={t("pages.nodes.table.create")} className="overlay-dialog-editor" onClose={() => setCreateState(null)}>
          <div className="editor-overlay-header">
            <strong>{t("pages.nodes.table.create")}</strong>
            <OverlayCloseButton onClick={() => setCreateState(null)} />
          </div>
          <NodeEditor
            mode="create"
            moduleName={selectedModule}
            node={createDraft}
            onSaved={() => {
              setCreateState(null);
              void tableState.tableNodesQuery.refetch();
            }}
            parentPicker={{
              canSelectRoot: canCreateTableInRoot,
              parentEntityNames: tableParentEntityNames,
            }}
            schema={createSchema}
            variant="embedded"
          />
        </OverlayDialog>
      ) : null}
      {deleteNodeState !== null ? (
        <NodeDeleteOverlay
          moduleName={selectedModule}
          node={deleteNodeState}
          nodeTitle={resolveNodeDisplayLabel(deleteNodeState) || t("pages.nodes.tree.unnamed")}
          onClose={() => setDeleteNodeState(null)}
          onDeleted={() => {
            const deletedNodeId = typeof deleteNodeState.id === "string" ? deleteNodeState.id : "";
            if (deletedNodeId.length === 0) {
              setDeleteNodeState(null);
              return;
            }
            removeDeletedSubtreeFromTree({
              branchAbortControllersRef,
              branchRequestVersionsRef,
              branchStatesRef,
              moduleName: selectedModule,
              nodeId: deletedNodeId,
              nodesByKeyRef,
              setBranchStates,
              setExpandedNodeIds,
              setNodesByKey,
            });
            setCreateState(null);
            setCreateMenuState(null);
            setDeleteNodeState(null);
            navigateToTree(selectedModule);
          }}
        />
      ) : null}
    </section>
    </>
  );
}

function buildTreeItems(args: {
  branchStates: Record<string, BranchState>;
  entityNamesInModule: string[];
  entityPresentationRegistry: NodeEntityPresentationRegistry;
  entitySchemaRegistry: Record<string, JsonSchema>;
  expandedNodeIds: string[];
  moduleName: string;
  nodesByKey: Record<string, NodeDocument>;
  user: AuthenticatedUser | null;
  onCreateRequest: (parentId: string, targets: string[], anchorElement: HTMLElement) => void;
  onDeleteRequest: (node: NodeDocument) => void;
  onSelect: (nodeId: string) => void;
  onToggle: (nodeId: string) => void;
  rootNodeIds: string[];
  selectedNodeAncestorIds: Set<string>;
  selectedNodeId: string | null;
  t: (key: TranslationKey) => string;
}) {
  const { rootNodeIds } = args;

  return rootNodeIds
    .map((nodeId) => args.nodesByKey[makeNodeKey(args.moduleName, nodeId)])
    .filter((node): node is NodeDocument => node !== undefined)
    .map((node) => buildNodeTreeItem(args, node));
}

function buildNodeTreeItem(
  args: {
    branchStates: Record<string, BranchState>;
    entityNamesInModule: string[];
    entityPresentationRegistry: NodeEntityPresentationRegistry;
    entitySchemaRegistry: Record<string, JsonSchema>;
    expandedNodeIds: string[];
    moduleName: string;
    nodesByKey: Record<string, NodeDocument>;
    user: AuthenticatedUser | null;
    onCreateRequest: (parentId: string, targets: string[], anchorElement: HTMLElement) => void;
    onDeleteRequest: (node: NodeDocument) => void;
    onSelect: (nodeId: string) => void;
    onToggle: (nodeId: string) => void;
    selectedNodeAncestorIds: Set<string>;
    selectedNodeId: string | null;
    t: (key: TranslationKey) => string;
  },
  node: NodeDocument,
): TreeNavItem {
  const nodeId = typeof node.id === "string" ? node.id : "";
  const branchKey = makeBranchKey(args.moduleName, nodeId);
  const branchState = args.branchStates[branchKey] ?? EMPTY_BRANCH_STATE;
  const entityName = typeof node.entity === "string" ? node.entity : "";
  const presentation = entityName.length > 0 ? args.entityPresentationRegistry[entityName] ?? null : null;
  const schema = entityName.length > 0 ? args.entitySchemaRegistry[entityName] ?? null : null;
  const treeLabel = resolveNodeDisplayLabel(node, presentation, "tree");
  const hasTreeLabelTemplate = presentation?.treeLabelTemplate !== null && presentation?.treeLabelTemplate !== undefined;
  const branchChildren = branchState.nodeIds
    .map((childId) => args.nodesByKey[makeNodeKey(args.moduleName, childId)])
    .filter((child): child is NodeDocument => child !== undefined);
  const hasLoadedChildren = branchState.isLoaded && branchChildren.length > 0;
  const hasChildren = presentation === null
    ? branchState.isLoaded
      ? hasLoadedChildren
      : true
    : presentation.canHaveChildren || hasLoadedChildren || (
      args.selectedNodeId === nodeId && !branchState.isLoaded
    );
  const createTargets =
    nodeId.length > 0 && canPopulateNodeDocument(node, args.user)
      ? resolveNodeCreateTargets(schema, args.entityNamesInModule)
      : [];
  const isActionVisible = createTargets.length > 0
    && (args.selectedNodeId === nodeId || args.selectedNodeAncestorIds.has(nodeId));
  const isDeleteVisible = nodeId.length > 0
    && canWriteNodeDocument(node, args.user)
    && (args.selectedNodeId === nodeId || args.selectedNodeAncestorIds.has(nodeId));

  let children: TreeNavItem[] = [];
  if (branchState.isLoaded) {
    children = branchChildren.map((child) => buildNodeTreeItem(args, child));
  } else if (branchState.error) {
    children = [{
      hasChildren: false,
      id: `${nodeId}:error`,
      title: branchState.error,
    }];
  }

  return {
    children,
    hasChildren,
    id: `node:${args.moduleName}:${nodeId}`,
    isActive: args.selectedNodeId === nodeId,
    isExpanded: hasChildren && args.expandedNodeIds.includes(nodeId),
    isLoading: branchState.isLoading,
    actions: [
      ...(isDeleteVisible ? [{
        ariaLabel: args.t("pages.nodes.delete.action"),
        icon: "trash" as const,
        onClick: () => args.onDeleteRequest(node),
        title: args.t("pages.nodes.delete.action"),
      }] : []),
      ...(isActionVisible ? [{
        ariaLabel: args.t("pages.nodes.tree.addChild"),
        icon: "plus" as const,
        onClick: (event: ReactMouseEvent<HTMLButtonElement>) => args.onCreateRequest(nodeId, createTargets, event.currentTarget),
        title: args.t("pages.nodes.tree.addChild"),
      }] : []),
    ],
    onClick: nodeId.length > 0 ? () => args.onSelect(nodeId) : undefined,
    onToggle: nodeId.length > 0 && hasChildren ? () => args.onToggle(nodeId) : undefined,
    title: hasTreeLabelTemplate ? treeLabel : treeLabel || args.t("pages.nodes.tree.unnamed"),
  };
}

async function toggleNodeBranch(args: {
  branchAbortControllersRef: RefObject<Record<string, AbortController>>;
  branchRequestVersionsRef: RefObject<Record<string, number>>;
  branchStatesRef: RefObject<Record<string, BranchState>>;
  expandedNodeIds: string[];
  moduleName: string;
  nodeId: string;
  nodesByKeyRef: RefObject<Record<string, NodeDocument>>;
  selectedModuleRef: RefObject<string>;
  setBranchStates: Dispatch<SetStateAction<Record<string, BranchState>>>;
  setExpandedNodeIds: Dispatch<SetStateAction<string[]>>;
  setNodesByKey: Dispatch<SetStateAction<Record<string, NodeDocument>>>;
  t: (key: TranslationKey) => string;
}) {
  if (args.expandedNodeIds.includes(args.nodeId)) {
    discardCollapsedBranch(args);
    return;
  }

  args.setExpandedNodeIds((current) => (current.includes(args.nodeId) ? current : [...current, args.nodeId]));
  const result = await ensureBranchLoaded({
    branchAbortControllersRef: args.branchAbortControllersRef,
    branchStatesRef: args.branchStatesRef,
    branchRequestVersionsRef: args.branchRequestVersionsRef,
    moduleName: args.moduleName,
    nodesByKeyRef: args.nodesByKeyRef,
    parentId: args.nodeId,
    selectedModuleRef: args.selectedModuleRef,
    setBranchStates: args.setBranchStates,
    setExpandedNodeIds: args.setExpandedNodeIds,
    setNodesByKey: args.setNodesByKey,
    t: args.t,
  });

  if (result.status === "loaded" && result.nodeIds.length === 0) {
    args.setExpandedNodeIds((current) => current.filter((id) => id !== args.nodeId));
  }
}

async function ensureBranchLoaded(args: {
  branchAbortControllersRef: RefObject<Record<string, AbortController>>;
  branchRequestVersionsRef: RefObject<Record<string, number>>;
  branchStatesRef: RefObject<Record<string, BranchState>>;
  force?: boolean;
  moduleName: string;
  nodesByKeyRef: RefObject<Record<string, NodeDocument>>;
  parentId: string | null;
  selectedModuleRef: RefObject<string>;
  setBranchStates: Dispatch<SetStateAction<Record<string, BranchState>>>;
  setExpandedNodeIds: Dispatch<SetStateAction<string[]>>;
  setNodesByKey: Dispatch<SetStateAction<Record<string, NodeDocument>>>;
  t: (key: TranslationKey) => string;
}): Promise<BranchLoadResult> {
  const branchKey = makeBranchKey(args.moduleName, args.parentId);
  const currentState = args.branchStatesRef.current[branchKey];

  if (!args.force && currentState?.isLoaded) {
    return { nodeIds: currentState.nodeIds, status: "loaded" };
  }

  if (currentState?.isLoading && !args.force) {
    return { status: "discarded" };
  }

  args.branchAbortControllersRef.current[branchKey]?.abort();
  const abortController = new AbortController();
  args.branchAbortControllersRef.current[branchKey] = abortController;
  const requestVersion = (args.branchRequestVersionsRef.current[branchKey] ?? 0) + 1;
  args.branchRequestVersionsRef.current[branchKey] = requestVersion;
  updateBranchStates(args.branchStatesRef, args.setBranchStates, (current) => ({
    ...current,
    [branchKey]: {
      error: null,
      isLoaded: false,
      isLoading: true,
      nodeIds: current[branchKey]?.nodeIds ?? [],
    },
  }));

  try {
    const nodes = args.parentId === null
      ? await getRootNodes(args.moduleName, abortController.signal)
      : await getChildNodes(args.moduleName, args.parentId, abortController.signal);

    if (
      args.selectedModuleRef.current !== args.moduleName ||
      args.branchRequestVersionsRef.current[branchKey] !== requestVersion
    ) {
      return { status: "discarded" };
    }

    const nodeIds = nodes
      .map((node) => (typeof node.id === "string" ? node.id : ""))
      .filter((nodeId) => nodeId.length > 0);
    const disappearedNodeIds = (currentState?.nodeIds ?? []).filter((nodeId) => !nodeIds.includes(nodeId));
    if (disappearedNodeIds.length > 0) {
      removeKnownSubtrees({
        branchAbortControllersRef: args.branchAbortControllersRef,
        branchRequestVersionsRef: args.branchRequestVersionsRef,
        branchStatesRef: args.branchStatesRef,
        expectedParentId: args.parentId,
        moduleName: args.moduleName,
        nodesByKeyRef: args.nodesByKeyRef,
        rootNodeIds: disappearedNodeIds,
        setBranchStates: args.setBranchStates,
        setExpandedNodeIds: args.setExpandedNodeIds,
        setNodesByKey: args.setNodesByKey,
      });
    }

    updateNodesByKey(args.nodesByKeyRef, args.setNodesByKey, (current) => {
      const next = { ...current };
      for (const node of nodes) {
        if (typeof node.id !== "string" || node.id.length === 0) {
          continue;
        }
        next[makeNodeKey(args.moduleName, node.id)] = node;
      }
      return next;
    });

    updateBranchStates(args.branchStatesRef, args.setBranchStates, (current) => ({
      ...current,
      [branchKey]: {
        error: null,
        isLoaded: true,
        isLoading: false,
        nodeIds,
      },
    }));

    return { nodeIds, status: "loaded" };
  } catch (error) {
    if (
      args.selectedModuleRef.current !== args.moduleName ||
      args.branchRequestVersionsRef.current[branchKey] !== requestVersion
    ) {
      return { status: "discarded" };
    }
    if (abortController.signal.aborted) {
      return { status: "discarded" };
    }
    const message = error instanceof ApiError
      ? localizeApiError(error, args.t)
      : args.t("pages.nodes.tree.loadError");

    updateBranchStates(args.branchStatesRef, args.setBranchStates, (current) => ({
      ...current,
      [branchKey]: {
        error: message,
        isLoaded: false,
        isLoading: false,
        nodeIds: current[branchKey]?.nodeIds ?? [],
      },
    }));

    return { nodeIds: currentState?.nodeIds ?? [], status: "failed" };
  } finally {
    if (args.branchAbortControllersRef.current[branchKey] === abortController) {
      delete args.branchAbortControllersRef.current[branchKey];
    }
  }
}

function discardCollapsedBranch(args: {
  branchAbortControllersRef: RefObject<Record<string, AbortController>>;
  branchRequestVersionsRef: RefObject<Record<string, number>>;
  branchStatesRef: RefObject<Record<string, BranchState>>;
  moduleName: string;
  nodeId: string;
  nodesByKeyRef: RefObject<Record<string, NodeDocument>>;
  setBranchStates: Dispatch<SetStateAction<Record<string, BranchState>>>;
  setExpandedNodeIds: Dispatch<SetStateAction<string[]>>;
  setNodesByKey: Dispatch<SetStateAction<Record<string, NodeDocument>>>;
}) {
  const descendantIds = new Set<string>();
  Object.values(args.nodesByKeyRef.current).forEach((node) => {
    const nodeId = typeof node.id === "string" ? node.id : "";
    if (nodeId.length > 0 && Array.isArray(node.ancestors) && node.ancestors.includes(args.nodeId)) {
      descendantIds.add(nodeId);
    }
  });

  args.setExpandedNodeIds((current) => current.filter((id) => id !== args.nodeId && !descendantIds.has(id)));
  const discardedBranchKeys = new Set<string>();
  Object.keys(args.branchStatesRef.current).forEach((branchKey) => {
    const branchNodeId = getBranchNodeId(args.moduleName, branchKey);
    if (branchNodeId === args.nodeId || descendantIds.has(branchNodeId)) {
      discardedBranchKeys.add(branchKey);
      args.branchAbortControllersRef.current[branchKey]?.abort();
      delete args.branchAbortControllersRef.current[branchKey];
      args.branchRequestVersionsRef.current[branchKey] = (args.branchRequestVersionsRef.current[branchKey] ?? 0) + 1;
    }
  });
  updateBranchStates(args.branchStatesRef, args.setBranchStates, (current) => Object.fromEntries(
    Object.entries(current).filter(([branchKey]) => {
      return !discardedBranchKeys.has(branchKey);
    }),
  ));
  updateNodesByKey(args.nodesByKeyRef, args.setNodesByKey, (current) => Object.fromEntries(
    Object.entries(current).filter(([, node]) => {
      const nodeId = typeof node.id === "string" ? node.id : "";
      return !descendantIds.has(nodeId);
    }),
  ));
}

function removeKnownSubtrees(args: {
  branchAbortControllersRef: RefObject<Record<string, AbortController>>;
  branchRequestVersionsRef: RefObject<Record<string, number>>;
  branchStatesRef: RefObject<Record<string, BranchState>>;
  expectedParentId?: string | null;
  moduleName: string;
  nodesByKeyRef: RefObject<Record<string, NodeDocument>>;
  rootNodeIds: string[];
  setBranchStates: Dispatch<SetStateAction<Record<string, BranchState>>>;
  setExpandedNodeIds: Dispatch<SetStateAction<string[]>>;
  setNodesByKey: Dispatch<SetStateAction<Record<string, NodeDocument>>>;
}) {
  const removedNodeIds = new Set(args.rootNodeIds);
  Object.values(args.nodesByKeyRef.current).forEach((node) => {
    const nodeId = typeof node.id === "string" ? node.id : "";
    if (nodeId.length > 0 && node.ancestors?.some((ancestorId) => removedNodeIds.has(ancestorId))) {
      removedNodeIds.add(nodeId);
    }
  });

  if (args.expectedParentId !== undefined) {
    const expectedParentId = args.expectedParentId ?? "";
    const protectedNodeIds = new Set<string>();
    const nodes = Object.values(args.nodesByKeyRef.current);

    for (const rootNodeId of args.rootNodeIds) {
      const node = nodes.find((candidate) => candidate.id === rootNodeId);
      if (node !== undefined && getNodeReferenceId(node.parent) !== expectedParentId) {
        protectedNodeIds.add(rootNodeId);
      }
    }

    let protectedNodeCount = 0;
    do {
      protectedNodeCount = protectedNodeIds.size;
      for (const node of nodes) {
        const nodeId = typeof node.id === "string" ? node.id : "";
        if (nodeId.length > 0 && node.ancestors?.some((ancestorId) => protectedNodeIds.has(ancestorId))) {
          protectedNodeIds.add(nodeId);
        }
      }
    } while (protectedNodeIds.size !== protectedNodeCount);

    protectedNodeIds.forEach((nodeId) => removedNodeIds.delete(nodeId));
  }

  args.setExpandedNodeIds((current) => current.filter((nodeId) => !removedNodeIds.has(nodeId)));
  const removedBranchKeys = new Set<string>();
  Object.keys(args.branchStatesRef.current).forEach((branchKey) => {
    if (!removedNodeIds.has(getBranchNodeId(args.moduleName, branchKey))) {
      return;
    }
    removedBranchKeys.add(branchKey);
    args.branchAbortControllersRef.current[branchKey]?.abort();
    delete args.branchAbortControllersRef.current[branchKey];
    args.branchRequestVersionsRef.current[branchKey] = (args.branchRequestVersionsRef.current[branchKey] ?? 0) + 1;
  });
  updateBranchStates(args.branchStatesRef, args.setBranchStates, (current) => Object.fromEntries(
    Object.entries(current)
      .filter(([branchKey]) => !removedBranchKeys.has(branchKey))
      .map(([branchKey, state]) => [branchKey, {
        ...state,
        nodeIds: state.nodeIds.filter((nodeId) => !removedNodeIds.has(nodeId)),
      }]),
  ));
  updateNodesByKey(args.nodesByKeyRef, args.setNodesByKey, (current) => Object.fromEntries(
    Object.entries(current).filter(([, node]) => {
      const nodeId = typeof node.id === "string" ? node.id : "";
      return !removedNodeIds.has(nodeId);
    }),
  ));
}

function updateBranchStates(
  branchStatesRef: RefObject<Record<string, BranchState>>,
  setBranchStates: Dispatch<SetStateAction<Record<string, BranchState>>>,
  update: (current: Record<string, BranchState>) => Record<string, BranchState>,
) {
  const next = update(branchStatesRef.current);
  branchStatesRef.current = next;
  setBranchStates(next);
}

function updateNodesByKey(
  nodesByKeyRef: RefObject<Record<string, NodeDocument>>,
  setNodesByKey: Dispatch<SetStateAction<Record<string, NodeDocument>>>,
  update: (current: Record<string, NodeDocument>) => Record<string, NodeDocument>,
) {
  const next = update(nodesByKeyRef.current);
  nodesByKeyRef.current = next;
  setNodesByKey(next);
}

function getTableFilterErrorMessage(error: unknown, t: (key: TranslationKey) => string) {
  const message = error instanceof ApiError
    ? localizeApiError(error, t)
    : t("pages.nodes.table.filter.requestError");
  return `${t("pages.nodes.table.filter.requestError")}: ${message}`;
}

function getTableSortErrorMessage(error: unknown, t: (key: TranslationKey) => string) {
  const message = error instanceof ApiError
    ? localizeApiError(error, t)
    : t("pages.nodes.table.sort.requestError");
  return `${t("pages.nodes.table.sort.requestError")}: ${message}`;
}

function makeBranchKey(moduleName: string, parentId: string | null) {
  return parentId === null ? `root:${moduleName}` : `node:${moduleName}:${parentId}`;
}

function makeNodeKey(moduleName: string, nodeId: string) {
  return `${moduleName}:${nodeId}`;
}

function applyCreatedNodeToTree(args: {
  branchStatesRef: RefObject<Record<string, BranchState>>;
  moduleName: string;
  nextNode: NodeDocument;
  nodesByKeyRef: RefObject<Record<string, NodeDocument>>;
  parentId: string | null;
  setBranchStates: Dispatch<SetStateAction<Record<string, BranchState>>>;
  setExpandedNodeIds: Dispatch<SetStateAction<string[]>>;
  setNodesByKey: Dispatch<SetStateAction<Record<string, NodeDocument>>>;
}) {
  const nextNodeId = typeof args.nextNode.id === "string" ? args.nextNode.id : "";
  if (nextNodeId.length === 0) {
    return;
  }

  const branchKey = makeBranchKey(args.moduleName, args.parentId);
  updateNodesByKey(args.nodesByKeyRef, args.setNodesByKey, (current) => ({
    ...current,
    [makeNodeKey(args.moduleName, nextNodeId)]: args.nextNode,
  }));
  updateBranchStates(args.branchStatesRef, args.setBranchStates, (current) => {
    const branchState = current[branchKey] ?? EMPTY_BRANCH_STATE;
    const nextNodeIds = branchState.nodeIds.includes(nextNodeId)
      ? branchState.nodeIds
      : [...branchState.nodeIds, nextNodeId];

    return {
      ...current,
      [branchKey]: {
        ...branchState,
        error: null,
        isLoaded: true,
        isLoading: false,
        nodeIds: nextNodeIds,
      },
    };
  });

  if (args.parentId !== null) {
    args.setExpandedNodeIds((current) =>
      current.includes(args.parentId!)
        ? current
        : [...current, args.parentId!],
    );
  }
}

function removeDeletedSubtreeFromTree(args: {
  branchAbortControllersRef: RefObject<Record<string, AbortController>>;
  branchRequestVersionsRef: RefObject<Record<string, number>>;
  branchStatesRef: RefObject<Record<string, BranchState>>;
  moduleName: string;
  nodeId: string;
  nodesByKeyRef: RefObject<Record<string, NodeDocument>>;
  setBranchStates: Dispatch<SetStateAction<Record<string, BranchState>>>;
  setExpandedNodeIds: Dispatch<SetStateAction<string[]>>;
  setNodesByKey: Dispatch<SetStateAction<Record<string, NodeDocument>>>;
}) {
  removeKnownSubtrees({
    ...args,
    rootNodeIds: [args.nodeId],
  });
}

function getBranchNodeId(moduleName: string, branchKey: string) {
  const prefix = `node:${moduleName}:`;
  return branchKey.startsWith(prefix) ? branchKey.slice(prefix.length) : "";
}
