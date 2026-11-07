# Permissions and ACL

Sandala applies access control in two independent layers:

1. **Node ACL** controls whether an actor may read, write, or populate a
   particular node.
2. **Field modes** control whether a role may see or write an individual field
   inside a node it can otherwise access.

An operation must satisfy both applicable layers. A publicly visible field does
not expose a node that its reader cannot read, and a writable node does not make
a restricted field writable.

## Node ACL

Every node has an `owner`, a `group`, and a `perm` object:

```json
{
  "owner": "8b06138e-d43d-4dba-a185-bb8c61f814c4",
  "group": "6bfaa146-ae0b-4431-9fca-75ba070093b8",
  "perm": {
    "owner": {"r": true, "w": true, "p": true},
    "group": {"r": true, "w": false, "p": false},
    "others": {"r": true, "w": false, "p": false}
  }
}
```

The three `perm` sections select the permission set for one relationship to the
node:

| Section | Used when |
| --- | --- |
| `owner` | The actor's `user_id` equals the node's `owner`. |
| `group` | The actor is not the owner and the node's `group` is in the actor's `groups`. |
| `others` | Neither of the preceding relationships applies, including an anonymous actor. |

This follows Unix permission precedence. Ownership wins over group membership:
an owner uses `perm.owner` even when `perm.group` or `perm.others` would grant
more access.

### Node permissions

| Permission | Effect |
| --- | --- |
| `r` — read | The actor can see and read the node. Without it, the node is absent from normal queries and cannot be fetched by ID. |
| `w` — write | The actor can change the node, subject to field modes. It is also required to delete a node. |
| `p` — populate | The actor can create a direct child in the node or move an existing node directly under it, subject to entity child rules. |

Node ACL is not inherited. Each descendant has its own owner, group, and
permissions. The virtual module root has equivalent `root_owner`, `root_group`,
and `root_perm` settings, but only its `p` permission is meaningful: it controls
creation and moves at the root.

Superusers bypass node ACL. The `admin` role does not: admins are evaluated as
owner, group member, or other just like ordinary authenticated users.

## Field modes

Each user-defined field has `x-meta.visibility-mode` and `x-meta.write-mode`.
They use the same ordered vocabulary:

| Mode | Role allowed by visibility or write mode |
| --- | --- |
| `all` | Any role, including an anonymous actor. |
| `admin` | `admin` and `superuser`. |
| `superuser` | `superuser` only. |
| `none` | No role, including `superuser`. |

Field modes do not replace node ACL. For example, an `all` field is returned
only when the actor can read its node. To patch such a field, a non-superuser
also needs node `w` permission; to create a node containing it, the actor needs
`p` permission on the parent or virtual root.

The two field modes are independent. `visibility-mode: none` prevents reading
the field, while `write-mode: none` prevents submitting it in an ordinary node
write. Neither restriction is bypassed by a superuser.

Nested fields cannot be more broadly visible or writable than their containing
Object or Array. A child field cannot be more accessible than a hidden or
write-restricted container. A visible container may still contain more
restricted child fields.

## How the layers interact

| Operation | Node requirement | Field requirement |
| --- | --- | --- |
| Fetch or query a node | `r` | Each returned field must satisfy its visibility mode. |
| Create a node | `p` on its selected parent or the virtual root | Each submitted field must satisfy its write mode. |
| Patch a node field | `w` on the node being changed | Each submitted field must satisfy its write mode. |
| Move a node | `w` on the node being moved, and `p` on its selected parent or the virtual root | Changed node fields must satisfy their write modes. |
| Delete a subtree | `w` on every active node in the subtree | Not applicable. |

The effective role can therefore produce a deliberately partial document: a
reader may see a node while some fields are omitted. A field that is not visible
cannot be requested explicitly in a projection, filter, or sort expression.

## ACL and links

Link resolution applies the target node's read ACL and the target field's
visibility modes. A resolved Link or LinkArray therefore contains only targets
that the current actor may read and whose entity remains allowed by the link
schema.

This is why a raw stored link ID and a resolved link can differ. The distinction
is important when designing editable Link and LinkArray fields, and is explored
in [Links and resolution](links-and-resolution.md).

## Changing ACL

`owner`, `group`, and `perm` are system access fields, not ordinary
user-defined schema fields. Sandala applies dedicated checks when they change:

- only a superuser can change `owner`;
- a node owner with `w` permission, or a superuser, can change `group` or
  `perm`;
- a non-superuser changing `group` may select only one of their own groups.

The dedicated ACL operation can apply an owner, group, or permission change to
a node alone or recursively to its active descendants. In the recursive case,
the actor needs `w` on every active node affected by the operation. See
[Patch node ACL](../reference/rest-api/nodes.md#patch-node-acl) for the complete
request and response contract.

See [Users and authentication](users-and-authentication.md) for the built-in
user and group identities that supply owners, groups, and roles.
