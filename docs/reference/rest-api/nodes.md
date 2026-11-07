# Nodes

Nodes are the records stored in a module's tree. Their entity schema determines
user-defined fields; Sandala maintains the common system fields described in
[Entity schemas](entity-schemas.md). Node reads and writes use node ACL and
field visibility/write modes together. See [Permissions and ACL](../../concepts/permissions-and-acl.md)
for that model.

All paths on this page are below `/api/v1/`.

## Access model

Node endpoints accept an anonymous request or an authenticated actor. A read
returns only active nodes (`deleted: false`) that the actor may read, and only
fields visible to that actor. A node that exists but is unreadable is reported
as not found; an ACL-hidden linked target is omitted during resolution.

Integrators may impose additional read restrictions and response-field
exclusions through query hooks. These can also affect linked targets and can
apply to superusers.
Output-only field exclusions are distinct from schema visibility: they do not
by themselves prohibit filtering or sorting by the excluded fields.

Creating or changing a node additionally requires the relevant node ACL
permission and field `write-mode`. A normal create usually needs an actor so
Sandala can assign `owner` and `group`; anonymous registration through the
built-in user-registration flow is a deliberate exception.

`superuser` bypasses node ACL, but does not bypass a field's
`visibility-mode: none` or `write-mode: none`.

## Reading and querying nodes

`GET /nodes/{module}/{id}/` reads one known node. The two POST query endpoints
read collections with the same query language. The entity-scoped endpoint fixes
an entity in its path and, when no projection is supplied, provides a more
helpful default resolution.

### Query parameters

`project`, `filter`, `sort`, `limit`, and `offset` make up a node query.

| Parameter | Type | Default | Meaning |
| --- | --- | --- | --- |
| `project` | non-empty array of strings, or `"*"` | endpoint-dependent; see below | Fields to return and links to resolve. |
| `filter` | object | `{}` | Conditions that select nodes. |
| `sort` | object | deterministic internal order | Ordered sort paths and directions. |
| `limit` | positive integer or `null` | no limit | Maximum number of returned nodes. |
| `offset` | non-negative integer | `0` | Number of matching nodes to skip. |

`project`, `filter`, and `sort` use dot paths through objects, arrays, and
resolved links where their schemas permit it. A path must be visible to the
current actor at every segment. Explicitly requesting, filtering, or sorting
by an invisible field returns `400` with `error: "query_validation_failed"`.
Array paths address item fields without an index: use `editions.publisher.name`,
not `editions.0.publisher.name`. Numeric array indexes are not supported.

### Projection and resolution

`project` has two jobs: selecting response fields and asking Sandala to resolve
stored link IDs into node objects.

The default depends on the read endpoint. This table applies only when
`project` is omitted and describes the resolution requested by that default.
Filter and sort paths can request further resolution, as explained below.

| Endpoint | Default fields | Default link resolution |
| --- | --- | --- |
| `POST /nodes/{module}/query/` | `["*"]` | None; links remain stored IDs unless another query path resolves them. |
| `GET /nodes/{module}/{id}/` | All visible fields. | All visible user-defined links at any nesting depth, plus `owner` and `group`, resolve one level and include all visible target fields. Links inside those targets, and the source node's `parent` and `ancestors`, remain IDs. |
| `POST /nodes/{module}/entity/{entity}/query/` | The same default as Get one node. | The same one-level resolution as Get one node. |

- `["*"]` returns all visible fields, recursively through ordinary objects
  and arrays. It does not itself request resolution of `Link` or `LinkArray`.
- For every read endpoint, `"*"` and `["*"]` are equivalent root wildcard
  projections. The single-node GET endpoint also accepts `project=*` as a URL
  shorthand.
- A field path such as `name` returns that field only. Selecting a link field
  itself, such as `author`, does not request its resolution.
- A path that enters a link, such as `author.name`, resolves `author` and
  returns its `name` field.
- `author.*` resolves `author` and returns all visible fields of that target.
  It does not itself request resolution of that target's own links.

Within a projection path, `*` may appear only as its final complete segment;
`author.*.name` is invalid.

For example:

```json
{
  "project": ["title", "author.name", "publisher.*"]
}
```

returns `title`, a resolved `author` with `name`, and a resolved `publisher`
with all of its visible fields. Fields used only in `filter` or `sort` do not
appear in the response unless they fall within a selected container or wildcard.

Paths in `project`, `filter`, and `sort` jointly determine which links resolve.
For example, `project: ["author"]` with
`filter: {"author.name": "Ursula K. Le Guin"}` returns a resolved `author`,
not its stored ID. The same applies to links included by `["*"]`: a wildcard
does not undo resolution requested elsewhere in the query.

Sandala resolves only active targets that match `x-meta.link` and that the
actor may read, subject to any read restrictions added by query hooks. A non-null
`Link` with no matching target becomes `null`; a resolved `LinkArray` omits
unmatched target IDs and becomes `[]` if none match. The order of resolved
`LinkArray` targets is not guaranteed. This is why a resolved read is not
necessarily a lossless representation of the stored link values.

A narrow projection, such as `author.name`, can omit a null or empty parent
field (`author`) instead of returning that field's value. Select the whole
parent field, for example with `author.*`, when its presence matters.

System fields `parent`, `ancestors`, `owner`, and `group` can be addressed as
links too. `parent` targets any entity in the same module; `ancestors` is a
multi-link to those entities; `owner` targets `users/user`; and `group` targets
`users/group`.

### Compatibility across entity schemas

A general query can consider nodes of several entities at once. The relevant
schema set is all entity schemas in the module unless a root-level `entity`
filter narrows it with `eq` or `in`. Sandala validates every segment of a path
used by `project`, `filter`, or `sort` against that whole relevant set before
running the query.

A field may be absent from some of those schemas. Where it is present, however,
the path must be compatible: a path that enters a reference requires the same
reference kind (`Link` or `LinkArray`) and a compatible target module; every
such field must also be visible to the actor. Incompatible field kinds,
reference target modules, or visibility produce `400` with
`error: "query_validation_failed"` rather than a query with an arbitrary
interpretation.

The distinction is intentional for a terminal path. A projection, filter, or
sort on `author` itself may span entities where `author` is a link in one
schema and a scalar in another, or where the links target different modules.
It does not require compatible link targets while the field remains
unresolved. Once a path enters the field, such as `author.name` or `author.*`,
those incompatibilities are rejected. When compatible links allow different
target entities, resolution still respects each source field's own allowed
list.

### Narrowing query scope and work

When a client knows the entity or entities it needs, put that condition at the
top level of `filter`:

```json
{
  "filter": {
    "entity": { "in": ["Book", "Magazine"] },
    "published": true
  },
  "project": ["title", "author.name"]
}
```

This narrows the schemas considered for path compatibility and link resolution.
It can also reduce the number of nodes that Sandala needs to process before
resolving links. For the same reason, keep selective conditions on direct
scalar fields or Arrays of scalar items at the top level of the implicit AND
where practical, rather than only inside a nested logical expression or
behind a link path.

Early filtering does not replace the complete filter or change its meaning.
Entity-scope narrowing also affects schema compatibility checks, however:
moving an entity condition into a logical group can broaden the schemas
considered and expose otherwise irrelevant schema or visibility conflicts.

### Early filter narrowing

When a query needs one or more link lookups, Sandala can apply some filter
conditions before those lookups. This reduces the number of source nodes that
need link-resolution work. Active-node and read-ACL restrictions apply
regardless of whether user conditions qualify for early narrowing.

A user condition is also eligible for early narrowing when all of these are
true:

- it is a direct field condition at the root of `filter`, or a direct field
  condition in an item of the root `and` array;
- its path contains no dot;
- in every schema in the current entity scope that defines the field, it is
  a scalar or an `Array` of scalar items, after unwrapping nullable forms;
- it uses a valid filter expression.

The particular valid operator does not matter: `eq`, ranges, `in`, `regex`,
and the other documented operators are eligible when the preceding conditions
hold. Eligibility depends on the field schema, not the operand: `Object`,
`File`, `Image`, `Video`, arrays of those types, `Link`, and `LinkArray` are
not eligible, even for an `exists` or `size` condition. Conditions inside
`or` or `not`, conditions deeper inside a logical group, and dotted paths such
as `author.name` are not eligible either. The complete filter is still
evaluated after resolution.

Entity scope is a separate optimization. Only a root-level `entity` condition
using `eq` or `in` narrows the schemas used for path compatibility and lookup
planning. A direct entity condition in an item of the root `and` array can be
evaluated early, but does not narrow that schema scope. An entity condition in
`or`, `not`, or a deeper logical group does neither.

### Filtering

A filter is an object whose field values are either shorthand equality values
or an operator object:

```json
{
  "title": "A Wizard of Earthsea",
  "year": { "gte": 1968, "lt": 1970 },
  "tags": { "in": ["fantasy", "classic"] }
}
```

The available operators are:

| Operator | Matches when | Example |
| --- | --- | --- |
| `eq` | The value equals the operand. | `{ "year": { "eq": 1968 } }` |
| `neq` | The value does not equal the operand. | `{ "status": { "neq": "draft" } }` |
| `gt` | The value is greater than the operand. | `{ "year": { "gt": 2000 } }` |
| `gte` | The value is greater than or equal to the operand. | `{ "year": { "gte": 2000 } }` |
| `lt` | The value is less than the operand. | `{ "year": { "lt": 2000 } }` |
| `lte` | The value is less than or equal to the operand. | `{ "year": { "lte": 2000 } }` |
| `in` | The value equals any member of the operand array. | `{ "language": { "in": ["en", "ru"] } }` |
| `nin` | The value equals no member of the operand array. | `{ "language": { "nin": ["en", "ru"] } }` |
| `exists` | The field is present (`true`) or absent (`false`). | `{ "subtitle": { "exists": true } }` |
| `size` | The field is an array with exactly this many elements. | `{ "authors": { "size": 2 } }` |
| `regex` | A string value matches the regular-expression pattern. | `{ "title": { "regex": "^The " } }` |

`eq` has the shorthand form `{ "year": 1968 }`. The matching behavior for
arrays, including `eq`, `in`, and `nin`, follows MongoDB query semantics.
`in` and `nin` require array operands; `exists` requires a Boolean; `size`
requires a non-negative integer, not a Boolean; and `regex` requires a string.
Use an explicit `eq` operator when comparing a whole object, since an object
directly beneath a field name is interpreted as an operator map.

Value comparisons on a whole object or array, and sorting by such a container,
are rejected if its stored descendants include fields hidden from the actor.
This prevents inferring hidden values through the parent. `exists` and `size`
remain available when the container itself is visible, since they do not
inspect its contents.

Multiple top-level conditions are combined with AND. Logical groups use
non-empty arrays:

```json
{
  "or": [
    { "year": { "lt": 1970 } },
    { "year": { "gte": 2020 } }
  ],
  "not": [
    { "title": { "regex": "^Draft" } }
  ]
}
```

`and`, `or`, and `not` each take a non-empty array of filter objects. `and`
requires every filter object to match; `or` requires at least one; `not`
requires that none of them match.

A filter whose path ends at a `Link` or `LinkArray`, such as
`{ "author": "<uuid>" }`, compares the stored ID or ID array and does not
resolve the link. To filter a resolved target, enter the link path, for
example `{ "author.name": "Ursula K. Le Guin" }`. Use `author.id` to compare
the ID of a resolved target.

The same link cannot be both used as a terminal ID filter and resolved by
`project`, `filter`, or `sort` in one query. That ambiguous combination is
rejected. See [Links and resolution](../../concepts/links-and-resolution.md)
for the distinction between stored and resolved values.

Clients cannot filter by `deleted`. Non-superusers also cannot filter by
`perm` or a path below `perm`. Regardless of a client filter, standard queries
exclude soft-deleted nodes and return only nodes that the actor may read.

### Sorting and pagination

Each `sort` entry maps a path to `"asc"` or `"desc"`:

```json
{
  "sort": {
    "author.name": "asc",
    "year": "desc"
  },
  "limit": 20,
  "offset": 40
}
```

Paths that enter links resolve those links for sorting but do not make them
appear in the response unless selected by the projection. A terminal link
path sorts by its stored ID or ID array and follows the same no-mixing rule
as terminal link filters.

Sandala always produces a deterministic order: without `sort`, it uses a
stable internal ascending order; with `sort`, it adds a stable internal
tie-breaker. Pagination with `limit` and `offset` is therefore stable while
the matching data remains unchanged.

`limit` may be omitted or `null` for no limit; otherwise it is a positive
integer. `offset` is a non-negative integer and cannot be `null`. Neither
accepts a Boolean, and neither may exceed `9223372036854775807` (the largest
signed 64-bit integer).

MongoDB's internal `_id` is always omitted from node responses and cannot be
explicitly projected at a node root, including a linked target. Use the public
`id` field instead. A user-defined property with that name inside an ordinary
Object is not a node identifier and follows the ordinary field rules.

### General query endpoint

`POST /nodes/{module}/query/`

Send the query in a JSON `query` wrapper:

```json
{
  "query": {
    "project": ["title", "author.name"],
    "filter": { "entity": "Book", "year": { "gte": 1968 } },
    "sort": { "title": "asc" },
    "limit": 20,
    "offset": 0
  }
}
```

An empty request body, `{}`, and `{ "query": {} }` all mean an empty query.
Any other non-empty body without an object-valued `query` is invalid. A
successful response is `200 OK`:

```json
{
  "nodes": [
    {
      "title": "A Wizard of Earthsea",
      "author": { "name": "Ursula K. Le Guin" }
    }
  ]
}
```

Its default `project` is `["*"]`, which does not request resolution. Links
resolve only where another path in `project`, `filter`, or `sort` enters them.

### Get one node

`GET /nodes/{module}/{id}/`

The optional `project` query parameter is normally a URL-encoded JSON array,
for example:

```text
GET /api/v1/nodes/library/…/?project=["title","author.*"]
```

With an explicit `project`, it follows the projection rules above. Without
`project`, Sandala returns all visible fields and resolves every visible
user-defined `Link` and `LinkArray` field at any nesting depth, plus `owner`
and `group`. Each resolved target includes all of its visible fields, with its
own links left as IDs. `parent` and `ancestors` remain IDs by default.

The successful `200 OK` response wraps one `node`. A missing, soft-deleted, or
unreadable node returns `404` with `error: "not_found"`.

### List nodes of one entity

`POST /nodes/{module}/entity/{entity}/query/`

This endpoint returns `{"nodes": [...]}`. It accepts the same JSON `query`
wrapper as the general query endpoint:

```json
{
  "query": {
    "filter": { "year": { "gte": 1968 } },
    "sort": { "title": "asc" }
  }
}
```

The path entity limits the result to that entity. A user `filter` can narrow
the result further but cannot return nodes of another entity. A conflicting
condition, such as `{ "entity": "Author" }`, simply produces an empty result.

Without `project`, this endpoint uses the same default resolution as Get one
node: visible user-defined links, `owner`, and `group` resolve one level.
Filter and sort paths may request further resolution. A missing entity schema
returns `404`.

## Create a node

`POST /nodes/{module}/`

Send a complete node document in a `node` wrapper. `entity` is required and
must name an entity schema in the module:

```json
{
  "node": {
    "entity": "Book",
    "title": "A Wizard of Earthsea",
    "parent": null
  }
}
```

If `id` is omitted, Sandala generates a UUID. If supplied, it must be a unique
UUID string in this module. Sandala sets
`deleted`, `cdate`, and `mdate`; it derives `depth` and `ancestors` from
`parent`; and it ignores a caller-supplied value for those managed fields.

If valid `owner`, `group`, or `perm` values are absent, Sandala supplies the
current actor's user ID, primary group, and the entity's
`x-meta.perm.default`, respectively. `owner` and `group` must identify
non-deleted `users/user` and `users/group` nodes. A non-superuser may supply
only their own user ID as `owner` and one of their groups as `group`.

For `parent: null`, Sandala checks the module virtual-root populate permission
and `root_children_entities`. For a non-null parent, it checks that the parent
is active and in the same module, that the actor has its `p` permission, and
that the child entity is allowed by the parent's `x-meta.children.entities`.

User-defined link values are allowed to be dangling. Sandala validates the
node against its entity schema, removes transient `Password` values before
storage, and returns `201 Created` with the newly created node. Links in that
response are returned as stored IDs, without resolution.

## Patch a node

`PATCH /nodes/{module}/{id}/`

Send changed top-level fields in a `node` wrapper:

```json
{
  "node": {
    "title": "A Wizard of Earthsea (revised)",
    "parent": "b0313e66-29a7-40b4-a235-e55f99f66826"
  }
}
```

The node must be active and the actor must have its `w` permission. Every
submitted user field must also be writable to that actor. The PATCH merges
top-level fields into the current node; supplying an `Object` field replaces
that whole object, rather than recursively merging its children.

`id`, `entity`, `ancestors`, `depth`, `deleted`, `cdate`, and `mdate` in the
payload are ignored. An ordinary PATCH cannot change `owner`, `group`, or
`perm`: a changed value is rejected with
`acl_fields_not_allowed_in_node_patch`. Use the dedicated ACL endpoint below.

Changing `parent` moves the node. Sandala applies the same active-parent,
populate-permission, allowed-child, root, and cycle checks as create. It
recomputes the moved node's hierarchy and updates `depth` and `ancestors` for
all descendants, including soft-deleted descendants.

### Protection of ACL-hidden links

Resolution does not reveal linked targets that the actor cannot read. Sandala
therefore protects active link targets that are hidden only by ACL from being
accidentally lost in a PATCH assembled from a resolved response. It does not
protect dangling, deleted, or no-longer-allowed targets.

For a `LinkArray` whose path does not pass through an `Array`, Sandala adds the
missing protected IDs from the current node to the submitted value. A caller
can still intentionally remove any readable target.

Outside an `Array`, a submitted single `Link` (including `parent`) must retain
its protected target ID. Replacing it returns `400` with
`error: "link_patch_acl_hidden_references_missing"`. The same error occurs if
a nullable `LinkArray` that contains protected targets is submitted as `null`.

For a `Link` or `LinkArray` nested within an `Array`, the submitted array branch
must retain all protected references for that link path. Sandala does not add
IDs automatically in this case. Omitting a protected reference returns the
same error. `details.field_errors` identifies the outermost relevant Array for
an array-nested link, or the link field otherwise.

The caller can resolve the error by including all ACL-hidden IDs in the
affected link values. `GET /nodes/{module}/{id}/?project=["*"]` returns the raw
stored IDs for that purpose, subject to field visibility and query hooks.

Passing `null` for a container `Object` or `Array`, omitting a nested container
from a replacement Object, or passing an empty Array is treated as an
intentional removal of that container; its descendant links are not preserved.
A supplied Object is treated as a whole replacement, so its omitted child
links are checked.

This protection is specific to ACL-hidden targets. It does not preserve
references hidden only by query hooks, whether through read restrictions or
response-field exclusions. Integrators using those hooks are responsible for
safe editing of the affected links.

On success Sandala validates the candidate schema, removes transient Password
values, applies the patch, and returns `200 OK` with `{"node": {...}}`. Links
in that response are returned as stored IDs, without resolution.

## Patch node ACL

`PATCH /nodes/{module}/{id}/acl/`

This endpoint is the only ordinary API path for changing `owner`, `group`, or
`perm`. Send a non-empty `node` object containing only any of those fields,
plus optional Boolean `recursive`:

```json
{
  "node": {
    "group": "6bfaa146-ae0b-4431-9fca-75ba070093b8",
    "perm": {
      "owner": { "r": true, "w": true, "p": true },
      "group": { "r": true, "w": false, "p": false },
      "others": { "r": false, "w": false, "p": false }
    }
  },
  "recursive": true
}
```

The actor needs `w` on every node affected by the operation. A non-superuser
cannot change an owner; only a node owner or a superuser can change `group` or
`perm`; and a non-superuser's replacement group must belong to that actor.
Changed owners and groups must be non-deleted users and groups.

With `recursive: false` (the default), only the path node is considered. With
`recursive: true`, Sandala applies the requested ACL changes to that node and
all active descendants. If validation fails for any affected node, no ACL
changes are applied. Nodes whose ACL already has the requested values are not
updated.

The response is `200 OK`:

```json
{
  "node": { "id": "…", "entity": "Book" },
  "updated_count": 4
}
```

`node` is the root node after the operation and respects field visibility.

## Delete a node

`DELETE /nodes/{module}/{id}/`

Deletion is a soft delete. Sandala marks the requested active node and all of
its active descendants as `deleted: true`; it does not physically remove them.
The actor needs `w` on the root and every active descendant. If any check or a
validation fails, no node in the subtree is deleted.

On success the endpoint returns `200 OK`:

```json
{
  "deleted_count": 3
}
```

Deleted nodes are excluded from all standard reads and cannot be read, patched,
or deleted through these endpoints.

## Errors

All failures use the [common error contract](errors.md). Node endpoints allow
anonymous access where node ACL and field modes permit it. They return `401`
with `authentication_error` only when a supplied cookie or Bearer credential
is invalid.

The tables below cover the router and Sandala's built-in node service.
Integrator-installed hooks may reject a read or write with
additional Sandala error codes; those errors use the same envelope. The
built-in `users/user` and `users/group` hooks are documented in
[Users and groups](users-and-groups.md#errors).

Known database query rejections, such as an invalid regular expression, too
many sort fields, or an unsupported combination of values or operations
(including sorting parallel arrays), return `400` with
`query_validation_failed`. Unclassified database failures use the common
`500` error response, without exposing database diagnostics.

### Query nodes

`POST /nodes/{module}/query/`

| Status | Error code | Meaning |
| --- | --- | --- |
| `400` | `request_body_invalid` | A non-empty JSON body does not contain an object in `query`. |
| `400` | `query_validation_failed` | The query has an invalid parameter, pagination range, operator, path, sort direction, link-resolution combination, schema collision, or field-visibility violation, or is rejected as a known invalid database query. |

### Get one node

`GET /nodes/{module}/{id}/`

| Status | Error code | Meaning |
| --- | --- | --- |
| `400` | `parameter_invalid` | The URL `project` parameter is neither the raw `*` shorthand nor valid JSON of string or array type. |
| `400` | `query_validation_failed` | The explicit projection is invalid, refers to an unavailable path, or violates field visibility or link-resolution rules. |
| `404` | `not_found` | The node does not exist, is soft-deleted, is unreadable to the actor, or has no available entity schema. |

### List nodes of one entity

`POST /nodes/{module}/entity/{entity}/query/`

| Status | Error code | Meaning |
| --- | --- | --- |
| `400` | `request_body_invalid` | A non-empty JSON body does not contain an object in `query`. |
| `400` | `query_validation_failed` | Query values (including pagination ranges), paths, visibility, filters, sorting, or link-resolution combinations are invalid, or execution is rejected as a known invalid database query. |
| `404` | `not_found` | The requested entity schema does not exist in the module. |

### Create a node

`POST /nodes/{module}/`

| Status | Error code | Meaning |
| --- | --- | --- |
| `400` | `request_body_invalid` | The JSON body is not an object or does not contain an object in `node`. |
| `400` | `parameter_invalid` | `entity` is missing or invalid, or a directly checked scalar such as `id` or `parent` has the wrong type. |
| `400` | `field_write_forbidden` | A submitted user field is not writable by the actor's field write mode. |
| `400` | `owner_required` | No usable owner is supplied and Sandala cannot derive one from the actor. |
| `400` | `group_required` | No usable group is supplied and Sandala cannot derive one from the actor. |
| `400` | `owner_must_match_actor` | A non-superuser tries to create a node with another owner. |
| `400` | `group_not_in_actor_groups` | A non-superuser selects a group they do not belong to. |
| `400` | `owner_not_found` | The supplied owner is not an active `users/user` node. |
| `400` | `group_not_found` | The supplied group is not an active `users/group` node. |
| `400` | `parent_node_not_found` | A non-root parent does not exist or is soft-deleted. |
| `400` | `parent_write_forbidden` | The actor lacks populate (`p`) permission on the requested parent. |
| `400` | `root_create_forbidden` | The actor lacks populate permission on the virtual module root. |
| `400` | `entity_not_allowed_in_root` | The entity is not permitted directly below the module root. |
| `400` | `entity_not_allowed_under_parent` | The entity is not permitted as a child of the requested parent entity. |
| `400` | `document_validation_failed` | The completed node does not match its effective entity schema. `details.field_errors` identifies schema validation failures. |
| `400` | `validation_error` | Another built-in node invariant is invalid, such as inconsistent module or hierarchy metadata. |
| `404` | `not_found` | The requested entity schema or, for a root node, the module does not exist. |
| `409` | `node_id_already_exists` | The supplied node ID is already used in this module. |
| `409` | `conflict` | The write violates another unique index on the module collection. |

### Patch a node

`PATCH /nodes/{module}/{id}/`

| Status | Error code | Meaning |
| --- | --- | --- |
| `400` | `request_body_invalid` | The JSON body is not an object or does not contain an object in `node`. |
| `400` | `acl_fields_not_allowed_in_node_patch` | The patch attempts to change `owner`, `group`, or `perm`; use the ACL endpoint instead. |
| `400` | `field_write_forbidden` | A submitted user field is not writable by the actor's field write mode. |
| `400` | `parameter_invalid` | A directly checked scalar, currently `parent`, has the wrong type. |
| `400` | `parent_same_as_current` | The node is assigned as its own parent. |
| `400` | `parent_node_not_found` | A new non-root parent does not exist or is soft-deleted. |
| `400` | `parent_write_forbidden` | The actor lacks populate (`p`) permission on the new parent. |
| `400` | `parent_cycle_detected` | The new parent is a descendant of the node being moved. |
| `400` | `root_create_forbidden` | Moving to the module root is not permitted for the actor. |
| `400` | `entity_not_allowed_in_root` | The node's entity is not permitted directly below the module root. |
| `400` | `entity_not_allowed_under_parent` | The node's entity is not permitted below the new parent entity. |
| `400` | `link_patch_acl_hidden_references_missing` | The patch would remove an ACL-hidden active reference that must be retained. `details.field_errors` identifies the relevant link or array container. |
| `400` | `document_validation_failed` | The patched node does not match its effective entity schema. `details.field_errors` identifies schema validation failures. |
| `400` | `validation_error` | The actor lacks write permission on the node, or another built-in node invariant is invalid. |
| `404` | `not_found` | The node is missing, soft-deleted, or has no available entity schema. |
| `409` | `conflict` | The write violates a unique index on the module collection. |

### Patch node ACL

`PATCH /nodes/{module}/{id}/acl/`

| Status | Error code | Meaning |
| --- | --- | --- |
| `400` | `request_body_invalid` | The JSON body is not an object or does not contain an object in `node`. |
| `400` | `parameter_invalid` | The top-level `recursive` property is present but is not Boolean. |
| `400` | `acl_patch_payload_invalid` | The ACL patch is empty or contains a property other than `owner`, `group`, or `perm`. |
| `400` | `owner_required` | The supplied replacement owner is empty or invalid. |
| `400` | `owner_change_forbidden` | A non-superuser attempts to change the owner. |
| `400` | `group_required` | The supplied replacement group is empty or invalid. |
| `400` | `group_change_forbidden` | An actor who is neither the owner nor a superuser attempts to change the group. |
| `400` | `group_not_in_actor_groups` | A non-superuser owner selects a group they do not belong to. |
| `400` | `perm_change_forbidden` | An actor who is neither the owner nor a superuser attempts to change permissions. |
| `400` | `owner_not_found` | The replacement owner is not an active `users/user` node. |
| `400` | `group_not_found` | The replacement group is not an active `users/group` node. |
| `400` | `document_validation_failed` | The resulting ACL does not match the effective entity schema. `details.field_errors` identifies schema validation failures. |
| `400` | `validation_error` | The actor lacks write permission on a node affected by the operation, or another built-in node invariant is invalid. |
| `404` | `not_found` | The root node is missing or soft-deleted, an affected node disappears during the operation, or an affected node has no available entity schema. |

### Delete a node

`DELETE /nodes/{module}/{id}/`

| Status | Error code | Meaning |
| --- | --- | --- |
| `400` | `descendant_write_forbidden` | The actor lacks write permission on at least one active descendant that would be deleted. |
| `400` | `validation_error` | The actor lacks write permission on the root node, or an affected node has invalid built-in metadata. |
| `404` | `not_found` | The root node does not exist or is already soft-deleted. |
