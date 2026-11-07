import type { TranslationKey } from "../../locales";
import type { NodeEditorField } from "./editorSchema";

type Translate = (key: TranslationKey) => string;

export function buildNodeTableSystemFields(t: Translate): NodeEditorField[] {
  const permissionKeys = { p: "permissions.populate", r: "permissions.read", w: "permissions.write" } as const;
  const subjectKeys = { group: "permissions.group", others: "permissions.others", owner: "permissions.owner" } as const;
  return [
    createField({ inputKind: "string", label: t("nodes.systemFields.id"), name: "id", semanticType: "SystemId" }),
    createField({ inputKind: "datetime", label: t("nodes.systemFields.cdate"), name: "cdate", semanticType: "SystemCdate" }),
    createField({ inputKind: "datetime", label: t("nodes.systemFields.mdate"), name: "mdate", semanticType: "SystemMdate" }),
    createField({ inputKind: "link", label: t("nodes.systemFields.owner"), linkTargetEntities: ["user"], linkTargetModule: "users", name: "owner", semanticType: "SystemOwner", writable: true }),
    createField({ inputKind: "link", label: t("nodes.systemFields.group"), linkTargetEntities: ["group"], linkTargetModule: "users", name: "group", semanticType: "SystemGroup", writable: true }),
    createField({
      children: (["owner", "group", "others"] as const).map((subject) => createField({
        children: (["r", "w", "p"] as const).map((permission) => createField({
          inputKind: "boolean",
          label: t(permissionKeys[permission]),
          name: permission,
          path: ["perm", subject, permission],
          semanticType: "SystemPermission",
        })),
        inputKind: "object",
        label: t(subjectKeys[subject]),
        name: subject,
        path: ["perm", subject],
        semanticType: "SystemPermissionGroup",
      })),
      inputKind: "object",
      label: t("nodes.systemFields.perm"),
      name: "perm",
      semanticType: "SystemPerm",
    }),
  ];
}

function createField(args: Partial<NodeEditorField> & Pick<NodeEditorField, "inputKind" | "label" | "name" | "semanticType">): NodeEditorField {
  return {
    children: args.children ?? [],
    description: "",
    fieldSchema: args.fieldSchema ?? {},
    inputKind: args.inputKind,
    isNullable: false,
    isRequired: false,
    itemKind: null,
    itemSchema: null,
    label: args.label,
    linkTargetEntities: args.linkTargetEntities ?? [],
    linkTargetModule: args.linkTargetModule ?? null,
    name: args.name,
    path: args.path ?? [args.name],
    semanticType: args.semanticType,
    visible: true,
    writable: args.writable ?? false,
  };
}
