# Architecture

This page is for contributors. It describes the boundaries that let Sandala
run both as its bundled Flask application and as a library embedded in another
Python application. It is not a REST API reference; use the [Python API](../reference/python-api.md)
and [REST API](../reference/rest-api/overview.md) references for supported
integration contracts.

## Runtime shape

Sandala has three runtime layers. A request normally crosses them in one
direction:

```text
HTTP request
    │
    ▼
api                  Flask routes, request parsing, cookies, HTTP responses
    │
    ▼
core services        domain operations, authorization, validation, hooks, queries
    │
    ▼
storage repositories MongoDB and blob-storage access
    │
    ▼
MongoDB / filesystem / S3-compatible storage
```

`bootstrap.build_container()` is the composition root. It is deliberately
outside those layers: it reads the resolved configuration, creates storage
objects, gives them to the core services, and returns the resulting container.
The standard Flask application calls the same factory, so its domain behavior
and an embedded application's domain behavior are identical when they call the
same service with the same input and actor.

At import time, the important dependency rule is:

```text
api ───────────────► bootstrap, core
bootstrap ─────────► core, storage
core ──────────────► no api or Flask modules
storage ───────────► no core or api modules
```

Core services receive repository and blob-storage objects as constructor
dependencies. There is intentionally no formal repository-interface hierarchy:
the composition root supplies the concrete objects. This keeps the business
layer independent of MongoDB classes while avoiding an abstraction that has no
second implementation.

Keep external dependencies small. MongoDB access uses PyMongo directly rather
than a heavy ORM/ODM layer; core remains independent of the HTTP framework.
Add a dependency only for a substantial capability that the existing stack
does not reasonably provide, rather than introducing a parallel framework or
duplicating an existing subsystem.

## Package responsibilities

| Area | Owns | Does not own |
| --- | --- | --- |
| `sandala/api/` | Flask app factory, routes, request parsing, cookie handling, HTTP status codes, response wrappers, REST error serialization, and serving the bundled Admin UI. | ACL decisions, schema validation, query semantics, or persistence rules. |
| `sandala/core/` | Services, domain errors, node ACL and field-mode evaluation, schema and document validation, hooks, asset rules, authentication logic, and query/aggregation-pipeline planning. | Flask request objects, HTTP status codes, response serialization, or direct MongoDB connections. |
| `sandala/storage/` | MongoDB repositories and local-filesystem or S3-compatible blob operations. | Authorization, JSON Schema interpretation, link rules, hook dispatch, or REST formatting. |
| `sandala/bootstrap.py` | Configuration resolution, dependency construction, built-in users-module initialization, and returning the service container. | Request handling or endpoint-specific behavior. |
| `sandala/config.py` | Defaults, environment parsing, explicit-configuration precedence, and configuration normalization. | Connecting to MongoDB or changing application state at import time. |

The boundary is behavioral as well as structural. For example, a repository
may execute a Mongo aggregation pipeline, but it does not decide which ACL
predicates, lookups, projections, or visibility exclusions belong in that
pipeline.
`QueryBuilder` in `core` makes those decisions; `NodeRepository.aggregate()`
only executes the supplied pipeline.

## Composition and lifecycle

`build_container(config=None)` is the only place that wires Sandala's concrete
dependencies together. Its construction sequence is intentional:

1. resolve defaults, environment values, and the explicit configuration;
2. connect to MongoDB and construct repositories;
3. ensure indexes for the system repositories;
4. construct security and blob-storage services;
5. construct the module, entity, node, and asset services;
6. register the built-in users-module hooks and ensure the built-in users
   module, default group, and root user exist.
7. construct the authentication service.

Build one container at process startup and reuse its services for that process.
Importing `sandala` neither creates a global Flask app nor connects to a
database. Calling `build_container()` creates the database connection and
performs the initialization described above, but does not create a Flask app.
This makes independent application instances and test configurations possible.

`create_app(config=None)` is the Flask application factory. It registers error
handlers and built-in routes around a container, then loads configured
`HOOK_MODULES`. In contrast, an embedded application that calls
`build_container()` directly registers hooks itself. See [Writing hooks](../guides/writing-hooks.md)
and [Embedding Sandala](../guides/embedding-sandala.md).

## Service boundary

Services are the domain entry points. They accept ordinary Python values and,
for protected operations, an actor dictionary; operations that allow anonymous
access accept `None`. They do not accept Flask requests, response wrappers, or
HTTP-shaped bodies. For example, a REST route unwraps `{"node": ...}` before
calling `NodeService.create()`, while an embedded application passes the inner
node object directly.

Services are responsible for loading the data needed for an operation and
enforcing its invariants for both reads and writes. In particular, they own:

- module and entity metadata checks;
- node ACL, field visibility, and field write-mode decisions;
- schema validation and system-field management;
- node hierarchy maintenance, soft deletion, and ACL changes;
- hook dispatch for node reads and writes;
- query planning, including system restrictions, resolution, and final
  projection;
- asset target validation and binary-storage coordination;
- authentication and personal-access-token rules.

Routes may perform transport-specific validation that is impossible without
HTTP context, such as requiring a JSON body, decoding a JSON query parameter,
or reading a multipart upload. They then delegate the domain operation rather
than reproducing any item in the list above.

Do not use repositories from an integration to read or modify nodes, schemas,
or identities. Doing so bypasses service invariants. Two controlled internal
paths are deliberately different: users-module bootstrap creates its initial
metadata and nodes through repositories, and the demo-data seed validates
generated documents before a bulk repository write for speed. Neither is a
model for ordinary application writes or a test of the normal node write path.

## Errors and transport

Core code raises `SandalaError` subclasses. They carry a stable machine code,
a human-readable message, and optional structured details, but no HTTP status
or JSON response shape.

The Flask error handler maps domain error families to HTTP status codes and
serializes the REST error object. Unexpected exceptions are logged and become
HTTP 500 responses. An embedded host catches the same domain exceptions and
chooses its own RPC, job, CLI, or HTTP representation.

This separation is important: adding an HTTP status code or a `jsonify()` call
to `core` makes direct use harder and couples domain tests to Flask. Conversely,
an API route should not invent a second error taxonomy for an invariant already
expressed by a service.

## Where changes belong

When changing Sandala, start from the responsibility rather than the nearest
file:

| Change | Primary home | Typical companion work |
| --- | --- | --- |
| A new REST path or HTTP representation | `api/` | Call an existing or newly added service; update REST reference and transport tests. |
| A domain rule, authorization decision, or node lifecycle behavior | `core/services/`, `core/validation/`, or another focused core module | Add unit and, where storage behavior matters, integration coverage. |
| Query syntax, resolution, visibility, or pipeline semantics | `core/query/` and `QueryBuilder` orchestration | Preserve the query decomposition; add query-builder and relevant Mongo integration tests. |
| A MongoDB query or collection operation | `storage/mongo/` | Keep policy in the caller; wire any new repository dependency in `bootstrap.py`. |
| Blob backend I/O | `storage/blob/` | Keep asset descriptor and target rules in `AssetService`. |
| A configurable behavior | `config.py` | Document it in [Configuration](../reference/configuration.md) and pass it explicitly through the composition root. |
| An installation-specific business rule | a hook module or embedding host | Prefer the public hook and service boundaries over edits to Sandala internals. |
| Admin UI state, rendering, or data-fetching behavior | `admin-ui/` | Follow [Frontend architecture](frontend-architecture.md); never treat UI checks as authorization. |

## Contributor checklist

Before merging a backend change, check these architectural questions:

- Does `core` remain free of Flask and HTTP-response concerns?
- Is a REST route only translating transport data and delegating to a service?
- Does every ordinary application write pass through the appropriate service
  and its validation? Bootstrap and intentionally isolated bulk tools are the
  documented internal exceptions.
- Is storage code free of policy decisions that belong to a service or query
  planner?
- Is a new dependency constructed explicitly in `build_container()` rather
  than created as a hidden import-time singleton?
- Does the change belong in a specialized subsystem instead of growing a
  catch-all service or `QueryBuilder`?

The next development pages describe the request lifecycle and the specialized
subsystems behind these boundaries.
