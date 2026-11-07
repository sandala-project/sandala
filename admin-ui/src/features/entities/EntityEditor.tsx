import { useMutation } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { Button } from "../../components/Button";
import { CheckboxField, TextField } from "../../components/Field";
import { Card } from "../../components/Card";
import { FormErrorSummary, FormSection } from "../../components/Form";
import { MultiValueSelect } from "../../components/MultiValueSelect";
import type { SelectOption } from "../../components/Select";
import { ApiError } from "../../lib/api";
import { localizeApiError } from "../../lib/errors";
import { useI18n } from "../../providers/I18nProvider";
import type { JsonSchema } from "./api";
import { createEntitySchema, updateEntitySchema } from "./api";
import { FieldEditorNode } from "./FieldEditorNode";
import { FieldEditorOverlay } from "./FieldEditorOverlay";
import {
  buildFieldSchemaFromValues,
  deleteFieldFromSchema,
  reorderFieldsInSchema,
  upsertFieldInSchema,
} from "./fieldEditorSchema";
import {
  buildEntitySchemaWithRootEdits,
  getSchemaChildrenEntities,
  getSchemaDefaultPerm,
  getSchemaLabelTemplates,
  splitSchemaFields,
  type SchemaFieldNode,
} from "./schema";

type EntityEditorProps = {
  allEntityOptions: SelectOption[];
  allEntitiesInModule: string[];
  allModuleOptions: SelectOption[];
  canEdit: boolean;
  moduleName: string;
  mode: "create" | "edit";
  onSaved: (schema: JsonSchema) => void;
  schema: JsonSchema;
  selectedEntity: string;
};

type EntityEditorFormValues = {
  allowedChildEntities: string[];
  description: string;
  entityTitle: string;
  permGroupP: boolean;
  permGroupR: boolean;
  permGroupW: boolean;
  permOthersP: boolean;
  permOthersR: boolean;
  permOthersW: boolean;
  permOwnerP: boolean;
  permOwnerR: boolean;
  permOwnerW: boolean;
  referenceLabelTemplate: string;
  treeLabelTemplate: string;
};

type OverlayState =
  | { mode: "create"; parentPath: string[] }
  | { mode: "edit"; node: SchemaFieldNode };

export function EntityEditor({
  allEntityOptions,
  allEntitiesInModule,
  allModuleOptions,
  canEdit,
  moduleName,
  mode,
  onSaved,
  schema,
  selectedEntity,
}: EntityEditorProps) {
  const { t } = useI18n();
  const [draftSchema, setDraftSchema] = useState(schema);
  const [draggedFieldPath, setDraggedFieldPath] = useState<string[] | null>(null);
  const [overlayState, setOverlayState] = useState<OverlayState | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitApiError, setSubmitApiError] = useState<ApiError | null>(null);
  const editorContentRef = useRef<HTMLDivElement | null>(null);
  const effectiveEntityName = selectedEntity.length > 0 ? selectedEntity : schema.title ?? "";
  const { customFields } = useMemo(
    () => splitSchemaFields(draftSchema, { entityName: effectiveEntityName, moduleName }),
    [draftSchema, effectiveEntityName, moduleName],
  );
  const {
    formState: { errors, isDirty },
    control,
    handleSubmit,
    register,
    reset,
    setError,
    subscribe,
  } = useForm<EntityEditorFormValues>({
    defaultValues: getFormDefaults(schema, selectedEntity),
  });
  const formError = Object.keys(errors).length > 0 ? t("errors.form.invalid") : submitError;

  useEffect(() => {
    setDraftSchema(schema);
    setDraggedFieldPath(null);
    reset(getFormDefaults(schema, selectedEntity));
    setOverlayState(null);
    setSubmitError(null);
    setSubmitApiError(null);
  }, [reset, schema, selectedEntity]);

  useEffect(() => subscribe({
    callback: () => {
      setSubmitError(null);
      setSubmitApiError(null);
    },
    formState: { values: true },
  }), [subscribe]);

  const saveMutation = useMutation({
    mutationFn: async (values: EntityEditorFormValues) => {
      const nextEntityTitle = values.entityTitle.trim();
      if (
        mode === "create" &&
        allEntitiesInModule.some((entityName) => entityName === nextEntityTitle)
      ) {
        setError("entityTitle", {
          message: t("entities.validation.duplicateEntityTitle"),
        });
        throw new Error("duplicate_entity_title");
      }

      const childrenEntities = values.allowedChildEntities;
      const invalidEntities = childrenEntities.filter((name) => !allEntitiesInModule.includes(name));

      if (invalidEntities.length > 0) {
        setError("allowedChildEntities", {
          message: `${t("entities.errors.unknownChildren")}: ${invalidEntities.join(", ")}`,
        });
        throw new Error("invalid_children_entities");
      }

      const nextSchema = buildEntitySchemaWithRootEdits(draftSchema, {
        childrenEntities,
        defaultPerm: {
          group: { p: values.permGroupP, r: values.permGroupR, w: values.permGroupW },
          others: { p: values.permOthersP, r: values.permOthersR, w: values.permOthersW },
          owner: { p: values.permOwnerP, r: values.permOwnerR, w: values.permOwnerW },
        },
        description: values.description.trim(),
        referenceLabelTemplate: values.referenceLabelTemplate,
        title: values.entityTitle.trim(),
        treeLabelTemplate: values.treeLabelTemplate,
      });

      return mode === "create"
        ? createEntitySchema(moduleName, nextEntityTitle, nextSchema)
        : updateEntitySchema(moduleName, selectedEntity, nextSchema);
    },
    onSuccess: (nextSchema) => {
      setSubmitError(null);
      setSubmitApiError(null);
      setDraftSchema(nextSchema);
      onSaved(nextSchema);
      reset(getFormDefaults(nextSchema, mode === "create" ? nextSchema.title ?? selectedEntity : selectedEntity));
    },
    onError: (error) => {
      if (error instanceof ApiError) {
        setSubmitApiError(error);
        setSubmitError(localizeApiError(error, t));
      } else if (
        error instanceof Error &&
        error.message !== "invalid_children_entities" &&
        error.message !== "duplicate_entity_title"
      ) {
        setSubmitApiError(null);
        setSubmitError(t("errors.api.unknown"));
      }
    },
  });

  return (
    <div className="editor-layout">
      <div className="editor-content" ref={editorContentRef}>
        <Card tone="muted">
          <form className="entity-meta-form">
            <TextField
              error={errors.entityTitle?.message}
              label={t("entities.form.entityTitle")}
              readOnly={mode === "edit"}
              {...register("entityTitle", {
                validate: (value) =>
                  value.trim().length > 0 || t("entities.validation.entityTitle"),
              })}
            />
            <TextField
              error={errors.description?.message}
              label={t("entities.form.description")}
              readOnly={!canEdit}
              {...register("description")}
            />
            <TextField
              label={t("entities.form.treeLabelTemplate")}
              readOnly={!canEdit}
              {...register("treeLabelTemplate")}
            />
            <TextField
              label={t("entities.form.referenceLabelTemplate")}
              readOnly={!canEdit}
              {...register("referenceLabelTemplate")}
            />
            <Controller
              control={control}
              name="allowedChildEntities"
              render={({ field, fieldState }) => (
                <MultiValueSelect
                  disabled={!canEdit}
                  emptyText={t("entities.overlay.noOptions")}
                  error={fieldState.error?.message}
                  label={t("entities.form.allowedChildEntities")}
                  onChange={field.onChange}
                  options={allEntitiesInModule.map((entityName) => ({
                    label: allEntityOptions.find((option) => option.value === entityName)?.label ?? entityName,
                    value: entityName,
                  }))}
                  placeholder={t("entities.form.allowedChildEntities.placeholder")}
                  values={field.value}
                />
              )}
            />
          </form>
        </Card>

        <FormSection title={<strong>{t("entities.fields.title")}</strong>}>
          <div className="entity-field-tree">
            {customFields.map((field) => (
              <FieldEditorNode
                canEdit={canEdit}
                draggedPath={draggedFieldPath}
                key={field.path.join(".")}
                node={field}
                onAddNested={(parentPath) => setOverlayState({ mode: "create", parentPath })}
                onDelete={(path) => {
                  setSubmitError(null);
                  setSubmitApiError(null);
                  setDraftSchema((current) => deleteFieldFromSchema(current, path));
                }}
                onDragEnd={() => setDraggedFieldPath(null)}
                onDragStart={(path) => setDraggedFieldPath(path)}
                onEdit={(nodeToEdit) => setOverlayState({ mode: "edit", node: nodeToEdit })}
                onReorder={(sourcePath, targetPath, position) => {
                  setSubmitError(null);
                  setSubmitApiError(null);
                  setDraftSchema((current) => reorderFieldsInSchema(current, sourcePath, targetPath, position));
                }}
              />
            ))}
          </div>
          {canEdit ? (
            <div className="entity-fields-add-action">
              <Button kind="ghost" onClick={() => setOverlayState({ mode: "create", parentPath: [] })} type="button">
                {t("entities.fields.add")}
              </Button>
            </div>
          ) : null}
        </FormSection>

        <FormSection title={<strong>{t("entities.access.title")}</strong>}>
          <div className="entity-permissions-grid">
            <div className="permissions-column">
              <div className="field-label">{t("permissions.owner")}</div>
              <CheckboxField disabled={!canEdit} label={t("permissions.read")} {...register("permOwnerR")} />
              <CheckboxField disabled={!canEdit} label={t("permissions.write")} {...register("permOwnerW")} />
              <CheckboxField disabled={!canEdit} label={t("permissions.populate")} {...register("permOwnerP")} />
            </div>
            <div className="permissions-column">
              <div className="field-label">{t("permissions.group")}</div>
              <CheckboxField disabled={!canEdit} label={t("permissions.read")} {...register("permGroupR")} />
              <CheckboxField disabled={!canEdit} label={t("permissions.write")} {...register("permGroupW")} />
              <CheckboxField disabled={!canEdit} label={t("permissions.populate")} {...register("permGroupP")} />
            </div>
            <div className="permissions-column">
              <div className="field-label">{t("permissions.others")}</div>
              <CheckboxField disabled={!canEdit} label={t("permissions.read")} {...register("permOthersR")} />
              <CheckboxField disabled={!canEdit} label={t("permissions.write")} {...register("permOthersW")} />
              <CheckboxField disabled={!canEdit} label={t("permissions.populate")} {...register("permOthersP")} />
            </div>
          </div>
        </FormSection>
      </div>

      {canEdit ? (
        <div className="editor-action-bar">
          {formError ? <FormErrorSummary apiError={submitApiError ?? undefined} hasFieldErrors={Object.keys(errors).length > 0} message={formError} scrollContainerRef={editorContentRef} /> : null}
          <Button
            disabled={saveMutation.isPending || (!isDirty && draftSchema === schema)}
            onClick={handleSubmit(async (values) => {
              await saveMutation.mutateAsync(values);
            })}
            type="button"
          >
            {saveMutation.isPending
              ? mode === "create"
                ? t("entities.create.creating")
                : t("entities.save.saving")
              : mode === "create"
                ? t("entities.create.action")
                : t("entities.save.action")}
          </Button>
        </div>
      ) : null}

      {overlayState !== null ? (
        <FieldEditorOverlay
          allModuleOptions={allModuleOptions}
          currentModuleName={moduleName}
          currentSchema={draftSchema}
          onClose={() => setOverlayState(null)}
          onSubmit={(values) => {
            setSubmitError(null);
            setSubmitApiError(null);
            setDraftSchema((current) => {
              const existingFieldSchema = overlayState.mode === "edit" ? overlayState.node.fieldSchema : undefined;
              const nextFieldSchema = buildFieldSchemaFromValues(values, existingFieldSchema);

              return upsertFieldInSchema({
                fieldSchema: nextFieldSchema,
                isRequired: values.isRequired,
                parentPath: overlayState.mode === "edit" ? overlayState.node.path.slice(0, -1) : overlayState.parentPath,
                previousPath: overlayState.mode === "edit" ? overlayState.node.path : undefined,
                schema: current,
                targetName: values.name.trim(),
              });
            });
            setOverlayState(null);
          }}
          parentPath={overlayState.mode === "edit" ? overlayState.node.path.slice(0, -1) : overlayState.parentPath}
          sourceNode={overlayState.mode === "edit" ? overlayState.node : null}
        />
      ) : null}
    </div>
  );
}

function getFormDefaults(schema: JsonSchema, selectedEntity: string): EntityEditorFormValues {
  const defaultPerm = getSchemaDefaultPerm(schema);
  const labelTemplates = getSchemaLabelTemplates(schema);
  return {
    allowedChildEntities: getSchemaChildrenEntities(schema),
    description: schema.description ?? "",
    entityTitle: schema.title ?? selectedEntity,
    permGroupP: defaultPerm.group.p,
    permGroupR: defaultPerm.group.r,
    permGroupW: defaultPerm.group.w,
    permOthersP: defaultPerm.others.p,
    permOthersR: defaultPerm.others.r,
    permOthersW: defaultPerm.others.w,
    permOwnerP: defaultPerm.owner.p,
    permOwnerR: defaultPerm.owner.r,
    permOwnerW: defaultPerm.owner.w,
    referenceLabelTemplate: labelTemplates.reference,
    treeLabelTemplate: labelTemplates.tree,
  };
}
