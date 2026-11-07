import type { ReactNode } from "react";
import { formatDateForDisplay, formatUtcDateTimeForDisplay } from "../../lib/dateTime";
import type { TranslationKey } from "../../locales";
import type { NodeDocument } from "./api";
import type { NodeEditorField } from "./editorSchema";
import { resolveNodeDisplayLabel } from "./presentation";
import { NodeDisplayLabel } from "./NodeDisplayLabel";

type CellArgs = {
  field: NodeEditorField;
  node: NodeDocument;
  onOpenLinkedNode?: (node: NodeDocument, moduleName: string) => void;
  locale: string;
  t: (key: TranslationKey) => string;
  value: unknown;
};

type Presenter = {
  render: (args: CellArgs) => ReactNode;
  supports: (args: CellArgs) => boolean;
};

const PRESENTERS: Presenter[] = [
  {
    supports: ({ field }) => field.semanticType === "SystemPerm",
    render: ({ value, t }) => renderPermissionMatrix(value, t),
  },
  {
    supports: ({ field }) => field.inputKind === "link",
    render: ({ field, onOpenLinkedNode, value }) => renderLinkValue(field, value, onOpenLinkedNode),
  },
  {
    supports: ({ field }) => field.inputKind === "link-array",
    render: ({ field, onOpenLinkedNode, value }) => renderLinkArrayValue(field, value, onOpenLinkedNode),
  },
  {
    supports: ({ field }) => field.inputKind === "boolean",
    render: ({ value, t }) => (
      <span className={`node-table-bool ${value === true ? "is-true" : "is-false"}`.trim()}>
        {value === true ? t("common.true") : t("common.false")}
      </span>
    ),
  },
  {
    supports: ({ field }) => field.semanticType === "Password",
    render: ({ value }) => renderPasswordValue(value),
  },
  {
    supports: ({ field }) => field.inputKind === "string" || field.inputKind === "text" || field.inputKind === "number" || field.inputKind === "integer",
    render: ({ field, value }) => renderTextValue(value, field.inputKind === "number" || field.inputKind === "integer"),
  },
  {
    supports: ({ field }) => field.inputKind === "date",
    render: ({ locale, value }) => renderDateValue(value, locale),
  },
  {
    supports: ({ field }) => field.inputKind === "datetime",
    render: ({ locale, value }) => renderDateTimeValue(value, locale),
  },
  {
    supports: ({ field }) => field.inputKind === "object" && field.semanticType === "Image",
    render: ({ value }) => renderImageValue(value),
  },
  {
    supports: ({ field }) => field.inputKind === "object" && (field.semanticType === "File" || field.semanticType === "Video"),
    render: ({ field, value }) => renderFileLikeValue(field, value),
  },
  {
    supports: ({ field, value }) =>
      field.inputKind === "array-primitive" && Array.isArray(value),
    render: ({ field, locale, value }) => renderPrimitiveArrayValue(field, value, locale),
  },
  {
    supports: ({ field, value }) =>
      field.inputKind === "array-asset" && Array.isArray(value),
    render: ({ field, value }) => renderAssetArrayValue(field, value),
  },
  {
    supports: ({ field, value }) =>
      field.inputKind === "array-object" && Array.isArray(value) && canRenderSingleFieldObjectArray(field),
    render: ({ field, locale, onOpenLinkedNode, value, t }) => renderSingleFieldObjectArray(field, value, locale, t, onOpenLinkedNode),
  },
];

export function renderNodeTableCell(args: {
  field: NodeEditorField | null;
  locale: string;
  node: NodeDocument;
  onOpenLinkedNode?: (node: NodeDocument, moduleName: string) => void;
  t: (key: TranslationKey) => string;
}) {
  if (args.field === null) {
    return null;
  }

  const value = args.node[args.field.name];
  const presenterArgs: CellArgs = {
    field: args.field,
    locale: args.locale,
    node: args.node,
    onOpenLinkedNode: args.onOpenLinkedNode,
    t: args.t,
    value,
  };
  const presenter = PRESENTERS.find((item) => item.supports(presenterArgs));

  if (presenter !== undefined) {
    return presenter.render(presenterArgs);
  }

  return renderFallbackValue(args.field, value);
}
function renderTextValue(value: unknown, isNumeric = false) {
  const text = typeof value === "string" || typeof value === "number"
    ? String(value)
    : "";
  return <span className={`node-table-text ${isNumeric ? "node-table-text-number" : ""}`.trim()}>{text}</span>;
}

function renderPasswordValue(value: unknown) {
  return typeof value === "string" && value.length > 0
    ? <span className="node-table-text">••••••••</span>
    : <span className="node-table-text" />;
}

function renderPermissionMatrix(value: unknown, t: (key: TranslationKey) => string) {
  const subjects = ["owner", "group", "others"] as const;
  const permissions = ["r", "w", "p"] as const;
  return (
    <div aria-label={t("nodes.systemFields.perm")} className="node-table-permission-matrix">
      {permissions.flatMap((permission) => subjects.map((subject) => {
        const enabled = isRecord(value) && isRecord(value[subject]) && value[subject][permission] === true;
        const subjectLabel = t(`permissions.${subject}` as TranslationKey);
        const permissionLabel = t(`permissions.${permission === "r" ? "read" : permission === "w" ? "write" : "populate"}` as TranslationKey);
        return <span aria-label={`${subjectLabel}: ${permissionLabel}`} className={`node-table-permission-cell ${enabled ? "is-enabled" : ""}`.trim()} key={`${subject}.${permission}`} title={`${subjectLabel}: ${permissionLabel}`} />;
      }))}
    </div>
  );
}

function renderDateValue(value: unknown, locale: string) {
  return <span className="node-table-text">{formatDateForDisplay(value, locale)}</span>;
}

function renderDateTimeValue(value: unknown, locale: string) {
  return <span className="node-table-text">{formatUtcDateTimeForDisplay(value, locale)}</span>;
}

function renderLinkValue(field: NodeEditorField, value: unknown, onOpenLinkedNode?: (node: NodeDocument, moduleName: string) => void) {
  let label: ReactNode = "";
  if (isNodeDocument(value)) {
    label = <NodeDisplayLabel moduleName={field.linkTargetModule} node={value} purpose="reference" />;
  } else if (typeof value === "string") {
    label = value;
  }

  return label !== "" ? renderLinkChip({ field, label, node: value, onOpenLinkedNode }) : null;
}

function renderLinkArrayValue(field: NodeEditorField, value: unknown, onOpenLinkedNode?: (node: NodeDocument, moduleName: string) => void) {
  if (!Array.isArray(value) || value.length === 0) {
    return null;
  }

  const items = value.map((item) => ({
    label: isNodeDocument(item)
      ? <NodeDisplayLabel moduleName={field.linkTargetModule} node={item} purpose="reference" />
      : typeof item === "string" ? item : "",
    node: isNodeDocument(item) ? item : null,
    key: isNodeDocument(item) && typeof item.id === "string" ? item.id : typeof item === "string" ? item : "",
  })).filter((item) => item.label !== "");

  if (items.length === 0) {
    return null;
  }

  return (
    <div className="node-table-chip-list">
      {items.map((item, index) => (
        <span className="node-table-chip node-table-chip-link" key={`${item.key}:${index}`}>
          {renderLinkChip({ field, label: item.label, node: item.node, onOpenLinkedNode })}
        </span>
      ))}
    </div>
  );
}

function renderLinkChip(args: {
  field: NodeEditorField;
  label: ReactNode;
  node: unknown;
  onOpenLinkedNode?: (node: NodeDocument, moduleName: string) => void;
}) {
  const node = isNodeDocument(args.node) ? args.node : null;
  const canOpen = node !== null
    && typeof node.id === "string"
    && node.id.length > 0
    && Object.keys(node).some((key) => key !== "id")
    && args.onOpenLinkedNode !== undefined
    && args.field.linkTargetModule !== null;

  return canOpen ? (
    <button
      className="node-table-link"
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        args.onOpenLinkedNode!(node, args.field.linkTargetModule!);
      }}
      type="button"
    >{args.label}</button>
  ) : <span>{args.label}</span>;
}

function renderImageValue(value: unknown) {
  if (!isRecord(value) || typeof value.url !== "string" || value.url.length === 0) {
    return null;
  }

  return (
    <div className="node-table-media node-table-media-image">
      <img alt="" className="node-table-thumb" src={value.url} />
    </div>
  );
}

function renderFileLikeValue(field: NodeEditorField, value: unknown) {
  if (!isRecord(value) || typeof value.url !== "string" || value.url.length === 0) {
    return <span className="node-table-text" />;
  }

  if (field.semanticType === "Video") {
    return (
      <div className="node-table-media">
        <video
          aria-label={extractFileLabel(value.url)}
          className="node-table-thumb"
          muted
          playsInline
          preload="metadata"
          src={value.url}
        />
      </div>
    );
  }

  const label = extractFileLabel(value.url);
  return <span className="node-table-text">{label}</span>;
}

function renderPrimitiveArrayValue(field: NodeEditorField, value: unknown, locale: string) {
  if (!Array.isArray(value) || value.length === 0) {
    return <span className="node-table-text" />;
  }

  const items = value
    .map((item) => field.itemKind === "password"
      ? maskPasswordItem(item)
      : field.itemKind === "datetime"
        ? formatUtcDateTimeForDisplay(item, locale)
        : field.itemKind === "date"
          ? formatDateForDisplay(item, locale)
        : stringifySimpleValue(item))
    .filter((item) => item.length > 0);

  return (
    <div className="node-table-chip-list">
      {items.map((item, index) => <span className="node-table-chip" key={`${item}:${index}`}>{item}</span>)}
    </div>
  );
}

function renderAssetArrayValue(field: NodeEditorField, value: unknown) {
  if (!Array.isArray(value) || value.length === 0) {
    return null;
  }

  if (field.itemSchema?.["x-meta"]?.["semantic-type"] === "Image") {
    const images = value.filter(
      (item): item is Record<string, unknown> => isRecord(item) && typeof item.url === "string" && item.url.length > 0,
    );

    return (
      <div className="node-table-media-list">
        {images.map((item, index) => <img alt="" className="node-table-thumb" key={`${item.url}:${index}`} src={String(item.url)} />)}
      </div>
    );
  }

  if (field.itemSchema?.["x-meta"]?.["semantic-type"] === "Video") {
    const videos = value.filter(
      (item): item is Record<string, unknown> => isRecord(item) && typeof item.url === "string" && item.url.length > 0,
    );

    return (
      <div className="node-table-media-list">
        {videos.map((item, index) => (
          <video
            aria-label={extractFileLabel(String(item.url))}
            className="node-table-thumb"
            key={`${item.url}:${index}`}
            muted
            playsInline
            preload="metadata"
            src={String(item.url)}
          />
        ))}
      </div>
    );
  }

  const urls = value
    .filter((item): item is Record<string, unknown> => isRecord(item) && typeof item.url === "string" && item.url.length > 0)
    .map((item) => extractFileLabel(String(item.url)));

  if (urls.length === 0) {
    return renderJsonValue(value);
  }

  return (
    <div className="node-table-chip-list">
      {urls.map((url, index) => <span className="node-table-chip" key={`${url}:${index}`}>{url}</span>)}
    </div>
  );
}

function renderSingleFieldObjectArray(field: NodeEditorField, value: unknown, locale: string, t: (key: TranslationKey) => string, onOpenLinkedNode?: (node: NodeDocument, moduleName: string) => void) {
  if (!Array.isArray(value) || value.length === 0) {
    return null;
  }

  const child = field.children[0];
  if (child === undefined) {
    return renderJsonValue(value);
  }

  const items = value.map((item) => {
    if (!isRecord(item)) {
      return { label: "", node: null };
    }

    const childValue = item[child.name];
    const linkedNode = child.inputKind === "link" && isNodeDocument(childValue) ? childValue : null;
    const label = describeNestedValue(child, childValue, locale, t);
    return {
      label,
      labelNode: linkedNode === null
        ? label
        : <NodeDisplayLabel moduleName={child.linkTargetModule} node={linkedNode} purpose="reference" />,
      node: linkedNode,
    };
  }).filter((item) => item.label.length > 0);

  return (
    <div className="node-table-chip-list">
      {items.map((item, index) => (
        <span className={`node-table-chip ${child.inputKind === "link" ? "node-table-chip-link" : ""}`.trim()} key={`${item.label}:${index}`}>
          {child.inputKind === "link"
            ? renderLinkChip({ field: child, label: item.labelNode, node: item.node, onOpenLinkedNode })
            : item.labelNode}
        </span>
      ))}
    </div>
  );
}

function describeNestedValue(field: NodeEditorField, value: unknown, locale: string, t: (key: TranslationKey) => string) {
  if (field.semanticType === "Password") {
    return maskPasswordItem(value);
  }

  if (field.inputKind === "link") {
    if (isNodeDocument(value)) {
      return resolveNodeDisplayLabel(value);
    }
    return typeof value === "string" ? value : "";
  }

  if (field.inputKind === "object" && field.semanticType === "Image") {
    if (isRecord(value) && typeof value.url === "string") {
      return extractFileLabel(value.url);
    }
    return "";
  }

  if (field.inputKind === "object" && (field.semanticType === "File" || field.semanticType === "Video")) {
    if (isRecord(value) && typeof value.url === "string") {
      return extractFileLabel(value.url);
    }
    return "";
  }

  if (field.inputKind === "boolean") {
    return value === true ? t("common.true") : t("common.false");
  }

  if (field.inputKind === "datetime") {
    return formatUtcDateTimeForDisplay(value, locale);
  }

  if (field.inputKind === "date") {
    return formatDateForDisplay(value, locale);
  }

  return stringifySimpleValue(value);
}

function renderFallbackValue(field: NodeEditorField, value: unknown) {
  if (field.inputKind === "object") {
    return renderJsonValue(maskPasswordValues(field, value));
  }

  if (field.inputKind === "array-object" || field.inputKind === "array-asset" || field.inputKind === "array-primitive") {
    return renderJsonValue(maskPasswordValues(field, value));
  }

  if (value === null || value === undefined || value === "") {
    return null;
  }

  return <span className="node-table-text">{stringifySimpleValue(value)}</span>;
}

function renderJsonValue(value: unknown) {
  const text = JSON.stringify(value);
  return <span className="node-table-text node-table-json">{text ?? ""}</span>;
}

function canRenderSingleFieldObjectArray(field: NodeEditorField) {
  if (field.children.length !== 1) {
    return false;
  }

  const child = field.children[0];
  if (child === undefined) {
    return false;
  }

  return (
    child.inputKind === "string"
    || child.inputKind === "text"
    || child.inputKind === "number"
    || child.inputKind === "password"
    || child.inputKind === "integer"
    || child.inputKind === "boolean"
    || child.inputKind === "date"
    || child.inputKind === "datetime"
    || child.inputKind === "link"
    || (child.inputKind === "object" && (child.semanticType === "Image" || child.semanticType === "File" || child.semanticType === "Video"))
  );
}

function stringifySimpleValue(value: unknown) {
  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }

  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }

  return "";
}

function maskPasswordItem(value: unknown) {
  return typeof value === "string" && value.length > 0 ? "••••••••" : "";
}

function maskPasswordValues(field: NodeEditorField, value: unknown): unknown {
  if (field.semanticType === "Password") {
    return maskPasswordItem(value);
  }

  if (field.inputKind === "array-primitive" && field.itemKind === "password" && Array.isArray(value)) {
    return value.map(maskPasswordItem);
  }

  if (field.inputKind === "object" && isRecord(value)) {
    return maskPasswordObjectFields(field.children, value);
  }

  if (field.inputKind === "array-object" && Array.isArray(value)) {
    return value.map((item) => isRecord(item) ? maskPasswordObjectFields(field.children, item) : item);
  }

  return value;
}

function maskPasswordObjectFields(fields: NodeEditorField[], value: Record<string, unknown>) {
  const next = { ...value };
  fields.forEach((child) => {
    next[child.name] = maskPasswordValues(child, value[child.name]);
  });
  return next;
}

function extractFileLabel(url: string) {
  const parts = url.split("/");
  const lastPart = parts.at(-1);
  return lastPart && lastPart.length > 0 ? lastPart : url;
}

function isNodeDocument(value: unknown): value is NodeDocument {
  return isRecord(value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
