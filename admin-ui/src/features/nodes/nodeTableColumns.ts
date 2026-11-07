import type { NodeEditorField } from "./editorSchema";

export type NodeTableColumn = {
  defaultWidth: number;
  field: NodeEditorField | null;
  key: string;
  label: string;
  kind: "actions" | "field";
  minWidth: number;
  resizable: boolean;
};

export function buildNodeTableColumns(args: {
  fields: NodeEditorField[];
}) {
  const columns: NodeTableColumn[] = [
    {
      defaultWidth: 80,
      field: null,
      key: "__actions__",
      kind: "actions",
      label: "",
      minWidth: 80,
      resizable: false,
    },
  ];

  args.fields.forEach((field) => {
    columns.push({
      defaultWidth: getDefaultNodeTableColumnWidth(field),
      field,
      key: field.path.join("."),
      kind: "field",
      label: field.label,
      minWidth: getMinNodeTableColumnWidth(field),
      resizable: true,
    });
  });

  return columns;
}

export function buildNodeTableGridTemplateColumns(columns: NodeTableColumn[], columnSizing: Record<string, number>) {
  return columns
    .map((column) => `${resolveNodeTableColumnWidth(column, columnSizing)}px`)
    .join(" ");
}

export function getNodeTableColumnEditMode(field: NodeEditorField | null, canWriteNode: boolean) {
  if (field === null) {
    return "none" as const;
  }

  if (field.semanticType.startsWith("System")) {
    return "none" as const;
  }

  const isInlineEditable =
    field.inputKind === "string"
    || field.inputKind === "number"
    || field.inputKind === "integer"
    || field.inputKind === "boolean"
    || field.inputKind === "date"
    || field.inputKind === "datetime"
    || field.inputKind === "link"
    || field.inputKind === "link-array";

  if (isInlineEditable) {
    if (!field.writable || !canWriteNode) {
      return "none" as const;
    }
    return "inline" as const;
  }

  return field.writable && canWriteNode ? "overlay" as const : "view-overlay" as const;
}

export function resolveNodeTableColumnWidth(column: NodeTableColumn, columnSizing: Record<string, number>) {
  return Math.max(column.minWidth, columnSizing[column.key] ?? column.defaultWidth);
}

export function getDefaultNodeTableColumnSizing(columns: NodeTableColumn[]) {
  return columns.reduce<Record<string, number>>((acc, column) => {
    acc[column.key] = column.defaultWidth;
    return acc;
  }, {});
}

function getDefaultNodeTableColumnWidth(field: NodeEditorField) {
  switch (field.inputKind) {
    case "boolean":
      return 120;
    case "date":
      return 160;
    case "datetime":
      return 190;
    case "number":
    case "integer":
      return 140;
    case "link":
      return 220;
    case "link-array":
      return 260;
    case "array-asset":
      return 220;
    case "object":
      return field.semanticType === "Image" || field.semanticType === "File" || field.semanticType === "Video" ? 220 : 180;
    default:
      return 220;
  }
}

function getMinNodeTableColumnWidth(field: NodeEditorField) {
  switch (field.inputKind) {
    case "boolean":
      return 100;
    case "date":
      return 140;
    case "datetime":
      return 170;
    case "number":
    case "integer":
      return 120;
    default:
      return 160;
  }
}
