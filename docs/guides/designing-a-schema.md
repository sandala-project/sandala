# Designing a schema

An entity schema turns a domain concept into a node type that Sandala can
validate, secure, query, and render in the Admin UI. Design the model before
writing JSON: decide which facts belong to one node, which facts have their own
identity, and how nodes participate in the module tree.

This guide uses a library module, but the decisions apply to any domain. The
complete JSON Schema vocabulary is in [Semantic types](../reference/semantic-types.md);
the HTTP contract for storing a schema is in [Entity schemas](../reference/rest-api/entity-schemas.md).

## 1. Draw the boundaries first

Start with a module boundary. A module owns one node tree and a set of entity
schemas. Parent-child relationships cannot cross that boundary, although links
can point to another module.

The tree is optional. A module may instead contain independent root nodes of
several entity types and be used as a set of related tables. In that model,
clients use entity-scoped API requests and the Admin UI's Table view; no
entity needs to allow children. Plan parent-child rules only when hierarchy is
part of the domain.

For each entity, answer these questions before choosing fields:

1. Does this record need a stable identity, its own ACL, or a place in a tree?
2. Is it independently created, edited, queried, or reused by other records?
3. Which entity types may be direct children of it?
4. Which facts are intrinsic parts of the record rather than independent
   records?

For example, `Book`, `Author`, and `Publisher` usually deserve separate node
types. An ISBN, publication year, or physical dimensions normally belongs to
the Book node itself.

Technical entity and field names become part of API paths, projections,
filters, integrations, and stored data. Treat them as stable identifiers;
prefer names such as `Book`, `publication_year`, and `primary_author` over UI
labels or names that are likely to be renamed.

## 2. Choose composition or links deliberately

Sandala supports two complementary ways to represent a complex domain model.

### Composition: embed values in the node

Use an `Object` or `Array` when the value is an inseparable part of its parent:
it has no independent identity, is normally edited together with the parent,
and does not need its own ACL or reuse. This is composition.

A book's physical dimensions are a typical embedded Object:

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "width_mm": {
      "type": "integer",
      "minimum": 1,
      "x-meta": {
        "semantic-type": "Integer",
        "visibility-mode": "all",
        "write-mode": "all"
      }
    },
    "height_mm": {
      "type": "integer",
      "minimum": 1,
      "x-meta": {
        "semantic-type": "Integer",
        "visibility-mode": "all",
        "write-mode": "all"
      }
    }
  },
  "required": ["width_mm", "height_mm"],
  "x-meta": {
    "semantic-type": "Object",
    "visibility-mode": "all",
    "write-mode": "all"
  }
}
```

Composition keeps closely related data together and avoids a lookup when the
parent is read. It is a poor fit when the embedded value later needs an
independent lifecycle, permissions, reuse, or a relationship of its own.

### References: connect independent nodes

Use `Link` or `LinkArray` when the target is an independent node. It can then
be reused by other nodes, have separate permissions, be queried independently,
and appear in the module tree. This is a reference relationship.

For example, a Book can link to an Author node:

```json
{
  "type": "string",
  "format": "uuid",
  "x-meta": {
    "semantic-type": "Link",
    "visibility-mode": "all",
    "write-mode": "all",
    "link": {
      "module": "library",
      "entities": ["Author"]
    }
  }
}
```

Create the target module and its target schemas before creating a schema that
links to them: Sandala validates the link module and allowed entity names at
schema creation time. One Link or LinkArray field targets one module. A link
can allow several entity types from that module, but it cannot mix modules.

Links are references, not copies. A target that is deleted, no longer allowed
by the link schema, or unreadable to the requesting actor is absent from a
resolved response. Design clients so that they tolerate such a missing target.
See [Links and resolution](../concepts/links-and-resolution.md) for the read
semantics.

### Ordered relationships need an object around the link

`LinkArray` is the compact choice for an unordered collection of references.
Do not rely on its order after resolution: MongoDB lookup results have no
ordering guarantee, even though the stored array of IDs has one.

When order is meaningful, model an ordered Array of Objects containing a
single Link instead. For example, a book's credits can preserve the sequence
and carry a role alongside each author:

```json
{
  "type": "array",
  "items": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "author": {
        "type": "string",
        "format": "uuid",
        "x-meta": {
          "semantic-type": "Link",
          "visibility-mode": "all",
          "write-mode": "all",
          "link": {
            "module": "library",
            "entities": ["Author"]
          }
        }
      },
      "role": {
        "type": "string",
        "x-meta": {
          "semantic-type": "String",
          "visibility-mode": "all",
          "write-mode": "all"
        }
      }
    },
    "required": ["author"],
    "x-meta": {
      "semantic-type": "Object",
      "visibility-mode": "all",
      "write-mode": "all"
    }
  },
  "x-meta": {
    "semantic-type": "Array",
    "visibility-mode": "all",
    "write-mode": "all"
  }
}
```

Sandala preserves the order of that outer Array while resolving its nested
links. The trade-off is real: resolving a link inside an array requires extra
aggregation stages to process array elements and reconstruct the array. Use it
when the sequence or per-relationship metadata matters; use `LinkArray` for a
simple unordered set of references.

## 3. Choose field types and constraints

For each field, select the semantic type that expresses its product meaning,
then apply the smallest useful validation constraints. For example:

- use `String` with `enum` for a small controlled vocabulary;
- use `Integer` with bounds for quantities or a publication year;
- use `Date` for a calendar date and `DateTime` for a timestamp; send
  DateTime values in UTC with `Z` when possible;
- use `File`, `Image`, or `Video` for asset descriptors, rather than inventing
  a look-alike object structure;
- use `LinkArray`, rather than an Array of Link, for an unordered collection
  of references.

Make a field required only when every valid node must contain it from its first
version. `required` and nullable are independent: a required nullable field
must exist but may contain `null`. A field added to an existing entity is often
best introduced as optional, populated across existing nodes, and made
required only in a later schema replacement.

`Password` is deliberately different from an ordinary String: it is a
transient input and cannot be required. A `before_create` or `before_patch`
hook can transform it into a safe stored value; Sandala removes the submitted
Password value before persistence. See [Password is transient](../concepts/schemas-and-semantic-types.md#password-fields-are-transient).

## 4. Set field modes and default node permissions

Every user-defined field needs `x-meta.visibility-mode` and
`x-meta.write-mode`. These describe who may receive or submit that field by
role; node ACL separately controls access to each individual node. A field is
usable only when both layers allow the operation.

Start with the narrowest modes that fit the data. In particular:

- use `none` for values that must never pass through ordinary node APIs, such
  as a stored password hash;
- do not place a broadly visible or writable nested field inside a more
  restrictive Object or Array: nested modes may only be equally or more
  restrictive;
- remember that `admin` does not bypass node ACL. Only a superuser bypasses
  node-level ACL, and even a superuser cannot bypass a `none` field mode.

At the schema root, `x-meta.perm.default` is the complete ACL copied to a new
node unless an allowed operation sets access values differently. Decide whether
new nodes should be private to their owner, shared with their group, or public
before creating real data. The [Permissions and ACL](../concepts/permissions-and-acl.md)
concept explains the two layers in detail.

## 5. Define the tree rule and useful labels

`x-meta.children.entities` controls only direct children in the same module.
List the permitted entity names; use an empty array for a leaf entity. It does
not control links or query results.

Set `x-ui.labels.tree` and `x-ui.labels.reference` when the Admin UI needs a
clear label for this entity. Each is a simple template with substitutions such
as `{{title}}` or `{{metadata.edition}}`. A path can traverse Objects but not
Arrays. Sandala checks that labels are strings, but does not check their paths,
so test them with representative nodes. A missing, hidden, null, array, or
object endpoint renders as an empty string.

A label template does not request or resolve linked nodes. Do not use a path
through a Link or LinkArray, such as `{{author.name}}`: it is not a supported
label source and normally renders as an empty string. Use values stored on the
node itself instead.

For a Book, a concise pair is usually enough:

```json
{
  "x-ui": {
    "labels": {
      "tree": "📖 {{title}}",
      "reference": "📖 {{title}}"
    }
  }
}
```

## 6. Assemble and create the schema

An ordinary submitted schema omits Sandala's system fields. Its root needs a
closed object shape, user-field `properties`, root metadata, and any required
field names. The entity name comes from the path, not the JSON body.

Create a `Book` schema after the `library` module exists:

```bash
curl --fail-with-body --silent --show-error \
  --cookie "$COOKIE_JAR" \
  --header 'Content-Type: application/json' \
  --data @book-schema.json \
  "$SANDALA_URL/modules/library/entities/Book/"
```

`book-schema.json` wraps the root schema in an `entity` property:

```json
{
  "entity": {
    "description": "Book",
    "type": "object",
    "additionalProperties": false,
    "properties": {},
    "required": [],
    "x-meta": {
      "children": {"entities": []},
      "perm": {
        "default": {
          "owner": {"r": true, "w": true, "p": true},
          "group": {"r": true, "w": false, "p": false},
          "others": {"r": true, "w": false, "p": false}
        }
      }
    }
  }
}
```

Replace the empty `properties` and `required` shown above with the fields you
designed. The request requires a superuser. On success, Sandala returns the
effective schema, including canonical system fields.

The same schema can be created in the Admin UI by a superuser. The UI is a
schema editor over this contract, not a separate schema language; see
[Using the Admin UI](using-the-admin-ui.md).

## 7. Evolve schemas conservatively

Updating an entity uses full replacement, not a partial patch. Before accepting
the replacement, Sandala validates every existing node of that entity,
including soft-deleted nodes, against the new effective schema. A compatibility
failure identifies the first incompatible node and field error.

This makes a staged evolution safer:

1. add new fields as optional;
2. populate or transform existing data;
3. introduce tighter constraints or requiredness only once every node meets
   them.

A field can be removed or renamed in the schema only if no stored node of that
entity contains the old field, including soft-deleted nodes. Changing a field's
name in the schema does not rename it in stored documents. Sandala has no
built-in migration for renaming or removing stored fields, and ordinary node
PATCH has no general field-removal operation. Choose stable field names and
avoid silently repurposing a name with a different meaning.

## Design checklist

Before creating or replacing a schema, verify that:

- entity and field identifiers are stable technical names;
- each fact is deliberately embedded or linked;
- target schemas exist before Link or LinkArray fields name them;
- ordered relationships use an Array of Objects with a Link, not LinkArray;
- constraints express genuine data invariants rather than temporary UI rules;
- each field has visibility and write modes compatible with its container;
- default node ACL and permitted child entities match the intended workflow;
- label templates use fields that readers can normally see;
- a replacement schema still validates every current and soft-deleted node.

The next practical step is to create, edit, move, and delete nodes that conform
to the schema.
