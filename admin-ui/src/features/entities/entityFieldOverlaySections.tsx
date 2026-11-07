import { useQuery } from "@tanstack/react-query";
import { Controller, type UseFormReturn } from "react-hook-form";
import { CheckboxField, TextField } from "../../components/Field";
import { MultiValueSelect } from "../../components/MultiValueSelect";
import { Select, type SelectOption } from "../../components/Select";
import { StringListInput } from "../../components/StringListInput";
import { structureKeys } from "../../lib/queryKeys";
import { STRUCTURE_QUERY_OPTIONS } from "../../lib/queryOptions";
import { useI18n } from "../../providers/I18nProvider";
import { getEntities } from "./api";
import { getEntityDisplayLabel } from "./presentation";
import {
  ACCESS_MODES,
  ARRAY_ITEM_TYPES,
  FIELD_SEMANTIC_TYPES,
  buildFieldSchemaFromValues,
  type FieldEditorValues,
  validateFieldAccessTree,
  validateMutuallyExclusiveBounds,
  validateNumericInput,
  validateRegexPattern,
} from "./fieldEditorSchema";

type FormApi = Pick<
  UseFormReturn<FieldEditorValues>,
  "control" | "formState" | "getValues" | "register"
>;

type OverlayCommonProps = {
  allModuleOptions: SelectOption[];
  disabled: boolean;
  form: FormApi;
  parentVisibilityMode: FieldEditorValues["visibilityMode"] | null | undefined;
  parentWriteMode: FieldEditorValues["writeMode"] | null | undefined;
  semanticType: FieldEditorValues["semanticType"];
  selectedLinkModule: string;
  sourceFieldSchema: Record<string, unknown> | undefined;
};

export function FieldAccessSection({
  disabled,
  form,
  parentVisibilityMode,
  parentWriteMode,
  sourceFieldSchema,
}: Pick<
  OverlayCommonProps,
  "disabled" | "form" | "parentVisibilityMode" | "parentWriteMode" | "sourceFieldSchema"
>) {
  const { t } = useI18n();
  const { control, formState: { errors }, getValues } = form;

  return (
    <div className="overlay-grid">
      <Controller
        control={control}
        name="visibilityMode"
        rules={{
          validate: (value) => {
            const candidateValues = { ...getValues(), visibilityMode: value };
            return validateFieldAccessTree(
              buildFieldSchemaFromValues(candidateValues, sourceFieldSchema),
              {
                parentVisibilityMode,
                parentWriteMode,
              },
              t,
            ).visibilityMode ?? true;
          },
        }}
        render={({ field }) => (
          <Select
            disabled={disabled}
            error={errors.visibilityMode?.message}
            label={t("schema.visible")}
            onBlur={field.onBlur}
            onChange={field.onChange}
            options={getAccessModeOptions(t)}
            value={field.value}
          />
        )}
      />
      <Controller
        control={control}
        name="writeMode"
        rules={{
          validate: (value) => {
            const candidateValues = { ...getValues(), writeMode: value };
            return validateFieldAccessTree(
              buildFieldSchemaFromValues(candidateValues, sourceFieldSchema),
              {
                parentVisibilityMode,
                parentWriteMode,
              },
              t,
            ).writeMode ?? true;
          },
        }}
        render={({ field }) => (
          <Select
            disabled={disabled}
            error={errors.writeMode?.message}
            label={t("schema.write")}
            onBlur={field.onBlur}
            onChange={field.onChange}
            options={getAccessModeOptions(t)}
            value={field.value}
          />
        )}
      />
    </div>
  );
}

export function FieldBaseSection({
  disabled,
  form,
  isRequiredAllowed,
}: Pick<OverlayCommonProps, "disabled" | "form"> & { isRequiredAllowed: boolean }) {
  const { t } = useI18n();
  const { register } = form;

  return (
    <div className="overlay-checkboxes">
      <CheckboxField disabled={disabled || !isRequiredAllowed} label={t("schema.required")} {...register("isRequired")} />
      <CheckboxField disabled={disabled} label={t("schema.nullable")} {...register("isNullable")} />
    </div>
  );
}

export function TypeSpecificFields({
  allModuleOptions,
  disabled,
  form,
  semanticType,
  selectedLinkModule,
}: OverlayCommonProps) {
  const { t } = useI18n();
  const {
    control,
    formState: { errors },
    getValues,
    register,
  } = form;

  if (semanticType === "String" || semanticType === "Password" || semanticType === "Text" || semanticType === "RichText") {
    return (
      <div className="overlay-grid">
        <TextField
          error={errors.pattern?.message}
          label={t("entities.overlay.pattern")}
          readOnly={disabled}
          {...register("pattern", {
            validate: (value) => validateRegexPattern(value, t),
          })}
        />
        {semanticType === "String" ? (
          <Controller
            control={control}
            name="enumValues"
            render={({ field, fieldState }) => (
              <StringListInput
                disabled={disabled}
                error={fieldState.error?.message}
                label={t("entities.overlay.enumValues")}
                onChange={field.onChange}
                placeholder={t("entities.overlay.enumValues.placeholder")}
                values={field.value}
              />
            )}
          />
        ) : null}
        <TextField
          error={errors.minLength?.message}
          label={t("entities.overlay.minLength")}
          readOnly={disabled}
          {...register("minLength", {
            validate: (value) => validateNumericInput(value, t, { integer: true, nonNegative: true }),
          })}
        />
        <TextField
          error={errors.maxLength?.message}
          label={t("entities.overlay.maxLength")}
          readOnly={disabled}
          {...register("maxLength", {
            validate: (value) => validateNumericInput(value, t, { integer: true, nonNegative: true }),
          })}
        />
      </div>
    );
  }

  if (semanticType === "Number" || semanticType === "Integer") {
    return (
      <div className="overlay-grid">
        <TextField
          error={errors.minimum?.message}
          label={t("entities.overlay.minimum")}
          readOnly={disabled}
          {...register("minimum", {
            validate: (value) =>
              validateNumericInput(value, t, { integer: semanticType === "Integer" }) === true
                ? validateMutuallyExclusiveBounds(value, getValues("exclusiveMinimum"), t)
                : validateNumericInput(value, t, { integer: semanticType === "Integer" }),
          })}
        />
        <TextField
          error={errors.maximum?.message}
          label={t("entities.overlay.maximum")}
          readOnly={disabled}
          {...register("maximum", {
            validate: (value) =>
              validateNumericInput(value, t, { integer: semanticType === "Integer" }) === true
                ? validateMutuallyExclusiveBounds(value, getValues("exclusiveMaximum"), t)
                : validateNumericInput(value, t, { integer: semanticType === "Integer" }),
          })}
        />
        <TextField
          error={errors.exclusiveMinimum?.message}
          label={t("entities.overlay.exclusiveMinimum")}
          readOnly={disabled}
          {...register("exclusiveMinimum", {
            validate: (value) =>
              validateNumericInput(value, t, { integer: semanticType === "Integer" }) === true
                ? validateMutuallyExclusiveBounds(value, getValues("minimum"), t)
                : validateNumericInput(value, t, { integer: semanticType === "Integer" }),
          })}
        />
        <TextField
          error={errors.exclusiveMaximum?.message}
          label={t("entities.overlay.exclusiveMaximum")}
          readOnly={disabled}
          {...register("exclusiveMaximum", {
            validate: (value) =>
              validateNumericInput(value, t, { integer: semanticType === "Integer" }) === true
                ? validateMutuallyExclusiveBounds(value, getValues("maximum"), t)
                : validateNumericInput(value, t, { integer: semanticType === "Integer" }),
          })}
        />
        <TextField
          error={errors.multipleOf?.message}
          label={t("entities.overlay.multipleOf")}
          readOnly={disabled}
          {...register("multipleOf", {
            validate: (value) => validateNumericInput(value, t, {
              integer: semanticType === "Integer",
              positive: value.trim().length > 0,
            }),
          })}
        />
      </div>
    );
  }

  if (semanticType === "Array") {
    return (
      <div className="overlay-grid">
        <Controller
          control={control}
          name="arrayItemType"
          render={({ field }) => (
            <Select
              disabled={disabled}
              label={t("entities.overlay.arrayItemType")}
              onBlur={field.onBlur}
              onChange={field.onChange}
              options={ARRAY_ITEM_TYPE_OPTIONS}
              value={field.value}
            />
          )}
        />
        <TextField
          error={errors.minItems?.message}
          label={t("entities.overlay.minItems")}
          readOnly={disabled}
          {...register("minItems", {
            validate: (value) => validateNumericInput(value, t, { integer: true, nonNegative: true }),
          })}
        />
        <TextField
          error={errors.maxItems?.message}
          label={t("entities.overlay.maxItems")}
          readOnly={disabled}
          {...register("maxItems", {
            validate: (value) => validateNumericInput(value, t, { integer: true, nonNegative: true }),
          })}
        />
      </div>
    );
  }

  if (semanticType === "Link" || semanticType === "LinkArray") {
    return (
      <div className="overlay-grid">
        <Controller
          control={control}
          name="linkModule"
          rules={{
            validate: (value) =>
              semanticType === "Link" || semanticType === "LinkArray"
                ? value.trim().length > 0 || t("entities.overlay.validation.linkModule")
                : true,
          }}
          render={({ field }) => (
            <Select
              disabled={disabled}
              error={errors.linkModule?.message}
              label={t("entities.overlay.linkModule")}
              onBlur={field.onBlur}
              onChange={field.onChange}
              options={allModuleOptions}
              value={field.value}
            />
          )}
        />
        <LinkEntitiesField
          control={control}
          disabled={disabled}
          error={errors.linkEntities?.message}
          label={t("entities.overlay.linkEntities")}
          moduleName={selectedLinkModule}
          required
        />
        {semanticType === "LinkArray" ? (
          <TextField
            error={errors.minItems?.message}
            label={t("entities.overlay.minItems")}
            readOnly={disabled}
            {...register("minItems", {
              validate: (value) => validateNumericInput(value, t, { integer: true, nonNegative: true }),
            })}
          />
        ) : null}
        {semanticType === "LinkArray" ? (
          <TextField
            error={errors.maxItems?.message}
            label={t("entities.overlay.maxItems")}
            readOnly={disabled}
            {...register("maxItems", {
              validate: (value) => validateNumericInput(value, t, { integer: true, nonNegative: true }),
            })}
          />
        ) : null}
      </div>
    );
  }

  return null;
}

function LinkEntitiesField({
  control,
  disabled,
  error,
  label,
  moduleName,
  required,
}: {
  control: UseFormReturn<FieldEditorValues>["control"];
  disabled: boolean;
  error?: string;
  label: string;
  moduleName: string;
  required: boolean;
}) {
  const { t } = useI18n();
  const entitiesQuery = useQuery({
    ...STRUCTURE_QUERY_OPTIONS,
    enabled: moduleName.trim().length > 0,
    queryKey: structureKeys.entities(moduleName),
    queryFn: ({ signal }) => getEntities(moduleName, signal),
  });

  const options = (entitiesQuery.data ?? []).map((entityDoc) => ({
    label: getEntityDisplayLabel(entityDoc),
    value: entityDoc.title,
  }));

  return (
    <Controller
      control={control}
      name="linkEntities"
      rules={{
        validate: (value) => (required ? value.length > 0 || t("entities.overlay.validation.linkEntities") : true),
      }}
      render={({ field }) => (
        <MultiValueSelect
          disabled={disabled}
          emptyText={entitiesQuery.isPending ? t("common.loading") : t("entities.overlay.noOptions")}
          error={error}
          label={label}
          onChange={field.onChange}
          options={options}
          placeholder={t("entities.overlay.linkEntities.placeholder")}
          values={field.value}
        />
      )}
    />
  );
}

const ARRAY_ITEM_TYPE_OPTIONS: SelectOption[] = ARRAY_ITEM_TYPES.map((type) => ({
  label: type,
  value: type,
}));

function translateMode(mode: string, t: ReturnType<typeof useI18n>["t"]) {
  switch (mode) {
    case "all":
      return t("schema.mode.all");
    case "admin":
      return t("schema.mode.admin");
    case "superuser":
      return t("schema.mode.superuser");
    case "none":
      return t("schema.mode.none");
    default:
      return t("schema.unknown");
  }
}

function getAccessModeOptions(t: ReturnType<typeof useI18n>["t"]): SelectOption[] {
  return ACCESS_MODES.map((mode) => ({
    label: translateMode(mode, t),
    value: mode,
  }));
}

export const FIELD_SEMANTIC_TYPE_OPTIONS: SelectOption[] = FIELD_SEMANTIC_TYPES.map((type) => ({
  label: type,
  value: type,
}));
