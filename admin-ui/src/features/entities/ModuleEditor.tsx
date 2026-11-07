import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Controller, useForm } from "react-hook-form";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { CheckboxField, TextField } from "../../components/Field";
import { FormSection } from "../../components/Form";
import { FormErrorSummary } from "../../components/Form";
import { MultiValueSelect } from "../../components/MultiValueSelect";
import type { SelectOption } from "../../components/Select";
import { ApiError } from "../../lib/api";
import { localizeApiError, localizeApiFieldError } from "../../lib/errors";
import { getReferenceId } from "../../lib/references";
import { useI18n } from "../../providers/I18nProvider";
import { createModule, type ModuleDocument, updateModule } from "./api";
import { NodeLinkSelect } from "../nodes/NodeLinkSelect";
import type { NodeDocument } from "../nodes/api";

type ModuleEditorProps = {
  allEntityOptions: SelectOption[];
  allModuleNames: string[];
  allEntitiesInModule: string[];
  canEdit: boolean;
  initialRootGroup?: string;
  initialRootOwner?: string;
  mode: "create" | "edit";
  module: ModuleDocument | null;
  onSaved: (module: ModuleDocument) => void;
};

type ModuleEditorFormValues = {
  description: string;
  name: string;
  rootChildrenEntities: string[];
  rootGroup: NodeDocument | string;
  rootOwner: NodeDocument | string;
  rootPermGroup: boolean;
  rootPermOthers: boolean;
  rootPermOwner: boolean;
};

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function ModuleEditor({
  allEntityOptions,
  allModuleNames,
  allEntitiesInModule,
  canEdit,
  initialRootGroup,
  initialRootOwner,
  mode,
  module,
  onSaved,
}: ModuleEditorProps) {
  const { t } = useI18n();
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitApiError, setSubmitApiError] = useState<ApiError | null>(null);
  const editorContentRef = useRef<HTMLDivElement | null>(null);
  const {
    control,
    formState: { errors, isDirty },
    handleSubmit,
    register,
    reset,
    setError,
    subscribe,
  } = useForm<ModuleEditorFormValues>({
    defaultValues: getFormDefaults(module, {
      rootGroup: initialRootGroup,
      rootOwner: initialRootOwner,
    }),
  });
  const formError = Object.keys(errors).length > 0 ? t("errors.form.invalid") : submitError;

  useEffect(() => {
    reset(getFormDefaults(module, {
      rootGroup: initialRootGroup,
      rootOwner: initialRootOwner,
    }));
    setSubmitError(null);
    setSubmitApiError(null);
  }, [initialRootGroup, initialRootOwner, mode, module, reset]);

  useEffect(() => subscribe({
    callback: () => {
      setSubmitError(null);
      setSubmitApiError(null);
    },
    formState: { values: true },
  }), [subscribe]);

  const saveMutation = useMutation({
    mutationFn: async (values: ModuleEditorFormValues) => {
      const nextModuleName = values.name.trim();
      if (
        mode === "create" &&
        allModuleNames.some((moduleName) => moduleName === nextModuleName)
      ) {
        setError("name", {
          message: t("modules.validation.duplicateName"),
        });
        throw new Error("duplicate_module_name");
      }

      const editablePayload = {
        description: values.description.trim(),
        root_children_entities: values.rootChildrenEntities,
        root_group: getReferenceId(values.rootGroup),
        root_owner: getReferenceId(values.rootOwner),
        root_perm: {
          group: { p: values.rootPermGroup },
          others: { p: values.rootPermOthers },
          owner: { p: values.rootPermOwner },
        },
      };

      if (mode === "create") {
        return createModule({
          ...editablePayload,
          name: nextModuleName,
        });
      }

      if (module === null) {
        throw new Error("Module is missing");
      }

      return updateModule(module.name, editablePayload);
    },
    onSuccess: (nextModule) => {
      setSubmitError(null);
      setSubmitApiError(null);
      reset(getFormDefaults(nextModule, {
        rootGroup: initialRootGroup,
        rootOwner: initialRootOwner,
      }));
      onSaved(nextModule);
    },
    onError: (error) => {
      if (error instanceof ApiError) {
        setSubmitApiError(error);
        const fieldErrors = error.details?.field_errors;
        if (Array.isArray(fieldErrors)) {
          let mappedFieldError = false;
          for (const fieldError of fieldErrors) {
            const location = Array.isArray(fieldError.location) ? fieldError.location.join(".") : "";
            const fieldName = mapApiFieldError(location);
            if (fieldName !== null) {
              mappedFieldError = true;
              const normalizedFieldError = error.fieldErrors.find((item) => item.location.join(".") === location);
              setError(fieldName, { message: normalizedFieldError === undefined ? localizeApiError(error, t) : localizeApiFieldError(normalizedFieldError, t) });
            }
          }
          if (mappedFieldError) {
            setSubmitError(null);
            return;
          }
        }

        setSubmitError(localizeApiError(error, t));
        return;
      }

      if (
        error instanceof Error &&
        error.message !== "duplicate_module_name"
      ) {
        setSubmitApiError(null);
        setSubmitError(t("errors.api.unknown"));
        return;
      }

      if (!(error instanceof Error)) {
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
              error={errors.name?.message}
              label={t("modules.form.name")}
              readOnly={mode === "edit"}
              {...register("name", {
                validate: (value) =>
                  value.trim().length > 0 || t("modules.validation.name"),
              })}
            />
            <TextField
              error={errors.description?.message}
              label={t("modules.form.description")}
              readOnly={!canEdit}
              {...register("description")}
            />
            <div className="module-editor-grid">
              <Controller
                control={control}
                name="rootOwner"
                rules={{
                  validate: (value) => validateUuid(value, t("modules.validation.rootOwner")),
                }}
                render={({ field, fieldState }) => (
                  <NodeLinkSelect
                    canWrite={canEdit}
                    error={fieldState.error?.message}
                    label={t("modules.form.rootOwner")}
                    mode="single"
                    onBlur={field.onBlur}
                    onChange={field.onChange}
                    placeholder={t("pages.nodes.editor.linkPlaceholder")}
                    resolveSelectedReferences
                    targetEntities={["user"]}
                    targetModule="users"
                    value={field.value}
                  />
                )}
              />
              <Controller
                control={control}
                name="rootGroup"
                rules={{
                  validate: (value) => validateUuid(value, t("modules.validation.rootGroup")),
                }}
                render={({ field, fieldState }) => (
                  <NodeLinkSelect
                    canWrite={canEdit}
                    error={fieldState.error?.message}
                    label={t("modules.form.rootGroup")}
                    mode="single"
                    onBlur={field.onBlur}
                    onChange={field.onChange}
                    placeholder={t("pages.nodes.editor.linkPlaceholder")}
                    resolveSelectedReferences
                    targetEntities={["group"]}
                    targetModule="users"
                    value={field.value}
                  />
                )}
              />
            </div>

            <Controller
              control={control}
              name="rootChildrenEntities"
              render={({ field, fieldState }) => (
                <MultiValueSelect
                  disabled={!canEdit}
                  emptyText={t("entities.overlay.noOptions")}
                  error={fieldState.error?.message}
                  label={t("modules.form.rootChildrenEntities")}
                  onChange={field.onChange}
                  options={allEntitiesInModule.map((entityName) => ({
                    label: allEntityOptions.find((option) => option.value === entityName)?.label ?? entityName,
                    value: entityName,
                  }))}
                  placeholder={t("modules.form.rootChildrenEntities.placeholder")}
                  values={field.value}
                />
              )}
            />
          </form>
        </Card>

        <FormSection title={<strong>{t("modules.form.rootPerm")}</strong>}>
          <div className="module-permissions-grid">
            <CheckboxField
              disabled={!canEdit}
              label={t("modules.form.rootPerm.owner")}
              {...register("rootPermOwner")}
            />
            <CheckboxField
              disabled={!canEdit}
              label={t("modules.form.rootPerm.group")}
              {...register("rootPermGroup")}
            />
            <CheckboxField
              disabled={!canEdit}
              label={t("modules.form.rootPerm.others")}
              {...register("rootPermOthers")}
            />
          </div>
        </FormSection>
      </div>

      {canEdit ? (
        <div className="editor-action-bar">
          {formError ? <FormErrorSummary apiError={submitApiError ?? undefined} hasFieldErrors={Object.keys(errors).length > 0} message={formError} scrollContainerRef={editorContentRef} /> : null}
          <Button
            disabled={saveMutation.isPending || !isDirty}
            onClick={handleSubmit(
              async (values) => {
                await saveMutation.mutateAsync(values);
              },
            )}
            type="button"
          >
            {saveMutation.isPending
              ? mode === "create"
                ? t("modules.create.creating")
                : t("modules.save.saving")
              : mode === "create"
                ? t("modules.create.action")
                : t("modules.save.action")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function getFormDefaults(
  module: ModuleDocument | null,
  initialValues: { rootGroup?: string; rootOwner?: string },
): ModuleEditorFormValues {
  if (module === null) {
    return {
      description: "",
      name: "",
      rootChildrenEntities: [],
      rootGroup: initialValues.rootGroup ?? "",
      rootOwner: initialValues.rootOwner ?? "",
      rootPermGroup: false,
      rootPermOthers: false,
      rootPermOwner: true,
    };
  }

  return {
    description: module.description,
    name: module.name,
    rootChildrenEntities: module.root_children_entities,
    rootGroup: module.root_group,
    rootOwner: module.root_owner,
    rootPermGroup: Boolean(module.root_perm.group?.p),
    rootPermOthers: Boolean(module.root_perm.others?.p),
    rootPermOwner: Boolean(module.root_perm.owner?.p),
  };
}

function validateUuid(value: unknown, emptyMessage: string) {
  const normalized = getReferenceId(value);
  if (normalized.length === 0) {
    return emptyMessage;
  }

  return UUID_PATTERN.test(normalized) || emptyMessage;
}

function mapApiFieldError(location: string): keyof ModuleEditorFormValues | null {
  switch (location) {
    case "name":
      return "name";
    case "description":
      return "description";
    case "root_owner":
      return "rootOwner";
    case "root_group":
      return "rootGroup";
    case "root_children_entities":
      return "rootChildrenEntities";
    default:
      return null;
  }
}
