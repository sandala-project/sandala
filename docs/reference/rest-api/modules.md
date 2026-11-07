# Modules

A module is the boundary for one set of entity schemas and one node tree. Its
technical `name` is used in API paths and as the MongoDB collection name for
its nodes. See [Modules and entities](../../concepts/modules-and-entities.md)
for the model behind these endpoints.

All paths on this page are below `/api/v1/`.

## Module representation

Every response returns a module document with these fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `name` | string | Unique technical module name. It is not editable after creation. |
| `description` | string | Human-readable module label. |
| `root_owner` | UUID string | ID of a non-deleted `users/user` node that owns the virtual root. |
| `root_group` | UUID string | ID of a non-deleted `users/group` node assigned to the virtual root. |
| `root_perm` | object | Populate (`p`) permission for the virtual root. |
| `root_children_entities` | array of strings | Entity names permitted directly below the virtual root. An empty array permits every entity in this module. |

`root_perm` contains exactly the three role sections below. Each section
contains exactly its Boolean `p` permission:

```json
{
  "owner": { "p": true },
  "group": { "p": true },
  "others": { "p": false }
}
```

The virtual root is not a stored node. Its settings control creating a node
with `parent: null` and moving a node to `parent: null`.

## List modules

`GET /modules/`

Requires an authenticated actor with the `admin` or `superuser` role. The
response is sorted by `name` in ascending order.

```json
{
  "modules": [
    {
      "name": "library",
      "description": "Library",
      "root_owner": "8b06138e-d43d-4dba-a185-bb8c61f814c4",
      "root_group": "6bfaa146-ae0b-4431-9fca-75ba070093b8",
      "root_perm": {
        "owner": { "p": true },
        "group": { "p": true },
        "others": { "p": false }
      },
      "root_children_entities": []
    }
  ]
}
```

Returns `200 OK`.

## Get a module

`GET /modules/{module}/`

Requires an authenticated `admin` or `superuser`. `{module}` is the technical
module name. A successful response has a single `module` property containing
the module representation and returns `200 OK`.

## Create a module

`POST /modules/`

Requires an authenticated `superuser`. Send a JSON object with a `module`
object:

```json
{
  "module": {
    "name": "library",
    "description": "Library",
    "root_perm": {
      "owner": { "p": true },
      "group": { "p": true },
      "others": { "p": false }
    },
    "root_children_entities": []
  }
}
```

| Field | Required | Rules |
| --- | --- | --- |
| `name` | Yes | Non-empty string. Leading and trailing whitespace is removed before it is stored and compared for uniqueness. |
| `description` | Yes | String. Leading and trailing whitespace is removed; an empty result is allowed. |
| `root_perm` | Yes | The exact virtual-root permission object described above. |
| `root_owner` | No | UUID of a non-deleted `users/user` node. If omitted, Sandala uses the actor's `user_id`. |
| `root_group` | No | UUID of a non-deleted `users/group` node. If omitted, Sandala uses the actor's `primary_group`. |
| `root_children_entities` | Yes | Must be an empty array at creation time: a new module has no entity schemas yet. |

Extra properties in the submitted `module` object are ignored. On success,
Sandala creates the node-collection indexes for the module and returns the
created representation as `{"module": {…}}` with `201 Created`.

## Update a module

`PATCH /modules/{module}/`

Requires an authenticated `superuser`. The JSON request body wraps a partial
update in `module`:

```json
{
  "module": {
    "description": "Public library",
    "root_children_entities": ["Book", "CatalogFolder"]
  }
}
```

Only these fields may appear in the patch:

| Field | Rules |
| --- | --- |
| `description` | String; leading and trailing whitespace is removed. |
| `root_perm` | The exact virtual-root permission object. |
| `root_owner` | UUID of a non-deleted `users/user` node. |
| `root_group` | UUID of a non-deleted `users/group` node. |
| `root_children_entities` | Array of non-empty entity names that already exist in this module. Names are trimmed and duplicate entries are removed, preserving first occurrence order. |

`name` is immutable. Any other field, including `name`, makes the request
invalid. An empty patch is allowed and returns the current representation.
The response is `200 OK` with the final module document in `module`.

## Delete a module

`DELETE /modules/{module}/`

Requires an authenticated `superuser`. Sandala refuses deletion while the
module has at least one entity schema or at least one non-deleted node. Soft-
deleted nodes do not themselves prevent module deletion.

On success, the endpoint returns `200 OK`:

```json
{
  "status": "ok"
}
```

## Errors

All failures use the [common error contract](errors.md). Every endpoint on
this page can return these authentication and authorization errors:

| Status | Error code | Meaning |
| --- | --- | --- |
| `401` | `authentication_error` | No acceptable credential was supplied, or the supplied credential is invalid. |
| `403` | `access_denied` | The authenticated actor lacks the required role: `admin` or `superuser` for reads, and `superuser` for changes. |

### Get a module

| Status | Error code | Meaning |
| --- | --- | --- |
| `404` | `not_found` | The module named in the path does not exist. |

### Create a module

| Status | Error code | Meaning |
| --- | --- | --- |
| `400` | `request_body_invalid` | The JSON body is not an object or does not contain an object in `module`. |
| `400` | `parameter_invalid` | A scalar parameter is malformed, such as an empty `name`, a non-string `description`, or an invalid root owner or group UUID. |
| `400` | `validation_error` | `root_perm`, root identity references, or `root_children_entities` violates a module rule. In particular, a newly created module must have an empty `root_children_entities` array. |
| `409` | `conflict` | A module with the requested name already exists. |

### Update a module

| Status | Error code | Meaning |
| --- | --- | --- |
| `400` | `request_body_invalid` | The JSON body is not an object or does not contain an object in `module`. |
| `400` | `parameter_invalid` | The patch includes an immutable or unknown property, or a scalar parameter is malformed. |
| `400` | `validation_error` | `root_perm`, root identity references, or `root_children_entities` violates a module rule. For example, every named child entity must already exist in this module. |
| `404` | `not_found` | The module named in the path does not exist. |

### Delete a module

| Status | Error code | Meaning |
| --- | --- | --- |
| `404` | `not_found` | The module named in the path does not exist. |
| `409` | `conflict` | The module still has an entity schema or at least one non-deleted node. |
