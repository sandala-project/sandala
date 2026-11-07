# Query builder

`QueryBuilder` turns Sandala's node-query payload into a MongoDB aggregation
pipeline. It is the policy boundary for node reads: it combines the query DSL,
entity schemas, field visibility, node read ACL, link resolution, projection,
sorting, pagination, and restrictions added by query hooks before
`NodeRepository` executes the node selection.

This page is for contributors changing query behavior. The supported request
syntax and response semantics are defined in the [Nodes REST reference](../reference/rest-api/nodes.md).
The [Links and resolution](../concepts/links-and-resolution.md) concept page
explains the user-facing model. [Request lifecycle](request-lifecycle.md)
describes service orchestration, execution, result hooks, and error timing.

## Responsibility and shape

`QueryBuilder` is an orchestrator, not a home for every query rule. It owns the
order in which specialized collaborators run, but the collaborators own their
respective transformations and validations:

```text
query payload + actor + module
    │
    ▼
before_query for the main query, then normalize and validate input
    │
    ▼
schemas, semantic behavior, and visible path resolution
    │
    ▼
system and required filters + user filter + lookup plan
    │
    ▼
before_query for linked targets + lookup stages + output exclusions
    │
    ▼
pipeline stages
    │
    ▼
NodeRepository.aggregate(module, pipeline)
```

The repository deliberately has no query-policy decision. It receives a
finished pipeline and runs it. Conversely, `QueryBuilder` does not hold a
MongoDB collection or execute the node selection itself. It obtains schemas
through the entity repository.

| Module | Responsibility |
| --- | --- |
| `query_builder.py` | Orchestrates before-query hooks, normalization, schema scope, lookup planning, and final pipeline assembly. |
| `filter_compiler.py` | Validates and compiles the filter DSL, collects filter paths, protects system fields, and builds the safe early match. |
| `acl_filter.py` | Builds the node-permission Mongo predicate with owner, group, then others precedence. |
| `projection_normalizer.py` | Separates response projection paths from lookup paths and normalizes output exclusions. |
| `schema_resolver.py` | Walks compatible schemas, checks path and container-content visibility, detects collisions, and validates stored-only paths for required filters. |
| `lookup_planner.py` | Converts paths that enter a reference into a tree of lookup operations. |
| `lookup_pipeline_builder.py` | Generates regular, nested, and array-aware `$lookup` stages from that tree. |
| `reference_resolution_conflicts.py` | Rejects a query that simultaneously resolves a reference and treats the same path as its stored ID. |
| `visibility_exclusions.py` | Finds hidden descendants to remove from wildcard and whole-container projections at each node scope. |
| `pipeline_builder.py` | Places the completed match, lookup, sort, projection, exclusion, offset, and limit stages in order. |
| `semantic_registry.py` | Defines whether a semantic type is scalar, a container, a reference, or a multi-reference, and how it exposes children or targets. |
| `system_fields.py` | Supplies synthetic query schemas for system fields that can participate in paths, including node relations and owner/group references. |
| `schema_utils.py`, `path_utils.py` | Shared nullable-schema and dot-path helpers. |

When a change does not naturally belong in `QueryBuilder`, extend one of these
focused modules instead. In particular, a semantic type belongs in the
semantic registry, not in a new conditional branch in the orchestrator.

## Build sequence

`NodeService.query()` calls
`QueryBuilder.build_query(module, payload, actor=...)`. The builder:

1. Copies the payload and dispatches `before_query` for the main query using
   the shared hook registry. Subsequent steps use the query left by all
   handlers, including a replacement query.
2. Normalizes and validates `project`, `filter`, `sort`, `limit`, and `offset`.
   Pagination values must fit a signed 64-bit integer. The sort
   receives `_id: asc` as a deterministic final tie-breaker when the caller did
   not supply `_id`.
3. Builds the system read filter: active nodes only, plus the actor's read ACL
   predicate unless the actor is a superuser. It rejects user filters on
   `deleted`; a non-superuser also cannot filter on `perm` or its descendants.
4. Infers a schema scope from the modified query. Only a root-level
   `entity` equality or `in` condition narrows that scope; another equivalent
   logical form still has ordinary query semantics but does not narrow the
   schemas considered for path compatibility. Required hook filters are
   compiled separately and do not narrow this schema scope.
5. Collects paths from projection, filter, and sort, then resolves them against
   the scoped schemas at the actor's visibility level. This produces a lookup
   tree for paths that enter a reference. It validates terminal reference
   conflicts and prepares response and lookup projections, auxiliary fields,
   and schema-visibility exclusions.
6. Compiles the early and final matches. Required hook filters use stored
   values, independently of the client's post-resolution filter.
7. Builds lookup stages recursively. For each resolution path, it dispatches
   `before_query` for the target module, adds that context's required filter
   to the target match, and collects its output exclusions.
8. Normalizes the collected exclusions and assembles the completed match,
   lookup, sort, projection, exclusion, offset, and limit stages.

The result is a `BuiltQuery` containing the pipeline and the query after the
main-query handlers. `NodeService.query()` passes the pipeline unchanged to
`NodeRepository.aggregate()` and uses the query for its after-query context.
`QueryBuilder.build()` is a convenience wrapper returning only the pipeline.

### Schema reads within one build

Each build creates a `_QuerySchemaContext` shared by filter compilation, path
resolution, lookup planning, and visibility collection. Its lazy
`get_module_schemas()` cache loads each needed module at most once during
that build, including modules reached through several links.

The cache belongs to this build, not the service or process. A later build
loads schemas again; actors, lookup plans, hook restrictions, and result data
are not cached across requests. Service preparation such as deriving a
default projection can perform its own schema read outside this cache.

## Query-hook restrictions in the plan

The builder dispatches before-query hooks during construction, not during
MongoDB execution. Handlers for the main query share its mutable context;
the builder validates and plans their final query. For a linked target,
`_build_lookup_hook_filter()` creates a context for that path and compiles
its restrictions through callbacks passed in `LookupBuildContext`. Storage
never receives hook handlers. The actor used for authorization remains the
one supplied to the build, independently of changes to a hook's actor copy.

Required filters and output exclusions are accumulated outside the editable
query, so later query replacements cannot discard them. The complete public
context and mutation contract is in [Node hooks](../reference/node-hooks.md#query-hooks).

### Stored-value filters

Required filters pass through `SchemaPathResolver.validate_stored_paths()`
and the ordinary DSL compiler, rather than the client lookup planner. The
stored-path validator permits traversal through embedded containers but
rejects descent through references or scalar fields. A missing field in one
entity schema is allowed: module policies may apply only to some entities.
Unlike client path checks, this validation does not enforce caller visibility.

The compiled conditions are ANDed with the system restrictions before
resolution of the affected nodes. They neither replace ACL nor add lookup
work. In particular, a condition on a stored Link ID can coexist with
resolution of that Link: it is not reapplied to the resulting object.

### Output exclusions

Exclusions do not contribute paths to lookup planning. Target-relative paths
are prefixed with the resolution path and collected with main-query
exclusions. `ProjectionNormalizer` removes redundant child paths when a
parent is already excluded.

Hook exclusions are applied in the main pipeline after filtering, sorting,
and projection, but before pagination, not inside the target lookup projection.
An excluded target value must remain available until outer filters and sorts
have consumed it. Schema visibility is a different restriction: an explicitly
hidden path is rejected during client query validation, and hidden target
values are removed within their own lookup scope.

## Security and visibility invariants

The cross-service authorization rules and trust boundaries are described in
[ACL and field visibility](acl-and-field-visibility.md). This section focuses
on their consequences for query construction.

These invariants apply to the constructed pipeline, including nested lookups.
The later, trusted `after_query` transformation is outside the builder; its
output is not revalidated for ACL or field visibility.

- Soft-deleted nodes are never returned. `deleted: false` is part of the
  system filter, and user filters may not override it.
- A superuser bypasses node `perm` checks, but not the active-node restriction.
- Every other actor receives the Unix-style ACL predicate: owner permission
  applies first; otherwise a matching group permission applies; otherwise the
  `others` permission applies. The group branch deliberately excludes an actor
  who is the owner, so the owner cannot fall through to a more permissive group
  rule.
- A path explicitly named by `project`, `filter`, or `sort` must be visible at
  every relevant schema segment. An invisible path is a query validation error,
  not an empty result.
- Comparing a whole stored container or sorting by it also checks the
  visibility of its descendants. Otherwise a condition on a visible parent
  could reveal a hidden child. `exists` and `size` do not inspect child values
  and need only the path's visibility. This traversal stops at references:
  the stored value contains IDs, not target documents.
- Wildcard and whole-container projections remove hidden descendants with
  `$unset`. `VisibilityExclusionsCollector` unwraps nullable containers and
  inspects ordinary children, while reference targets are sanitized in their
  own lookup scope. This also covers a selected Object or Array without an
  explicit wildcard. If any defining schema hides a path, that path is
  excluded for all nodes in the shared scope.
- Lookup pipelines apply the same system read filter to their targets. A link
  target must also satisfy its reference's entity scope and any required
  target-module filters. A superuser does not bypass hook restrictions unless
  the hook explicitly omits them.

### Path validation and internal fields

Path syntax is validated independently of schema traversal, even when the
entity scope is empty. `path_utils.py` rejects operator-like segments, empty
segments, NUL characters, and misplaced wildcards, so the DSL cannot inject
MongoDB expressions as field names. Array descent addresses item schemas,
not numeric positions; numeric property names of ordinary Objects remain
valid. Schema validation reserves the `__sandala_` prefix used for temporary
pipeline fields and disallows ambiguous user field names.

MongoDB `_id` is excluded from response projections and is unavailable as an
explicit node-root projection or a field reached directly through a
reference. User-defined `_id` properties inside ordinary Objects are not
MongoDB node IDs and retain ordinary field behavior.

### Resolving owner and group without changing ACL meaning

`owner` and `group` are stored UUIDs but may be resolved like ordinary links.
For a non-superuser, resolving either top-level field would otherwise replace
the UUID before the final ACL match runs. When such a lookup is present,
`QueryBuilder` copies the raw UUID into a temporary field before lookup,
evaluates the final ACL predicate against that copy, and removes the temporary
field immediately afterwards.

Those extra stages appear only when a non-superuser resolves top-level `owner`
or `group`. Nested lookups do not need the mechanism: their target ACL match
occurs before that target's own links are resolved.

## References, containers, and projections

The union of projection, filter, and sort paths determines reference
resolution. `author.name` and `author.*`, for example, create a lookup for
`author`; selecting only terminal `author` does not request one. If another
query path resolves it, a projection of `author` or `*` returns that resolved
value rather than restoring the stored UUID.

`$lookup` writes its result to a temporary array. For `Link`, a `$set`
expression selects its first target or `null`; the reference itself does not
require `$unwind`. `LinkArray` keeps the target array, omitting unmatched
targets without promising their original order. Absent and null source
references remain absent and null. Object branches are rebuilt with guarded
`$mergeObjects` so resolving a child does not materialize an absent/null
parent or discard its siblings. Temporary lookup fields are removed.

The same distinction applies to filters and sorting. A terminal condition such
as `{"author": {"eq": "<id>"}}` addresses the stored UUID. If the query also
resolves `author`, that meaning would become ambiguous after lookup, so Sandala
rejects it. A condition or sort on `author.id` instead explicitly addresses the
resolved object.

### Array reconstruction

`LookupPlanNode.array_ancestors` records every ordinary array on the path
within the current source document. For `sections.team.groups.reviewer`,
both `sections` and `groups` may be Arrays of Objects. The builder records
their states and item indexes, unwinds outermost first, and performs the
reference lookup. A nested target lookup starts its own array-ancestor chain.

Reconstruction runs innermost first. Group keys include the source MongoDB
`_id` and the indexes of the remaining outer arrays, preventing different
outer elements' children from being merged. Sorting by captured indexes
restores item order. Saved types and indexes preserve missing, null, and
empty containers; null object items and parents are restored without creating
placeholder objects. Each group keeps one base-document snapshot plus its
index/value pairs, rather than copying the full document at every level.

Direct `Array<Array>`, `Array<Link>`, and `Array<LinkArray>` are rejected by
schema validation. Arrays separated by Objects remain supported. Keep
reconstruction in `lookup_pipeline_builder.py`, not in routes or the filter
compiler.

### Reference target scopes

Schema traversal allows a field to be absent from some source entities, but
checks visibility and compatibility in the schemas that define it. A terminal
stored-value path does not require compatible reference targets; entering a
reference requires compatible reference kinds and a common target module.

For an ordinary `Link` or `LinkArray`, an empty `x-meta.link.entities` list
means that no target entity is resolvable. The system `parent` and `ancestors`
relations do not use `x-meta.link`. Their semantic strategy creates a
`ReferenceTarget` with `entity_scope_mode="all_module"`; its empty internal
entity list means every entity in the current module.

This distinction lives in `ReferenceTarget.entity_scope_mode`, not in a special
case in the generic lookup code.

Compatible references with the same path can have different allowed targets
in different source entities. The resolver forms a union for target-schema
planning but also retains `entities_by_source`. Only when those lists differ,
the lookup receives a source-entity variable and an `$expr` condition tying
allowed targets to that source. Sources with an empty explicit list match
no targets. Identical lists need no extra variable or expression. Entity names
inside these generated expressions are wrapped in `$literal`.

### Projection channels

Projection paths serve two purposes: they select the final response and they
can request lookup work. Filter and sort paths can need lookup work too, even
when they must not appear in the response. `ProjectionNormalizer` and the
lookup projection builder keep these channels separate:

- the final projection contains only requested response paths, plus the
  wildcard behavior requested by `*` or `.*`;
- a lookup projection includes fields needed for a deeper lookup, filter, or
  sort, even if they are absent from the final response;
- auxiliary filter/sort values appear in the response only if covered by the
  requested projection, including a selected parent container or wildcard;
- helper fields introduced by lookup reconstruction or raw-ACL preservation
  are removed and never become response fields.

This separation is necessary for a query such as a filter on `author.name`
with a final projection containing only `title`.

## Pipeline order and early narrowing

Without lookups, the pipeline begins with one match combining the system,
user, and required hook filters. With lookups, it has this shape (optional
stages are omitted when unused):

```text
$match  early safe user predicates + system filter + main required filters
[preserve raw owner/group UUIDs when required]
$lookup / reference assignment / array reconstruction stages
$match  complete system-and-user filter
$unset  temporary raw ACL fields
$sort
$project
$unset  schema-visibility and hook output exclusions
$skip
$limit
```

Pushing client conditions into the early match is an optimization, not a
second interpretation of the query. Only direct root conditions or direct
conditions in the root `and` array are candidates; their paths must have no
dot and every defining schema in scope must treat the field as a scalar or
an Array of scalars. Objects and references are excluded even for presence
or size checks, because resolution can change their stored contents. See the
[full eligibility rules](../reference/rest-api/nodes.md#early-filter-narrowing).

The final match always contains the complete compiled user filter and system
filter. Required filters follow a separate rule: they must inspect stored
values, so the main ones run only in the early match when lookups exist.
Each target's required filters likewise run before its nested lookups.
Reapplying those conditions after resolution could compare an ID against an
object or an original array against its resolved contents.

Do not move final filtering after projection, visibility exclusions, skip, or
limit. Doing so can leak fields, alter pagination, or let an unresolved lookup
change the selected set.

## Extending query behavior safely

Start by locating the policy being changed:

| Change | Primary place |
| --- | --- |
| Filter operator or early-match eligibility | `filter_compiler.py` |
| Projection canonicalization | `projection_normalizer.py` |
| Field-path compatibility or visibility | `schema_resolver.py` or `visibility_exclusions.py` |
| Reference target or container behavior | `semantic_registry.py` |
| Lookup-tree shape | `lookup_planner.py` |
| Mongo stages for a resolved path | `lookup_pipeline_builder.py` |
| Final stage order | `pipeline_builder.py` |
| ACL predicate | `acl_filter.py` |
| Required-filter validation or hook-exclusion placement | `query_builder.py`, `schema_resolver.py`, and `projection_normalizer.py` |

For a new semantic type, provide a strategy that supplies its `FieldBehavior`,
child schema where it is a container, and reference target where it is a
reference. This makes it available consistently to path resolution, lookup
planning, and visibility traversal.

Query changes need both pipeline and database-level coverage. Add a unit test
for the constructed pipeline and a Mongo integration test for the observable
result whenever a change can affect ACL, resolution, visibility, filtering,
sorting, arrays, or pagination. When it changes a system relation such as
`parent`, `ancestors`, `owner`, or `group`, cover projection and resolution as
well as filtering, sorting, visibility, and schema collisions.

The broader test strategy and current commands belong in the Testing developer
documentation. This page records the behavioral coverage that a query change
must preserve rather than the current arrangement of test files.
