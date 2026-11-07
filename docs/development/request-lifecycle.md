# Request lifecycle

This page describes how the bundled Flask application turns an HTTP request
into a Sandala operation. It is for contributors who need to change a route,
a service, query planning, or hook behavior without moving a responsibility
across a layer boundary. It complements [Architecture](architecture.md); the
[REST API](../reference/rest-api/overview.md) remains the public HTTP
contract.

An embedded application starts at the service boundary described near the end
of this page. It does not reproduce the Flask-specific stages.

## The usual path

For a normal API request, the flow is:

```text
HTTP request
    │
    ▼
Flask route match
    │
    ├── obtain an optional or required actor
    ├── parse the route's JSON, query, or multipart representation
    ▼
core service
    ├── load required state and schemas
    ├── apply domain authorization and validation
    ├── plan a read or prepare a write
    └── invoke node write and query hooks where applicable
    ▼
storage repository or blob backend
    ▼
service result
    ▼
route response wrapper and JSON serialization
    ▼
Flask after-request session-cookie renewal, when applicable
```

An error can leave this path at any stage. A `SandalaError` reaches the shared
Flask error handler and becomes the documented REST error object. An unexpected
exception is logged and becomes a safe `500` response. Framework routing
errors, such as an unknown path, retain Flask's ordinary response rather than
Sandala's error envelope.

Routes are intentionally thin. They choose the service, read transport data,
and wrap its result; they do not implement a second version of schema,
permission, query, or persistence behavior.

## Authentication is selected by the route

Authentication is not a global Flask `before_request` handler. A route that
needs an actor chooses one of two helpers:

- `attach_optional_auth_context()` authenticates a supplied credential, but
  leaves the actor as `None` when the request has no credential. Node and asset
  routes use this path because their ACL or field rules can permit anonymous
  work.
- `require_auth_context()` uses the same authentication path and raises an
  authentication error if no actor results. Module, entity-schema, current-user,
  and PAT routes use it.

The helpers read a Bearer PAT from `Authorization` and the configured session
cookie. Bearer takes precedence. An invalid Bearer credential therefore fails
the request instead of falling back to a valid cookie. On a successful lookup,
`AuthService` builds an actor from the current active user record and the route
keeps it in Flask's request-local `g` object. Services receive that actor as a
plain dictionary; they do not know about cookies or Flask.

`AuthService` can renew a session approaching its idle expiry. The helper
records the renewed session ID in `g`, and the application-wide
after-request handler emits the replacement cookie on the response. This keeps
session-cookie mechanics in `api` while the authentication service works only
with raw credentials and domain data.

## Transport parsing and delegation

Routes use the parsing helpers in `api/payloads.py` for recurring HTTP shapes:
JSON objects, named JSON wrappers, JSON-valued query parameters, and JSON
objects encoded in multipart form fields. They reject a malformed transport
shape before calling a service. For example, a node create route unwraps
`{"node": {...}}`; a node query route unwraps `{"query": {...}}`; an asset
upload reads the binary `file` form part and parses its `target` form field.

That parsing does not establish whether a field exists, is writable, has the
right type, or is permitted for the actor. Those are domain decisions made by
the receiving service. Keep this distinction when adding a route: validate the
HTTP representation in `api`, then pass the domain value to `core`.

## Read path and query planning

Public node reads converge on `NodeService.query()` for their final selection.
The service coordinates planning, storage execution, and result processing:

```text
NodeService.query(module, payload, actor=...)
    ├── QueryBuilder.build_query(...)
    │   ├── dispatch before_query during planning
    │   └── validate the query and build the pipeline
    ├── NodeRepository.aggregate(...)
    ├── dispatch after_query on the selected, projected page
    └── return the final result list
```

The service and builder share the same `NodeHookRegistry`. The builder invokes
`before_query` for the main query and for linked-target contexts while building
the pipeline. The repository only executes that pipeline; it does not dispatch
hooks or decide read policy.

After successful aggregation, `after_query` runs once for the main query,
including an empty result. It processes the selected page before the service
returns it, rather than running separately for linked targets. Planning,
restriction placement, and projection are described in
[Query builder](query-builder.md). The public contracts are in the
[Nodes reference](../reference/rest-api/nodes.md) and
[Node hooks](../reference/node-hooks.md#query-hooks).

Recognized database query rejections are translated at two boundaries:
`NodeRepository.aggregate()` converts the driver exception to
`StorageQueryRejectedError`, and `NodeService.query()` converts that storage
error to `QueryValidationError`. Other database failures propagate as
unexpected errors. This keeps driver-specific classification in storage and
the domain error contract in core; the route needs neither classification.

`NodeService.get()` first performs a minimal, access-controlled read to learn
the node's entity schema. This internal schema-discovery read does not invoke
query hooks. If the caller omitted `project`, the service derives that
endpoint's default projection from the visible schema. It then calls
`query()` with both the node ID and its entity, so query hooks apply to the
actual selection and returned node. An empty final result becomes
`NotFoundError`.

`NodeService.list_entity()` loads the entity schema, adds the entity
restriction and any default projection, then delegates to `query()` as well.
This is why a single-node read and an entity-scoped query can provide useful
default link resolution without giving the route its own resolution logic.

Module and entity-schema reads follow their own services rather than this
pipeline, but retain the same division of responsibility: the route handles
HTTP; the service applies role and metadata rules; the repository performs the
storage operation.

## Node write path

Create and ordinary PATCH share the same broad lifecycle, although each has
operation-specific hierarchy and ACL checks:

```text
route payload + actor
    │
    ▼
load schema and, for PATCH, the current active node
    │
    ▼
initial write-mode checks and, for PATCH, node-ACL checks
    │
    ▼
for PATCH, protect ACL-hidden references in the copied payload
    │
    ▼
before_create or before_patch hooks
    │
    ▼
service-managed fields, ACL and hierarchy checks, candidate validation
    │
    ▼
remove transient Password values
    │
    ▼
repository insert or replacement
    │
    ▼
hierarchy update when a node moved, then after_create or after_patch hooks
    │
    ▼
read the result through NodeService.query(), including query hooks
```

The service, not the route or hook, owns system fields such as timestamps,
entity, soft-delete state, and hierarchy fields. It also applies default
owner, group, and permissions where appropriate. `before_create`,
`before_patch`, and `before_acl_patch` receive a copy of the payload and may
change it or its actor. The resulting effective actor governs checks that occur
after the hook; the service validates the candidate before storage. `Password`
values remain available to the relevant before hook, but Sandala removes them
only after successful validation and before the node is stored.

The returned node is not a direct echo of the candidate. Create and ordinary
PATCH perform their final read through `NodeService.query()`, so the response
passes through ordinary read restrictions, projection, and query hooks.

Write preparation reads stored state through repositories rather than the
query-hook path. Query hooks therefore customize reads, not write
authorization. In particular, automatic reference protection during PATCH
uses stored targets and node ACL; it does not extend to references hidden
only by query hooks. The protection runs before `before_patch`, so the write
hook sees any protected LinkArray IDs added to the copied payload.

### ACL patch and deletion

`NodeService.patch_acl()` uses its own hook events because its payload is
limited to `owner`, `group`, and `perm`. For a recursive operation it loads the
active subtree, prepares and validates every affected candidate, then performs
one bulk update. It calls `after_acl_patch` only for candidates whose ACL
values changed. After those hooks, it reads the requested node through the
query path to produce the response; that read also invokes query hooks.

Deletion similarly loads the active subtree. It runs every `before_delete`
hook before any node is soft-deleted, performs the bulk soft delete, and then
runs `after_delete` for the same nodes. The traversal is deterministic: parent
before descendant, then node ID within a depth. See [Writing hooks](../guides/writing-hooks.md)
for examples, [Node hooks](../reference/node-hooks.md) for the event contexts,
and [Protection of ACL-hidden links](../reference/rest-api/nodes.md#protection-of-acl-hidden-links)
for the separate protection applied during ordinary PATCH.

### Failure timing matters

A failure before repository mutation prevents that mutation. This includes a
validation error or an exception from a before-write hook. An after-write
hook runs only after the corresponding write has succeeded. Its exception is
returned to the caller, but it cannot undo the stored node or ACL change.

Query-hook timing is relative to the read, not the write: `before_query`
failure prevents query execution, while `after_query` failure happens after
selection. Both events also run during the final read after create, patch,
and ACL patch. An error there, or an empty result that becomes
`NotFoundError`, does not roll back the preceding write. Integrations
therefore need idempotent hook side effects and their own retry or
reconciliation strategy where a later stage can fail.

Registry ownership, context data flow, and recursive dispatch phases are
described in [Node hooks](node-hooks.md).

## Asset path

Asset uploads are a parallel service path rather than node writes:

```text
multipart file + JSON target + actor
    ▼
AssetService validates target schema and field write mode
    ▼
optional image transformation
    ▼
blob storage write
    ▼
asset descriptor response
```

An upload does not create or patch a node. The client or a hook later assigns
the returned descriptor to a node field through the usual node write path.
Public asset delivery is separate again: the `/assets/...` route opens a
storage key and streams the result; it does not authenticate the request or
evaluate node ACL. The public behavior is documented in [Assets](../reference/rest-api/assets.md).

## Embedded applications

An embedded host calls `build_container()` once and invokes the returned
services directly. It begins at the service box in the diagrams above. The
host owns its request parsing, credential extraction, session-cookie handling,
response shape, and mapping of `SandalaError` exceptions to its transport.

It should still authenticate a credential through `AuthService`, pass the
resulting actor to the selected service, and use service methods rather than
repositories for ordinary application operations. This preserves the same
schema, ACL, hook, and validation behavior as the bundled API. See
[Embedding Sandala](../guides/embedding-sandala.md) for an implementation
pattern and [Python API](../reference/python-api.md) for supported services.

## Changing a lifecycle safely

When changing request processing, preserve these properties:

- Keep Flask request objects, cookies, HTTP wrappers, and response status
  decisions in `api`.
- Keep authorization, validation, hook dispatch, defaulting, and query
  planning in `core`.
- Do not bypass the service layer from a new route or integration for an
  ordinary domain write.
- Keep before-write hooks in the pre-write decision path and after-write
  hooks after persistence. Query hooks belong to read planning and result
  processing, including a write operation's final read.
- Add tests at the boundary that changed: route tests for HTTP parsing and
  serialization, service tests for domain behavior, and Mongo integration
  tests when pipeline or repository behavior matters.
