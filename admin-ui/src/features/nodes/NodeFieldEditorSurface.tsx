import { EmptyState } from "../../components/EmptyState";
import { FormSection } from "../../components/Form";
import type { TranslationKey } from "../../locales";
import type { NodeDocument } from "./api";
import type { NodeEditorField } from "./editorSchema";
import { NodeFieldRenderer } from "./NodeFieldRenderer";
import type { NodeDraft, PathSegment } from "./useNodeDraft";

export function NodeFieldEditorSurface(args: {
  canWriteNode: boolean;
  draft: NodeDraft;
  entityName: string;
  fieldErrors: Record<string, string>;
  fields: NodeEditorField[];
  moduleName: string;
  onBlur: (path: PathSegment[]) => void;
  onChange: (path: PathSegment[], value: unknown) => void;
  onImmediateChange: (path: PathSegment[], value: unknown) => void;
  onOpenLinkedNode?: (node: NodeDocument, moduleName: string, onUpdated?: (node: NodeDocument) => void) => void;
  onPasswordValidationChange: (path: PathSegment[], message: string | null) => void;
  onStructureChange: (path: PathSegment[], value: unknown) => void;
  t: (key: TranslationKey) => string;
  title?: string;
  variant?: "bare" | "default" | "single-field-overlay";
}) {
  const content = args.fields.length === 0 ? (
    <EmptyState
      description={args.t("pages.nodes.editor.empty.description")}
      title={args.t("pages.nodes.editor.empty.title")}
    />
  ) : (
    <div className={`node-editor-fields ${args.variant === "single-field-overlay" ? "node-editor-fields-single" : ""}`.trim()}>
      {args.fields.map((field) => (
        <NodeFieldRenderer
          canWriteNode={args.canWriteNode}
          draft={args.draft}
          entityName={args.entityName}
          field={field}
          fieldErrors={args.fieldErrors}
          moduleName={args.moduleName}
          onBlur={args.onBlur}
          onChange={args.onChange}
          onImmediateChange={args.onImmediateChange}
          onOpenLinkedNode={args.onOpenLinkedNode}
          onPasswordValidationChange={args.onPasswordValidationChange}
          onStructureChange={args.onStructureChange}
          path={field.path}
          presentation={args.variant === "single-field-overlay" ? "single-field-root" : "default"}
          key={field.path.join(".")}
          t={args.t}
        />
      ))}
    </div>
  );

  if (args.variant === "bare" || args.variant === "single-field-overlay") {
    return content;
  }

  return <FormSection title={<strong>{args.title ?? args.t("pages.nodes.editor.fields")}</strong>}>{content}</FormSection>;
}
