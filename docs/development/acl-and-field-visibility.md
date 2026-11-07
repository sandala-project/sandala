# ACL and field visibility

This page describes the authorization boundaries contributors need to preserve
across services, query planning, and hooks. The public permission model is in
[Permissions and ACL](../concepts/permissions-and-acl.md); field metadata is
defined in [Semantic types](../reference/semantic-types.md#x-meta).

Node ACL and field modes answer different questions. Node ACL selects which
nodes an actor may operate on. Field modes restrict the fields available within
that operation. Neither layer substitutes for the other, and neither belongs
in an HTTP route or storage repository.

## Authorization inputs

Node operations receive an actor dictionary or `None`, not credentials.
`AuthService` builds the actor from the current active user record; the transport obtains it
through the authentication helpers. An embedded host supplies the equivalent
trusted actor. Accepting an actor dictionary from an untrusted request body
would bypass authentication, regardless of the later permission checks.

Node ACL uses `user_id`, `groups`, and the superuser role. `primary_group`
supplies a default group for new nodes; it is not a second group-membership
source in the ACL evaluator. Field modes use the actor's role, independently
of ownership and group membership.

`core/access.py` owns the role normalization and access orders. Actor roles
have levels `all: 0`, `admin: 1`, and `superuser: 2`. Field modes use the same
levels plus `none: 3`; a field is available only when the actor's level meets
its required level. No actor reaches `none`. A missing or unrecognized actor
role normalizes to `all`, including for an anonymous actor.

Use the shared helpers rather than duplicating role-checking logic. Being an
admin does not bypass node ACL, and being a superuser does not bypass field
modes or the active-node restriction.

## Keep service and query ACL decisions equivalent

Node authorization has two implementations:

- `NodeService._can_node_action()` evaluates a loaded node in Python for
  read preparation and write, populate, and delete checks.
- `build_node_permission_filter()` in `core/query/acl_filter.py` builds the
  MongoDB predicate for reads and for checks that search for denied nodes.

Both use mutually exclusive owner, group, then others precedence. Conceptually,
after the superuser bypass, the decision is:

```text
if actor owns the node:
    use perm.owner[permission]
else if node.group is in actor.groups:
    use perm.group[permission]
else:
    use perm.others[permission]
```

A denied owner cannot fall through to a more permissive group or others
section. The Mongo predicate encodes that exclusion explicitly in its group
and others branches; it is not an OR of three independent grants. The group
branch likewise prevents a group member from falling through to others.

Keep both implementations equivalent for valid node documents and trusted
actors. Changes to one without the other can make a node readable through a
query but inaccessible by ID, or make a subtree write check disagree with the
same node's Python check. The schema's complete Boolean `perm` structure is
part of that equivalence; raw repository writes are not a supported way to
create arbitrary permission shapes.

The virtual module root reuses the Python evaluator through a small node-like
value: the service maps the module's `root_owner`, `root_group`, and
`root_perm` to `owner`, `group`, and `perm`, respectively. Only populate
permission is checked there. This avoids introducing a different precedence
rule for root creation and moves. Permission checks and entity child rules
remain separate conditions.

The `r`, `w`, and `p` bits are independent. Write or populate permission does
not imply read permission, and node permissions are not inherited from a
parent. Subtree operations check the applicable nodes rather than treating
the selected subtree root as an authorization shortcut.

## Read authorization precedes response shaping

`QueryBuilder` adds the active-node restriction and, for a non-superuser, the
read ACL predicate independently of the client's filter. These restrictions
apply to the main selection and every linked-target lookup. A source node's
read permission does not authorize reading its linked targets.

Authorization does not depend on whether the client selects `owner`, `group`,
or `perm` in the response. The pipeline evaluates its matches before the final
response projection and pagination. Applying ACL only after a page has been
selected would both change pagination and leave intermediate lookups outside
the intended read boundary.

Resolving `owner` or `group` needs special care because it replaces a stored
UUID with an object or `null`. The final main-query ACL check still needs the
original UUID. The builder preserves just the affected top-level values for a
non-superuser and removes those temporary copies after the final match. A
linked target's own ACL check runs before that target's links are resolved.
The exact stage placement and conditional optimization are described in
[Query builder](query-builder.md#resolving-owner-and-group-without-changing-acl-meaning).

`NodeService.get()` first reads the raw identity and ACL metadata needed to
check the node and find its entity schema. An absent or unreadable node raises
the same not-found error. Its final result still comes through the query path,
including query policies, visibility checks, and projection; the preliminary
repository result is not a response document.

Write preparation similarly needs raw current state, including fields hidden
from the caller. Loading the caller's projected document instead would lose
information needed for validation and safe updates. Keep those internal reads
separate from response reads: successful creates, patches, and ACL changes
use the query path for their final returned node. A committed write can be
followed by a failed read if the actor cannot read the resulting node. That
failure is not a rollback; see [Request lifecycle](request-lifecycle.md).

## Field visibility has two enforcement paths

Hiding fields only in the final response is insufficient. A client could infer
a hidden value from which nodes match a filter or from their sorted order.
Sandala therefore both validates named paths and sanitizes selected documents.

### Explicit paths

`SchemaPathResolver` checks every schema segment named by projection, filter,
or sort, including segments inside Objects, Arrays, and resolved references.
An explicitly hidden path raises `QueryValidationError`; it is not silently
ignored or interpreted as a missing value.

When several entities participate in a schema scope, a field may be absent
from some of them, but every schema defining it must allow the access. A
visible definition in one entity cannot override a hidden definition in
another. The [schema-scope rules](query-builder.md#reference-target-scopes)
explain how main queries and references determine the schemas considered.

Comparing or sorting a whole stored container also checks its descendants.
Otherwise, selecting a visible Object in a condition could reveal one of its
hidden children without naming that child. `exists` and `size` do not inspect
child values and require only the path's own visibility. This inspection
stops at references, whose stored contents are IDs rather than target nodes.

### Selected documents

`VisibilityExclusionsCollector` finds hidden descendants for wildcard and
whole-container projections. It traverses the ordinary stored structure,
including Array items, while reference targets are sanitized in their own
lookup scope. If any defining schema hides a path, that path is excluded
throughout the shared scope.

This is needed even when the parent Object or Array is explicitly selected:
selecting a visible container does not grant access to every child inside it.
Lookup projections must also retain their own visibility exclusions rather
than relying only on the main document's cleanup. Projection fields needed
only for filtering or sorting must not become extra response fields; the
[projection channels](query-builder.md#projection-channels) keep those uses
separate.

The default projection used by single-node and entity-scoped reads is another
consumer of the visibility rules, not an exemption from them. Its recursive
link-path collector skips fields the actor cannot see, so a default read does
not generate explicit paths that would fail normal query validation. Custom
projections still pass the same path checks and output sanitization.

## Nested modes and write checks

`EntitySchemaValidator` establishes the schema-level invariants: a child's
visibility and write modes cannot be broader than its containing Object or
Array, and an ordinary Array's immediate item modes equal the array's modes.
`LinkArray.items` is a technical UUID schema, not a separately protected field.
The canonical children of File, Image, and Video descriptors use their
container's modes rather than independent child settings.

Every traversal must unwrap a nullable schema before reading semantic
metadata or selecting its children, including nullable Array items. Otherwise
wrapping a restricted field in `anyOf` can accidentally bypass its modes.
Unwrapping selects the schema to inspect, not the values to check: submitting
`null` still requires the field's write permission. The complete nullable
schema remains in use for document validation; see
[Validation and schema evolution](validation-and-schema-evolution.md#traversing-nullable-schemas).

On create and ordinary patch, `NodeService._enforce_write_mode()` checks the
original submitted user fields. It recursively checks supplied Object
properties and Array items, including the container itself. These are
submitted-value checks, not a visibility check or a second full-document
validation. Unknown properties are left to candidate schema validation, and
system fields follow their dedicated service rules.

In particular, `owner`, `group`, and `perm` are not ordinary writable fields.
The ordinary patch rejects client changes to them and directs callers to the
ACL operation. That operation checks write permission and ownership rules
against each current node before its hook, then validates the hook-adjusted
ACL payload with that node's effective actor before preparing the update.
Recursive preparation checks every active node before the bulk write; it does
not assume a descendant has its parent's owner or permissions. The public
rules are in [Patch node ACL](../reference/rest-api/nodes.md#patch-node-acl).

## Hooks are trusted application code

On create and ordinary patch, field write checks run before the corresponding
before hook. The service does not rerun them over trusted hook additions,
allowing a hook to set a field whose write mode is `none`, such as a password
hash. The complete candidate still undergoes schema validation. The mutable
`before_create`, `before_patch`,
and `before_acl_patch` events may change the actor used by subsequent checks
and defaults; they cannot retroactively authorize a client operation rejected
before the hook. The actor and mutation contract is defined in
[Node hooks](../reference/node-hooks.md#payload-and-actor-changes).

Query hooks have a different boundary. Their actor copy does not replace the
actor used to authorize the query. A required filter may inspect fields hidden
from the caller, but is ANDed with the system restrictions and cannot remove
the built-in active-node or ACL predicates.

Hook output exclusions are not schema visibility modes. They remove fields
from returned documents without preventing client filtering or sorting by
otherwise visible fields. `after_query` can further transform the selected
page, but its output is not checked again for ACL or field visibility. A hook
that inserts data or calls a service with a more privileged actor owns the
resulting disclosure decision. See the [query-hook contract](../reference/node-hooks.md#query-hooks)
and [restriction placement](query-builder.md#query-hook-restrictions-in-the-plan).

The built-in hidden-reference protection for ordinary PATCH addresses target
node ACL, not arbitrary query-hook policies. Do not assume a new query policy
automatically changes what that write-side protection preserves. Its algorithm
and trade-offs are described in [Link patching](link-patching.md); the public
boundary is described under [Protection of ACL-hidden links](../reference/rest-api/nodes.md#protection-of-acl-hidden-links).

## Boundaries to preserve when changing access behavior

- Keep Python ACL evaluation and generated Mongo predicates equivalent,
  especially when an owner or group member has fewer permissions than others.
- Cover anonymous actors, admins, superusers, and the `none` field mode;
  superuser ACL bypass must not become an unconditional read/write bypass.
- Preserve both explicit-path rejection and hidden-descendant removal,
  including nullable Objects, Array items, and linked targets.
- Check that resolving or omitting ACL fields from a projection cannot change
  the selected nodes, and that pagination follows the authorized selection.
- Keep client permissions separate from trusted hook capabilities and raw
  service preparation. Repositories do not independently apply authorization.
- Do not extend node visibility promises to binary delivery: asset upload
  checks the target field's write mode, while the public asset route has no
  node ACL. Hiding a descriptor field does not revoke its URL.

Permission changes need coverage at both the Python decision level and the
MongoDB result level. A plausible predicate alone does not establish that
projection, lookup placement, and container traversal preserve its meaning.
