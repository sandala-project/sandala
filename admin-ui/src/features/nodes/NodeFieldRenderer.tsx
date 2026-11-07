import { lazy, Suspense, useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "../../components/Button";
import { CheckboxField, TextAreaField, TextField } from "../../components/Field";
import { IconButton } from "../../components/IconButton";
import { Select } from "../../components/Select";
import type { TranslationKey } from "../../locales";
import type { NodeDocument } from "./api";
import type { NodeEditorField } from "./editorSchema";
import { uploadImageAsset } from "./api";
import { AssetArrayItemControl, FileFieldControl, ImageFieldControl, VideoFieldControl } from "./NodeAssetFieldControls";
import { NodeLinkSelect } from "./NodeLinkSelect";
import {
  isAtomicAssetSemanticType,
  getSemanticTypeFromSchema,
} from "./nodeFieldUtils";
import { fromUtcDateTimeLocalValue, toUtcDateTimeLocalValue } from "../../lib/dateTime";
import { getValueAtPath, type NodeDraft, type PathSegment } from "./useNodeDraft";

const RichTextField = lazy(async () => ({
  default: (await import("../../components/RichTextField")).RichTextField,
}));

type ScalarInputKind = Exclude<
  NodeEditorField["inputKind"],
  "array-asset" | "array-object" | "array-primitive" | "link" | "link-array" | "object" | "unknown"
>;

type ScalarFieldDescriptor = {
  checkboxLabel: string;
  fieldPath: string;
  kind: ScalarInputKind;
  label: string;
  password: boolean;
  richText: boolean;
};

export function NodeFieldRenderer({
  canWriteNode,
  draft,
  entityName,
  field,
  fieldErrors,
  moduleName,
  onBlur,
  onChange,
  onImmediateChange,
  onOpenLinkedNode,
  onPasswordValidationChange,
  onStructureChange,
  path,
  presentation = "default",
  t,
}: {
  canWriteNode: boolean;
  draft: NodeDraft;
  entityName: string;
  field: NodeEditorField;
  fieldErrors: Record<string, string>;
  moduleName: string;
  onBlur: (path: PathSegment[]) => void;
  onChange: (path: PathSegment[], value: unknown) => void;
  onImmediateChange: (path: PathSegment[], value: unknown) => void;
  onOpenLinkedNode?: (node: NodeDocument, moduleName: string, onUpdated?: (node: NodeDocument) => void) => void;
  onPasswordValidationChange: (path: PathSegment[], message: string | null) => void;
  onStructureChange: (path: PathSegment[], value: unknown) => void;
  path: PathSegment[];
  presentation?: "default" | "single-field-root";
  t: (key: TranslationKey) => string;
}) {
  const value = getValueAtPath(draft, path);
  const fieldPathKey = toPathKey(path);
  const canWrite = canWriteNode && field.writable;
  const helperText = getHelperText(field);
  const isSingleFieldRoot = presentation === "single-field-root";

  if (field.semanticType === "Image") {
    return (
      <ImageFieldControl
        canWrite={canWrite}
        entityName={entityName}
        error={fieldErrors[fieldPathKey]}
        field={field}
        flat={isSingleFieldRoot}
        helperText={helperText}
        hideLabel={isSingleFieldRoot}
        moduleName={moduleName}
        onChange={(nextValue) => onImmediateChange(path, nextValue)}
        value={value}
        t={t}
      />
    );
  }

  if (field.semanticType === "File") {
    return (
      <FileFieldControl
        canWrite={canWrite}
        entityName={entityName}
        error={fieldErrors[fieldPathKey]}
        field={field}
        flat={isSingleFieldRoot}
        helperText={helperText}
        hideLabel={isSingleFieldRoot}
        moduleName={moduleName}
        onChange={(nextValue) => onImmediateChange(path, nextValue)}
        value={value}
        t={t}
      />
    );
  }

  if (field.semanticType === "Video") {
    return (
      <VideoFieldControl
        canWrite={canWrite}
        entityName={entityName}
        error={fieldErrors[fieldPathKey]}
        field={field}
        flat={isSingleFieldRoot}
        helperText={helperText}
        hideLabel={isSingleFieldRoot}
        moduleName={moduleName}
        onChange={(nextValue) => onImmediateChange(path, nextValue)}
        value={value}
        t={t}
      />
    );
  }

  if (field.inputKind === "link" && field.linkTargetModule !== null) {
    return (
      <NodeLinkSelect
        canWrite={canWrite}
        error={fieldErrors[fieldPathKey]}
        hideLabel={isSingleFieldRoot}
        label={field.label}
        mode="single"
        onBlur={() => onBlur(path)}
        onChange={(nextValue) => onImmediateChange(path, nextValue)}
        onOpenNode={onOpenLinkedNode}
        placeholder={t("pages.nodes.editor.linkPlaceholder")}
        targetEntities={field.linkTargetEntities}
        targetModule={field.linkTargetModule}
        value={value}
      />
    );
  }

  if (field.inputKind === "link-array" && field.linkTargetModule !== null) {
    return (
      <NodeLinkSelect
        canWrite={canWrite}
        error={fieldErrors[fieldPathKey]}
        hideLabel={isSingleFieldRoot}
        label={field.label}
        mode="multiple"
        onBlur={() => onBlur(path)}
        onChange={(nextValue) => onImmediateChange(path, nextValue)}
        onOpenNode={onOpenLinkedNode}
        placeholder={t("pages.nodes.editor.linkPlaceholder")}
        targetEntities={field.linkTargetEntities}
        targetModule={field.linkTargetModule}
        value={value}
      />
    );
  }

  if (field.inputKind === "object") {
    return (
      <div className={`node-field-block ${isSingleFieldRoot ? "node-field-block-flat" : ""}`.trim()} data-field-path={fieldPathKey}>
        {!isSingleFieldRoot ? <div className="field-label">{field.label}</div> : null}
        <div className="node-structured-control">
          {helperText ? <div className="node-structured-helper">{helperText}</div> : null}
          {fieldErrors[fieldPathKey] ? <div className="field-error">{fieldErrors[fieldPathKey]}</div> : null}
          <div className="node-field-children">
            {field.children.map((child) => (
              <NodeFieldRenderer
                canWriteNode={canWrite}
                draft={draft}
                entityName={entityName}
                field={child}
                fieldErrors={fieldErrors}
                moduleName={moduleName}
                onBlur={onBlur}
                  onChange={onChange}
                onImmediateChange={onImmediateChange}
                onOpenLinkedNode={onOpenLinkedNode}
                onPasswordValidationChange={onPasswordValidationChange}
                onStructureChange={onStructureChange}
                path={[...path, child.name]}
                key={`${fieldPathKey}.${child.name}`}
                t={t}
              />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (field.inputKind === "array-object") {
    const items = Array.isArray(value) ? value : [];

    return (
      <StructuredCollectionField
        addItemLabel={t("pages.nodes.editor.addItem")}
        canWrite={canWrite}
        error={fieldErrors[fieldPathKey]}
        flat={isSingleFieldRoot}
        helperText={helperText}
        items={items}
        label={field.label}
        onAdd={() => {
          onStructureChange(path, [...items, createEmptyArrayObjectItem(field)]);
        }}
        renderItem={(_item, index, removeItem, itemKey) => (
          <div className="node-array-item" key={itemKey}>
            <div className="node-array-item-header">
              <strong>#{index + 1}</strong>
              {canWrite ? <RemoveArrayItemButton onClick={removeItem} t={t} /> : null}
            </div>
            <div className="node-field-children">
              {field.children.map((child) => (
                <NodeFieldRenderer
                  canWriteNode={canWrite}
                  draft={draft}
                  entityName={entityName}
                  field={child}
                  fieldErrors={fieldErrors}
                  moduleName={moduleName}
                  onBlur={onBlur}
                  onChange={onChange}
                  onImmediateChange={onImmediateChange}
                  onOpenLinkedNode={onOpenLinkedNode}
                  onPasswordValidationChange={onPasswordValidationChange}
                  onStructureChange={onStructureChange}
                  path={[...path, index, child.name]}
                  key={`${fieldPathKey}.${index}.${child.name}`}
                  t={t}
                />
              ))}
            </div>
          </div>
        )}
        removeItemAt={(index) => {
          onStructureChange(path, items.filter((__, itemIndex) => itemIndex !== index));
        }}
      />
    );
  }

  if (field.inputKind === "array-asset") {
    const items = Array.isArray(value) ? value : [];

    return (
      <StructuredCollectionField
        addItemLabel={t("pages.nodes.editor.addItem")}
        canWrite={canWrite}
        error={fieldErrors[fieldPathKey]}
        flat={isSingleFieldRoot}
        helperText={helperText}
        items={items}
        label={field.label}
        onAdd={() => {
          onStructureChange(path, [...items, undefined]);
        }}
        renderItem={(item, index, removeItem, itemKey) => (
          <div className="node-array-item" key={itemKey}>
            <div className="node-array-item-header">
              <strong>#{index + 1}</strong>
              {canWrite ? <RemoveArrayItemButton onClick={removeItem} t={t} /> : null}
            </div>
            <AssetArrayItemControl
              canWrite={canWrite}
              entityName={entityName}
              error={fieldErrors[toPathKey([...path, index])]}
              field={field}
              moduleName={moduleName}
              onBlur={() => onBlur([...path, index])}
              onChange={(nextValue) => onImmediateChange([...path, index], nextValue)}
              t={t}
              value={item}
            />
          </div>
        )}
        removeItemAt={(index) => {
          onStructureChange(path, items.filter((__, itemIndex) => itemIndex !== index));
        }}
      />
    );
  }

  if (field.inputKind === "array-primitive") {
    const items = Array.isArray(value) ? value : [];

    return (
      <StructuredCollectionField
        addItemLabel={t("pages.nodes.editor.addItem")}
        canWrite={canWrite}
        error={fieldErrors[fieldPathKey]}
        flat={isSingleFieldRoot}
        helperText={helperText}
        items={items}
        label={field.label}
        onAdd={() => {
          onStructureChange(path, [...items, createEmptyPrimitiveValue(field.itemKind)]);
        }}
        renderItem={(item, index, removeItem, itemKey) => (
          <div className="node-array-item node-array-item-inline" key={itemKey}>
            <ScalarFieldControl
              canWrite={canWrite}
              descriptor={buildArrayItemScalarDescriptor(field)}
              entityName={entityName}
              enumOptions={getItemStringEnumOptions(field)}
              error={fieldErrors[toPathKey([...path, index])]}
              hideLabel
              onBlur={() => onBlur([...path, index])}
              onChange={(nextValue) => onChange([...path, index], nextValue)}
              moduleName={moduleName}
              onPasswordValidationChange={(message) => onPasswordValidationChange([...path, index], message)}
              t={t}
              value={item}
            />
            {canWrite ? <RemoveArrayItemButton onClick={removeItem} t={t} /> : null}
          </div>
        )}
        removeItemAt={(index) => {
          onStructureChange(path, items.filter((__, itemIndex) => itemIndex !== index));
        }}
      />
    );
  }

  return (
    <ScalarFieldControl
      canWrite={canWrite}
      descriptor={buildScalarFieldDescriptor(field)}
      entityName={entityName}
      enumOptions={getFieldStringEnumOptions(field)}
      error={fieldErrors[fieldPathKey]}
      hideLabel={isSingleFieldRoot}
      onBlur={() => onBlur(path)}
      onChange={(nextValue) => onChange(path, nextValue)}
      moduleName={moduleName}
      onPasswordValidationChange={(message) => onPasswordValidationChange(path, message)}
      t={t}
      value={value}
    />
  );
}

function StructuredCollectionField({
  addItemLabel,
  canWrite,
  error,
  flat = false,
  helperText,
  items,
  label,
  onAdd,
  removeItemAt,
  renderItem,
}: {
  addItemLabel: string;
  canWrite: boolean;
  error?: string;
  flat?: boolean;
  helperText: string;
  items: unknown[];
  label: string;
  onAdd: () => void;
  removeItemAt: (index: number) => void;
  renderItem: (item: unknown, index: number, removeItem: () => void, itemKey: string) => ReactNode;
}) {
  const [itemKeys, setItemKeys] = useState(() => createCollectionKeys(items.length));

  useEffect(() => {
    setItemKeys((current) => {
      if (current.length === items.length) {
        return current;
      }

      if (current.length < items.length) {
        return [...current, ...createCollectionKeys(items.length - current.length)];
      }

      return current.slice(0, items.length);
    });
  }, [items.length]);

  return (
    <div className={`node-field-block ${flat ? "node-field-block-flat" : ""}`.trim()}>
      {!flat ? <div className="field-label">{label}</div> : null}
      <div className="node-structured-control">
        {helperText ? <div className="node-structured-helper">{helperText}</div> : null}
        {error ? <div className="field-error">{error}</div> : null}
        <div className="node-array-list">
          {items.map((item, index) =>
            renderItem(
              item,
              index,
              () => {
                setItemKeys((current) => current.filter((_, itemIndex) => itemIndex !== index));
                removeItemAt(index);
              },
              itemKeys[index] ?? `item-${index}`,
            ),
          )}
        </div>
        {canWrite ? (
          <div className="node-structured-actions">
            <Button
              kind="ghost"
              onClick={() => {
                setItemKeys((current) => [...current, ...createCollectionKeys(1)]);
                onAdd();
              }}
              type="button"
            >
              {addItemLabel}
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

let collectionKeyCounter = 0;

function createCollectionKeys(count: number) {
  return Array.from({ length: count }, () => `item-${collectionKeyCounter++}`);
}

function RemoveArrayItemButton({ onClick, t }: { onClick: () => void; t: (key: TranslationKey) => string }) {
  const label = t("pages.nodes.editor.removeItem");

  return <IconButton icon="trash" label={label} onClick={onClick} size="regular" />;
}

function ScalarFieldControl({
  canWrite,
  descriptor,
  entityName,
  enumOptions = [],
  error,
  hideLabel = false,
  onBlur,
  onChange,
  moduleName,
  onPasswordValidationChange,
  t,
  value,
}: {
  canWrite: boolean;
  descriptor: ScalarFieldDescriptor;
  entityName: string;
  enumOptions?: { label: string; value: string }[];
  error?: string;
  hideLabel?: boolean;
  onBlur: () => void;
  onChange: (value: unknown) => void;
  moduleName: string;
  onPasswordValidationChange: (message: string | null) => void;
  t: (key: TranslationKey) => string;
  value: unknown;
}) {
  if (descriptor.password) {
    return (
      <PasswordFieldControl
        canWrite={canWrite}
        descriptor={descriptor}
        error={error}
        hideLabel={hideLabel}
        onBlur={onBlur}
        onChange={onChange}
        onValidationChange={onPasswordValidationChange}
        t={t}
        value={value}
      />
    );
  }

  if (descriptor.richText) {
    return (
      <Suspense
        fallback={(
          <TextAreaField
            error={error}
            label={hideLabel ? "" : descriptor.label}
            onBlur={onBlur}
            onChange={(event) => onChange(event.target.value)}
            readOnly={!canWrite}
            rows={6}
            value={formatScalarValue(value)}
          />
        )}
      >
        <RichTextField
          canWrite={canWrite}
          error={error}
          hideLabel={hideLabel}
          label={descriptor.label}
          onBlur={onBlur}
          onChange={onChange}
          onImageUpload={canWrite ? (file) => uploadImageAsset({ entityName, fieldPath: descriptor.fieldPath, file, moduleName }) : undefined}
          t={t}
          value={value}
        />
      </Suspense>
    );
  }

  if (descriptor.kind === "boolean") {
    return (
      <div className="node-checkbox-row">
        {!hideLabel ? <div className="field-label">{descriptor.label}</div> : null}
        <CheckboxField
          checked={Boolean(value)}
          disabled={!canWrite}
          label={hideLabel ? "" : descriptor.checkboxLabel}
          onChange={(event) => onChange(event.target.checked)}
        />
        {error ? <span className="field-error">{error}</span> : null}
      </div>
    );
  }

  if (descriptor.kind === "datetime") {
    const localValue = toUtcDateTimeLocalValue(value);

    return (
      <label className="field">
        {!hideLabel ? <span className="field-label">{descriptor.label}</span> : null}
        <div className="datetime-control">
          <input
            className={["field-control", !canWrite ? "is-readonly" : ""].filter(Boolean).join(" ")}
            onBlur={onBlur}
            onChange={(event) => onChange(fromUtcDateTimeLocalValue(event.target.value))}
            onMouseDown={(event) => {
              if (!canWrite) {
                event.preventDefault();
              }
            }}
            readOnly={!canWrite}
            step={60}
            tabIndex={!canWrite ? -1 : undefined}
            type="datetime-local"
            value={localValue}
          />
          <span className="datetime-zone">{t("common.utc")}</span>
        </div>
        {error ? <span className="field-error">{error}</span> : null}
      </label>
    );
  }

  if (descriptor.kind === "string" && enumOptions.length > 0) {
    return (
      <Select
        disabled={!canWrite}
        error={error}
        label={hideLabel ? undefined : descriptor.label}
        onBlur={onBlur}
        onChange={onChange}
        options={enumOptions}
        value={typeof value === "string" ? value : ""}
      />
    );
  }

  if (descriptor.kind === "text") {
    return (
      <TextAreaField
        error={error}
        label={hideLabel ? "" : descriptor.label}
        onBlur={onBlur}
        onChange={(event) => onChange(event.target.value)}
        readOnly={!canWrite}
        rows={6}
        value={formatScalarValue(value)}
      />
    );
  }

  return (
    <TextField
      error={error}
      label={hideLabel ? "" : descriptor.label}
      onBlur={onBlur}
      onChange={(event) => onChange(event.target.value)}
      readOnly={!canWrite}
      type={getInputType(descriptor.kind)}
      value={formatScalarValue(value)}
    />
  );
}

function PasswordFieldControl({
  canWrite,
  descriptor,
  error,
  hideLabel,
  onBlur,
  onChange,
  onValidationChange,
  t,
  value,
}: {
  canWrite: boolean;
  descriptor: ScalarFieldDescriptor;
  error?: string;
  hideLabel: boolean;
  onBlur: () => void;
  onChange: (value: string) => void;
  onValidationChange: (message: string | null) => void;
  t: (key: TranslationKey) => string;
  value: unknown;
}) {
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const passwordRef = useRef(password);
  const previousValueRef = useRef(value);
  const mismatchMessage = t("pages.nodes.editor.validation.passwordMismatch");
  const mismatch = password !== confirmation;

  useEffect(() => {
    passwordRef.current = password;
  }, [password]);

  useEffect(() => {
    onValidationChange(mismatch ? mismatchMessage : null);
  }, [mismatch, mismatchMessage, onValidationChange]);

  useEffect(() => {
    if (previousValueRef.current === value) {
      return;
    }
    previousValueRef.current = value;
    if (typeof value === "string" && value === passwordRef.current) {
      return;
    }
    setPassword("");
    setConfirmation("");
  }, [onValidationChange, value]);

  useEffect(() => () => onValidationChange(null), [onValidationChange]);

  function synchronize(nextPassword: string, nextConfirmation: string) {
    if (nextPassword !== nextConfirmation) {
      onValidationChange(mismatchMessage);
      return;
    }
    onValidationChange(null);
    onChange(nextPassword);
  }

  return (
    <div className={`node-password-field ${hideLabel ? "node-password-field-compact" : ""}`.trim()}>
      {!hideLabel ? <div className="field-label">{descriptor.label}</div> : null}
      <div className="node-password-inputs">
        <TextField
          autoComplete="new-password"
          label={t("pages.nodes.editor.password.value")}
          onBlur={onBlur}
          onChange={(event) => {
            const nextPassword = event.target.value;
            setPassword(nextPassword);
            synchronize(nextPassword, confirmation);
          }}
          readOnly={!canWrite}
          type="password"
          value={password}
        />
        <TextField
          autoComplete="new-password"
          error={mismatch ? mismatchMessage : error}
          label={t("pages.nodes.editor.password.confirmation")}
          onBlur={onBlur}
          onChange={(event) => {
            const nextConfirmation = event.target.value;
            setConfirmation(nextConfirmation);
            synchronize(password, nextConfirmation);
          }}
          readOnly={!canWrite}
          type="password"
          value={confirmation}
        />
      </div>
    </div>
  );
}

function getHelperText(field: NodeEditorField) {
  const description = field.description.trim();
  const label = field.label.trim();

  if (description.length === 0 || description === label) {
    return "";
  }

  return description;
}

function buildScalarFieldDescriptor(field: NodeEditorField): ScalarFieldDescriptor {
  if (!isScalarInputKind(field.inputKind)) {
    throw new Error(`Field '${field.name}' is not scalar`);
  }

  return {
    checkboxLabel: field.description || field.label,
    fieldPath: field.path.join("."),
    kind: field.inputKind,
    label: field.label,
    password: field.semanticType === "Password",
    richText: field.semanticType === "RichText",
  };
}

function buildArrayItemScalarDescriptor(field: NodeEditorField): ScalarFieldDescriptor {
  if (!isScalarInputKind(field.itemKind)) {
    throw new Error(`Field '${field.name}' does not have scalar array items`);
  }

  return {
    checkboxLabel: field.label,
    fieldPath: field.path.join("."),
    kind: field.itemKind,
    label: field.label,
    password: getSemanticTypeFromSchema(field.itemSchema) === "Password",
    richText: getSemanticTypeFromSchema(field.itemSchema) === "RichText",
  };
}

function getFieldStringEnumOptions(field: NodeEditorField) {
  if (field.inputKind !== "string") {
    return [];
  }

  return mapStringEnumOptions(field.fieldSchema.enum);
}

function getItemStringEnumOptions(field: NodeEditorField) {
  if (field.itemKind !== "string") {
    return [];
  }

  return mapStringEnumOptions(field.itemSchema?.enum);
}

function mapStringEnumOptions(enumValues: unknown) {
  return Array.isArray(enumValues)
    ? enumValues
        .filter((item): item is string => typeof item === "string")
        .map((item) => ({ label: item, value: item }))
    : [];
}

function isScalarInputKind(kind: NodeEditorField["inputKind"] | NodeEditorField["itemKind"]): kind is ScalarInputKind {
  return kind === "boolean" || kind === "date" || kind === "datetime" || kind === "integer" || kind === "number" || kind === "password" || kind === "string" || kind === "text";
}

function createEmptyArrayObjectItem(field: NodeEditorField) {
  const item: Record<string, unknown> = {};

  field.children.forEach((child) => {
    if (child.inputKind === "boolean") {
      item[child.name] = false;
      return;
    }
    if (child.inputKind === "array-primitive" || child.inputKind === "array-object" || child.inputKind === "array-asset") {
      item[child.name] = [];
      return;
    }
    if (child.inputKind === "object") {
      if (isAtomicAssetSemanticType(child.semanticType)) {
        item[child.name] = undefined;
        return;
      }
      item[child.name] = {};
      return;
    }
    item[child.name] = undefined;
  });

  return item;
}

function createEmptyPrimitiveValue(kind: string | null) {
  if (kind === "boolean") {
    return false;
  }
  return "";
}

function getInputType(kind: string) {
  if (kind === "date") {
    return "date";
  }
  return "text";
}

function formatScalarValue(value: unknown) {
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number") {
    return String(value);
  }
  return "";
}

function toPathKey(path: PathSegment[]) {
  return path.join(".");
}
