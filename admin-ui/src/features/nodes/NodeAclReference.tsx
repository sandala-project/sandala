import type { NodeDocument } from "./api";
import { NodeDisplayLabel } from "./NodeDisplayLabel";

export function NodeAclReference(args: { node: NodeDocument | null }) {
  return (
    <span className="node-acl-reference">
      {args.node === null ? "—" : <NodeDisplayLabel moduleName="users" node={args.node} purpose="reference" />}
    </span>
  );
}
