# Node hooks

This page describes hook ownership, dispatch, and data flow for contributors
changing Sandala. The [Node hooks reference](../reference/node-hooks.md) owns
the event and context contract; [Writing node hooks](../guides/writing-hooks.md)
provides integration examples. Do not introduce separate hook behavior in REST
routes: the same service operation dispatches the same handlers when called
through Python.

## One registry per service container

`build_container()` creates a `NodeHookRegistry`, gives it to `NodeService`,
and registers the built-in users-module handlers. `NodeService` passes that
same registry to its `QueryBuilder`. The registry contains registrations, not
request data or query plans.

The dispatch responsibilities are split deliberately:

| Owner | Responsibility |
| --- | --- |
| `NodeHookRegistry` | Store registrations, select matching handlers, and invoke them in order. |
| `NodeService` | Create write contexts, consume supported write changes, coordinate recursive operations, and run `after_query` on executed results. |
| `QueryBuilder` | Run `before_query` while planning the main selection and linked-target lookups, then compile the resulting query and restrictions. |
| `create_app()` | Import configured integration modules and call their registration functions during application startup. |

The standard app loads `HOOK_MODULES` after the container and built-in hooks
exist. Calling `build_container()` directly registers the built-in handlers
but does not load those integration modules. This preserves an embedding host's
control over initialization. The loader calls `register_hooks(app, container)`
for each configured module in order and fails startup if importing or
registration fails.

Keep registrations attached to the container rather than a module-global
registry. Two applications created in one process need independent
registrations and service dependencies. An imported hook module may be reused
by Python, but its registration function is called with each application's
own container. Register during startup; the registry is not a synchronized
runtime configuration service.

## Dispatch ordering and scope

`register()` records an event, handler, optional module/entity scope,
priority, and a monotonically increasing registration order. `dispatch()`
sorts that event's registrations by `(priority, order)`, tests the scope, and
calls each matching handler synchronously with the same context object.

Scope specificity does not confer precedence. A global handler does not
automatically run before or after an entity-specific handler; their priority
and registration order decide. Built-in handlers participate in this same
ordering rather than a separate dispatch phase.

Write scopes match the context's module and entity. Query events reject an
entity scope at registration, because planning operates on a module's schema
scope rather than a particular returned node. A target-module registration
can therefore match link planning as well as a main query for that module.

Handler return values are ignored. An exception interrupts the dispatch and
propagates to its caller; later handlers are not invoked. The registry does
not interpret results, validate node candidates, catch domain exceptions, or
translate errors into HTTP responses.

Some call sites use `has_hooks()` to avoid preparing unused after-event
snapshots or lookup contexts. This is a scope precheck, not a second dispatch
algorithm or an authorization decision. Keep its matching rules consistent
with `dispatch()`.

Priority applies within one dispatch. It does not reorder different events,
nodes in a recursive operation, or query-planning contexts. Those sequences
belong to the service or builder.

## Context mutation is consumed by the caller

Both context classes are slotted dataclasses, but neither the registry nor the
dataclass turns every attribute assignment into a service action. The code
that creates a context decides which values it reads after dispatch.

The important ownership distinctions are:

| Context data | How the operation consumes it |
| --- | --- |
| Mutable write `payload` | The context and service share a copied payload dictionary. In-place edits affect the candidate; replacing the context attribute does not replace the service's dictionary. |
| Mutable before-write `actor` | The service reads `context.actor` after dispatch, so in-place changes or replacement determine the effective actor for subsequent checks. |
| Main before-query `query` | The builder reads `context.query` after dispatch, allowing edits or replacement before validation and planning. |
| After-write `current`, `candidate`, and `result` | These are snapshots, not storage handles or the final response. Their mutation does not change the service's stored state or returned node. |
| After-query `result` | The service takes the final `context.result` as its result list, accepting edits or replacement. |

All matching handlers share one context during a dispatch. A later handler
can see earlier edits, including a replaced query or result list. Deep copies
at service boundaries isolate callers and operation state; they are not
recreated between handlers. Identity and scope fields remain observational
metadata, not supported mutation channels.

Write hooks receive `NodeHookContext`. Create and ordinary patch check the
caller's submitted field write modes before dispatch; ordinary patch also
checks the current node's write ACL. The service copies the payload, performs
ordinary patch's hidden-reference preparation on that copy, and shares it
with the mutable before context. Trusted additions do not pass through a
second caller field-write check, but the candidate still passes schema
validation and the applicable remaining ACL and hierarchy checks. Changing
the actor does not undo checks that already rejected the operation.
See [ACL and field visibility](acl-and-field-visibility.md#hooks-are-trusted-application-code).

For an accepted write, after contexts distinguish the original `actor` from
the `effective_actor` left by before handlers. Their raw snapshots can include
fields hidden from the caller. In create and ordinary patch, the after-event
payload can also retain submitted Password values, while candidate and result
snapshots reflect transient-value removal before storage. Copying snapshots
does not make them safe to return or log as caller-visible data.

The after-write `result` is intentionally not a response transformation
channel. Create, ordinary patch, and ACL patch perform a subsequent read
through `NodeService.query()` to produce the returned node. Response
transformations belong in `after_query`, not in mutations of stored-node
snapshots. The complete write lifecycle is in [Request lifecycle](request-lifecycle.md#node-write-path).

## Query contexts belong to planning and execution

Query hooks use `NodeQueryHookContext`, not a partially populated write
context. `QueryBuilder.build_query()` deep-copies the query payload and
dispatches the main `before_query` context before normalizing the final query,
inferring its schema scope, and constructing the plan. Later handlers see
earlier query changes, but validation and planning consume the final query
after dispatch, not a separately built pipeline for each handler.

Linked-target contexts are created during lookup construction. Each has the
target module and the full resolution path; it has no independent editable
query. Its restrictions are returned to the lookup-building code rather than
executed by the handler. The contexts are per planned path, not per selected
node or Array item, and are dispatched before MongoDB has produced a result.
An eventually empty selection can still have invoked before-query handlers.

The builder returns a `BuiltQuery` containing the pipeline and the final
main query. `NodeService.query()` executes the pipeline, creates a fresh
after-query context with a query snapshot and the selected result list, then
dispatches `after_query` once. There is no after-query dispatch for each
linked-target context. The event sees the already projected and paginated
main result, including an empty list.

The service validates the final after-query result as a list of dictionaries.
It does not reapply schema visibility or node ACL to that transformed list,
nor does it refill a page shortened by a handler. `get()` selects the first
node from the final list and treats an empty list as not found. These are
trusted transformations, not another Mongo selection phase.

The query actor is separate from those mutation channels. The builder and
service authorize using the actor supplied to the read, not the context's
actor copy. A query handler cannot switch authorization by assigning that
attribute. Read helpers and write operations' final reads all use this shared
query path; internal schema discovery and raw write preparation do not become
query-hook dispatch points.

### Restrictions have separate ownership

Required filters and output exclusions are accumulated outside the editable
`query` dictionary. This is necessary because replacing that dictionary must
not discard restrictions already added by another handler.

`add_required_filter()` copies the supplied dictionary when it is added.
`required_filters` returns a deep-copied tuple snapshot, so modifying a
previous argument or an inspected snapshot cannot mutate the accumulated
conditions. `exclude_fields()` validates its path arguments before updating
a set, and `excluded_fields` returns a sorted tuple snapshot. Both mutation
methods check that the event is `before_query`.

The builder validates and compiles the collected filters, ANDs them with the
built-in read restrictions, and applies them to stored values. It prefixes
linked-target exclusions with the context's resolution path and collects them
for final output removal. These transformations belong in query planning,
not the registry or storage. See [Query-hook restrictions in the plan](query-builder.md#query-hook-restrictions-in-the-plan)
for their placement and their distinction from schema visibility.

## Recursive writes are service orchestration

The registry has no subtree traversal or batch-event semantics. `NodeService`
creates one context per affected active node and invokes the ordinary
dispatcher. The service determines the parent-before-descendant order, with
node ID ordering within a depth.

For recursive ACL patch, each node starts with its own copy of the original
payload and actor. An effective actor chosen for one node does not become the
initial actor for the next node. The service prepares and validates every
node before the bulk update, and records after-event snapshots only for nodes
whose ACL changes. Thus a no-op node can run a before hook without running an
after hook. The final response read uses the selected subtree root's effective
actor, not the last descendant's actor.

Subtree deletion has two dispatch passes over the same active-node snapshot:
all before events, then the bulk soft delete, then all after events. A failure
in the first pass prevents that delete. The common `deleted_count` supplied
afterwards is the operation's total, not a separate count for each node.

An ordinary move is different: descendant hierarchy maintenance does not
dispatch ordinary patch hooks for each descendant. Its `after_patch` event
belongs to the node being moved and runs after hierarchy updates finish.
Keep this distinction when changing bulk repository operations.

## Failure boundaries follow persistence

There is no exception recovery loop in `dispatch()`. Once a handler raises,
control returns through the service's normal error path. Domain exceptions
are preserved for Python callers and serialized by the REST layer, not by
the registry; see [Architecture](architecture.md#errors-and-transport).

An event's `before` or `after` name is relative to its own operation. A
`before_query` exception during a write's final response read happens after
the node write, even though it prevents that read from executing. Likewise,
after-write and after-query exceptions do not undo completed storage work.
Moving those dispatch points across persistence would change observable
failure semantics.

Preparing every node before a recursive bulk write prevents validation or
before-handler failures from applying only part of that planned write. It is
not a transaction around the handlers themselves, external effects, or the
full sequence of repository calls. If an after handler fails, later handlers
and later nodes' after events may not run even though the write is complete.

The dispatcher supplies no automatic retry, compensation, or exactly-once
delivery for side effects. Integrations need their own idempotency and
reconciliation where partial side effects or a retried request are possible.

## Reentrancy and request-local state

A handler calling a node service can enter the same registry again. There is
no automatic recursion suppression or hook-free nested-service mode. Query
hooks can re-enter during planning, before the outer query has even executed.
Keep nested calls intentional and bounded; do not solve recursion by silently
bypassing service invariants through raw repository access.

Services and their registered handlers are reused across requests. A handler
may capture container services, but request-specific actors, payloads, and
results belong to local variables and contexts, not shared module globals or
handler-instance attributes. Keep the same discipline when adding caches or
mutable state to built-in handlers.

When changing this subsystem, verify ordering across different scopes,
context ownership and supported replacements, isolation between containers
and requests, and exception timing relative to persistence. Check both main
queries and linked-target planning, plus recursive write phases. A new event
needs an explicit owner, context, mutation-consumption rule, and failure
boundary; adding its name to the registry alone does not define its behavior.
