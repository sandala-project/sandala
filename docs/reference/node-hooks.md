# Node hooks

Node hooks run trusted, synchronous Python handlers around node reads and
writes. Register them on `container["node_service"].hooks`; the same handlers
apply through the REST API and the direct Python services.

This page defines the public hook contract. For integration setup and worked
examples, see [Writing node hooks](../guides/writing-hooks.md). Query and node
payloads use the shapes in [Nodes](rest-api/nodes.md), without REST wrappers.

The **main query** selects the nodes returned directly by a read operation.
Link resolution retrieves the nodes referenced by those results. This
distinction is unrelated to a node's position in its module's tree.

## Registration and ordering

```python
hooks.register(
    event,
    handler,
    module=None,
    entity=None,
    priority=100,
)
```

`event` and `handler` are positional arguments; the remaining arguments are
keyword-only. A handler receives one context argument. `register()` returns
the registered handler. Handler return values are ignored: supported changes
are made through the context instead.

Several handlers may be registered for one event. Lower priorities run first;
equal priorities retain registration order. All matching handlers for an
event receive the same context, so later handlers see earlier changes.

| Scope | Write hooks | Query hooks |
| --- | --- | --- |
| No `module` or `entity` | All modules and entities. | All modules. |
| `module="library"` | Every entity in that module. | Main queries for that module and resolution of links targeting it. |
| `entity="Book"` | That entity in any module. | Not supported. |
| Both `module` and `entity` | That entity in that module. | Not supported. |

An unsupported event or an entity-scoped query registration raises
`ValueError`; a non-callable handler raises `TypeError`. Query hooks have
module scope because a selection may consider several entity types together.

For the standard REST application, configured hook modules expose
`register_hooks(app, container)` and are loaded through `HOOK_MODULES`.
`build_container()` alone does not load them; embedded applications register
their handlers during startup. See the [registration guide](../guides/writing-hooks.md#register-a-hook-module-for-the-rest-application)
for both forms.

## Write hooks

Write handlers receive `NodeHookContext`, available from
`sandala.core.services.node_hooks`.

### Events

`event`, `module`, `entity`, and `actor` are common to every write context.
Other available fields are listed below; fields not supplied for an event
have the value `None`.

| Event | When it runs | Additional context | Supported changes |
| --- | --- | --- | --- |
| `before_create` | After initial field-write checks, before the new node is completed, validated, and inserted. | `payload` | `payload`, `actor` |
| `after_create` | After the node is inserted. | `node_id`, `payload`, `candidate`, `result`, `effective_actor` | None |
| `before_patch` | After reading the node and initial write checks, before the changed node is validated and saved. | `node_id`, `current`, `payload` | `payload`, `actor` |
| `after_patch` | After the node is saved and any move-related hierarchy updates finish. | `node_id`, `current`, `payload`, `candidate`, `result`, `effective_actor` | None |
| `before_acl_patch` | After initial write and ACL checks, before the changed ACL is validated and saved. | `node_id`, `current`, `payload` | `payload`, `actor` |
| `after_acl_patch` | After a changed ACL is saved. | `node_id`, `current`, `payload`, `candidate`, `result`, `effective_actor` | None |
| `before_delete` | After write-access checks, before subtree deletion. | `node_id`, `current` | None |
| `after_delete` | After subtree deletion. | `node_id`, `current`, `deleted_count` | None |

### Context fields

| Field | Type | Meaning |
| --- | --- | --- |
| `event` | string | The write event being handled. |
| `module` | string | The node's module. |
| `entity` | string | The entity being created, or the current node's entity for other operations. |
| `node_id` | string or `None` | The affected node ID. In `before_create` it is `None`; the proposed ID is in `payload["id"]`. |
| `actor` | dictionary or `None` | Initially a snapshot of the caller's actor. The three mutable before events may change it. After-write events receive the original caller's actor. |
| `effective_actor` | dictionary or `None` | In `after_create`, `after_patch`, and `after_acl_patch`, the actor resulting from the corresponding before handlers. |
| `payload` | dictionary or `None` | The operation's field payload. It may be changed in `before_create`, `before_patch`, and `before_acl_patch`; the corresponding after events receive a snapshot after those changes. |
| `current` | dictionary or `None` | The stored node before patch, ACL patch, or deletion. |
| `candidate` | dictionary or `None` | The completed and validated node prepared for a successful create, patch, or ACL patch. |
| `result` | dictionary or `None` | A stored-node snapshot after create, patch, or ACL patch. It is not the final read response. |
| `deleted_count` | integer or `None` | In `after_delete`, the total count deleted by the original subtree operation, not a per-node count. |

`current`, `candidate`, and `result` are trusted snapshots, not caller-visible
projections; they may contain fields hidden from the caller. Treat them and
the identity fields as read-only. Changing an after-write `result` does not
change stored data or the returned API response; use `after_query` to
transform returned data.

### Payload and actor changes

Only `before_create`, `before_patch`, and `before_acl_patch` may change
`payload` and `actor`. The payload dictionary is shared with the operation:
edit it in place rather than assigning a replacement to `context.payload`.
The three events also support replacing `context.actor`.

Client field-write checks happen before these hooks. A trusted handler can
therefore fill fields the caller could not submit directly. The resulting
node still passes schema validation and the applicable remaining hierarchy
and ACL checks. Changing the actor affects checks and defaults performed
after the handler; it does not undo initial authorization checks.

The payload has these operation-specific properties:

- Before create, it already contains a generated UUID if the caller omitted
  `id`.
- Before ordinary patch, supplied LinkArray values outside Arrays may already
  include ACL-hidden IDs retained by Sandala. See [Protection of ACL-hidden
  links](rest-api/nodes.md#protection-of-acl-hidden-links).
- Before ACL patch, only `owner`, `group`, and `perm` may be changed. This
  restriction and the resulting ACL values are checked after the handlers.
  Its after event receives only fields actually saved, including `mdate`.

Password inputs remain available in the create and ordinary patch payloads,
including their after-event snapshots. Their `candidate` and `result`
snapshots have had transient Password values removed. See [Password is
transient](semantic-types.md#password-is-transient).

### Recursive operations

A recursive ACL patch invokes `before_acl_patch` for each active affected
node, including nodes whose ACL will remain unchanged. `after_acl_patch` runs
only for nodes whose ACL actually changes. Validation failure prevents the
ACL changes from being applied.

Subtree deletion invokes both delete events for every affected active node,
in parent-before-child order, with nodes at the same depth ordered by `id`.
All `before_delete` handlers finish before deletion begins. If one rejects
the operation, no node is deleted and no `after_delete` handler runs. After
successful deletion, after handlers run in the same node order.

## Query hooks

Query handlers receive `NodeQueryHookContext`, available from
`sandala.core.services.node_hooks`.

### Events

| Event | When it runs | Additional context | Supported changes |
| --- | --- | --- | --- |
| `before_query` | Before execution, for the main query and each link-resolution path. | The main query object; restriction methods in every context | Modify or replace `query` in the main-query context; add required filters and output exclusions. |
| `after_query` | Once after the main query succeeds, including an empty result, after projection, sorting, and pagination. | `query`, `result` | Modify or replace `result`. |

The events apply to `query()`, `get()`, and `list_entity()`. They also run for
the final reads that produce the returned node after `create()`, `patch()`,
and `patch_acl()`. They are read hooks, not write-authorization hooks.

A before hook runs once per resolution path, not once per returned node or
array item. Reading the same module through several links can therefore
invoke its hook several times. `after_query` runs for the result of the main
query only, not separately for linked targets.

### Context fields

| Field | Type | Meaning |
| --- | --- | --- |
| `event` | string | `before_query` or `after_query`. |
| `module` | string | The module read in this context. For a linked target, this is its target module. |
| `actor` | dictionary or `None` | A snapshot of the actor used for the read. Changing it does not change query authorization. |
| `query` | dictionary or `None` | The main query object without the REST wrapper. For linked-target contexts, `None`, not a separate editable query. |
| `path` | string | `""` for the main-query context; otherwise the dot path identifying the link being resolved, such as `author.city`. |
| `is_lookup` | Boolean property | Read-only indication that `path` identifies a linked-target context. |
| `result` | list of dictionaries or `None` | The selected result of the main query in `after_query`; otherwise `None`. |
| `required_filters` | tuple of dictionaries | Read-only snapshot of filters added through `add_required_filter()`. |
| `excluded_fields` | tuple of strings | Read-only snapshot of paths added through `exclude_fields()`, sorted by path. |

Treat `event`, `module`, `actor`, and `path` as observational
context. Unlike the mutable write hooks, query hooks cannot switch the
effective actor.

### Query and result changes

In the main-query context, `before_query` may edit or replace `context.query`.
All before handlers share the context, so later handlers see query changes
made by earlier ones. The final query passes normal validation before
execution. `after_query` receives a snapshot of that query.

In `after_query`, mutate `context.result` or assign a replacement list of
node dictionaries. This includes removing items or adding response-only
fields. The final result after all handlers is what `query()` and
`list_entity()` return. `get()` takes its first node; an empty final result
becomes `NotFoundError`. A result that is not a list of dictionaries raises
`ValueError`.

These changes affect only returned data, not stored nodes. The transformed
result is not checked again against schema visibility or node ACL, so a
trusted handler must not reintroduce hidden data.

The hook receives an already selected page. Removing rows here may shorten
that page; Sandala does not fetch replacements. Use a required filter rather
than an after hook for restrictions that must participate in selection and
pagination.

### Required filters

`context.add_required_filter(filter_dsl)` adds a condition using the ordinary
[filter language](rest-api/nodes.md#filtering). Conditions from all hooks
combine with AND and apply in addition to the client query and built-in read
restrictions. Replacing `context.query` in a later hook does not remove them.
They apply to superusers too unless the handler explicitly omits them.

Required filters inspect stored values in the current module, before link
resolution. They may traverse embedded Objects and Arrays, and compare a
stored Link or LinkArray by its IDs, but may not enter a link's target fields.
For example, `metadata.region` and `author` are valid stored paths;
`author.name` is not valid when `author` is a Link. To restrict Author targets,
register a hook for their module instead. A required filter on `author` can
coexist with resolution of `author` elsewhere in the query.

Unlike client filters, required filters may use fields hidden from the caller,
including ACL metadata. Using a field in a required filter does not expose it
in the response or grant the caller permission to query it.

`filter_dsl` must be a dictionary. Invalid filter structure, operators, operand
types, or traversal through a link raise `QueryValidationError`.

### Output exclusions

`context.exclude_fields(*paths)` removes fields from the final response,
including fields explicitly selected by the client. Each argument is a
non-empty dot path without wildcards, empty segments, NUL characters, or
segments beginning with `$`. Invalid arguments raise `QueryValidationError`.

Write paths relative to the nodes selected in the current context, without
prepending `context.path`. Sandala automatically applies the exclusions at
the corresponding location in the final response. For example, a hook
registered for the `people` module can always call `exclude_fields("email")`:
this removes `email` when querying `people` directly, `author.email` when
resolving a link to `people` through `author`, and `book.author.email` when
resolving it through `book.author`. The hook does not need to inspect the link
path or adjust its arguments.

A hook for the main query can also target a particular nested path directly:
`exclude_fields("author.email")` removes that field under `author` in its
result. Exclusions do not request link resolution themselves, and paths
absent from a returned node have no effect.

Exclusions are uniform within a context, not conditional on an individual
node's entity: when one link can resolve several entities, excluding `email`
excludes that path from all of them. Exclusions from all hooks accumulate and
survive later changes to `query`.

This is output redaction, not schema visibility. Excluded values remain
available to valid client filters and sorts. Use field visibility modes when
the client must not query a field at all. Both restriction methods are
available only in `before_query`; calling them in `after_query` raises
`ValueError`.

Custom query restrictions do not extend automatic PATCH protection to
references hidden only by those restrictions. Integrators are responsible
for safe editing of such references; see [Protection of ACL-hidden
links](rest-api/nodes.md#protection-of-acl-hidden-links).

## Errors and side effects

A handler may raise a `SandalaError` subclass to reject an operation. Through
the Python API, the exception reaches the caller unchanged. Through REST, it
uses the [standard error envelope](rest-api/errors.md). Unexpected Python
exceptions become safe `500 internal_error` responses in REST.

| Failure point | Effect |
| --- | --- |
| Before-write handler | The operation stops before its node write. |
| After-write handler | The error reaches the caller, but the node write has already happened and is not rolled back. |
| `before_query` | The query does not execute. |
| `after_query` | The read has completed, but the error is returned instead of its result. |
| Either query event during a write operation's final read | The write has already happened and is not rolled back. |

Side effects performed by a handler are not rolled back when a later handler
or validation fails. Calls to node services from a hook can invoke hooks
again; avoid unbounded recursion. Hooks run in request handling and should
not keep caller-specific state in shared module globals.
