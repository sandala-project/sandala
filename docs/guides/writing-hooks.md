# Writing node hooks

Node hooks let an integration run trusted Python code around Sandala node
reads and changes. They are useful for domain-specific read restrictions,
normalization, validation, derived values, and side effects such as notifying
another system.

Hooks belong to `NodeService`, so the same registrations apply to requests
made through the bundled REST API and to calls made through the
[Python API](../reference/python-api.md). They are not an HTTP middleware and
do not need an internal HTTP request to use Sandala services.

Use hooks for rules specific to an installation. Keep reusable schema and ACL
rules in the entity schema and Sandala permission model instead.

The [Node hooks reference](../reference/node-hooks.md) defines every event,
context field, supported change, and failure behavior. This guide focuses on
setup and integration examples.

## Register a hook module for the REST application

Put the integration code in an importable Python module. Each configured
module exposes a callable `register_hooks(app, container)` function. The
container gives it access to the public services:

```python
# my_project/sandala_hooks.py
from sandala.core.errors import ValidationError


def normalize_book_title(context):
    if context.payload is None or "title" not in context.payload:
        return

    title = context.payload["title"]
    if not isinstance(title, str):
        raise ValidationError("Book title must be a string")

    normalized = title.strip()
    if not normalized:
        raise ValidationError("Book title cannot be blank")

    context.payload["title"] = normalized


def register_hooks(app, container):
    hooks = container["node_service"].hooks
    hooks.register(
        "before_create",
        normalize_book_title,
        module="library",
        entity="Book",
    )
    hooks.register(
        "before_patch",
        normalize_book_title,
        module="library",
        entity="Book",
    )
```

Make the module available to the application process, then configure its
import path. In an environment-based deployment, use a comma-separated list:

```bash
SANDALA_HOOK_MODULES=my_project.sandala_hooks python -m sandala.api
```

The equivalent `HOOK_MODULES` Python configuration value is a list of strings:

```python
{
    "HOOK_MODULES": ["my_project.sandala_hooks"],
}
```

Sandala imports configured modules while it creates the Flask application. A
module that cannot be imported, or that does not provide a callable
`register_hooks`, stops application startup. This makes a deployment problem
visible instead of silently starting without its business rules.

When Sandala is embedded through `build_container()`, it deliberately does not
autoload `HOOK_MODULES`. Register directly on the returned service during the
host application's startup:

```python
container = build_container(config)
container["node_service"].hooks.register(
    "before_create",
    normalize_book_title,
    module="library",
    entity="Book",
)
```

See [Configuration](../reference/configuration.md#hooks-and-admin-ui) and the
[Python API](../reference/python-api.md) for the surrounding setup.

## Scope and order hooks deliberately

Write-hook registrations can apply globally, to a module, or to one entity:

```python
hooks.register("before_patch", audit_change)  # Every node in every module.
hooks.register("before_patch", audit_library, module="library")
hooks.register(
    "before_patch",
    normalize_book_title,
    module="library",
    entity="Book",
    priority=50,
)
```

Lower `priority` values run first. Use explicit priorities only when one hook
really depends on another hook's output. Otherwise, independently scoped
hooks are easier to maintain. The complete scope and ordering rules are in
[Registration and ordering](../reference/node-hooks.md#registration-and-ordering).

Query hooks use the same priority ordering, but can be registered only
globally or for a module, not for an entity. A query may consider several
entity types together. See [Customize node reads](#customize-node-reads).

## Choose a write event

Use `before_create` or `before_patch` when a rule must validate or change data
before it is stored. Use `before_acl_patch` for ACL-specific changes and
`before_delete` to reject a deletion. After-write events are useful for
notifications and other side effects, not for changing the saved node.

Each receives a `NodeHookContext`. The event table and complete field
definitions are in [Write hooks](../reference/node-hooks.md#write-hooks).
Changing the actor is an advanced authorization capability; reserve it for
small, trusted adapters rather than ordinary business logic.

### Create and ordinary patch

Use `before_create` and `before_patch` for rules that affect node fields. The
example above trims a title only when the caller actually supplied `title`, so
the patch form does not invent a value for an unrelated edit.

Use `current` in a patch hook when a decision needs the stored value:

```python
def prevent_isbn_change(context):
    if context.payload is None or "isbn" not in context.payload:
        return
    if context.current and context.current.get("isbn"):
        raise ValidationError("ISBN cannot be changed after it is assigned")
```

Password values are available to `before_create` and `before_patch` hooks.
This supports an integration that derives a separate stored value, such as a
password hash. Sandala removes `Password` fields before persisting a created
or normally patched node. The [Password semantic type](../reference/semantic-types.md#password-is-transient)
describes that contract and its schema restrictions.

### Generate a derived image

A common use of a `before_create` or `before_patch` hook is to create a
preview alongside a newly supplied image. For example, a Book schema can have
two `Image` fields: `cover` for the original and `cover_preview` for a 320 px
WebP rendition. The hook below adds the preview only when a request supplies
a new `cover` descriptor.

Add these functions to the existing hook module, then call
`register_cover_preview_hooks()` from its existing `register_hooks()` function.

```python
def make_cover_preview(asset_service):
    def create_cover_preview(context):
        if context.payload is None or "cover" not in context.payload:
            return

        original = asset_service.open_descriptor(context.payload["cover"])
        try:
            preview = asset_service.store_image(
                original.stream,
                filename="cover-preview.webp",
                target={
                    "module": context.module,
                    "entity": context.entity,
                    "field": "cover_preview",
                },
                transform={"format": "webp", "width": 320},
                actor=context.actor,
            )
        finally:
            original.stream.close()

        context.payload["cover_preview"] = preview

    return create_cover_preview


def register_cover_preview_hooks(hooks, asset_service):
    create_cover_preview = make_cover_preview(asset_service)
    for event in ("before_create", "before_patch"):
        hooks.register(
            event,
            create_cover_preview,
            module="library",
            entity="Book",
        )
```

For example, extend the `register_hooks()` function shown earlier with:

```python
register_cover_preview_hooks(
    container["node_service"].hooks,
    container["asset_service"],
)
```

`AssetService.open_descriptor()` reads the original stream through Sandala's
configured storage backend, rather than requesting the public descriptor URL
through a delivery route, CDN, or reverse proxy. With an S3 backend this still
uses the S3 client's network request. It accepts a descriptor returned by
Sandala upload, including one whose URL uses `ASSET_PUBLIC_BASE_URL`. An
external URL without Sandala's `/assets/...` path cannot be opened this way.
`store_image()` validates and stores a fresh derived asset, then returns the
descriptor assigned to `cover_preview`.

The target field used for the derived asset must be an `Image` field whose
write mode permits the effective actor. `AssetService` checks the target
schema and its field write mode even when it is called from a hook. Use the
same permissions deliberately for `cover` and `cover_preview`, or provide a
trusted actor adapter when that is appropriate for the integration.

The preview binary is stored before the surrounding node write completes. If
later validation or the node save fails, the newly stored preview can remain
unreferenced. Likewise, replacing a cover creates a new preview rather than
deleting the old one. Plan cleanup for an integration that creates many
derivatives.

### ACL patch

`before_acl_patch` is specific to the ACL operation. Its payload may contain
only `owner`, `group`, and `perm`; keep it that way when changing it. Sandala
rechecks both this restriction and the ACL values after the hook runs.

Write recursive ACL handlers to be safe for repeated calls. For example, an
audit event should include `context.node_id` rather than assuming one callback
per HTTP request. See [Recursive operations](../reference/node-hooks.md#recursive-operations)
for which nodes receive each event.

### Delete

Use `before_delete` to reject deletion when it violates a business rule, and
`after_delete` for notifications. Deleting a node also affects its active
descendants, so do not assume a hook is called only for the node named in the
request. The [recursive-operation contract](../reference/node-hooks.md#recursive-operations)
defines event order and the meaning of `deleted_count`.

## Customize node reads

Use `before_query` to adjust a query or add read restrictions, and
`after_query` to transform its returned data. These handlers receive
`NodeQueryHookContext`, rather than the write-event context. See
[Query hooks](../reference/node-hooks.md#query-hooks) for the event table,
context fields, and supported changes.

### Add a module-wide read rule

Suppose Book has a Boolean `published` field, and records in `library` may
also contain `internal_notes`. This hook shows ordinary readers only published
Books and omits notes from responses, while leaving other entity types
available:

```python
def restrict_library_reads(context):
    if (context.actor or {}).get("role") in {"admin", "superuser"}:
        return

    context.add_required_filter({
        "or": [
            {"entity": {"neq": "Book"}},
            {"published": True},
        ]
    })
    context.exclude_fields("internal_notes")


def register_read_hooks(hooks):
    hooks.register(
        "before_query",
        restrict_library_reads,
        module="library",
    )
```

Call `register_read_hooks(container["node_service"].hooks)` from the hook
module's `register_hooks()` function. Do not pass `entity="Book"`: query hooks
are module-wide. Express entity-specific selection rules in the filter itself
so they also work for queries that mix entity types.

The same module rule applies when library nodes are resolved through links,
including links from another module. `before_query` runs for the main query
and each resolved link path, not for every returned node. The handler above
therefore needs no manual traversal of linked objects. Its role check is an
explicit choice: query-hook restrictions do not automatically exempt
superusers.

Use `add_required_filter()` for mandatory conditions rather than replacing
the client's `filter`. Required conditions combine with the client's query.
They cannot enter a link's target fields: put restrictions on Author reads in
the Author module's hook instead. See [Required
filters](../reference/node-hooks.md#required-filters) for the stored-value rules.

`exclude_fields()` only removes output fields. In this example, it does not
prevent an otherwise valid query from filtering or sorting by `internal_notes`.
Use schema visibility modes if the field must be unavailable to client
queries, not merely omitted from responses.

### Adjust the main query

The main query selects the nodes returned directly by the read operation.
Its `context.query` is an editable query dictionary. For linked-target contexts
it is `None`, so check `context.is_lookup` before changing it. For example, a
hook can provide a default page size:

```python
def default_page_size(context):
    if not context.is_lookup:
        context.query.setdefault("limit", 100)


hooks.register("before_query", default_page_size, module="library")
```

This is a default, not an enforced maximum. The resulting query still follows
the ordinary validation rules. Query hooks cannot change the actor used for
authorization; use `context.actor` only to decide which rules to add.

### Transform the selected result

`after_query` receives the final result of the main query in `context.result`,
including when it is empty. For example, an integration can add a display hint:

```python
def add_display_hint(context):
    for node in context.result:
        title = node.get("title")
        if isinstance(title, str):
            node["display_hint"] = title.upper()


hooks.register("after_query", add_display_hint, module="library")
```

The added value is not stored and does not need to be a schema field. Assign
to `context.result` to replace the list; returning a value from the handler
does not replace it. For all supported transformations, see
[Query and result changes](../reference/node-hooks.md#query-and-result-changes).

This result has already been projected, sorted, and paginated. Use a required
filter for selection rules rather than dropping rows afterward, which can
leave short pages. Transform only data safe to return: Sandala does not apply
ACL and visibility checks again after the handler.

Keep read handlers free of assumptions that the caller used a collection
endpoint: they also participate in the final reads after writes. Custom read
rules do not authorize writes or extend automatic protection of hidden links;
see [Protection of ACL-hidden
links](../reference/rest-api/nodes.md#protection-of-acl-hidden-links).

## Return errors clients can understand

Raise a `SandalaError` subclass for an expected business rejection. For a
general validation failure, `ValidationError` is usually enough:

```python
from sandala.core.errors import ValidationError


def require_review_note(context):
    if context.payload and context.payload.get("status") == "published":
        if not context.payload.get("review_note"):
            raise ValidationError("A review note is required before publishing")
```

Through REST, Sandala turns this into its normal structured error response.
Through the Python API, the same exception reaches the caller. An unrelated
Python exception is treated as an internal error by REST, so do not use it for
ordinary input validation. The [REST error reference](../reference/rest-api/errors.md)
defines the response envelope.

Choose a before-write event for a rejection that must prevent saving. Use
after-write hooks for idempotent side effects, and arrange retry or
reconciliation when an external call can fail. A failure after the write,
including in a query hook preparing its response, does not roll the write
back. See [Errors and side effects](../reference/node-hooks.md#errors-and-side-effects)
for the complete failure contract.

## Keep hooks focused and test them

Hooks run in the request path. Keep them fast, deterministic, and narrow:

- use schemas for field shape and field access, and built-in ACL for node
  permissions; add installation-specific read restrictions through query hooks;
- avoid network calls in `before_*` hooks unless the operation genuinely depends
  on the result;
- make after-write integrations idempotent, because a caller can retry after an
  error even though the node was saved;
- test both the handler's domain cases and its registration scope through the
  relevant `NodeService` operation.

The public integration boundary is the [Node hooks
contract](../reference/node-hooks.md). Avoid
coupling a hook module to Sandala's repositories or HTTP route internals.
