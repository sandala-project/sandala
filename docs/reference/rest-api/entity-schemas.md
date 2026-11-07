# Entity schemas

An entity schema defines one node type inside a module. It is a constrained
JSON Schema Draft 7 document with Sandala metadata. The path identifies both
the module and the entity name:

```text
/api/v1/modules/{module}/entities/{entity}/
```

This page specifies the resource endpoints. For the schema model, semantic
types, links, field modes, and the meaning of `x-ui`, see [Schemas and
semantic types](../../concepts/schemas-and-semantic-types.md). The exact
allowed schema vocabulary is in [Semantic types](../semantic-types.md).

## Schema representation

The API returns a full entity schema in an `entity` property. Its root `title`
is always the `{entity}` path value. A returned schema includes Sandala's
common node system fields in `properties` and `required`:

```text
id, entity, parent, owner, group, perm, depth, ancestors, deleted, cdate, mdate
```

Sandala manages those fields when nodes are created, updated, moved, or
deleted. They are part of the effective node schema, but normally do not need
to be submitted when creating or replacing an entity schema.

| Field | JSON Schema type | Meaning |
| --- | --- | --- |
| `id` | string, `format: uuid` | Stable node identifier. |
| `entity` | string | Technical name of this node's entity schema. |
| `parent` | string or `null` | Direct parent node ID; `null` places the node at the module root. |
| `owner` | string, `format: uuid` | ID of the owning `users/user` node. |
| `group` | string, `format: uuid` | ID of the node's `users/group`. |
| `perm` | closed object | Node ACL: `owner`, `group`, and `others` sections, each with Boolean `r`, `w`, and `p` permissions. |
| `depth` | integer, minimum `0` | Number of ancestor nodes, equal to the length of `ancestors`. Root nodes have `0`; the virtual root is not counted. |
| `ancestors` | array of strings | Ordered IDs of every ancestor, ending with the direct parent. Root nodes use an empty array. |
| `deleted` | boolean | Soft-deletion marker. |
| `cdate` | string, `format: date-time` | Creation timestamp. |
| `mdate` | string, `format: date-time` | Timestamp of the most recent node update. |

At minimum, the submitted user-schema root contains:

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {},
  "x-meta": {
    "children": { "entities": [] },
    "perm": {
      "default": {
        "owner": { "r": true, "w": true, "p": true },
        "group": { "r": true, "w": false, "p": false },
        "others": { "r": true, "w": false, "p": false }
      }
    }
  }
}
```

`required` is optional in a submitted schema and is treated as an empty array
when absent. `x-meta.children.entities` lists entity names in the same module
that may be direct children. An empty list means this entity accepts no child
nodes. `x-meta.perm.default` is the complete node ACL assigned by default to a
new node of this entity.

`x-ui` is an optional root-level object. Its currently supported values are
`x-ui.labels.tree` and `x-ui.labels.reference`, each a string template for the
admin UI. Templates support simple Mustache-compatible substitutions such as
`{{name}}` and `{{metadata.edition}}`. Path segments support Unicode characters,
including names such as `{{название}}` or `{{данные.标题}}`. A path may traverse
object values but not an array. A missing, `null`, invisible, array, or object
value at the substitution endpoint renders as an empty string. Other Mustache
constructs remain literal.
Sandala validates the `x-ui` structure and the string type of its labels, but
does not validate template paths or contents.

### System fields in submitted schemas

A client may either omit every system field from both `properties` and
`required`, or provide every system field in both places. In the latter case,
each system-field schema must exactly match Sandala's canonical definition.
Partial inclusion, or a system field with a modified schema, is invalid.

Every schema returned by the API includes the canonical system-field
definitions. If a submitted `title` differs from `{entity}`, the path value
wins.

## List entity schemas

`GET /modules/{module}/entities/`

Requires an authenticated `admin` or `superuser`. Returns `200 OK` with a
lightweight list; it does not return full schemas:

```json
{
  "entities": [
    {
      "title": "Book",
      "description": "Book"
    }
  ]
}
```

An empty result is returned when the module currently has no entity schemas.

## Get an entity schema

`GET /modules/{module}/entities/{entity}/`

Requires an authenticated `admin` or `superuser`. Returns `200 OK` and the
full, system-field-enriched schema:

```json
{
  "entity": {
    "title": "Book",
    "type": "object",
    "additionalProperties": false,
    "properties": { "…": "…" },
    "required": ["…"],
    "x-meta": { "…": "…" }
  }
}
```

## Create an entity schema

`POST /modules/{module}/entities/{entity}/`

Requires an authenticated `superuser`. Send the complete schema inside an
`entity` wrapper:

```json
{
  "entity": {
    "description": "Book",
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "name": {
        "description": "Name",
        "type": "string",
        "minLength": 1,
        "x-meta": {
          "semantic-type": "String",
          "visibility-mode": "all",
          "write-mode": "all"
        }
      }
    },
    "required": ["name"],
    "x-meta": {
      "children": { "entities": [] },
      "perm": {
        "default": {
          "owner": { "r": true, "w": true, "p": true },
          "group": { "r": true, "w": false, "p": false },
          "others": { "r": true, "w": false, "p": false }
        }
      }
    }
  }
}
```

Sandala validates the constrained JSON Schema shape and then validates
Sandala-specific rules, including semantic types, visibility and write modes,
link targets, permitted child entities, and default permissions. See
[Errors](errors.md) for the shared error envelope and the endpoint-specific
codes below.

See [Semantic types](../semantic-types.md) for the exact field shapes, allowed
JSON Schema keywords, and `x-meta` members accepted in `properties`.

On success it returns the full enriched schema in `entity` with `201 Created`.

## Replace an entity schema

`PUT /modules/{module}/entities/{entity}/`

Requires an authenticated `superuser`. The request has the same complete
`{"entity": {…}}` form and validation rules as creation. This is a full
replacement, not a partial update: fields omitted from the submitted schema
are no longer part of the entity schema.

Before storing the replacement, Sandala validates every existing node of this
entity, including soft-deleted nodes, against the new effective schema. If any
node is incompatible, the error identifies the first incompatible node in
`details.node_id` and explains the validation failure in
`details.field_errors`.

The built-in `users/user` and `users/group` schemas have additional protection:
their core fields and requiredness cannot change through this endpoint, though
their `description` values may change. Integrators may add other fields.
Their complete schema and node-operation contract is in
[Users and groups](users-and-groups.md).

On success, the endpoint returns `200 OK` with the final enriched schema in
`entity`.

## Delete an entity schema

`DELETE /modules/{module}/entities/{entity}/`

Requires an authenticated `superuser`. Sandala refuses deletion if at least
one non-deleted node of that entity exists. Soft-deleted nodes do not block
deletion.

After deletion, Sandala updates related module and schema metadata that names
the entity as an allowed child or link target. Stored node values are not
rewritten.

On success, returns:

```json
{
  "status": "ok"
}
```

The status is `200 OK`.

## Errors

All failures use the [common error contract](errors.md). Every endpoint on
this page can return these authentication and authorization errors:

| Status | Error code | Meaning |
| --- | --- | --- |
| `401` | `authentication_error` | No acceptable credential was supplied, or the supplied credential is invalid. |
| `403` | `access_denied` | The authenticated actor lacks the required role: `admin` or `superuser` for reads, and `superuser` for changes. |

### Get an entity schema

| Status | Error code | Meaning |
| --- | --- | --- |
| `404` | `not_found` | The module and entity path does not identify an existing schema. |

### Create an entity schema

| Status | Error code | Meaning |
| --- | --- | --- |
| `400` | `request_body_invalid` | The JSON body is not an object or does not contain an object in `entity`. |
| `400` | `schema_validation_failed` | The submitted schema does not match Sandala's constrained JSON Schema vocabulary. `details.field_errors` identifies structural validation failures. |
| `400` | `validation_error` | The schema violates a Sandala rule beyond its structural shape, such as a link target that does not exist, invalid all-or-none system fields, incompatible nested access modes, or a required `Password` field. |
| `409` | `conflict` | An entity with the requested name already exists in the module. |

### Replace an entity schema

| Status | Error code | Meaning |
| --- | --- | --- |
| `400` | `request_body_invalid` | The JSON body is not an object or does not contain an object in `entity`. |
| `400` | `schema_validation_failed` | The submitted schema does not match Sandala's constrained JSON Schema vocabulary. `details.field_errors` identifies structural validation failures. |
| `400` | `validation_error` | The schema violates a Sandala rule, including protected-field rules for `users/user` and `users/group`. |
| `400` | `document_validation_failed` | At least one existing node, including a soft-deleted node, is incompatible with the replacement schema. `details.node_id` identifies the first such node and `details.field_errors` describes the failed validation. |
| `404` | `not_found` | The module and entity path does not identify an existing schema. |

### Delete an entity schema

| Status | Error code | Meaning |
| --- | --- | --- |
| `404` | `not_found` | The module and entity path does not identify an existing schema. |
| `409` | `conflict` | The entity still has at least one non-deleted node. |
