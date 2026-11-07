# Links and resolution

A `Link` stores one node ID. A `LinkArray` stores several node IDs. They are
ordinary UUID values in storage; resolving a link is a read-time operation that
replaces those IDs with node documents.

This distinction is deliberate. It keeps writes inexpensive and permits a
stored reference to outlive a target node, while readers still receive only
targets they may see.

## Declaring a link

Both link semantic types use `x-meta.link` to name one target module and the
target entities that may be resolved. For example, a Book's `author` can point
to an Author in the `library` module, while another link points to a user in
the `users` module.

See the [`x-meta` reference](../reference/semantic-types.md#x-meta) for the
metadata shape and [Links](../reference/semantic-types.md#links) for the
stored-value contract.

## Stored values and resolved values

Consider a Book whose stored `author` value is the Author node's UUID:

```json
{
  "title": "A Wizard of Earthsea",
  "author": "d91f6d22-9f61-4d38-9f0c-0c04d9233f2d"
}
```

A projection such as `["title", "author.id", "author.name"]` asks for the
linked author's fields rather than its stored UUID. A resolved result can
look like this:

```json
{
  "title": "A Wizard of Earthsea",
  "author": {
    "id": "d91f6d22-9f61-4d38-9f0c-0c04d9233f2d",
    "name": "Ursula K. Le Guin"
  }
}
```

The response contains an author object, but the Book still stores only its ID.
Resolution works through Object and Array fields, and it can continue through
links on the target node.

## Choosing a projection

`project` selects response fields. A path such as `author.name` also asks
Sandala to resolve the link; `author.*` selects all visible fields of its
target. Selecting `author` itself, or using `["*"]` for all visible fields,
does not itself request resolution.

Paths in `project`, `filter`, and `sort` jointly determine which links resolve.
The projection determines which of those resolved values appear in the
response.

The general query endpoint's default projection does not request resolution.
The single-node GET and entity-scoped POST query endpoints provide convenient
defaults that resolve links for you. The endpoint defaults, including system
links such as `owner` and `group`, are listed in
[Projection and resolution](../reference/rest-api/nodes.md#projection-and-resolution).

## Access control during resolution

Resolution returns only active targets allowed by the link schema and readable
to the actor. It respects field visibility. Integrators can impose additional
read restrictions through query hooks, including during link resolution.

A resolved response can therefore be incomplete: an actor may receive fewer
LinkArray items than are stored, or see only some fields of a linked node.
This changes the response, not the value stored in the source node.

See [Permissions and ACL](permissions-and-acl.md) for the underlying access
model.

## Filtering and sorting through links

Paths below a link address fields of the resolved target. For example, a query
can filter Books by `author.name` or sort them by `publisher.name`.

For example, this query returns Books written by Ursula K. Le Guin and includes
the resolved author name in each result:

```json
{
  "filter": {
    "entity": "Book",
    "author.name": {"eq": "Ursula K. Le Guin"}
  },
  "sort": {"author.name": "asc"},
  "project": ["title", "author.name"]
}
```

By contrast, a filter on `author` compares the UUID stored on Book. It does not
read the Author node:

```json
{
  "filter": {
    "entity": "Book",
    "author": {"eq": "d91f6d22-9f61-4d38-9f0c-0c04d9233f2d"}
  },
  "project": ["title", "author"]
}
```

These are different operations: `author` addresses a stored ID, while
`author.id` addresses the ID of a resolved target. The rules for combining
them are described in [Filtering](../reference/rest-api/nodes.md#filtering).
For queries spanning several entity types, see
[Compatibility across entity schemas](../reference/rest-api/nodes.md#compatibility-across-entity-schemas).

## Patching a response that contains resolved links

Resolved data is a view, not a complete stored document to send back unchanged.
When editing links, submit their IDs rather than the resolved objects, and
remember that a response may omit targets the actor cannot read.

Ordinary PATCH protects references hidden by ACL against accidental loss.
References hidden only by query hooks are not covered by this protection;
integrators are responsible for safe editing in that case. The exact behavior
and handling of conflicts are
described in [Protection of ACL-hidden
links](../reference/rest-api/nodes.md#protection-of-acl-hidden-links).
