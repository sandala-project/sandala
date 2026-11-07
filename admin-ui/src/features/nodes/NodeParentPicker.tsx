import { useMemo } from "react";
import { useAuth } from "../../providers/AuthProvider";
import { useI18n } from "../../providers/I18nProvider";
import type { NodeDocument } from "./api";
import { NodeTreePicker } from "./NodeTreePicker";
import { canPopulateNodeDocument } from "./treeCapabilities";

export function NodeParentPicker(args: {
  canSelectRoot: boolean;
  disabled?: boolean;
  error?: string;
  excludeNodeId?: string;
  moduleName: string;
  onChange: (parentId: string | null) => void;
  parentEntityNames: string[];
  value: string | null | undefined;
}) {
  const auth = useAuth();
  const { t } = useI18n();
  const eligibleEntities = useMemo(() => new Set(args.parentEntityNames), [args.parentEntityNames]);

  function isNodeSelectable(node: NodeDocument) {
    const nodeId = typeof node.id === "string" ? node.id : "";
    const isExcluded = args.excludeNodeId !== undefined && (
      nodeId === args.excludeNodeId || node.ancestors?.includes(args.excludeNodeId) === true
    );

    return !isExcluded && typeof node.entity === "string" && eligibleEntities.has(node.entity) && canPopulateNodeDocument(node, auth.user);
  }

  return <NodeTreePicker
    disabled={args.disabled}
    emptyLabel={t("pages.nodes.parentPicker.empty")}
    error={args.error}
    isNodeSelectable={isNodeSelectable}
    label={t("nodes.systemFields.parent")}
    moduleName={args.moduleName}
    onChange={args.onChange}
    placeholder={t("pages.nodes.parentPicker.placeholder")}
    rootOption={args.canSelectRoot ? {
      isSelectable: true,
      label: t("pages.nodes.parentPicker.root"),
      value: null,
    } : undefined}
    toggleLabel={t("pages.nodes.parentPicker.toggle")}
    value={args.value}
  />;
}
