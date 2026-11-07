# Validation and schema evolution

This page describes how Sandala validates entity schemas and node documents,
and what a contributor must preserve when changing either process. The public
schema vocabulary belongs in [Semantic types](../reference/semantic-types.md);
the public entity-schema endpoints belong in [Entity schemas](../reference/rest-api/entity-schemas.md).

## Stored and effective schemas

An entity repository stores the user portion of an entity schema. It does not
store the common node system fields. `EntitySchemaValidator` accepts a submitted
schema that either omits every system field or includes the complete canonical
set, then normalizes the result to the user portion. `EntityService` enriches a
schema with system fields when returning it through the service or REST API.

`build_effective_node_schema()` is the other direction: it enriches the stored
user schema before validating a node candidate. The same effective schema is
used when a schema replacement is checked against existing nodes. This keeps
the node contract consistent across create, patch, and schema evolution.

```text
submitted schema
    │
    ├── structural and Sandala-specific validation
    ├── canonical-system-fields check, if supplied
    ▼
stored user schema
    │
    ├── enrich for service/API response
    ▼
returned schema with system fields

stored user schema
    │
    ├── build_effective_node_schema()
    ▼
effective node schema used for document validation
```

The entity path remains authoritative for `title`: validation replaces a
submitted title with the `{entity}` path value. Do not make callers, routes, or
repositories responsible for reproducing this normalization.

## Schema validation boundary

The meta-schema is a JSON Schema that validates an entity schema, rather than a
node document. Sandala keeps its constrained Draft 7 definition in
`_META_SCHEMA` in `sandala/core/validation/schema_validator.py`.
`EntitySchemaValidator.validate_create_or_update()` first removes any submitted
system fields temporarily and validates the remaining root and field structure
against this meta-schema.

The meta-schema also enforces user-field naming restrictions and rejects
immediate `Array`, `Link`, and `LinkArray` item types inside an ordinary Array,
including nullable forms. These are structural constraints, not repository
checks. Their public definitions are in [Field names](../reference/semantic-types.md#field-names)
and [Array](../reference/semantic-types.md#array).

The validator then applies the Sandala rules that depend on system fields or
surrounding metadata:

- system fields, if supplied, appear all together in both `properties` and
  `required`, with their exact canonical definitions;
- `x-meta.children.entities` names existing entities in the current module;
- a `Link` or `LinkArray` names an existing target module and existing target
  entities;
- nested field visibility and write modes cannot be wider than their
  container; immediate `Array.items` modes exactly match the array;
- every `Object.required` name exists in that object's `properties`;
- `Password`, and an `Array` whose immediate item type is `Password`, cannot
  be required, including nullable forms.

Structural errors are normalized as schema validation errors with field
locations. Rules that require repository knowledge or cross-field comparison
raise domain validation errors. Keep that division: the meta-schema describes
shape; `EntitySchemaValidator` owns rules that require semantic context.

### Traversing nullable schemas

Before reading semantic metadata or traversing children, select the non-null
branch of a nullable schema. `EntitySchemaValidator` uses
`_extract_non_null_schema()`; service traversal uses `unwrap_nullable()` from
`core/query/schema_utils.py`. Apply the same rule to `Array.items`, not only
to named properties. Unwrapping is for semantic inspection: retain the full
`anyOf` schema when passing it to the JSON Schema document validator.

This keeps nullable fields subject to their write modes, including when the
submitted value is `null`. It also lets Password cleanup reach fields inside
nullable Objects and array items, and lets entity-deletion cleanup reach link
metadata in those same schema branches.

## Node candidate validation

`NodeService` constructs a complete candidate before validating it. On create,
the candidate contains service-managed identity, hierarchy, timestamp, and ACL
values. On ordinary patch, it starts as the current node and receives the patch
values after the relevant `before_*` hook. The validator receives that complete
candidate and the effective schema, rather than validating the transport
payload in isolation.

Consequently, `additionalProperties: false` is an invariant of stored nodes as
well as submitted schemas: a successful ordinary write leaves a node conforming
to its effective entity schema. Do not introduce repository-level writes for
ordinary nodes, because they could bypass that invariant.

`Password` has a deliberately different storage lifecycle. A submitted value
is visible to the corresponding `before_create` or `before_patch` hook and is
validated as a constrained string. Only after successful candidate validation
does `NodeService` recursively remove `Password` values and
`Array<Password>` values before persistence. This ordering lets a hook derive a
safe value such as a password hash while ensuring that an invalid password is
still rejected. It also explains why `Password` and `Array<Password>` fields
cannot be required: persisted nodes do not retain them. A containing Object
can still be required while its Password property remains optional.

## Replacing an entity schema

Schema replacement is validation, not migration. `EntityService.update()`
uses this order:

```text
validate submitted replacement
    ▼
apply users-module protected-field checks when applicable
    ▼
validate every node of that entity against the new effective schema
    ▼
replace the stored user schema
```

The node iteration includes active and soft-deleted nodes. The first document
that fails stops the operation; its error includes the node ID and normalized
field errors. The repository is not asked to replace the schema until all of
those checks succeed.

There is no automatic transformation of nodes during this process. In
particular, a schema replacement never cleans up old stored properties.
Ordinary node PATCH also merges provided values into the current document; it
does not provide a general field-removal operation. A supported migration
mechanism would need its own explicit lifecycle and documentation.

## Built-in user and group schemas

The `users/user` and `users/group` schemas are ordinary entity schemas with
additional service protection. Before existing nodes are validated, the entity
service compares their protected fields and requiredness with the stored
version. Those definitions cannot be removed or structurally changed; their
`description` values may change, and integrators may add other fields. The
public built-in schema and node-operation rules are in
[Users and groups](../reference/rest-api/users-and-groups.md).

## Deleting an entity schema

Entity deletion is separate from replacement. It is blocked while the entity
has active nodes, but soft-deleted nodes do not block it. Once the schema is
removed, `EntityService` also removes the entity from the module's
`root_children_entities`, from same-module child-entity lists, and from link
target lists in every stored schema. It does not rewrite stored node values.

Keep this cleanup in `EntityService`: it is metadata integrity maintenance,
not a repository responsibility. In particular, it must continue to traverse
nested `Object` and `Array` field schemas when removing a target entity from
link metadata.

## Maintaining this subsystem

When a schema rule changes, determine which layer owns it before editing code:

- constrained JSON Schema shape belongs in `schema_validator.py`'s
  meta-schema;
- repository-aware semantic checks belong in `EntitySchemaValidator`;
- candidate construction and document validation belong in `NodeService`;
- schema persistence and replacement sequencing belong in `EntityService`.

Update the semantic-type reference, public entity-schema contract, and this
page whenever the observable validation or evolution behavior changes. A new
semantic type also needs its query semantic behavior and Admin UI treatment
considered; see [Query builder](query-builder.md) and
[Frontend architecture](frontend-architecture.md).
