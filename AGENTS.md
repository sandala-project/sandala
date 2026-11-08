# AGENTS

## Read first

Start with [Architecture](docs/development/architecture.md), then read the
documentation relevant to the task using the routing table below. Do not load
the entire documentation set for a focused change.

The English documentation in `docs/` defines the current public contracts and
development invariants. Check it against implementation and relevant tests;
report or resolve discrepancies rather than silently introducing another
interpretation.

## Documentation routing

Read the relevant pages before changing behavior, and update their canonical
contract or invariant when that behavior changes. Follow links to Concepts or
Guides when an explanation or worked example is affected too.

| Area | Primary documents |
| --- | --- |
| HTTP contracts and errors | [REST overview](docs/reference/rest-api/overview.md), the affected endpoint reference, and [Errors](docs/reference/rest-api/errors.md). |
| Modules and entity schemas | [Modules](docs/reference/rest-api/modules.md), [Entity schemas](docs/reference/rest-api/entity-schemas.md), [Semantic types](docs/reference/semantic-types.md), and [Validation and schema evolution](docs/development/validation-and-schema-evolution.md). |
| Node reads, filters, sorting, projection, and resolution | [Nodes](docs/reference/rest-api/nodes.md), [Query builder](docs/development/query-builder.md), and [Request lifecycle](docs/development/request-lifecycle.md). |
| Node ACL, field modes, and safe reference editing | [Permissions and ACL](docs/concepts/permissions-and-acl.md), [ACL and field visibility](docs/development/acl-and-field-visibility.md), and [Link patching](docs/development/link-patching.md). |
| Write and query hooks | [Node hooks reference](docs/reference/node-hooks.md), [Writing hooks](docs/guides/writing-hooks.md), and [Node hooks internals](docs/development/node-hooks.md). |
| Users, groups, authentication, sessions, and PATs | [Users and groups](docs/reference/rest-api/users-and-groups.md), [Authentication](docs/reference/rest-api/authentication.md), and [Bootstrap and the users module](docs/development/bootstrap-and-users-module.md). |
| Assets, repositories, indexes, and blob backends | [Assets](docs/reference/rest-api/assets.md) and [Storage](docs/development/storage.md). |
| Direct Python use and application composition | [Python API](docs/reference/python-api.md) and [Embedding Sandala](docs/guides/embedding-sandala.md). |
| Configuration, packaging, and deployment | [Configuration](docs/reference/configuration.md), [Installation](docs/getting-started/installation.md), and [Deployment](docs/getting-started/deployment.md). |
| CI, release automation, and documentation publication | [CI and releases](docs/development/ci-and-releases.md) and [Testing](docs/development/testing.md). |
| Admin UI behavior and implementation | [Admin UI](docs/reference/admin-ui.md), [Using the Admin UI](docs/guides/using-the-admin-ui.md), and [Frontend architecture](docs/development/frontend-architecture.md). |

## Working rules

- Change code, relevant tests, and documentation together when a public
  contract or observable behavior changes.
- Prefer established project patterns over new abstractions or helper modules
  that introduce a parallel way of doing the same work. Keep dependencies small;
  add one only for a substantial architectural or UX reason.
- For users/auth changes, inspect user and group hooks, bootstrap schemas and
  initialization, authentication services, and related documentation together.
- For query changes, preserve the query-builder invariants and verify the
  observable MongoDB behavior, not only the constructed pipeline.
- Treat visibility and ACL checks as security boundaries. Test the absence of
  hidden data as well as the presence of allowed results.

## Architecture boundaries

- `core` owns business logic, authorization, validation, hooks, and query
  planning. It must not depend on Flask, HTTP request objects, response
  serialization, or HTTP status codes.
- `api` owns HTTP parsing, request/response wrappers, cookies, and error
  serialization. Delegate domain decisions to services rather than duplicating
  them in routes.
- `storage` owns MongoDB and blob I/O, not ACL, schema interpretation, hook
  dispatch, or other domain policy. Keep driver-specific error classification
  here; core translates storage-level errors into domain errors.
- `bootstrap.py` constructs dependencies explicitly. Do not create application
  or database singletons with import-time side effects.

Keep policy in services and the query builder. Repositories execute operations
chosen by those layers; direct repository access is not an alternative public
integration API.

## Environment and backend checks

Use the project virtual environment from the repository root:

- Python: `./.venv/bin/python`
- Pytest: `./.venv/bin/python -m pytest`

Do not assume global `python` or `pytest` commands are available. Setup,
integration prerequisites, and coverage guidelines are in
[Testing](docs/development/testing.md).

Start with focused tests, then broaden the run in proportion to the change:

```bash
./.venv/bin/python -m pytest tests/test_node_api.py
./.venv/bin/python -m pytest tests/test_users_module.py tests/test_auth_api.py
./.venv/bin/python -m pytest -m 'not integration'
./.venv/bin/python -m pytest -m integration
```

Integration tests require Docker/Testcontainers; S3 scenarios also need the
optional S3 dependencies. Use isolated test resources, never a development or
production database. Inspect skip reasons: skipped integration tests are not
evidence that the behavior passed.

Respect task-specific testing instructions, including when the user is already
running a full suite. Report what was actually run and any failures or skips.

## Frontend

The separate React/TypeScript Vite application is in `admin-ui/`. Run its
commands from that directory:

- `npm run dev` — development server.
- `npm run check` — TypeScript checks.
- `npm run build` — TypeScript checks and production build.

After substantive frontend edits, run at least `npm run build` and verify
affected UI workflows as appropriate. The existing Playwright suite is only
a login-screen smoke test, not comprehensive workflow coverage.

Preserve schema-driven controls, metadata-cache and node-snapshot lifetimes,
localization, and the shared UI foundations. Backend validation and
authorization remain authoritative; do not recreate them as independent UI
business rules.

## Documentation changes

- Maintain Markdown in `docs/` as the single published source.
- Describe implemented behavior in the present tense. Do not turn a current
  contract into a proposal or promise unimplemented features.
- Keep Concepts conceptual, Guides task-oriented, Reference precise, and
  Development focused on implementation boundaries and invariants. Normative
  wording belongs in contributor constraints, not descriptions of existing
  behavior.
- Give each fact one canonical home. Link to it instead of repeating complete
  contracts or configuration tables across pages.
- Keep internal details and design reasoning in Development unless a caller
  needs them to use the public API correctly.

After each documentation edit, rebuild the site from the repository root:

```bash
./.venv/bin/zensical build
```

The root configuration is `zensical.toml`; generated output goes to
`.zensical/site/`. Check relative links and anchors, and update navigation when
adding or moving pages. Use `./.venv/bin/zensical serve` for local browsing.
