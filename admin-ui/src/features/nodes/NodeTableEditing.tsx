import { useLayoutEffect, useMemo, useRef, useState, type RefObject } from "react";
import { useMutation } from "@tanstack/react-query";
import { Button } from "../../components/Button";
import { CheckboxField, TextField } from "../../components/Field";
import { FormErrorSummary } from "../../components/Form";
import { OverlayDialog } from "../../components/OverlayDialog";
import { OverlayCloseButton } from "../../components/OverlayCloseButton";
import { Select } from "../../components/Select";
import { ApiError } from "../../lib/api";
import { fromUtcDateTimeLocalValue, normalizeUtcDateTimeValue, toUtcDateTimeLocalValue } from "../../lib/dateTime";
import { localizeApiError } from "../../lib/errors";
import type { TranslationKey } from "../../locales";
import { useI18n } from "../../providers/I18nProvider";
import type { JsonSchema } from "../entities/api";
import type { NodeDocument } from "./api";
import { updateNode } from "./api";
import type { NodeEditorField } from "./editorSchema";
import { NodeFieldEditorSurface } from "./NodeFieldEditorSurface";
import { NodeLinkSelect } from "./NodeLinkSelect";
import { mapApiFieldErrors, normalizeNodeFieldValue, replaceNodeReferences, useNodeDraft } from "./useNodeDraft";
import { getValueAtPath } from "./useNodeDraft";
import { validateSingleField } from "./nodeValidation";

export function NodeTableInlineEditor(args: {
  field: NodeEditorField;
  moduleName: string;
  node: NodeDocument;
  onCancel: () => void;
  onOpenLinkedNode: (node: NodeDocument, moduleName: string, onUpdated?: (node: NodeDocument) => void) => void;
  onSaved: (node: NodeDocument) => Promise<void> | void;
}) {
  const { t } = useI18n();
  const initialValue = useMemo(() => getValueAtPath(args.node, args.field.path), [args.field.path, args.node]);
  const [value, setValue] = useState<unknown>(() => (
    isLinkField(args.field) ? initialValue : toEditableValue(args.field, initialValue)
  ));
  const [error, setError] = useState<string | null>(null);
  const editorRef = useRef<HTMLDivElement | null>(null);
  const placement = useInlineEditorPlacement(editorRef);

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payloadValue = normalizeInlineValue(args.field, value);
      const nextErrors = validateSingleField(
        [args.field],
        { [args.field.name]: payloadValue },
        args.field.path,
        t,
      );
      const nextError = nextErrors.set[args.field.path.join(".")] ?? null;
      setError(nextError);

      if (nextError !== null) {
        throw new Error("node_validation_failed");
      }

      return updateNode(args.moduleName, String(args.node.id), {
        [args.field.name]: normalizeNodeFieldValue(args.field, payloadValue),
      });
    },
    onSuccess: async (nextNode) => {
      await args.onSaved(nextNode);
    },
    onError: (mutationError) => {
      if (mutationError instanceof ApiError) {
        const nextErrors = mapApiFieldErrors(mutationError, [args.field], t);
        setError(nextErrors[args.field.path.join(".")] ?? localizeApiError(mutationError, t));
        return;
      }

      if (mutationError instanceof Error && mutationError.message !== "node_validation_failed") {
        setError(t("errors.api.unknown"));
      }
    },
  });
  return (
    <div
      className={`node-table-inline-editor ${placement === "left" ? "is-flipped" : ""}`.trim()}
      onClick={(event) => event.stopPropagation()}
      onKeyDown={(event) => event.stopPropagation()}
      ref={editorRef}
      role="presentation"
    >
      {isLinkField(args.field) ? (
        <NodeLinkSelect
          canWrite={args.field.writable}
          error={error ?? undefined}
          hideLabel
          label={args.field.label}
          mode={args.field.inputKind === "link" ? "single" : "multiple"}
          onBlur={() => {
            const payloadValue = normalizeInlineValue(args.field, value);
            const nextErrors = validateSingleField(
              [args.field],
              { [args.field.name]: payloadValue },
              args.field.path,
              t,
            );
            setError(nextErrors.set[args.field.path.join(".")] ?? null);
          }}
          onChange={setValue}
          onOpenNode={(node, moduleName) => {
            args.onOpenLinkedNode(node, moduleName, (nextNode) => {
              setValue((current: unknown) => replaceNodeReferences(current, nextNode));
            });
          }}
          placeholder={t("pages.nodes.editor.linkPlaceholder")}
          targetEntities={args.field.linkTargetEntities}
          targetModule={args.field.linkTargetModule ?? ""}
          value={value}
        />
      ) : (
        <InlineScalarControl
          error={error}
          field={args.field}
          onBlur={() => {
            const payloadValue = normalizeInlineValue(args.field, value);
            const nextErrors = validateSingleField(
              [args.field],
              { [args.field.name]: payloadValue },
              args.field.path,
              t,
            );
            setError(nextErrors.set[args.field.path.join(".")] ?? null);
          }}
          onChange={(nextValue) => {
            setValue(nextValue);
            if (error !== null) {
              const payloadValue = normalizeInlineValue(args.field, nextValue);
              const nextErrors = validateSingleField(
                [args.field],
                { [args.field.name]: payloadValue },
                args.field.path,
                t,
              );
              setError(nextErrors.set[args.field.path.join(".")] ?? null);
            }
          }}
          t={t}
          value={value as boolean | string}
        />
      )}
      <div className="node-table-inline-actions">
        <Button
          kind="ghost"
          onClick={args.onCancel}
          type="button"
        >
          {t("common.cancel")}
        </Button>
        <Button
          disabled={saveMutation.isPending}
          onClick={() => {
            void saveMutation.mutateAsync();
          }}
          type="button"
        >
          {saveMutation.isPending ? t("common.loading") : t("common.apply")}
        </Button>
      </div>
    </div>
  );
}

function useInlineEditorPlacement(editorRef: RefObject<HTMLDivElement | null>) {
  const [placement, setPlacement] = useState<"left" | "right">("right");

  useLayoutEffect(() => {
    const editor = editorRef.current;
    if (editor === null) {
      return;
    }

    const cell = editor.parentElement;
    if (cell === null) {
      return;
    }

    const updatePlacement = () => {
      const cellRect = cell.getBoundingClientRect();
      const editorWidth = editor.getBoundingClientRect().width;
      const viewportPadding = 16;
      const availableRight = window.innerWidth - cellRect.left - viewportPadding;
      const availableLeft = cellRect.right - viewportPadding;
      const shouldFlip = editorWidth > availableRight && availableLeft >= editorWidth;

      setPlacement(shouldFlip ? "left" : "right");
    };

    updatePlacement();

    const resizeObserver = new ResizeObserver(updatePlacement);
    resizeObserver.observe(editor);
    resizeObserver.observe(cell);
    window.addEventListener("resize", updatePlacement);
    window.addEventListener("scroll", updatePlacement, true);

    return () => {
      resizeObserver.disconnect();
      window.removeEventListener("resize", updatePlacement);
      window.removeEventListener("scroll", updatePlacement, true);
    };
  }, [editorRef]);

  return placement;
}

export function NodeTableFieldOverlay(args: {
  canWriteNode: boolean;
  field: NodeEditorField;
  moduleName: string;
  node: NodeDocument;
  onClose: () => void;
  onOpenLinkedNode?: (node: NodeDocument, moduleName: string, onUpdated?: (node: NodeDocument) => void) => void;
  onSaved: (node: NodeDocument) => Promise<void> | void;
  schema: JsonSchema;
}) {
  const { t } = useI18n();
  const overlayBodyRef = useRef<HTMLDivElement | null>(null);
  const editorNode = useMemo<NodeDocument>(
    () => ({
      [args.field.name]: getValueAtPath(args.node, args.field.path),
    }),
    [args.field, args.node],
  );
  const {
    draft,
    fieldErrors,
    handleBlur,
    handleChange,
    handleChangeAndValidate,
    handleStructureChange,
    isDirty,
    mergeLinkedNode,
    setCustomFieldError,
    setFieldErrors,
    setSubmitApiError,
    setSubmitError,
    submitApiError,
    submitError,
    validateForSubmit,
  } = useNodeDraft({
    fields: [args.field],
    node: editorNode,
    t,
  });

  const saveMutation = useMutation({
    mutationFn: async () => {
      const nextErrors = validateForSubmit();
      if (Object.keys(nextErrors).length > 0) {
        setSubmitError(t("errors.form.invalid"));
        throw new Error("node_validation_failed");
      }

      return updateNode(args.moduleName, String(args.node.id), {
        [args.field.name]: normalizeNodeFieldValue(args.field, getValueAtPath(draft, args.field.path)),
      });
    },
    onSuccess: async (nextNode) => {
      await args.onSaved(nextNode);
    },
    onError: (mutationError) => {
      if (mutationError instanceof ApiError) {
        setSubmitApiError(mutationError);
        const nextErrors = mapApiFieldErrors(mutationError, [args.field], t);
        setFieldErrors(nextErrors);
        setSubmitError(Object.keys(nextErrors).length === 0 ? localizeApiError(mutationError, t) : t("errors.form.invalid"));
        return;
      }

      setSubmitApiError(null);
      if (mutationError instanceof Error && mutationError.message !== "node_validation_failed") {
        setSubmitError(t("errors.api.unknown"));
      }
    },
  });
  const formError = submitError ?? (Object.keys(fieldErrors).length > 0 ? t("errors.form.invalid") : null);

  return (
    <OverlayDialog
      ariaLabel={args.field.label}
      className="overlay-dialog-field"
      onClose={args.onClose}
    >
        <div className="field-overlay-header">
          <strong>{args.field.label}</strong>
          <OverlayCloseButton onClick={args.onClose} />
        </div>
        <div className="field-overlay-body" ref={overlayBodyRef}>
          <NodeFieldEditorSurface
            canWriteNode={args.canWriteNode}
            draft={draft}
            entityName={typeof args.schema.title === "string" ? args.schema.title : ""}
            fieldErrors={fieldErrors}
            fields={[args.field]}
            moduleName={args.moduleName}
            onBlur={handleBlur}
            onChange={handleChange}
            onImmediateChange={handleChangeAndValidate}
            onOpenLinkedNode={(node, moduleName) => {
              args.onOpenLinkedNode?.(node, moduleName, (nextNode) => {
                mergeLinkedNode(nextNode);
              });
            }}
            onPasswordValidationChange={setCustomFieldError}
            onStructureChange={handleStructureChange}
            t={t}
            variant="single-field-overlay"
          />
        </div>
        <div className="field-overlay-footer">
          {formError ? <FormErrorSummary apiError={submitApiError ?? undefined} hasFieldErrors={Object.keys(fieldErrors).length > 0} message={formError} scrollContainerRef={overlayBodyRef} /> : null}
          <div className="field-overlay-actions">
            <Button kind="ghost" onClick={args.onClose} type="button">
              {t("common.cancel")}
            </Button>
            <Button
              disabled={!args.canWriteNode || !args.field.writable || !isDirty || saveMutation.isPending}
              onClick={() => {
                void saveMutation.mutateAsync();
              }}
              type="button"
            >
              {saveMutation.isPending ? t("common.loading") : t("common.apply")}
            </Button>
          </div>
        </div>
    </OverlayDialog>
  );
}

function InlineScalarControl(args: {
  error: string | null;
  field: NodeEditorField;
  onBlur: () => void;
  onChange: (value: boolean | string) => void;
  t: (key: TranslationKey) => string;
  value: boolean | string;
}) {
  const enumOptions = Array.isArray(args.field.fieldSchema.enum)
    ? args.field.fieldSchema.enum
        .filter((item): item is string => typeof item === "string")
        .map((item) => ({ label: item, value: item }))
    : [];

  if (args.field.inputKind === "boolean") {
    return (
      <div className="node-table-inline-control node-table-inline-control-checkbox">
        <CheckboxField
          checked={Boolean(args.value)}
          label={args.field.label}
          onChange={(event) => args.onChange(event.target.checked)}
        />
        {args.error ? <span className="field-error">{args.error}</span> : null}
      </div>
    );
  }

  if (args.field.inputKind === "datetime") {
    const localValue = toUtcDateTimeLocalValue(args.value);

    return (
      <div className="node-table-inline-control">
        <div className="datetime-control">
          <input
            className="field-control"
            onBlur={args.onBlur}
            onChange={(event) => args.onChange(fromUtcDateTimeLocalValue(event.target.value))}
            step={60}
            type="datetime-local"
            value={localValue}
          />
          <span className="datetime-zone">{args.t("common.utc")}</span>
        </div>
        {args.error ? <span className="field-error">{args.error}</span> : null}
      </div>
    );
  }

  if (enumOptions.length > 0 && args.field.inputKind === "string") {
    return (
      <div className="node-table-inline-control">
        <Select
          error={args.error ?? undefined}
          onBlur={args.onBlur}
          onChange={(nextValue) => args.onChange(nextValue)}
          options={enumOptions}
          value={typeof args.value === "string" ? args.value : ""}
        />
      </div>
    );
  }

  return (
    <div className="node-table-inline-control">
      <TextField
        error={args.error ?? undefined}
        label=""
        onBlur={args.onBlur}
        onChange={(event) => args.onChange(event.target.value)}
        type={getInputType(args.field.inputKind)}
        value={typeof args.value === "string" ? args.value : ""}
      />
    </div>
  );
}

function toEditableValue(field: NodeEditorField, value: unknown) {
  if (field.inputKind === "boolean") {
    return Boolean(value);
  }

  if (typeof value === "string") {
    return value;
  }

  if (typeof value === "number") {
    return String(value);
  }

  return "";
}

function normalizeInlineValue(field: NodeEditorField, value: unknown) {
  if (isLinkField(field)) {
    return value;
  }

  if (field.inputKind === "boolean") {
    return Boolean(value);
  }

  if (field.inputKind === "datetime") {
    return normalizeUtcDateTimeValue(value);
  }

  if (field.inputKind === "number" || field.inputKind === "integer") {
    const trimmed = String(value).trim();
    if (trimmed.length === 0) {
      return "";
    }

    return Number.isNaN(Number(trimmed)) ? trimmed : Number(trimmed);
  }

  return value;
}

function isLinkField(field: NodeEditorField) {
  return (field.inputKind === "link" || field.inputKind === "link-array") && field.linkTargetModule !== null;
}

function getInputType(kind: NodeEditorField["inputKind"]) {
  switch (kind) {
    case "date":
      return "date";
    case "number":
    case "integer":
      return "number";
    default:
      return "text";
  }
}
