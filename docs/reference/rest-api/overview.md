# REST API overview

Sandala's versioned REST API is served below:

```text
/api/v1/
```

For example, a local default installation exposes the API at
`http://localhost:3000/api/v1/`. The canonical endpoint paths in this reference
end with a trailing slash; clients should use those paths exactly.

This API manages modules, entity schemas, nodes, authentication, and uploads.
The public binary asset route `/assets/...` and the admin UI route `/admin/`
are deliberately outside the versioned API prefix.

## Request and response format

Most endpoints consume and produce JSON. A request that creates or changes one
resource usually wraps it in a named top-level object:

```json
{
  "node": {
    "entity": "Book",
    "title": "A Wizard of Earthsea"
  }
}
```

The corresponding response uses the same resource name:

```json
{
  "node": {
    "id": "…",
    "entity": "Book",
    "title": "A Wizard of Earthsea"
  }
}
```

The exact wrapper and request shape are part of each endpoint's contract. Do
not infer a wrapper from a similarly named endpoint: for example, node queries
use `query`, login uses `credentials`, and asset uploads use multipart form
data rather than a JSON body.

Send JSON requests with `Content-Type: application/json`. Asset upload
endpoints use `multipart/form-data`; their `target` and optional `transform`
parts are JSON strings inside that form.

## Authentication

An endpoint either requires an authenticated actor or explicitly permits an
anonymous request. Node reads and writes, for example, may be anonymous when
the relevant ACL and field modes allow them; metadata management and PAT
management require authentication.

Sandala recognizes two credentials:

- an auth-session cookie, intended for browser clients;
- a PAT in `Authorization: Bearer <id>.<secret>`, intended for programmatic
  clients.

When both are present, the Bearer token takes precedence. A successful
credential creates an actor whose current user ID, groups, and role are used by
node ACL and field-mode checks. See [Users and authentication](../../concepts/users-and-authentication.md)
for the underlying model.

## Resource access

Authentication is not by itself permission to access a resource. Node
endpoints apply node ACL, field visibility, and field write modes. A caller may
therefore receive a partial node document, or receive a not-found result for a
node that exists but is not readable to that actor.

Module and entity-schema endpoints are metadata operations with their own role
requirements. Each reference page states the relevant authorization rule.

## Errors and status codes

Application errors use a JSON object with a stable machine-readable `error`
code and a human-readable `error_description`. Some errors add structured
`details`, including field locations for validation failures.

```json
{
  "error": "request_body_invalid",
  "error_description": "Request body must be a JSON object"
}
```

Sandala maps validation, authentication, authorization, not-found, and
conflict errors to the usual `400`, `401`, `403`, `404`, and `409` status
codes. Unexpected failures return a safe `500` response without exposing the
internal exception. Framework-level HTTP errors such as an unknown route or an
unsupported method retain the framework's normal HTTP response rather than
using Sandala's application-error envelope.

The Errors reference defines the common error contract, including
`details.field_errors`.
