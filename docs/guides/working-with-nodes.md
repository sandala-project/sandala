# Working with nodes

Nodes are the records that carry the data described by an entity schema. This
guide covers their ordinary lifecycle: create a node, place it in a tree when
the module uses one, read it, change its data or ACL, and soft-delete it.

Examples use the `library` module and assume that authentication and the
`SANDALA_URL` and `COOKIE_JAR` shell variables are already set up as in the
[Quickstart](../getting-started/quickstart.md). The complete HTTP contract,
including every error code, is in [Nodes](../reference/rest-api/nodes.md).

## Before you write

The selected entity schema controls the user-defined fields that a node may
contain. It also controls the default ACL, allowed child entity types, field
visibility, and field write access. If an integration does not already know
the schema, an `admin` or `superuser` can retrieve it:

```bash
curl --fail-with-body --silent --show-error \
  --cookie "$COOKIE_JAR" \
  "$SANDALA_URL/modules/library/entities/Book/"
```

An ordinary user's permission to work with nodes does not grant access to the
entity-schema endpoint.

The node's position and access fields are system fields. Sandala manages `id`,
`ancestors`, `depth`, `deleted`, `cdate`, and `mdate`; clients do not use an
ordinary patch to change them. `parent` is also a system field, but changing it
with an ordinary PATCH moves the node. `entity` is selected at creation and
remains fixed for the node's lifetime. `owner`, `group`, and `perm` use a
dedicated ACL operation after creation.

Every write is evaluated against two access layers:

- the actor needs the applicable node permission (`p` to create under a
  location, `w` to edit or delete a node);
- every submitted user-defined field must allow the actor through its
  `write-mode`.

An `admin` does not bypass node ACL. A superuser does, except that a field with
`write-mode: none` remains unwritable for every actor.

## Create a node

Send a complete initial node document inside a `node` wrapper. This creates a
root Book node:

```bash
curl --fail-with-body --silent --show-error \
  --cookie "$COOKIE_JAR" \
  --header 'Content-Type: application/json' \
  --data '{
    "node": {
      "entity": "Book",
      "title": "A Wizard of Earthsea",
      "year": 1968,
      "parent": null
    }
  }' \
  "$SANDALA_URL/nodes/library/"
```

The response has status `201 Created` and wraps the stored record in `node`.
If no `id` is supplied, Sandala generates a UUID. It fills in the hierarchy
fields from `parent`, assigns the current actor as `owner` and their primary
group as `group`, and copies the entity's default ACL into `perm`.

An authenticated non-superuser can explicitly supply only their own ID as the
owner and one of their groups as the group. A superuser may select another
active user or group. A caller-supplied `perm` is allowed at creation when it
passes the effective schema and the other create checks.

The created entity must be permitted at the selected location:

- at `parent: null`, the module's `root_children_entities` and virtual-root
  populate permission apply;
- at a concrete parent, that parent must be active, belong to the same module,
  permit the child entity in `x-meta.children.entities`, and grant the actor
  populate (`p`) permission.

Omit `parent` when the node should be a root node. A module does not need to
use its tree at all: independent root nodes of multiple entities can be used
as related tables.

### Create a child

To create below an existing node, send its ID as `parent`:

```json
{
  "node": {
    "entity": "Book",
    "title": "Tehanu",
    "parent": "b0313e66-29a7-40b4-a235-e55f99f66826"
  }
}
```

The endpoint remains `POST /nodes/library/`. Sandala derives the child's
`depth` and `ancestors`; do not calculate or submit them yourself.

User-defined Link and LinkArray values are stored as UUIDs. Their targets need
not currently exist, so a write can deliberately contain a dangling reference.
See [Links and resolution](../concepts/links-and-resolution.md) for the
difference between stored and resolved values.

## Read a node

Read a known node by ID:

```bash
curl --fail-with-body --silent --show-error \
  --cookie "$COOKIE_JAR" \
  "$SANDALA_URL/nodes/library/b0313e66-29a7-40b4-a235-e55f99f66826/"
```

Without an explicit projection, this endpoint returns every visible field and
resolves visible user-defined links one level deep, as well as `owner` and
`group`. This is convenient for displaying an individual record. `parent` and
`ancestors` remain IDs.

Use an explicit projection when a client needs a smaller shape or the raw IDs
stored in links. The canonical raw projection is `["*"]` as JSON:

```bash
curl --fail-with-body --silent --show-error --get \
  --cookie "$COOKIE_JAR" \
  --data-urlencode 'project=["*"]' \
  "$SANDALA_URL/nodes/library/b0313e66-29a7-40b4-a235-e55f99f66826/"
```

The shell request above serializes the JSON value `["*"]` safely into the
URL. It returns all visible fields while leaving Link and LinkArray values as
their stored UUIDs. An explicit field projection can also resolve only the
needed part of a target, for example `["title", "author.name"]`.

Read permission and field visibility still apply. A node that is missing,
soft-deleted, or unreadable returns the same `404 not_found` response, so an
API client must not infer which of those conditions occurred.

## Change node data

Use ordinary PATCH for user-defined fields and, when needed, `parent`:

```bash
curl --fail-with-body --silent --show-error \
  --request PATCH \
  --cookie "$COOKIE_JAR" \
  --header 'Content-Type: application/json' \
  --data '{
    "node": {
      "title": "A Wizard of Earthsea (revised)",
      "year": 1968
    }
  }' \
  "$SANDALA_URL/nodes/library/b0313e66-29a7-40b4-a235-e55f99f66826/"
```

PATCH merges the supplied top-level fields into the current node. It does not
recursively merge an Object field: if `metadata` is supplied, it replaces the
entire stored `metadata` object. Read the current value and include every child
that should remain before replacing an Object.

An ordinary PATCH ignores attempts to set managed system fields and rejects
changes to `owner`, `group`, or `perm`. It validates the resulting complete
node against its current schema, so an otherwise small patch can fail if it
makes a required value absent or violates a constraint.

### Move a node

Changing `parent` in the same PATCH moves a node. Supply the ID of a different
node as the destination:

```json
{
  "node": {
    "parent": "69d73158-fb89-44bc-a258-02d113915a70"
  }
}
```

Moving to `parent: null` returns the node to the module root. The actor needs
`w` on the moved node and `p` at the new location. The destination must be an
active node in the same module and permit the moving entity as a child; moving
under the node's own descendant is rejected. Sandala recalculates tree fields
for the moved node and all of its descendants, including soft-deleted ones.

### Change links without losing information

A resolved response is a view for the current actor, not necessarily the full
stored reference value: unreadable targets disappear from a resolved LinkArray
and make a resolved Link `null`. Do not treat a resolved value as a lossless
replacement value for an editable link field.

Sandala protects active targets hidden only by read ACL in common PATCH cases.
For a LinkArray that is not below an Array, it retains omitted hidden IDs while
allowing readable IDs to be removed intentionally. For a single Link or a link
nested within an Array, the submitted values must retain the protected IDs.
An update that omits a required protected reference returns
`link_patch_acl_hidden_references_missing` and identifies the relevant field.

When that happens, request the raw node with `project=["*"]`, preserve every
stored ID needed in the affected reference branch, and retry the PATCH. This
protection intentionally does not retain deleted, dangling, or no-longer-
allowed targets. See [Protection of ACL-hidden
links](../reference/rest-api/nodes.md#protection-of-acl-hidden-links) for the
complete preservation rules and container-removal behavior.

## Change ownership or permissions

`owner`, `group`, and `perm` are changed only through the ACL endpoint. For
example, this changes a node's group and ACL recursively through its active
subtree:

```bash
curl --fail-with-body --silent --show-error \
  --request PATCH \
  --cookie "$COOKIE_JAR" \
  --header 'Content-Type: application/json' \
  --data '{
    "node": {
      "group": "6bfaa146-ae0b-4431-9fca-75ba070093b8",
      "perm": {
        "owner": {"r": true, "w": true, "p": true},
        "group": {"r": true, "w": false, "p": false},
        "others": {"r": false, "w": false, "p": false}
      }
    },
    "recursive": true
  }' \
  "$SANDALA_URL/nodes/library/b0313e66-29a7-40b4-a235-e55f99f66826/acl/"
```

`recursive` defaults to `false`. With `true`, Sandala changes the path node
and every active descendant. The actor needs `w` on every affected node;
failure on one node prevents the operation. Nodes that already have the target
ACL are left unchanged.

Only a superuser can change `owner`. A node owner with `w` permission, or a
superuser, can change `group` and `perm`; a non-superuser owner may choose
only a group they belong to. The replacement owner and group must be active
`users/user` and `users/group` nodes. See [Permissions and ACL](../concepts/permissions-and-acl.md)
for the access model and [Users and groups](../reference/rest-api/users-and-groups.md)
for the built-in identities.

## Delete a subtree

Delete is a soft delete and always applies to the selected node and its active
descendants:

```bash
curl --fail-with-body --silent --show-error \
  --request DELETE \
  --cookie "$COOKIE_JAR" \
  "$SANDALA_URL/nodes/library/b0313e66-29a7-40b4-a235-e55f99f66826/"
```

The result reports the number of nodes marked deleted:

```json
{
  "deleted_count": 3
}
```

The actor needs `w` on the selected node and every active descendant. If any
required check fails, no node in the subtree is deleted. Deleted nodes remain
in storage but are excluded from normal reads, queries, and link resolution.
Their IDs remain non-reusable, and stored references to them may remain but no
longer resolve.

## Use the Admin UI for the same operations

The Admin UI applies the same API contract. In Tree view, select a node to
edit it, use the parent selector to move it, and use the node actions to create
children or soft-delete a subtree. In Table view, work with independent entity
records and inline-edit suitable scalar and link fields. The available controls
reflect the current schema and actor, but the server remains the final access
check.

See [Using the Admin UI](using-the-admin-ui.md) for the interface workflow.
See [Querying nodes](querying-nodes.md) for filtering, sorting, projections,
and pagination for node collections.
