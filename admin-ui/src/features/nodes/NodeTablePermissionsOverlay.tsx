import { NodeAclOverlay } from "./NodeAclOverlay";
import type { NodeDocument } from "./api";

export function NodeTablePermissionsOverlay(args: {
  canEdit: boolean;
  moduleName: string;
  node: NodeDocument;
  onClose: () => void;
  onSaved: (node: NodeDocument) => Promise<void> | void;
}) {
  return <NodeAclOverlay canEditGroup={false} canEditOwner={false} canEditPerm={args.canEdit} moduleName={args.moduleName} node={args.node} onClose={args.onClose} onSaved={args.onSaved} visibleField="perm" />;
}
