# Schemas and semantic types

Each entity is described by a JSON Schema Draft 7 document with Sandala
metadata. JSON Schema defines value structure and validation;
Sandala semantic types give that structure product-level meaning for the API,
query system, asset uploads, and admin UI.

For example, `String`, `Text`, and `RichText` are all JSON Schema strings, but
they have different intended presentation and editing behavior. A `Link` is a
UUID string in storage, but tells Sandala that the value may be resolved to a
node in another query.

## The shape of an entity schema

At its root, an entity schema is an object schema with a `properties` map and
`additionalProperties: false`. Sandala assigns the entity's technical name to
the root `title`. Every user-defined field has:

- an optional `description`, a human-readable field label;
- ordinary JSON Schema validation keywords appropriate to its value type;
- `x-meta.semantic-type`;
- `x-meta.visibility-mode` and `x-meta.write-mode`.

The root `x-meta` additionally contains default node permissions and permitted
child entities. Separately, an optional root-level `x-ui` object contains label
templates for the admin UI. This separates data and access rules from
presentation preferences.

Every node also has common system fields, such as `id`, `parent`, and `owner`.
Their meaning and the full root schema contract are described in
[Entity schemas](../reference/rest-api/entity-schemas.md#schema-representation).

Sandala intentionally accepts a constrained JSON Schema vocabulary. It rejects
unknown schema keywords and does not allow `additionalProperties: true` at an
entity root or inside an Object field. This keeps schemas, validation, queries,
and the admin UI aligned.

## Required and nullable are independent

`required` controls whether an object must contain a field. Nullability controls
whether a field's value may be `null`.

| Schema choice | Meaning |
| --- | --- |
| Not required, not nullable | The field may be absent; if present, it must contain a non-null value of its declared type. |
| Required, not nullable | The field must be present and contain a non-null value. |
| Not required, nullable | The field may be absent, or it may be present with `null` or a valid non-null value. |
| Required, nullable | The field must be present; its value may be `null` or a valid non-null value. |

An Object has its own `required` list for its direct properties. See
[Required and nullable fields](../reference/semantic-types.md#required-and-nullable-fields)
for the exact nullable schema form and type-specific restrictions.

## Semantic types

The semantic type is declared in `x-meta.semantic-type`. Choose it for the
meaning of a value, not just its JSON shape: an `Image` and a general `Object`
are both objects, but only the former describes an image asset and participates
in image-specific upload and editing behavior.

Each type comes with a supported schema vocabulary. The complete type list,
allowed validation keywords, field-name rules, and metadata forms are in
[Semantic types](../reference/semantic-types.md).

## Nested values

An `Object` embeds named fields inside a node. An `Array` repeats values
described by one item schema. Together they support deep document structures:
for example, a book can contain an array of editions, each with its own array
of chapter objects. Array levels are separated by Object fields, rather than
directly nesting arrays inside arrays. See [Object and
Array](../reference/semantic-types.md#object-and-array) for the supported forms.

File, Image, and Video are also object-shaped values, but their subfields are a
fixed descriptor contract rather than editable Sandala fields. A descriptor
stores a URL and optional media metadata, not the binary content itself. It may
describe a file uploaded through Sandala or an external URL that matches the
entity schema. The exact descriptor members are listed in the
[reference](../reference/semantic-types.md#file-image-and-video-descriptors).

See [Assets](assets.md) for Sandala-managed uploads, descriptor URLs, and their
access model.

## Field visibility and write modes

Every user-defined field declares two independent access modes:

- `x-meta.visibility-mode` controls whether an actor may receive the field;
- `x-meta.write-mode` controls whether an actor may submit it in a node write.

A field can therefore be readable without being writable, or writable without
being returned. Nested fields cannot be more broadly visible or writable than
their container. The exact metadata and nesting rules are in the
[reference](../reference/semantic-types.md#x-meta).

Node-level ACL is a separate layer and is explained in
[Permissions and ACL](permissions-and-acl.md). It limits read and write access
for anonymous actors, users, and admins. Superusers bypass node-level ACL, but
`visibility-mode: none` and `write-mode: none` remain absolute restrictions
even for a superuser. See that concept page for the complete role-to-mode
mapping.

## Links

Unlike an embedded Object, a link identifies a separate node: `Link` stores
one UUID and `LinkArray` stores a list of UUIDs. Their metadata limits the
targets to one module and a set of entity types; its exact form is described
in the [`x-meta` reference](../reference/semantic-types.md#x-meta).

Stored references do not guarantee that a target exists or is readable.
Resolution replaces IDs with the available target nodes in a response,
subject to the link schema and access restrictions; it does not change the
stored values.

See [Links and resolution](links-and-resolution.md) for the difference between
a stored UUID and a resolved response value.

## Password fields are transient

`Password` is for accepting a secret as input, not for storing it as an ordinary
node field. Sandala validates the input but removes it before persistence.
Application logic can derive a safe stored value, such as a password hash; the
built-in `users/user` schema uses this pattern. The type alone does not
implement authentication.

See [Password is transient](../reference/semantic-types.md#password-is-transient)
for the validation and persistence contract.
