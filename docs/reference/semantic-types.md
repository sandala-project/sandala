# Semantic types

Sandala entity schemas use a constrained JSON Schema Draft 7 vocabulary. Each
user-defined field is a JSON Schema value description plus `x-meta` that gives
the value product-level meaning. Sandala rejects unknown keywords in field
schemas, so this page is the authoritative allowed-keyword reference.

For the entity-schema endpoints and root schema contract, see [Entity
schemas](rest-api/entity-schemas.md).

## Common field form

Every non-null field schema contains exactly the keywords allowed for its
semantic type and this `x-meta` object:

```json
{
  "type": "string",
  "description": "Display name",
  "x-meta": {
    "semantic-type": "String",
    "visibility-mode": "all",
    "write-mode": "all"
  }
}
```

`description` is optional on every semantic type and is a human-readable
field label. `type`, `x-meta`, and any other required structural keywords are
shown in the type tables below.

### Field names

User-defined property names must be non-empty. They cannot contain `.`, `*`,
or the NUL character (`U+0000`), or begin with `$` or `__sandala_`. These rules
apply to properties at every nesting depth, including inside array items.

At the entity root, `and`, `or`, and `not` are also reserved. System fields
retain their canonical definitions, and MongoDB's [internal
identifier](rest-api/nodes.md#sorting-and-pagination) is not available as a
user-defined root field.

### `x-meta`

All ordinary fields require these members:

| Member | Allowed values | Meaning |
| --- | --- | --- |
| `semantic-type` | The exact type name from this page | Sandala semantic type. |
| `visibility-mode` | `all`, `admin`, `superuser`, `none` | Which actors may receive the field in a node response. |
| `write-mode` | `all`, `admin`, `superuser`, `none` | Which actors may submit the field in node create and patch operations. |

`none` is absolute: it hides or rejects the field even for a superuser. The
other modes use the same role ordering: `all` is widest, followed by `admin`,
`superuser`, and `none`.

Nested fields cannot be more visible or writable than their container.

`Link` and `LinkArray` also require `x-meta.link`:

```json
{
  "module": "library",
  "entities": ["Author"]
}
```

`module` is a non-empty module name. `entities` is an array of entity names in
that module; Sandala checks that the module and named entities exist when the
schema is created or replaced. One link field targets exactly one module. An
empty `entities` array is valid and means that no targets resolve; it does not
mean all entities in the module.

## Required and nullable fields

At an entity root or inside an `Object`, `required` is an array of direct
property names. It is independent of nullability.

To make a field nullable, use exactly this shape:

```json
{
  "anyOf": [
    {
      "type": "string",
      "x-meta": {
        "semantic-type": "String",
        "visibility-mode": "all",
        "write-mode": "all"
      }
    },
    { "type": "null" }
  ]
}
```

The `anyOf` wrapper contains exactly one non-null Sandala field schema and one
`{"type": "null"}` schema. The field metadata lives in the non-null branch;
the wrapper has no other keywords.

`Password` cannot be listed in `required`. An `Array<Password>` also cannot be
required. These restrictions apply to nullable forms too.

## Scalar text types

| Semantic type | Required JSON Schema form | Optional keywords | Notes |
| --- | --- | --- | --- |
| `String` | `type: "string"` | `pattern`, `enum`, `minLength`, `maxLength` | Plain short text. |
| `Password` | `type: "string"` | `pattern`, `minLength`, `maxLength` | No `enum`; transient input, described below. |
| `Text` | `type: "string"` | `pattern`, `minLength`, `maxLength` | Multi-line plain text. |
| `RichText` | `type: "string"` | `pattern`, `minLength`, `maxLength` | Rich-text content. |
| `Date` | `type: "string"`, `format: "date"` | none | ISO 8601 calendar date, for example `2026-09-26`. |
| `DateTime` | `type: "string"`, `format: "date-time"` | none | ISO 8601 date-time, for example `2026-09-26T14:30:00Z`. |

`minLength` and `maxLength` are non-negative integers. `pattern` is a JSON
Schema regular-expression string. `enum` is accepted only by `String`.

`DateTime` accepts the offsets permitted by the JSON Schema `date-time`
format. For consistency, clients are encouraged to send UTC values with a
trailing `Z`, such as `2026-09-26T14:30:00Z`; this gives timestamps from
different producers one unambiguous representation.

## Numeric and Boolean types

| Semantic type | Required JSON Schema form | Optional keywords |
| --- | --- | --- |
| `Number` | `type: "number"` | `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`, `multipleOf` |
| `Integer` | `type: "integer"` | `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`, `multipleOf` |
| `Boolean` | `type: "boolean"` | none |

For `Number`, every bound and `multipleOf` is a number, and `multipleOf` must
be greater than zero. For `Integer`, every bound is an integer and
`multipleOf` is an integer of at least one.

## Object and Array

### `Object`

An `Object` is a closed nested object:

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "label": {
      "type": "string",
      "x-meta": {
        "semantic-type": "String",
        "visibility-mode": "all",
        "write-mode": "all"
      }
    }
  },
  "required": ["label"],
  "x-meta": {
    "semantic-type": "Object",
    "visibility-mode": "all",
    "write-mode": "all"
  }
}
```

`type`, `properties`, `additionalProperties: false`, and `x-meta` are
required. Its own `required` array is optional, but every listed name must be
a property in this object. Object properties are ordinary Sandala field
schemas and can nest further objects and arrays.

### `Array`

An `Array` stores repeated values described by one Sandala field schema in
`items`:

```json
{
  "type": "array",
  "items": {
    "type": "string",
    "x-meta": {
      "semantic-type": "String",
      "visibility-mode": "all",
      "write-mode": "all"
    }
  },
  "minItems": 1,
  "x-meta": {
    "semantic-type": "Array",
    "visibility-mode": "all",
    "write-mode": "all"
  }
}
```

`type`, `items`, and `x-meta` are required. `minItems` and `maxItems` are
optional non-negative integers. Items may be scalar fields, `Object`, or
`File`, `Image`, and `Video` descriptors. An immediate item cannot be `Array`,
`Link`, or `LinkArray`, including their nullable forms.

Because `items` is itself a full Sandala field schema, it has its own
`x-meta`. Its `visibility-mode` and `write-mode` must exactly match those of
the containing `Array`. If it contains deeper fields, those fields follow the
usual rule and may only be equally or more restrictive.

An `Object` item can contain further arrays and links: for example,
`sections[] -> members[]` is allowed when each section is an Object with a
`members` property. Use `LinkArray` for a list of node references, or
`Array<Object>` with a link property when each item needs its own structure.

## File, Image, and Video descriptors

These types are closed object descriptors. Their internal properties are not
Sandala fields and do not contain `x-meta`.

| Type | Required schema structure | Required value member | Optional value members |
| --- | --- | --- | --- |
| `File` | Define `url`; may also define `mime-type`, `size` | `url` | `mime-type`, `size` |
| `Image` | Define `url`, `mime-type`, `width`, `height`, `size` | `url` | `mime-type`, `width`, `height`, `size` |
| `Video` | Define `url`, `mime-type`, `size` | `url` | `mime-type`, `size` |

All descriptor schemas use `type: "object"` and
`additionalProperties: false`. `url` and `mime-type` have `type: "string"`;
`size`, `width`, and `height` have `type: "integer"`. The descriptor's
`required` array must contain `url`; it may additionally require any optional
member. No other descriptor property names are allowed.

An `Image` field is an example:

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "url": { "type": "string" },
    "mime-type": { "type": "string" },
    "width": { "type": "integer" },
    "height": { "type": "integer" },
    "size": { "type": "integer" }
  },
  "required": ["url"],
  "x-meta": {
    "semantic-type": "Image",
    "visibility-mode": "all",
    "write-mode": "all"
  }
}
```

Descriptors can contain an external URL or one returned by Sandala's upload
endpoints.

## Links

| Semantic type | Required JSON Schema form | Purpose |
| --- | --- | --- |
| `Link` | `type: "string"`, `format: "uuid"`, `x-meta.link` | One node ID. |
| `LinkArray` | `type: "array"`, `items: {"type":"string", "format":"uuid"}`, `x-meta.link` | A list of node IDs. |

`LinkArray` also accepts `minItems` and `maxItems`, each a non-negative
integer. Its `items` object is a fixed UUID schema and has no `x-meta`.

Writes validate the UUID shape of user-defined link values, not the existence
or entity of their targets. A link can therefore be dangling, including after
a target is deleted or removed from the allowed-entity list. On reads,
resolution returns only active targets that match the source field's current
link metadata and are readable to the actor. In a query spanning several
source entities, each source field keeps its own allowed-entity list.

## Password is transient

`Password` validates input just like a constrained string during node create
and ordinary patch. After `before_create` or `before_patch` hooks run and the
candidate passes schema validation, Sandala removes `Password` fields and
`Array<Password>` values before persistence. A hook can therefore derive a
safe stored value, such as a password hash, without persisting clear text.

This is a storage behavior, not a promise that every application has a
password mechanism. The built-in `users/user` hook is one use of the type.
