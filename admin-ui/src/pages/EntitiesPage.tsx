import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { IconButton } from "../components/IconButton";
import { SplitPane } from "../components/SplitPane";
import { Spinner } from "../components/Spinner";
import { TreeNav, type TreeNavItem } from "../components/TreeNav";
import { EntityEditor } from "../features/entities/EntityEditor";
import { ModuleEditor } from "../features/entities/ModuleEditor";
import { StructureDeleteOverlay, type StructureDeleteTarget } from "../features/entities/StructureDeleteOverlay";
import { getEntities, getEntitySchema, getModules, type EntityListItem, type ModuleDocument } from "../features/entities/api";
import { getEntityDisplayLabel, getModuleDisplayLabel } from "../features/entities/presentation";
import { structureKeys } from "../lib/queryKeys";
import { SCHEMA_QUERY_OPTIONS, STRUCTURE_QUERY_OPTIONS } from "../lib/queryOptions";
import { canEditEntities } from "../lib/session";
import { useAuth } from "../providers/AuthProvider";
import { useI18n } from "../providers/I18nProvider";
import { getReferenceId } from "../lib/references";
import { createEmptyEntitySchema } from "../features/entities/schema";
import { APP_ROUTE_PREFIX } from "../router/routeConfig";

type EntitiesPanelMode = "module-create" | "module-edit" | "entity-create" | "entity-edit";

export function EntitiesPage() {
  const { t } = useI18n();
  const auth = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const params = useParams({ strict: false }) as { module?: string; entity?: string };
  const [expandedModules, setExpandedModules] = useState<string[]>([]);
  const [pendingModuleSelection, setPendingModuleSelection] = useState<string | null>(null);
  const [panelMode, setPanelMode] = useState<EntitiesPanelMode>("module-edit");
  const [pendingEntitySelection, setPendingEntitySelection] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<StructureDeleteTarget | null>(null);
  const canEdit = canEditEntities(auth.user);
  const selectedModule = params.module ?? "";
  const selectedEntity = params.entity ?? "";

  function navigateToModule(moduleName: string) {
    if (moduleName.trim().length === 0) {
      void navigate({ to: `${APP_ROUTE_PREFIX}/entities` });
      return;
    }

    void navigate({ to: `${APP_ROUTE_PREFIX}/entities/$module`, params: { module: moduleName } });
  }

  function navigateToEntity(moduleName: string, entityName: string) {
    if (moduleName.trim().length === 0) {
      void navigate({ to: `${APP_ROUTE_PREFIX}/entities` });
      return;
    }

    if (entityName.trim().length === 0) {
      void navigate({ to: `${APP_ROUTE_PREFIX}/entities/$module`, params: { module: moduleName } });
      return;
    }

    void navigate({
      to: `${APP_ROUTE_PREFIX}/entities/$module/$entity`,
      params: { entity: entityName, module: moduleName },
    });
  }

  const modulesQuery = useQuery({
    ...STRUCTURE_QUERY_OPTIONS,
    queryKey: structureKeys.modules(),
    queryFn: ({ signal }) => getModules(signal),
  });

  const modules = modulesQuery.data ?? [];
  const moduleEntityQueries = useQueries({
    queries: modules.map((moduleDoc) => ({
      ...STRUCTURE_QUERY_OPTIONS,
      enabled: expandedModules.includes(moduleDoc.name) || moduleDoc.name === selectedModule,
      queryKey: structureKeys.entities(moduleDoc.name),
      queryFn: ({ signal }: { signal: AbortSignal }) => getEntities(moduleDoc.name, signal),
    })),
  });

  const entitiesByModule = new Map(
    modules.map((moduleDoc, index) => [moduleDoc.name, moduleEntityQueries[index]?.data ?? []]),
  );
  const selectedModuleQuery = modules.findIndex((moduleDoc) => moduleDoc.name === selectedModule);
  const entities = entitiesByModule.get(selectedModule) ?? [];
  const selectedEntitiesQueryState = selectedModuleQuery >= 0 ? moduleEntityQueries[selectedModuleQuery] : null;

  const schemaQuery = useQuery({
    ...SCHEMA_QUERY_OPTIONS,
    enabled: panelMode === "entity-edit" && selectedModule.length > 0 && selectedEntity.length > 0,
    queryKey: structureKeys.schema(selectedModule, selectedEntity),
    queryFn: ({ signal }) => getEntitySchema(selectedModule, selectedEntity, signal),
  });

  useEffect(() => {
    if (modulesQuery.data === undefined || modulesQuery.data.length === 0) {
      return;
    }

    if (
      pendingModuleSelection !== null &&
      modulesQuery.data.some((moduleDoc) => moduleDoc.name === pendingModuleSelection)
    ) {
      setPendingModuleSelection(null);
    }

    const firstModule = modulesQuery.data[0];
    if (firstModule === undefined) {
      return;
    }

    if (selectedModule.length === 0) {
      if (panelMode === "module-create") {
        return;
      }

      navigateToModule(firstModule.name);
      setExpandedModules((current) => (current.includes(firstModule.name) ? current : [...current, firstModule.name]));
      setPanelMode("module-edit");
      return;
    }

    if (
      !modulesQuery.data.some((moduleDoc) => moduleDoc.name === selectedModule) &&
      pendingModuleSelection !== selectedModule
    ) {
      navigateToModule(firstModule.name);
      setExpandedModules((current) => (current.includes(firstModule.name) ? current : [...current, firstModule.name]));
      setPanelMode("module-edit");
    }
  }, [modulesQuery.data, panelMode, pendingModuleSelection, selectedModule]);

  useEffect(() => {
    if (modulesQuery.data === undefined) {
      return;
    }

    setExpandedModules((current) => current.filter((moduleName) => modulesQuery.data.some((moduleDoc) => moduleDoc.name === moduleName)));
  }, [modulesQuery.data]);

  useEffect(() => {
    if (selectedModule.length === 0) {
      return;
    }

    setExpandedModules((current) => (current.includes(selectedModule) ? current : [...current, selectedModule]));
  }, [selectedModule]);

  useEffect(() => {
    if (panelMode === "module-create" || panelMode === "entity-create") {
      return;
    }

    setPanelMode(selectedEntity.length > 0 ? "entity-edit" : "module-edit");
  }, [panelMode, selectedEntity]);

  useEffect(() => {
    if (selectedEntitiesQueryState?.data === undefined) {
      return;
    }

    if (
      pendingEntitySelection !== null &&
      selectedEntitiesQueryState.data.some((entityDoc) => entityDoc.title === pendingEntitySelection)
    ) {
      setPendingEntitySelection(null);
    }

    if (selectedEntitiesQueryState.data.length === 0) {
      if (selectedEntity.length > 0 && pendingEntitySelection !== selectedEntity) {
        navigateToModule(selectedModule);
      }
      return;
    }

    if (
      selectedEntity.length > 0 &&
      pendingEntitySelection !== selectedEntity &&
      !selectedEntitiesQueryState.data.some((entityDoc) => entityDoc.title === selectedEntity)
    ) {
      navigateToModule(selectedModule);
    }
  }, [navigate, pendingEntitySelection, selectedEntitiesQueryState?.data, selectedEntity, selectedModule]);

  const selectedModuleDoc = modules.find((moduleDoc) => moduleDoc.name === selectedModule) ?? null;
  const allModuleNames = modules.map((moduleDoc) => moduleDoc.name);
  const allModuleOptions = modules.map((moduleDoc) => ({
    label: getModuleDisplayLabel(moduleDoc),
    value: moduleDoc.name,
  }));
  const allEntityOptions = entities.map((entityDoc) => ({
    label: getEntityDisplayLabel(entityDoc),
    value: entityDoc.title,
  }));
  const treeItems: TreeNavItem[] = modules.map((moduleDoc) => {
    const moduleEntitiesQuery = moduleEntityQueries[modules.findIndex((item) => item.name === moduleDoc.name)];
    const moduleEntities = moduleEntitiesQuery?.data;
    const isSelectedModule = moduleDoc.name === selectedModule;
    const actions = canEdit && isSelectedModule
      ? [
          ...(moduleEntities !== undefined && moduleEntities.length === 0
            ? [{
                ariaLabel: t("pages.entities.delete.module.action"),
                icon: "trash" as const,
                onClick: () => setDeleteTarget({
                  kind: "module",
                  moduleName: moduleDoc.name,
                  resourceLabel: getModuleDisplayLabel(moduleDoc),
                }),
                title: t("pages.entities.delete.module.action"),
              }]
            : []),
          {
            ariaLabel: t("pages.entities.actions.addEntity"),
            icon: "plus" as const,
            onClick: () => {
              setPendingModuleSelection(null);
              navigateToModule(moduleDoc.name);
              setPendingEntitySelection(null);
              setExpandedModules((current) => (current.includes(moduleDoc.name) ? current : [...current, moduleDoc.name]));
              setPanelMode("entity-create");
            },
            title: t("pages.entities.actions.addEntity"),
          },
        ]
      : undefined;

    return {
      actions,
      children:
        expandedModules.includes(moduleDoc.name)
          ? getEntityTreeItems({
              canEdit,
              entities: entitiesByModule.get(moduleDoc.name) ?? [],
              isLoading: moduleEntitiesQuery?.isPending ?? false,
              onDelete: (entity) => setDeleteTarget({
                entityName: entity.title,
                kind: "entity",
                moduleName: moduleDoc.name,
                resourceLabel: getEntityDisplayLabel(entity),
              }),
              onSelect: (entityName) => {
                setExpandedModules((current) => (current.includes(moduleDoc.name) ? current : [...current, moduleDoc.name]));
                navigateToEntity(moduleDoc.name, entityName);
                setPendingEntitySelection(null);
                setPanelMode("entity-edit");
              },
              selectedEntity: moduleDoc.name === selectedModule ? selectedEntity : "",
              t,
            })
          : [],
      hasChildren: true,
      id: moduleDoc.name,
      isActive: moduleDoc.name === selectedModule && panelMode === "module-edit",
      isExpanded: expandedModules.includes(moduleDoc.name),
      onClick: () => {
        setPendingModuleSelection(null);
        navigateToModule(moduleDoc.name);
        setPanelMode("module-edit");
      },
      onToggle: () => {
        const isExpanded = expandedModules.includes(moduleDoc.name);
        setExpandedModules((current) =>
          current.includes(moduleDoc.name)
            ? current.filter((name) => name !== moduleDoc.name)
            : [...current, moduleDoc.name],
        );
        if (!isExpanded) {
          setPendingModuleSelection(null);
          navigateToModule(moduleDoc.name);
        }
      },
      title: getModuleDisplayLabel(moduleDoc),
    };
  });

  function handleDeleted() {
    if (deleteTarget === null) {
      return;
    }

    if (deleteTarget.kind === "module") {
      const moduleName = deleteTarget.moduleName;
      queryClient.setQueryData<ModuleDocument[]>(structureKeys.modules(), (current = []) =>
        current.filter((moduleDoc) => moduleDoc.name !== moduleName),
      );
      queryClient.removeQueries({ queryKey: structureKeys.entities(moduleName) });
      queryClient.removeQueries({ queryKey: ["structure", "schema", moduleName] });
      setExpandedModules((current) => current.filter((name) => name !== moduleName));
      setPendingModuleSelection(null);
      setPendingEntitySelection(null);
      setPanelMode("module-edit");
      navigateToModule("");
      void queryClient.invalidateQueries({ queryKey: ["structure"] });
    } else {
      const { entityName, moduleName } = deleteTarget;
      queryClient.setQueryData<EntityListItem[]>(structureKeys.entities(moduleName), (current = []) =>
        current.filter((entityDoc) => entityDoc.title !== entityName),
      );
      queryClient.removeQueries({ queryKey: structureKeys.schema(moduleName, entityName) });
      setPendingEntitySelection(null);
      if (selectedModule === moduleName && selectedEntity === entityName) {
        navigateToModule(moduleName);
        setPanelMode("module-edit");
      }
      void queryClient.invalidateQueries({ queryKey: ["structure"] });
    }

    setDeleteTarget(null);
  }

  return (
    <section className="entities-screen">
      <SplitPane className="entities-layout" storageKey="sandala.admin-ui.entities.split-pane">
        <aside className="entities-sidebar">
          <Card
            title={
              <div className="panel-header-actions">
                <strong>{t("pages.entities.panel.structure")}</strong>
                {canEdit ? (
                  <IconButton
                    icon="plus"
                    label={t("pages.entities.actions.addModule")}
                    onClick={() => {
                      setPendingModuleSelection(null);
                      navigateToModule("");
                      setPendingEntitySelection(null);
                      setPanelMode("module-create");
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
            ) : modules.length === 0 ? (
              <EmptyState description={t("pages.entities.empty.modules.description")} title={t("pages.entities.empty.modules.title")} />
            ) : (
              <TreeNav items={treeItems} />
            )}
          </Card>
        </aside>

        <div className="entities-main">
          {panelMode === "entity-edit" && selectedEntity.length > 0 && schemaQuery.isPending ? (
            <div className="panel panel-centered">
              <Spinner />
            </div>
          ) : panelMode === "module-create" ? (
            <ModuleEditor
              allEntityOptions={[]}
              allEntitiesInModule={[]}
              allModuleNames={allModuleNames}
              canEdit={canEdit}
              initialRootGroup={getReferenceId(auth.user?.primary_group) || undefined}
              initialRootOwner={auth.user?.id}
              mode="create"
              module={null}
              onSaved={(moduleDoc) => {
                setPendingModuleSelection(moduleDoc.name);
                navigateToModule(moduleDoc.name);
                setPendingEntitySelection(null);
                setPanelMode("module-edit");
                void modulesQuery.refetch();
              }}
            />
          ) : selectedModuleDoc !== null && panelMode === "module-edit" ? (
            <ModuleEditor
              allEntityOptions={allEntityOptions}
              allEntitiesInModule={entities.map((entityDoc) => entityDoc.title)}
              allModuleNames={allModuleNames}
              canEdit={canEdit}
              initialRootGroup={getReferenceId(auth.user?.primary_group) || undefined}
              initialRootOwner={auth.user?.id}
              mode="edit"
              module={selectedModuleDoc}
              onSaved={() => {
                void modulesQuery.refetch();
              }}
            />
          ) : panelMode === "entity-create" && selectedModule.length > 0 ? (
            <EntityEditor
              allEntityOptions={allEntityOptions}
              allEntitiesInModule={entities.map((entityDoc) => entityDoc.title)}
              allModuleOptions={allModuleOptions}
              canEdit={canEdit}
              mode="create"
              moduleName={selectedModule}
              onSaved={(nextSchema) => {
                const nextEntity = nextSchema.title ?? "";
                queryClient.setQueryData(
                  structureKeys.schema(selectedModule, nextEntity),
                  nextSchema,
                );
                setPendingEntitySelection(nextEntity);
                navigateToEntity(selectedModule, nextEntity);
                setPanelMode("entity-edit");
                void selectedEntitiesQueryState?.refetch();
              }}
              schema={createEmptyEntitySchema("")}
              selectedEntity=""
            />
          ) : panelMode === "module-edit" && pendingModuleSelection === selectedModule ? (
            <div className="panel panel-centered">
              <Spinner />
            </div>
          ) : schemaQuery.data !== undefined ? (
            <EntityEditor
              allEntityOptions={allEntityOptions}
              allEntitiesInModule={entities.map((entityDoc) => entityDoc.title)}
              allModuleOptions={allModuleOptions}
              canEdit={canEdit}
              mode="edit"
              moduleName={selectedModule}
              onSaved={(nextSchema) => {
                queryClient.setQueryData(
                  structureKeys.schema(selectedModule, selectedEntity),
                  nextSchema,
                );
                void selectedEntitiesQueryState?.refetch();
              }}
              schema={schemaQuery.data}
              selectedEntity={selectedEntity}
            />
          ) : panelMode === "entity-edit" && pendingEntitySelection === selectedEntity ? (
            <div className="panel panel-centered">
              <Spinner />
            </div>
          ) : entities.length === 0 ? (
            <PanelState
              description={t("pages.entities.placeholder.noEntity.description")}
              title={t("pages.entities.placeholder.noEntity.title")}
            />
          ) : (
            <PanelState
              description={t("pages.entities.placeholder.select.description")}
              title={t("pages.entities.placeholder.select.title")}
            />
          )}
        </div>
      </SplitPane>
      {deleteTarget !== null ? <StructureDeleteOverlay onClose={() => setDeleteTarget(null)} onDeleted={handleDeleted} target={deleteTarget} /> : null}
    </section>
  );
}

function getEntityTreeItems({
  canEdit,
  entities,
  isLoading,
  onDelete,
  onSelect,
  selectedEntity,
  t,
}: {
  canEdit: boolean;
  entities: EntityListItem[];
  isLoading: boolean;
  onDelete: (entity: EntityListItem) => void;
  onSelect: (entityName: string) => void;
  selectedEntity: string;
  t: ReturnType<typeof useI18n>["t"];
}): TreeNavItem[] {
  if (isLoading) {
    return [
      {
        id: "loading",
        title: t("common.loading"),
      },
    ];
  }

  if (entities.length === 0) {
    return [
      {
        id: "empty",
        title: t("pages.entities.empty.entities.title"),
      },
    ];
  }

  return entities.map((entityDoc) => ({
    actions: canEdit ? [{
      ariaLabel: t("pages.entities.delete.entity.action"),
      icon: "trash" as const,
      onClick: () => onDelete(entityDoc),
      title: t("pages.entities.delete.entity.action"),
    }] : undefined,
    id: entityDoc.title,
    isActive: entityDoc.title === selectedEntity,
    onClick: () => onSelect(entityDoc.title),
    title: getEntityDisplayLabel(entityDoc),
  }));
}

function PanelState({ description, title }: { description: string; title: string }) {
  return (
    <div className="panel panel-centered">
      <EmptyState description={description} title={title} />
    </div>
  );
}
