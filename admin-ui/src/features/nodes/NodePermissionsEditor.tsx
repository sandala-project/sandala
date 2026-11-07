import { CheckboxField } from "../../components/Field";
import type { TranslationKey } from "../../locales";
import type { NodeDraft, PathSegment } from "./useNodeDraft";
import { getValueAtPath } from "./useNodeDraft";

export function NodePermissionsEditor(args: {
  canEdit: boolean;
  draft: NodeDraft;
  onChange: (path: PathSegment[], value: boolean) => void;
  t: (key: TranslationKey) => string;
}) {
  return <div className="node-editor-permissions">
    {(["owner", "group", "others"] as const).map((group) => (
      <div className="permissions-column" key={group}>
        <div className="field-label">{args.t(`permissions.${group}` as TranslationKey)}</div>
        {(["r", "w", "p"] as const).map((permission) => {
          const labelKey = permission === "r" ? "permissions.read" : permission === "w" ? "permissions.write" : "permissions.populate";
          return <CheckboxField
            checked={Boolean(getValueAtPath(args.draft, ["perm", group, permission]))}
            disabled={!args.canEdit}
            key={permission}
            label={args.t(labelKey)}
            onChange={(event) => args.onChange(["perm", group, permission], event.target.checked)}
          />;
        })}
      </div>
    ))}
  </div>;
}
