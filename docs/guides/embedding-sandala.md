# Embedding Sandala

Sandala can run inside a Python application that owns its own HTTP, RPC,
message-consumer, or background-job interface. The host application decides
which operations exist publicly and how its responses look; Sandala services
continue to enforce schemas, node ACL, field modes, link rules, and hooks.

This guide is for that embedded mode. If the bundled REST API and admin UI are
the intended public interface, use the ordinary installation instead.

## Build one container at process startup

Create a container once for each application process, then reuse its services
for requests and background work. Do not create one per request.

```python
import os

from sandala.bootstrap import build_container


container = build_container({
    "MONGO_URI": os.environ["SANDALA_MONGO_URI"],
    "MONGO_DB": os.environ["SANDALA_MONGO_DB"],
})

nodes = container["node_service"]
assets = container["asset_service"]
auth = container["auth_service"]
```

Container construction resolves configuration, creates Sandala's required
indexes, registers built-in user hooks, and bootstraps the `users` module,
default group, and root user when required. Supply the initial root password
through the process environment or a secret manager, not Python source code.

The container includes storage repositories too, but they are implementation
details. Call `module_service`, `entity_service`, `node_service`,
`asset_service`, and `auth_service` rather than reading or changing MongoDB
documents directly.

## Pass domain payloads, not REST wrappers

Service calls receive the value inside the REST request wrapper. For example,
the REST API accepts `{"node": {...}}` for a node create; an embedded call
receives only the inner field object:

```python
book = nodes.create(
    "library",
    "Book",
    {"title": "A Wizard of Earthsea", "year": 1968},
    actor=actor,
)
```

The same rule applies to query and metadata operations:

```python
books = nodes.list_entity(
    "library",
    "Book",
    {
        "project": ["title", "year", "author.name"],
        "filter": {"year": {"gte": 1960}},
        "sort": {"title": "asc"},
    },
    actor=actor,
)

schema = container["entity_service"].get_schema("library", "Book", actor=actor)
```

Reading schema metadata requires an actor with the `admin` or `superuser` role.

Do not pass `{"query": ...}`, `{"module": ...}`, `{"entity": ...}`, or
other REST transport wrappers to services. The complete service-method table
is in the [Python API reference](../reference/python-api.md).

## Authenticate at the host boundary

An embedded application owns parsing credentials and choosing its own
authentication policy. To use Sandala's sessions and PATs, extract a Bearer
token and the configured session cookie, then call `authenticate_request()`:

```python
from sandala.core.errors import AuthenticationError


def authenticate_request(request):
    authorization = request.headers.get("Authorization")
    bearer_token = None
    if authorization:
        scheme, separator, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not separator or not token.strip():
            raise AuthenticationError("Invalid authorization header")
        bearer_token = token.strip()

    session_cookie = container["config"]["AUTH_SESSION_COOKIE_NAME"]
    session_id = request.cookies.get(session_cookie)

    return auth.authenticate_request(
        bearer_token=bearer_token,
        session_id=session_id,
    )
```

The result is `None` when no credential was provided. An invalid, expired, or
revoked credential raises `AuthenticationError`. When both credentials are
provided, a Bearer PAT takes precedence over the session cookie. A successful
result contains an `actor` for service calls:

```python
auth_result = authenticate_request(request)
if auth_result is None:
    raise YourUnauthenticatedResponse()

actor = auth_result["actor"]
```

Pass this actor unchanged to Sandala services. Do not construct an actor from
user-controlled claims, headers, or a user node received from the client.

### Preserve session renewal

`authenticate_request()` can renew a valid session near its idle expiry. When
the returned `renew_session` is true, the host must issue its normal session
cookie again with the returned `session_id`. Use the cookie name, domain,
path, secure, HTTP-only, SameSite, and max-age settings from
`container["config"]`; cookie construction is deliberately outside Sandala
core.

For a login endpoint, call `auth.login()` with the inner credentials object,
set a cookie from its `session_id`, and use its `actor` if the response needs
authenticated work. For logout, call `auth.logout(session_id)` and clear the
same cookie. The [authentication reference](../reference/rest-api/authentication.md)
defines Sandala's built-in HTTP behavior; an embedded application may expose a
different transport contract.

## Implement a focused endpoint

The host can expose an operation that is narrower than any REST endpoint while
still delegating data rules to Sandala. This framework-neutral example creates
a Book from a request body that is already parsed as JSON:

```python
from sandala.core.errors import AuthenticationError, SandalaError


def create_book(request):
    auth_result = authenticate_request(request)
    if auth_result is None:
        raise AuthenticationError("Authentication required")

    body = request.json
    if not isinstance(body, dict):
        raise YourBadRequestResponse("Body must be an object")

    try:
        book = nodes.create(
            "library",
            "Book",
            body,
            actor=auth_result["actor"],
        )
    except SandalaError as error:
        raise translate_sandala_error(error) from error

    return {"book": book}
```

`translate_sandala_error()` belongs to the host application. It can preserve
Sandala's `code`, `message`, and `details`, or map them to another public
format. Do not catch arbitrary `Exception` as a client error: unexpected
exceptions are application failures and should be logged and handled as such.

Sandala checks whether this actor can create the node at its parent, write the
submitted fields, and satisfy the entity schema. The host may add a separate
product rule before the call, such as allowing this endpoint only to a
particular tenant or application role.

## Use assets and hooks directly

`asset_service` is the direct equivalent of the upload endpoints. It takes a
binary stream and a schema-context `target`; it does not read or patch a node.

```python
with open("cover.png", "rb") as source:
    cover = assets.store_image(
        source,
        filename="cover.png",
        target={"module": "library", "entity": "Book", "field": "cover"},
        actor=actor,
    )

nodes.patch("library", book_id, {"cover": cover}, actor=actor)
```

The asset target still enforces its schema field's write mode, and the patch
still enforces the target node's ACL and field mode. For storage and delivery
semantics, see [Managing assets](managing-assets.md).

`build_container()` does not import `HOOK_MODULES`. Register integration hooks
on `container["node_service"].hooks` during host startup:

```python
def normalize_title(context):
    if context.payload and isinstance(context.payload.get("title"), str):
        context.payload["title"] = context.payload["title"].strip()


nodes.hooks.register(
    "before_create",
    normalize_title,
    module="library",
    entity="Book",
)
```

The [Writing hooks](writing-hooks.md) guide covers event timing, mutation
boundaries, errors, and derived assets.

## Keep background work explicit

Workers and scheduled jobs use the same services, but they have no HTTP
credentials to authenticate. Give them a deliberately chosen, trusted actor
whose authority matches the job. Never use an actor supplied in a queued job
payload without re-authenticating or otherwise verifying it.

Because the service layer is the shared enforcement point, using it from HTTP
handlers, workers, and hooks keeps validation and permission behavior aligned.
For the complete public surface, exception families, and actor representation,
refer to the [Python API reference](../reference/python-api.md).
