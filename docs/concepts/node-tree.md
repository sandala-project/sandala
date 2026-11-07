# Node tree

Each module owns one tree containing nodes of all of its entities. The tree is
not merely a presentation feature: parentage determines which nodes may be
created or moved, and node ACL controls who may populate each branch.

The tree has a virtual root. It is a module-level access boundary, not a stored
node. Nodes directly below it are root nodes.

## Representing a position

Sandala keeps three related system fields on every node:

| Field | Meaning |
| --- | --- |
| `parent` | The direct parent node ID, or `null` for a root node. |
| `ancestors` | The ordered IDs of every ancestor, from the top-level node through the direct parent. |
| `depth` | The number of ancestor nodes, equal to the length of `ancestors`. Root nodes have depth `0`; the virtual root is not counted. |

For this tree:

```text
virtual root
└── Fiction              depth 0, ancestors []
    └── Earthsea          depth 1, ancestors [Fiction]
        └── Tombs         depth 2, ancestors [Fiction, Earthsea]
```

`ancestors` is an implementation of the Ancestors Array pattern. It makes a
subtree query possible without walking the tree one level at a time.

## Creating nodes

A new node is created either at the root (`parent` absent or `null`) or below
an existing parent. Sandala checks both of these conditions:

1. the selected location permits the entity as a direct child;
2. the actor has populate (`p`) permission at that location.

The first condition comes from schema and module metadata:

- `root_children_entities` controls which entities may appear at the virtual
  root; an empty list allows every entity in that module;
- `x-meta.children.entities` controls children of a concrete entity; an empty
  list allows no children.

The second condition uses `root_perm` at the virtual root and `perm` on a real
parent node. Populate permission applies only to direct children. Each
descendant has its own access rules.

## Moving a node

Changing a node's `parent` moves it. The target must be an active node in the
same module, allow the moving node's entity as a child, and grant the actor
populate permission. Moving a node to its own descendant is rejected, so a
tree cannot become cyclic.

After a successful move, Sandala recalculates `ancestors` and `depth` for the
moved node and all of its descendants. This includes soft-deleted descendants,
so restoring or inspecting historical tree data does not leave stale paths.

## Soft deletion

Deleting a node soft-deletes that node and its entire subtree by setting
`deleted: true`. The records remain in MongoDB, but normal reads, links, and
queries consider only active nodes (`deleted: false`).

Before deletion, Sandala checks write permission on every active node in the
subtree. A missing permission anywhere prevents the deletion. Node-level hooks
also run for each active node before and after the subtree is marked deleted.

Soft deletion does not turn a node's ID into a reusable identity. References to
the deleted node may remain stored in Link or LinkArray fields; they simply no
longer resolve as active targets.

## Structural boundaries

- Parent-child relationships never cross module boundaries.
- A node has at most one parent and belongs to one entity for its lifetime.
- System tree fields are maintained by Sandala rather than supplied directly by
  clients.
- Links can cross modules, but links do not create structural parentage.

See [Modules and entities](modules-and-entities.md) for the distinction between
module roots and entity child rules. [Permissions and ACL](permissions-and-acl.md)
explains how Sandala decides whether an actor may read, write, or populate a
node.
