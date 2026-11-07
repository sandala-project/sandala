import { useEffect, useRef } from "react";
import { Controller, useForm } from "react-hook-form";
import { Button } from "../../components/Button";
import { TextField } from "../../components/Field";
import { OverlayDialog } from "../../components/OverlayDialog";
import { OverlayCloseButton } from "../../components/OverlayCloseButton";
import { Select, type SelectOption } from "../../components/Select";
import { useI18n } from "../../providers/I18nProvider";
import type { JsonSchema } from "./api";
import {
  buildFieldSchemaFromValues,
  canRequireField,
  getDefaultFieldEditorValues,
  getFieldEditorValuesFromNode,
  type FieldEditorValues,
  validateFieldEditorSubmit,
  validateFieldName,
} from "./fieldEditorSchema";
import {
  FieldAccessSection,
  FieldBaseSection,
  FIELD_SEMANTIC_TYPE_OPTIONS,
  TypeSpecificFields,
} from "./entityFieldOverlaySections";
import { getSchemaFieldNodeAtPath, getSchemaSiblingFieldNames, type SchemaFieldNode } from "./schema";

type FieldEditorOverlayProps = {
  allModuleOptions: SelectOption[];
  currentModuleName: string;
  currentSchema: JsonSchema;
  onClose: () => void;
  onSubmit: (values: FieldEditorValues) => void;
  parentPath: string[];
  sourceNode: SchemaFieldNode | null;
};

export function FieldEditorOverlay({
  allModuleOptions,
  currentModuleName,
  currentSchema,
  onClose,
  onSubmit,
  parentPath,
  sourceNode,
}: FieldEditorOverlayProps) {
  const { t } = useI18n();
  const parentNode = getSchemaFieldNodeAtPath(currentSchema, parentPath);
  const siblingNames = getSchemaSiblingFieldNames(currentSchema, parentPath);
  const isNameLocked = sourceNode !== null;
  const isStructureLocked = sourceNode !== null && !sourceNode.canEditStructure;
  const isDescriptionLocked = sourceNode !== null && !sourceNode.canEditDescription;
  const form = useForm<FieldEditorValues>({
    defaultValues: sourceNode
      ? getFieldEditorValuesFromNode(sourceNode)
      : getDefaultFieldEditorValues(currentModuleName),
    mode: "onBlur",
    reValidateMode: "onBlur",
  });
  const {
    clearErrors,
    control,
    formState: { errors },
    handleSubmit,
    register,
    setError,
    setValue,
    watch,
  } = form;

  const semanticType = watch("semanticType");
  const arrayItemType = watch("arrayItemType");
  const isRequired = watch("isRequired");
  const linkModule = watch("linkModule");
  const previousLinkModuleRef = useRef(linkModule);
  const isRequiredAllowed = canRequireField({ semanticType, arrayItemType });

  useEffect(() => {
    if (isRequiredAllowed || !isRequired) {
      return;
    }
    setValue("isRequired", false, { shouldDirty: true });
  }, [isRequired, isRequiredAllowed, setValue]);

  useEffect(() => {
    if ((semanticType === "Link" || semanticType === "LinkArray") && linkModule.trim().length === 0) {
      setValue("linkModule", currentModuleName, { shouldDirty: true });
    }
  }, [currentModuleName, linkModule, semanticType, setValue]);

  useEffect(() => {
    if (previousLinkModuleRef.current === linkModule) {
      return;
    }

    previousLinkModuleRef.current = linkModule;
    setValue("linkEntities", [], { shouldDirty: true });
  }, [linkModule, setValue]);

  return (
    <OverlayDialog
      ariaLabel={sourceNode ? t("entities.overlay.editField") : t("entities.overlay.addField")}
      className="overlay-dialog-field-editor"
      onClose={onClose}
    >
        <div className="overlay-header">
          <strong>{sourceNode ? t("entities.overlay.editField") : t("entities.overlay.addField")}</strong>
          <OverlayCloseButton onClick={onClose} />
        </div>

        <form
          className="overlay-form"
          onSubmit={handleSubmit((values) => {
            clearErrors();
            const candidateFieldSchema = buildFieldSchemaFromValues(values, sourceNode?.fieldSchema);

            const submitErrors = validateFieldEditorSubmit(
              values,
              {
                currentName: sourceNode?.name,
                fieldSchema: candidateFieldSchema,
                parentVisibilityMode: parentNode?.visibilityMode as FieldEditorValues["visibilityMode"] | null | undefined,
                parentWriteMode: parentNode?.writeMode as FieldEditorValues["writeMode"] | null | undefined,
                siblingNames,
              },
              t,
            );

            let hasErrors = false;
            for (const [fieldName, message] of Object.entries(submitErrors)) {
              if (message === undefined) {
                continue;
              }
              hasErrors = true;
              setError(fieldName as keyof FieldEditorValues, { message });
            }

            if (hasErrors) {
              return;
            }

            onSubmit({
              ...values,
              isRequired: canRequireField(values) ? values.isRequired : false,
            });
          })}
        >
          <div className="overlay-content">
            <div className="overlay-grid">
              <TextField
                error={errors.name?.message}
                label={t("entities.overlay.name")}
                readOnly={isNameLocked}
                {...register("name", {
                  required: t("entities.overlay.validation.name"),
                  validate: (value) => validateFieldName(value, t),
                })}
              />
              <Controller
                control={control}
                name="semanticType"
                render={({ field }) => (
                  <Select
                    disabled={isStructureLocked}
                    label={t("entities.overlay.semanticType")}
                    onBlur={field.onBlur}
                    onChange={field.onChange}
                    options={FIELD_SEMANTIC_TYPE_OPTIONS}
                    value={field.value}
                  />
                )}
              />
            </div>

            <TextField label={t("entities.overlay.description")} readOnly={isDescriptionLocked} {...register("description")} />

            <FieldAccessSection
              disabled={isStructureLocked}
              form={form}
              parentVisibilityMode={parentNode?.visibilityMode as FieldEditorValues["visibilityMode"] | null | undefined}
              parentWriteMode={parentNode?.writeMode as FieldEditorValues["writeMode"] | null | undefined}
              sourceFieldSchema={sourceNode?.fieldSchema}
            />

            <FieldBaseSection
              disabled={isStructureLocked}
              form={form}
              isRequiredAllowed={isRequiredAllowed}
            />

            <TypeSpecificFields
              allModuleOptions={allModuleOptions}
              disabled={isStructureLocked}
              form={form}
              parentVisibilityMode={parentNode?.visibilityMode as FieldEditorValues["visibilityMode"] | null | undefined}
              parentWriteMode={parentNode?.writeMode as FieldEditorValues["writeMode"] | null | undefined}
              selectedLinkModule={linkModule}
              semanticType={semanticType}
              sourceFieldSchema={sourceNode?.fieldSchema}
            />
          </div>

          <div className="overlay-actions">
            <Button kind="ghost" onClick={onClose} type="button">
              {t("common.cancel")}
            </Button>
            <Button type="submit">{sourceNode ? t("common.apply") : t("common.create")}</Button>
          </div>
        </form>
    </OverlayDialog>
  );
}
