# Querying nodes

Sandala has one query language for node collections. Use it to select fields,
filter values, resolve links, sort results, and paginate them. Queries always
respect active-node status, node read ACL, and field visibility; a client never
adds those restrictions itself. Integrators can add further read restrictions
through query hooks.

This guide focuses on practical query design. The complete parameter and
operator reference is in [Nodes](../reference/rest-api/nodes.md); the meaning
of stored and resolved links is in [Links and resolution](../concepts/links-and-resolution.md).

Examples use the `library` module and a cookie established as in the
[Quickstart](../getting-started/quickstart.md).

## Choose the read endpoint

Choose the endpoint from the scope of the result, not merely from the request
method:

| Need | Endpoint | Useful default |
| --- | --- | --- |
| One known node | `GET /nodes/{module}/{id}/` | Resolves visible user-defined links, owner, and group. |
| Nodes of one known entity | `POST /nodes/{module}/entity/{entity}/query/` | Fixes the entity and has the same convenient default resolution. |
| A cross-entity collection | `POST /nodes/{module}/query/` | Returns visible fields without requesting link resolution by default. |

The entity-scoped endpoint is usually the best choice for a table, picker, or
report containing one entity type. Its path restriction cannot be bypassed by
the request filter. Use the general endpoint when records of several entities
are genuinely needed together.

Every collection request sends its parameters inside a `query` wrapper:

```json
{
  "query": {
    "project": ["title", "year"],
    "filter": {"year": {"gte": 1960}},
    "sort": {"title": "asc"},
    "limit": 25,
    "offset": 0
  }
}
```

## Browse one entity

This request lists Books published since 1960, returns a small resolved author
summary, and orders the results by title:

```bash
curl --fail-with-body --silent --show-error \
  --request POST \
  --cookie "$COOKIE_JAR" \
  --header 'Content-Type: application/json' \
  --data '{
    "query": {
      "project": ["id", "entity", "title", "year", "author.name"],
      "filter": {"year": {"gte": 1960}},
      "sort": {"title": "asc"},
      "limit": 25,
      "offset": 0
    }
  }' \
  "$SANDALA_URL/nodes/library/entity/Book/query/"
```

The response is always an object with a `nodes` array:

```json
{
  "nodes": [
    {
      "id": "…",
      "entity": "Book",
      "title": "A Wizard of Earthsea",
      "year": 1968,
      "author": {
        "name": "Ursula K. Le Guin"
      }
    }
  ]
}
```

The entity path already limits the query to Book; no `filter.entity` is needed.

## Scope a general query early

The general query endpoint can span all schemas in a module. When a client
knows which entity types it needs, state that at the top level of `filter`:

```json
{
  "query": {
    "filter": {
      "entity": {"in": ["Book", "Magazine"]},
      "published": true
    },
    "project": ["entity", "title", "published"],
    "sort": {"title": "asc"}
  }
}
```

This makes the intended collection clear and lets Sandala validate paths
against only the relevant schemas. It can also reduce the work done before
link resolution. Keep selective conditions on direct scalar fields at the
top level where practical.

Moving the entity condition into a logical group can broaden the schemas
considered for path validation. See [Early filter
narrowing](../reference/rest-api/nodes.md#early-filter-narrowing) for the exact
optimization rules and the distinction between filtering early and narrowing
the schema scope.

If an unscoped query enters a field that is a Link in one entity but a scalar,
another reference kind, or invisible in another, Sandala rejects the query
instead of guessing. Scope by `entity` or use an entity-scoped endpoint to
avoid unrelated schema collisions.

## Select only the fields you need

`project` controls both the response shape and whether a path through a Link
is resolved. A small explicit projection is normally the best choice for a
list view or API integration:

```json
{
  "project": ["title", "year", "author.name"]
}
```

This returns `title` and `year`, and replaces the stored `author` UUID with an
object containing only `name`. Selecting `author` itself does not request
resolution; `author.*` resolves the target and selects all its visible fields.

Paths in `project`, `filter`, and `sort` jointly determine which links resolve;
`project` determines which fields appear in the response. A selected link can
therefore be returned as an object because a filter or sort enters it.
Filtering or sorting through a link does not by itself select it for the
response.

`["*"]` selects all visible fields without itself requesting link resolution.
An explicit `project` replaces the endpoint's default projection. See
[Projection and resolution](../reference/rest-api/nodes.md#projection-and-resolution)
for those defaults and the full projection rules.

## Filter direct fields

At the simplest level, field conditions are combined with an implicit AND:

```json
{
  "filter": {
    "language": {"eq": "en"},
    "year": {"gte": 1960, "lt": 1970},
    "tags": {"in": ["fantasy", "classic"]}
  }
}
```

Use a scalar value as equality shorthand, for example `"published": true`.
Use `and`, `or`, or `not` with non-empty arrays of filter objects when the
logic needs grouping:

```json
{
  "filter": {
    "and": [
      {"published": true},
      {
        "or": [
          {"year": {"lt": 1970}},
          {"year": {"gte": 2020}}
        ]
      }
    ]
  }
}
```

The supported comparison, membership, existence, array-size, and regular-
expression operators are listed in the [filter reference](../reference/rest-api/nodes.md#filtering).
Array matching follows MongoDB query semantics; test an intended array filter
against representative data instead of assuming SQL-style row behavior.

Standard reads include only active nodes that the actor may read. A client
cannot filter on `deleted`; a non-superuser also cannot filter on `perm` or its
children. A query that explicitly names an invisible field in `project`,
`filter`, or `sort` fails validation rather than silently returning a partial
interpretation.

## Filter and sort through a link

Enter a link path to work with the target node. The examples in this section
use `POST /nodes/library/entity/Book/query/`. This query finds Books by a given
author and returns an author summary:

```json
{
  "query": {
    "filter": {
      "author.name": {"eq": "Ursula K. Le Guin"}
    },
    "project": ["title", "author.name"],
    "sort": {"author.name": "asc", "title": "asc"}
  }
}
```

Sandala resolves the target for `author.name`, applies the target's active-
node status, read ACL, field visibility, and link-entity rule, then evaluates
the condition. A target that the actor cannot read cannot make the source node
match this query.

A path that ends at the link itself compares the stored UUID instead:

```json
{
  "filter": {
    "author": "d91f6d22-9f61-4d38-9f0c-0c04d9233f2d"
  },
  "project": ["title", "author"]
}
```

Do not combine a terminal ID filter or sort with resolution of that same link.
For example, filtering on `author` while projecting `author.name` is ambiguous
and is rejected. Use one of these approaches instead:

- treat `author` as a raw stored ID everywhere in that query; or
- enter the link consistently, for example use `author.id` and `author.name`.

The same rule applies to LinkArray. A resolved LinkArray may contain fewer
items than the stored array because unreadable, deleted, dangling, or now-
disallowed targets do not resolve.

## Paginate predictable results

Use `limit` and `offset` with an explicit business sort:

```json
{
  "query": {
    "project": ["title", "year"],
    "filter": {"published": true},
    "sort": {"year": "desc", "title": "asc"},
    "limit": 50,
    "offset": 100
  }
}
```

Sandala makes every result order deterministic. When `sort` is absent, it uses
a stable internal order; when a sort has ties, it adds an internal tie-breaker.
Pages therefore remain stable while the matching data is unchanged. Like other
offset-based APIs, a sequence of pages can shift when matching nodes are
created, deleted, or changed between requests.

Collection responses contain only the `nodes` returned for the requested page;
they do not report how many nodes match the query in total. A client that needs
a conventional next-page control can request one extra item and treat a result
longer than the displayed page size as evidence that another page may exist.

## Build robust clients

Use these rules when turning a query into an application feature:

- choose the entity-scoped endpoint whenever the collection has one known
  entity type;
- use an explicit, narrow projection for repeated lists; resolve only fields
  the client displays or needs for a subsequent interaction;
- make an explicit business sort before paginating;
- handle an empty `nodes` array as an ordinary successful result;
- treat missing fields and `null` resolved Links as valid ACL-aware response
  shapes, not parsing failures;
- follow the [PATCH link-preservation rules](../reference/rest-api/nodes.md#protection-of-acl-hidden-links)
  when editing Link or LinkArray values from a resolved response.

The Admin UI's Table view uses the same query model: its filter, sort, and
column controls build a query, while Advanced JSON is useful for the full
language. See [Using the Admin UI](using-the-admin-ui.md) for the interface
workflow.
