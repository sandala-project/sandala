# Python API

Sandala can run as a library inside another Python application. This is useful
when the application owns its HTTP or messaging interface, adds its own
business operations, or uses hooks without making an internal HTTP request.

The public Python boundary is `build_container()` and the services it returns.
Services apply the same validation, ACL, field-mode, schema, and hook rules as
the bundled REST API. They accept domain values directly: do not pass REST
wrappers such as `{"node": ...}` or `{"query": ...}` to them.

For configuration keys and precedence, see [Configuration](configuration.md).
For the HTTP contract, use the [REST API reference](rest-api/overview.md).

## Build a container

```python
import os

from sandala.bootstrap import build_container


container = build_container({
    "MONGO_URI": os.environ["SANDALA_MONGO_URI"],
    "MONGO_DB": os.environ["SANDALA_MONGO_DB"],
})

nodes = container["node_service"]
```

`build_container(config=None)` merges configuration in the normal order and
connects to MongoDB. It creates the required database indexes, installs the
built-in users-and-groups hooks, and ensures that the `users` module, default
group, and root user exist.

Build one container when the application process starts and reuse its services
for that process's requests and background work. Do not put secrets in the
Python configuration dictionary or source code. When connecting to an empty
database for the first time, provide `SANDALA_ROOT_PASSWORD` through the
deployment environment or a secret manager so bootstrap can create the root
user. After that initial bootstrap, a normal embedded application does not
need the root password.

The function returns a mapping with these supported service entries:

| Key | Service | Purpose |
| --- | --- | --- |
| `config` | dictionary | Fully resolved Sandala configuration. |
| `module_service` | `ModuleService` | Module management. |
| `entity_service` | `EntityService` | Entity-schema management. |
| `node_service` | `NodeService` | Node reads, queries, changes, ACL changes, and node hooks. |
| `asset_service` | `AssetService` | Asset upload and binary opening. |
| `auth_service` | `AuthService` | Password login, sessions, Bearer PAT authentication, and PAT management. |

The container also exposes repository objects for Sandala's own application
composition. They are storage-level implementation details; integrations
should use services instead, so Sandala can continue to enforce its invariants
and evolve its storage implementation.

`build_container()` does **not** import modules listed in `HOOK_MODULES`.
Register hooks directly in an embedded application. The standard Flask
application created by `create_app()` performs that automatic hook-module
loading.

## Actors and authorization

Every service method that operates on protected resources accepts an `actor`
keyword argument. Pass `None` for an anonymous caller. To obtain a trustworthy
authenticated actor, use `AuthService` rather than reconstructing one from a
client-supplied user document:

```python
auth = container["auth_service"]
nodes = container["node_service"]

actor = auth.authenticate_bearer(bearer_token)
book = nodes.get("library", book_id, actor=actor)
```

An actor returned by Sandala has this shape:

```python
{
    "user_id": "8b06138e-d43d-4dba-a185-bb8c61f814c4",
    "primary_group": "6bfaa146-ae0b-4431-9fca-75ba070093b8",
    "groups": ["6bfaa146-ae0b-4431-9fca-75ba070093b8"],
    "role": "admin",
    "auth_type": "pat"
}
```

`role` is `all`, `admin`, or `superuser`; `auth_type` is `session` or `pat`.
The node service uses the identity and group values for node ACL, and the role
for field modes and metadata operations. The authorization model is the same
as for the REST API; see [Permissions and ACL](../concepts/permissions-and-acl.md).

## Services

The service methods below are the supported direct equivalents of the REST
operations. Payloads use the object documented for the operation itself, with
its outer HTTP wrapper removed.

### Modules and entity schemas

```python
modules = container["module_service"]
entities = container["entity_service"]

module = modules.create_module(module_payload, actor=actor)
schema = entities.create("library", "Book", schema_payload, actor=actor)
```

| Service | Methods |
| --- | --- |
| `module_service` | `list_modules(actor=...)`, `get_module(name, actor=...)`, `create_module(payload, actor=...)`, `patch_module(name, payload, actor=...)`, `delete_module(name, actor=...)` |
| `entity_service` | `list_entities(module, actor=...)`, `get_schema(module, entity, actor=...)`, `create(module, entity, schema, actor=...)`, `update(module, entity, schema, actor=...)`, `delete(module, entity, actor=...)` |

Module payloads and entity schemas have exactly the shapes in [Modules](rest-api/modules.md)
and [Entity schemas](rest-api/entity-schemas.md). In particular, supply a
schema document directly to `entity_service.create()` and `update()`, rather
than an `{"entity": schema}` wrapper.

### Nodes

```python
nodes = container["node_service"]

book = nodes.create(
    "library",
    "Book",
    {"title": "A Wizard of Earthsea"},
    actor=actor,
)

results = nodes.query(
    "library",
    {
        "filter": {"entity": "Book", "title": {"regex": "Earth"}},
        "project": ["title", "author.name"],
        "sort": {"title": "asc"},
    },
    actor=actor,
)
```

| Method | Direct payload and result |
| --- | --- |
| `create(module, entity, payload, actor=...)` | Creates a node from its field object and returns the created node. |
| `query(module, payload, actor=...)` | Returns a list for a query object containing optional `project`, `filter`, `sort`, `limit`, and `offset`. |
| `get(module, node_id, project=..., actor=...)` | Returns one readable node. Omit `project` for the single-node default resolution. |
| `list_entity(module, entity, payload, actor=...)` | Returns nodes of one entity. It applies the entity restriction independently of the user-supplied filter. |
| `patch(module, node_id, payload, actor=...)` | Applies the ordinary shallow node patch and returns the updated node. ACL fields use `patch_acl()` instead. |
| `patch_acl(module, node_id, payload, recursive=False, actor=...)` | Changes `owner`, `group`, and/or `perm`; returns `{"node": ..., "updated_count": ...}`. |
| `delete(module, node_id, actor=...)` | Soft-deletes the active node and active descendants; returns the number of deleted nodes. |

The node query language, projection defaults, link resolution, and patch
semantics are identical to [Nodes](rest-api/nodes.md). `query()` and
`list_entity()` receive the inner query object, not `{"query": ...}`.

### Node hooks

`node_service.hooks` is a `NodeHookRegistry`. Register a callable that accepts
one context argument:

```python
def normalize_title(context):
    if context.payload and "title" in context.payload:
        context.payload["title"] = context.payload["title"].strip()


nodes.hooks.register(
    "before_create",
    normalize_title,
    module="library",
    entity="Book",
    priority=100,
)
```

The [Node hooks reference](node-hooks.md) defines registration scopes,
ordering, every write and query event, context fields, supported changes,
and failure behavior. See [Writing node hooks](../guides/writing-hooks.md)
for installation and practical examples.

### Assets

```python
assets = container["asset_service"]

with open("cover.png", "rb") as source:
    descriptor = assets.store_image(
        source,
        filename="cover.png",
        target={
            "module": "library",
            "entity": "Book",
            "field": "cover",
        },
        transform={"format": "webp", "width": 640},
        actor=actor,
    )
```

| Method | Purpose |
| --- | --- |
| `store_image(file_obj, *, filename=None, content_type=None, target, transform=None, actor=None)` | Stores an image for an `Image` or `RichText` schema context and returns an image descriptor. |
| `store_file(file_obj, *, filename=None, content_type=None, target, actor=None)` | Stores a file for a `File` context and returns a file descriptor. |
| `store_video(file_obj, *, filename=None, content_type=None, target, actor=None)` | Stores a video for a `Video` context and returns a video descriptor. |
| `store_image_from_path(path, **kwargs)`, `store_file_from_path(path, **kwargs)`, `store_video_from_path(path, **kwargs)` | Path-based forms of the corresponding stream methods. |
| `open_asset(storage_key)` | Returns `AssetOpenResult(storage_key, mime_type, size, stream)` for custom binary delivery. |
| `open_descriptor(descriptor)` | Opens an asset addressed by a Sandala-generated descriptor URL and returns the same `AssetOpenResult`. |

`file_obj` is a binary file-like object. `target` is the same schema-context
object as for HTTP uploads: it contains `module`, `entity`, and a dot-path
`field`. The service validates that context and its field write mode, but it
does not read or change a node. Asset descriptors and public-delivery behavior
are described in [Assets](rest-api/assets.md).

`open_descriptor()` is useful in hooks that create a derivative from an
already stored image. It understands both the default `/assets/...` URL and a
descriptor URL produced with `ASSET_PUBLIC_BASE_URL`. A descriptor URL without
a Sandala `/assets/...` path raises `AssetStorageKeyInvalidError`. The method
opens the configured storage backend directly; an S3 backend still makes its
own network request to S3.

### Authentication and PATs

```python
auth = container["auth_service"]

login = auth.login({"login": "alex", "password": password})
session_id = login["session_id"]
actor = login["actor"]
```

| Method | Result |
| --- | --- |
| `login(payload)` | Accepts `login` and `password`; returns `status`, a new `session_id`, and `actor`. |
| `logout(session_id)` | Revokes the session when the ID is present; otherwise does nothing. |
| `authenticate_bearer(token)` | Returns the authenticated PAT actor or raises `AuthenticationError`. |
| `authenticate_session(session_id)` | Returns the authenticated session actor or raises `AuthenticationError`. |
| `authenticate_request(bearer_token=..., session_id=...)` | Returns `None` for no credential, otherwise an authentication result with `actor`; Bearer takes precedence. The result can request session renewal. |
| `create_pat(payload, actor=...)`, `list_pats(actor=...)`, `get_pat(id, actor=...)`, `revoke_pat(id, actor=...)`, `rotate_pat(id, actor=...)` | Direct equivalents of the PAT operations. Create and rotate return the secret token once. |

In an embedded browser application, its transport layer owns cookie parsing,
setting, and renewal. Sandala's core authentication service deals only with
the raw session ID. See [Authentication](rest-api/authentication.md) for the
credential and PAT representations.

## Exceptions

Services raise ordinary Python exceptions rather than HTTP responses. All
Sandala domain errors inherit from `SandalaError` and provide `code`,
`message`, and optional structured `details`:

```python
from sandala.core.errors import SandalaError

try:
    node = nodes.get("library", book_id, actor=actor)
except SandalaError as error:
    log.error("Sandala request failed: %s (%s)", error.message, error.code)
    raise
```

The main error families are `ValidationError`, `AuthenticationError`,
`AuthorizationError`, `NotFoundError`, and `ConflictError`. Error codes have
the meanings described in [REST API errors](rest-api/errors.md), but the
service-level `details` are not always identical to the REST representation.

For JSON Schema validation failures, direct callers receive
`details["validation_errors"]`, a list of dictionaries with these fields:

| Python field | Meaning | REST field in `details.field_errors` |
| --- | --- | --- |
| `path` | Path to the affected field or container, as a list of strings and integers. | `location` |
| `validator` | JSON Schema keyword that failed validation. | `keyword` |
| `raw_message` | Original validation message. | `message`, with missing-required-property messages normalized for display. |

The REST layer performs this conversion; direct service calls do not. Domain
errors that already carry `details["field_errors"]` retain that structure in
both interfaces. An embedded application decides how to map exceptions to its
own transport format.

Hook exceptions also reach the direct caller. Their effects on reads, writes,
and side effects are described in [Errors and side
effects](node-hooks.md#errors-and-side-effects).
