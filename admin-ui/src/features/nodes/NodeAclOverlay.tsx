import { useMutation } from "@tanstack/react-query";
import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Button } from "../../components/Button";
import { CheckboxField } from "../../components/Field";
import { FormErrorSummary } from "../../components/Form";
import { OverlayCloseButton } from "../../components/OverlayCloseButton";
import { OverlayDialog } from "../../components/OverlayDialog";
import { ApiError } from "../../lib/api";
import { localizeApiError } from "../../lib/errors";
import type { TranslationKey } from "../../locales";
import { useI18n } from "../../providers/I18nProvider";
import { getLinkableNodesByIds, patchNodeAcl, type NodeDocument } from "./api";
import { EPHEMERAL_NODE_QUERY_OPTIONS } from "../../lib/queryOptions";
import { NodeLinkSelect } from "./NodeLinkSelect";
import { NodePermissionsEditor } from "./NodePermissionsEditor";
import { NodeAclReference } from "./NodeAclReference";
import { getNodeReferenceId } from "./nodeFieldUtils";
import { mapApiFieldErrors, sanitizePermValue, useNodeDraft } from "./useNodeDraft";

export function NodeAclSummary(args: { draft: NodeDocument; t: (key: TranslationKey) => string }) {
  const ownerId = getNodeReferenceId(args.draft.owner);
  const groupId = getNodeReferenceId(args.draft.group);
  const ownerQuery = useQuery({
    ...EPHEMERAL_NODE_QUERY_OPTIONS,
    enabled: typeof args.draft.owner === "string" && ownerId.length > 0,
    queryKey: ["nodes", "acl-summary-reference", "user", ownerId],
    queryFn: ({ signal }) => getLinkableNodesByIds({ entityNames: ["user"], ids: [ownerId], moduleName: "users", signal }).then((nodes) => nodes[0]),
  });
  const groupQuery = useQuery({
    ...EPHEMERAL_NODE_QUERY_OPTIONS,
    enabled: typeof args.draft.group === "string" && groupId.length > 0,
    queryKey: ["nodes", "acl-summary-reference", "group", groupId],
    queryFn: ({ signal }) => getLinkableNodesByIds({ entityNames: ["group"], ids: [groupId], moduleName: "users", signal }).then((nodes) => nodes[0]),
  });
  return (
    <div className="node-acl-summary">
      <div className="node-acl-summary-links">
        <SummaryValue label={args.t("nodes.systemFields.owner")} node={getResolvedReference(args.draft.owner, ownerQuery.data)} />
        <SummaryValue label={args.t("nodes.systemFields.group")} node={getResolvedReference(args.draft.group, groupQuery.data)} />
      </div>
      <div className="node-acl-summary-perm">
        <div aria-label={args.t("nodes.systemFields.perm")} className="node-acl-summary-permissions">
          {(["owner", "group", "others"] as const).map((subject) => (
            <div className="node-acl-summary-permission-column" key={subject}>
              <div className="field-label">{args.t(`permissions.${subject}` as TranslationKey)}</div>
              {(["r", "w", "p"] as const).map((permission) => (
                <div className="node-acl-summary-permission" key={permission}>
                  <span className={`node-acl-summary-permission-box ${isPermissionEnabled(args.draft.perm, subject, permission) ? "is-enabled" : ""}`.trim()} />
                  <span>{args.t(permission === "r" ? "permissions.read" : permission === "w" ? "permissions.write" : "permissions.populate")}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function isPermissionEnabled(value: unknown, subject: "owner" | "group" | "others", permission: "r" | "w" | "p") {
  if (!isRecord(value) || !isRecord(value[subject])) return false;
  return value[subject][permission] === true;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function NodeAclOverlay(args: {
  canEditGroup: boolean;
  canEditOwner: boolean;
  canEditPerm: boolean;
  moduleName: string;
  node: NodeDocument;
  onOpenLinkedNode?: (node: NodeDocument, moduleName: string, onUpdated?: (node: NodeDocument) => void) => void;
  onClose: () => void;
  onSaved: (node: NodeDocument) => Promise<void> | void;
  visibleField?: "owner" | "group" | "perm";
}) {
  const { t } = useI18n();
  const [recursive, setRecursive] = useState(false);
  const overlayBodyRef = useRef<HTMLDivElement | null>(null);
  const { draft, fieldErrors, handleChange, isDirty, mergeLinkedNode, setFieldErrors, setSubmitApiError, setSubmitError, submitApiError, submitError } = useNodeDraft({ fields: [], node: args.node, t });
  const visible = args.visibleField;
  const saveMutation = useMutation({
    mutationFn: () => {
      const node: Record<string, unknown> = {};
      if (visible === undefined || visible === "owner") node.owner = getNodeReferenceId(draft.owner) || null;
      if (visible === undefined || visible === "group") node.group = getNodeReferenceId(draft.group) || null;
      if (visible === undefined || visible === "perm") node.perm = sanitizePermValue(draft.perm);
      return patchNodeAcl({ moduleName: args.moduleName, nodeId: String(args.node.id), node, recursive });
    },
    onSuccess: async () => {
      const nextNode: NodeDocument = {
        ...args.node,
        owner: draft.owner as NodeDocument["owner"],
        group: draft.group as NodeDocument["group"],
        perm: draft.perm,
      };
      args.onClose();
      await args.onSaved(nextNode);
    },
    onError: (error) => {
      if (error instanceof ApiError) {
        setSubmitApiError(error);
        const errors = mapApiFieldErrors(error, [], t);
        setFieldErrors(errors);
        setSubmitError(Object.keys(errors).length === 0 ? localizeApiError(error, t) : t("errors.form.invalid"));
      } else if (error instanceof Error) {
        setSubmitApiError(null);
        setSubmitError(t("errors.api.unknown"));
      }
    },
  });
  const title = visible === undefined ? t("pages.nodes.editor.access") : t(`nodes.systemFields.${visible}` as TranslationKey);
  const formError = submitError ?? (Object.keys(fieldErrors).length > 0 ? t("errors.form.invalid") : null);

  return (
    <OverlayDialog ariaLabel={title} className="overlay-dialog-field overlay-dialog-node-acl" onClose={args.onClose}>
      <div className="field-overlay-header"><strong>{title}</strong><OverlayCloseButton onClick={args.onClose} /></div>
      <div className="field-overlay-body" ref={overlayBodyRef}>
        {visible === undefined || visible === "owner" ? <NodeLinkSelect canWrite={args.canEditOwner} error={fieldErrors.owner} label={t("nodes.systemFields.owner")} mode="single" onBlur={() => undefined} onChange={(value) => handleChange(["owner"], value)} onOpenNode={(node, moduleName) => args.onOpenLinkedNode?.(node, moduleName, mergeLinkedNode)} placeholder={t("pages.nodes.editor.linkPlaceholder")} resolveSelectedReferences targetEntities={["user"]} targetModule="users" value={draft.owner} /> : null}
        {visible === undefined || visible === "group" ? <NodeLinkSelect canWrite={args.canEditGroup} error={fieldErrors.group} label={t("nodes.systemFields.group")} mode="single" onBlur={() => undefined} onChange={(value) => handleChange(["group"], value)} onOpenNode={(node, moduleName) => args.onOpenLinkedNode?.(node, moduleName, mergeLinkedNode)} placeholder={t("pages.nodes.editor.linkPlaceholder")} resolveSelectedReferences targetEntities={["group"]} targetModule="users" value={draft.group} /> : null}
        {visible === undefined || visible === "perm" ? <NodePermissionsEditor canEdit={args.canEditPerm} draft={draft} onChange={handleChange} t={t} /> : null}
        <CheckboxField checked={recursive} disabled={!canEditVisible(args)} label={t("pages.nodes.editor.aclRecursive")} onChange={(event) => setRecursive(event.target.checked)} />
      </div>
      <div className="field-overlay-footer">
        {formError ? <FormErrorSummary apiError={submitApiError ?? undefined} hasFieldErrors={Object.keys(fieldErrors).length > 0} message={formError} scrollContainerRef={overlayBodyRef} /> : null}
        <div className="field-overlay-actions">
          <Button kind="ghost" onClick={args.onClose} type="button">{t("common.cancel")}</Button>
          <Button disabled={(!isDirty && !recursive) || saveMutation.isPending || !canEditVisible(args)} onClick={() => { void saveMutation.mutateAsync(); }} type="button">{saveMutation.isPending ? t("common.loading") : t("common.apply")}</Button>
        </div>
      </div>
    </OverlayDialog>
  );
}

function canEditVisible(args: { canEditGroup: boolean; canEditOwner: boolean; canEditPerm: boolean; visibleField?: "owner" | "group" | "perm" }) {
  if (args.visibleField === "owner") return args.canEditOwner;
  if (args.visibleField === "group") return args.canEditGroup;
  if (args.visibleField === "perm") return args.canEditPerm;
  return args.canEditOwner || args.canEditGroup || args.canEditPerm;
}

function getResolvedReference(value: unknown, resolved?: NodeDocument) {
  if (resolved !== undefined) return resolved;
  if (value !== null && typeof value === "object") return value as NodeDocument;
  return null;
}

function SummaryValue(args: { label: string; node: NodeDocument | null }) {
  return <div className="node-acl-summary-value"><span className="field-label">{args.label}</span><NodeAclReference node={args.node} /></div>;
}
