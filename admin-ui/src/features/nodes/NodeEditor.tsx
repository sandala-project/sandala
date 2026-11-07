import { useMutation } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { FormErrorSummary, FormSection } from "../../components/Form";
import { ApiError } from "../../lib/api";
import { localizeApiError } from "../../lib/errors";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import type { JsonSchema } from "../entities/api";
import { createNode, type NodeDocument, updateNode } from "./api";
import { buildCreatePayload } from "./nodeCreate";
import { canWriteNodeDocument, getNodeAclEditCapabilities } from "./nodeAccess";
import { buildNodeEditorFields } from "./editorSchema";
import { NodeFieldEditorSurface } from "./NodeFieldEditorSurface";
import { NodeMetadataSummary } from "./NodeMetadataSummary";
import { NodeParentPicker } from "./NodeParentPicker";
import { NodeAclOverlay, NodeAclSummary } from "./NodeAclOverlay";
import { NodeEditorOverlay } from "./NodeEditorOverlay";
import {
  buildPatchPayload,
  mapApiFieldErrors,
  useNodeDraft,
} from "./useNodeDraft";

type NodeEditorProps = {
  mode?: "create" | "edit";
  moduleName: string;
  node: NodeDocument;
  onSaved: (node: NodeDocument) => void;
  onAclUpdated?: (node: NodeDocument) => void;
  onUpdated?: (node: NodeDocument) => void;
  parentPicker?: {
    canSelectRoot: boolean;
    excludeNodeId?: string;
    parentEntityNames: string[];
  };
  schema: JsonSchema;
  variant?: "full" | "embedded";
};

export function NodeEditor({ mode = "edit", moduleName, node, onAclUpdated, onSaved, onUpdated, parentPicker, schema, variant = "full" }: NodeEditorProps) {
  const auth = useAuth();
  const { locale, t } = useI18n();
  const fields = useMemo(() => buildNodeEditorFields(schema, auth.user), [auth.user, schema]);
  const {
    draft,
    fieldErrors,
    handleBlur,
    handleChange,
    handleChangeAndValidate,
    handleStructureChange,
    isDirty,
    mergeLinkedNode,
    mergeValues,
    replaceWithNode,
    setFieldErrors,
    setCustomFieldError,
    setSubmitApiError,
    setSubmitError,
    submitApiError,
    submitError,
    validateForSubmit,
  } = useNodeDraft({ fields, node, t });
  const [isAclOpen, setIsAclOpen] = useState(false);
  const editorContentRef = useRef<HTMLDivElement | null>(null);
  const [linkedNode, setLinkedNode] = useState<{
    moduleName: string;
    nodeId: string;
    onUpdated?: (node: NodeDocument) => void;
  } | null>(null);

  const isCreateMode = mode === "create";
  const canWriteNode = useMemo(
    () => (isCreateMode ? true : canWriteNodeDocument(node, auth.user)),
    [auth.user, isCreateMode, node],
  );
  const isSuperuser = auth.user?.role === "superuser" || Boolean(auth.user?.superuser);
  const aclCapabilities = getNodeAclEditCapabilities(node, auth.user);
  const canEditOwner = isSuperuser;
  const canEditGroup = isCreateMode ? isSuperuser : aclCapabilities.canEditGroup;
  const canEditPerm = isCreateMode ? isSuperuser : aclCapabilities.canEditPerm;
  const aclNode = useMemo<NodeDocument>(() => ({
    ...node,
    owner: draft.owner as NodeDocument["owner"],
    group: draft.group as NodeDocument["group"],
    perm: draft.perm,
  }), [draft.group, draft.owner, draft.perm, node]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      const nextErrors = validateForSubmit();
      if (isCreateMode && parentPicker !== undefined && draft.parent === undefined) {
        setFieldErrors((current) => ({ ...current, parent: t("pages.nodes.parentPicker.required") }));
        setSubmitError(t("errors.form.invalid"));
        throw new Error("parent_required");
      }
      if (Object.keys(nextErrors).length > 0) {
        setSubmitError(t("errors.form.invalid"));
        throw new Error("node_validation_failed");
      }

      if (isCreateMode) {
        const payload = buildCreatePayload({
          canEditGroup,
          canEditOwner,
          canEditPerm,
          draft,
          fields,
        });

        return createNode(moduleName, payload);
      }

      const payload = buildPatchPayload({
        current: node,
        draft,
        fields,
      });

      const currentParentId = typeof node.parent === "string" && node.parent.length > 0 ? node.parent : null;
      const draftParentId = typeof draft.parent === "string" && draft.parent.length > 0 ? draft.parent : null;
      if (variant === "full" && currentParentId !== draftParentId) {
        payload.parent = draftParentId;
      }

      if (Object.keys(payload).length === 0) {
        throw new Error("empty_patch");
      }

      return updateNode(moduleName, String(node.id), payload);
    },
    onSuccess: (nextNode) => {
      replaceWithNode(nextNode);
      onSaved(nextNode);
    },
    onError: (error) => {
      if (error instanceof ApiError) {
        setSubmitApiError(error);
        const nextErrors = mapApiFieldErrors(error, fields, t);
        setFieldErrors(nextErrors);
        setSubmitError(Object.keys(nextErrors).length === 0 ? localizeApiError(error, t) : t("errors.form.invalid"));
        return;
      }

      setSubmitApiError(null);
      if (error instanceof Error && error.message !== "node_validation_failed" && error.message !== "parent_required" && error.message !== "empty_patch") {
        setSubmitError(t("errors.api.unknown"));
      }
    },
  });

  const entityName = typeof schema.title === "string" ? schema.title : "";
  const formError = submitError ?? (Object.keys(fieldErrors).length > 0 ? t("errors.form.invalid") : null);

  return (
    <div className="editor-layout">
      <div className="editor-content" ref={editorContentRef}>
        <Card tone="muted">
          {!isCreateMode ? <NodeMetadataSummary locale={locale} node={node} t={t} /> : null}
          <div className="node-editor-fields">
            {parentPicker !== undefined ? (
              <NodeParentPicker
                canSelectRoot={parentPicker.canSelectRoot}
                disabled={!canWriteNode}
                excludeNodeId={parentPicker.excludeNodeId}
                error={fieldErrors.parent}
                moduleName={moduleName}
                onChange={(parentId) => handleChange(["parent"], parentId)}
                parentEntityNames={parentPicker.parentEntityNames}
                value={typeof draft.parent === "string" ? draft.parent : draft.parent === null ? null : isCreateMode ? undefined : null}
              />
            ) : null}
            <NodeFieldEditorSurface
              canWriteNode={canWriteNode}
              draft={draft}
              entityName={entityName}
              fieldErrors={fieldErrors}
              fields={fields}
              moduleName={moduleName}
              onBlur={handleBlur}
              onChange={handleChange}
              onImmediateChange={handleChangeAndValidate}
              onStructureChange={handleStructureChange}
              onOpenLinkedNode={(linked, linkedModuleName, onUpdated) => {
                if (typeof linked.id === "string" && linked.id.length > 0) {
                  setLinkedNode({ moduleName: linkedModuleName, nodeId: linked.id, onUpdated });
                }
              }}
              onPasswordValidationChange={setCustomFieldError}
              t={t}
              variant="bare"
            />
          </div>
        </Card>

        {!isCreateMode && variant === "full" ? (
          <FormSection title={<strong>{t("pages.nodes.editor.access")}</strong>}>
            <NodeAclSummary draft={draft} t={t} />
            <div className="node-acl-summary-actions node-structured-actions">
              <Button kind="ghost" onClick={() => setIsAclOpen(true)} type="button">
                {t("common.edit")}
              </Button>
            </div>
          </FormSection>
        ) : null}
      </div>

      <div className="editor-action-bar">
        {formError ? <FormErrorSummary apiError={submitApiError ?? undefined} hasFieldErrors={Object.keys(fieldErrors).length > 0} message={formError} scrollContainerRef={editorContentRef} /> : null}
        <Button
          disabled={saveMutation.isPending || (!isCreateMode && !isDirty)}
          onClick={() => {
            void saveMutation.mutateAsync();
          }}
          type="button"
        >
          {saveMutation.isPending
            ? isCreateMode
              ? t("pages.nodes.editor.creating")
              : t("pages.nodes.editor.saving")
            : isCreateMode
              ? t("pages.nodes.editor.create")
              : t("pages.nodes.editor.save")}
        </Button>
      </div>
      {!isCreateMode && isAclOpen ? (
        <NodeAclOverlay
          canEditGroup={aclCapabilities.canEditGroup}
          canEditOwner={aclCapabilities.canEditOwner}
          canEditPerm={aclCapabilities.canEditPerm}
          moduleName={moduleName}
          node={aclNode}
          onOpenLinkedNode={(linked, linkedModuleName, onUpdated) => {
            if (typeof linked.id === "string" && linked.id.length > 0) {
              setLinkedNode({ moduleName: linkedModuleName, nodeId: linked.id, onUpdated });
            }
          }}
          onClose={() => setIsAclOpen(false)}
          onSaved={(nextNode) => {
            mergeValues({ owner: nextNode.owner ?? null, group: nextNode.group ?? null, perm: nextNode.perm ?? null });
            onAclUpdated?.(nextNode);
            onUpdated?.(nextNode);
          }}
        />
      ) : null}
      {linkedNode !== null && linkedNode.moduleName.length > 0 ? (
        <NodeEditorOverlay
          moduleName={linkedNode.moduleName}
          nodeId={linkedNode.nodeId}
          onClose={() => setLinkedNode(null)}
          onUpdated={(nextNode) => {
            linkedNode.onUpdated?.(nextNode);
            mergeLinkedNode(nextNode);
            onUpdated?.(nextNode);
          }}
        />
      ) : null}
    </div>
  );
}
