# Modules and entities

Sandala models content as **nodes**. A node is a typed record: its entity schema
defines which data it carries, and its module defines the tree to which it
belongs.

```text
Module
├── entity schemas
│   ├── Book
│   ├── Author
│   └── Publisher
└── one tree containing nodes of those entities
    ├── Book node
    ├── Author node
    └── Publisher node
```

This model separates the shape of content from the content itself:

- An **entity** is a named schema, comparable to a content type or class.
- A **node** is one concrete instance of an entity, comparable to a record or
  object.
- A **module** is the boundary that groups entity schemas and their nodes into
  one tree.

## Modules

A module has a unique technical `name`, a human-readable `description`, and a
virtual root for its tree. The technical name appears in REST paths and names
the MongoDB collection that stores the module's nodes.

All structural parent-child relationships remain inside one module. A `Book`
node in `library`, for example, cannot be a child of a node in `catalog`.
Links are different: a Link or LinkArray field may target a node in another
module.

Every module has these virtual-root settings:

| Setting | Purpose |
| --- | --- |
| `root_owner` | User that owns the virtual root. |
| `root_group` | Group assigned to the virtual root. |
| `root_perm` | Populate permission for creating or moving a node to the root. |
| `root_children_entities` | Entity names that may appear directly below the root. |

The root is not a stored node. Its ownership and populate permission are used
only when creating a root node or moving a node to `parent: null`.

An empty `root_children_entities` list means that any entity in the module may
be created at the root.

## Entity schemas

An entity schema is a JSON Schema document extended with Sandala metadata. Its
technical name is its `title`; an entity's URL also identifies that name when a
schema is created or updated. The schema describes user-defined fields and
their validation rules, semantic types, visibility, and write modes.

Each entity schema additionally defines:

| Metadata | Purpose |
| --- | --- |
| `x-meta.perm.default` | The ACL assigned to a newly created node unless a permitted operation supplies another value. |
| `x-meta.children.entities` | Entity names allowed as direct children of a node of this entity. |
| `x-ui.labels` | Optional templates used by the Sandala admin UI to label nodes in trees and reference controls. |

Unlike a module root, an empty `x-meta.children.entities` list means that nodes
of this entity do **not** allow children. This distinction is deliberate:

```text
root_children_entities = []        → any entity may be a root node
children.entities = []             → this entity may have no child nodes
```

The schema can omit the common system fields when it is stored or submitted.
Sandala adds those fields to the effective node schema and returns them in the
schema representation exposed by the API.

## Nodes and their system fields

Every node belongs to exactly one module and exactly one entity. In addition to
the fields defined by its entity schema, Sandala maintains these system fields:

| Group | Fields | Meaning |
| --- | --- | --- |
| Identity | `id`, `entity` | UUID node identifier and entity name. |
| Tree | `parent`, `ancestors`, `depth` | Direct parent, complete ancestor path, and number of ancestor nodes. `parent` is `null` for root nodes. |
| Access | `owner`, `group`, `perm` | Node owner, node group, and read/write/populate ACL. |
| Lifecycle | `deleted`, `cdate`, `mdate` | Soft-delete state, creation time, and last-modified time. |

`ancestors` uses the Ancestors Array model: it contains every ancestor ID in
order, including the direct parent and excluding the node itself. Root nodes
therefore have `depth: 0` and an empty `ancestors` array. `depth` equals the
length of `ancestors`; the virtual root is not counted.

Clients may supply their own UUID as `id` when creating a node; otherwise,
Sandala generates one. A node's `id` and `entity` cannot be changed after
creation. Sandala maintains `ancestors`, `depth`, `deleted`, `cdate`, and
`mdate` rather than accepting client-supplied values for them.

## The built-in users module

Sandala bootstraps a `users` module containing `user` and `group` entities.
They are ordinary nodes for the purposes of links and ownership, but their core
schemas and hooks protect the fields that implement authentication and access
control. The user, group, and authentication model is documented separately.

## Where to go next

Continue with [Schemas and semantic types](schemas-and-semantic-types.md) to
learn how entity schemas express validation constraints, nullable values,
nested objects, arrays, and links.
