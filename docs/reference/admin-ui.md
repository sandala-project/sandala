# Admin UI

Sandala Admin UI is the first-party browser application for managing nodes,
module structure, entity schemas, and personal access tokens. It is designed
for desktop work: the full workspace is supported from 900 px wide, with the
best experience at 1100 px and above.

For task-oriented instructions and screenshots, see [Using the Admin UI](../guides/using-the-admin-ui.md).

## Access and roles

The application signs in through the ordinary password login and uses
Sandala's auth-session cookie. It does not store a password or PAT in browser
storage.

Admin UI access requires an authenticated user with the `admin` or `superuser`
role. An ordinary `all` user sees an access-denied screen, even if that user
can read or edit particular nodes through the REST API.

An `admin` can work with nodes and inspect the structure area in read-only
mode. Only a `superuser` can create, change, or delete modules and entity
schemas. Node controls remain subject to the selected node's ACL and each
field's `write-mode`; a visible UI action is never a substitute for backend
authorization.

The account menu provides sign-out, light and dark themes, and UI language
selection.

## Work areas

The UI has three work areas.

| Area | Purpose |
| --- | --- |
| **Nodes** | Create, inspect, edit, organize, query, and soft-delete nodes. Tree view is hierarchy-oriented; Table view works with one entity at a time. |
| **Entities** | Inspect modules and entity schemas. Superusers can also change module properties, schemas, default permissions, child rules, label templates, and fields. |
| **Settings** | Edit the current user profile and manage personal access tokens. It also links to the user and group tables. |

Tree view loads branches on demand and opens the selected node in a persistent
editor pane. Table view supports incremental loading, configurable columns,
row-density choices, visual and advanced-JSON filtering and sorting, inline
editing where appropriate, and ACL editing.

The UI reads schema structure, semantic types, visibility, write modes, and
node permissions from Sandala. Node forms therefore use specialized controls
for links, assets, nested values, enums, rich text, and passwords. The backend
remains authoritative for validation and authorization. See [Semantic types](semantic-types.md),
[Permissions and ACL](../concepts/permissions-and-acl.md), and [Nodes](rest-api/nodes.md).

## Node editors

Tree view keeps the selected node's form in the right pane; Table view opens
the full form in an overlay. Supported scalar and link cells can be edited
inline. Complex values and `Password` use an overlay editor. Existing nodes
show `id`, `cdate`, and `mdate` as read-only information.

The parent picker allows compatible nodes on which the actor has populate
permission, or the module root when permitted. Other visible branches can
still be expanded, but unavailable targets are disabled. A node and its
descendants cannot be selected as its new parent. ACL changes use a separate
dialog with an option to apply changes to active descendants; see
[Patch node ACL](rest-api/nodes.md#patch-node-acl).

Link controls search the target entity's visible top-level text fields named
`name`, `title`, `caption`, `code`, and `description`, plus `id`. Fields used in
`x-ui.labels.reference` add search paths, including paths through nested Objects,
without replacing that base list. Paths through Arrays or links, missing or
invisible fields, non-text fields, and `Password` fields are skipped.
Search matches the beginning of a value and is case-sensitive.
When a link allows several entities, the control searches each separately and
combines their results, with up to 10 matches per entity. Already selected nodes
are excluded from the suggestions.

Password entry uses two side-by-side masked inputs. They must match before
submission; only the first value is sent. The control never fills in a stored
value. If a non-empty Password value nevertheless reaches a table, the table
shows fixed bullets rather than its characters.

## Visual filters and sorting

The table builders operate on the selected entity. They include visible
user fields, paths through Objects and Arrays of Objects, and relevant system
fields. The filter builder supports nested `and`, `or`, and `not` groups;
sort rules apply in their displayed order. Applying either restarts table
loading from the beginning.

`Password`, `Array<Password>`, and containers containing Password values are
excluded from both visual builders. Safe nested fields of such containers
remain available. This restriction does not hide the corresponding table
columns or forbid these paths in Advanced JSON.

Link conditions select target IDs rather than arbitrary target properties.
Asset fields offer presence and null comparisons rather than comparisons of
descriptor contents. Supported equality controls can pass an empty string or
`null` directly; link controls do not offer a null value. Use `exists` and
logical groups when field absence must be distinguished from a value.
The visual filter offers `perm` paths only to a superuser, following the
backend restriction on client ACL filters.

Advanced JSON uses the ordinary [node query language](rest-api/nodes.md).
Switching back to a visual builder is possible only when it can represent the
JSON without losing structure. Schema visibility and backend query validation
apply in both modes.

## Dates and times

`DateTime` inputs use a native date-and-time control labelled **UTC**. Values
with another offset are converted to UTC for editing; edited values are sent
as RFC 3339 strings ending in `Z`, not in the browser's local timezone.
Opening a form alone does not save a converted value.

Read-only date-time values, including node timestamps and PAT expiry times,
are formatted using the UI locale in UTC. `Date` values represent calendar
dates and are not shifted between timezones.

## Schema editor

The entity editor shows user-defined fields; common node system fields are
not editable schema entries. Dragging reorders fields within the same nesting
level and does not move them into or out of a container.

The fixed descriptor properties inside `Image`, `File`, and `Video` are shown
read-only, without separate visibility or write-mode controls. They cannot
be reordered, including when the descriptor is an Array item.

For `Password` and `Array<Password>`, the required checkbox remains visible
but disabled. Switching a field to either type clears an existing required
flag. The editor also protects the built-in user and group field definitions,
while allowing their descriptions to change; see
[Users and groups](rest-api/users-and-groups.md#built-in-schemas).

The main entity properties include tree and reference label templates. Clearing
a template removes its corresponding `x-ui.labels` key. Default permissions
for new nodes are edited separately from existing nodes' ACL.

## Availability

The standard Sandala application exposes the bundled UI at `/admin/` when a
production UI build is available. It may instead be mounted or hosted
separately by an integrator. The `ADMIN_UI_DIST` configuration setting is
documented in [Configuration](configuration.md).

For deployment instructions and runtime API configuration, see
[Host the admin UI separately](../getting-started/deployment.md#host-the-admin-ui-separately).

Implementation details for contributors, including the route namespace,
client-state boundaries, and testing conventions, are in [Frontend architecture](../development/frontend-architecture.md).
