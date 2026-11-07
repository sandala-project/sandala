# Bootstrap and the users module

The built-in `users` module is both ordinary node data and the source of
authentication identities. Its schemas and node hooks add identity rules to
the generic service lifecycle; they do not introduce a second CRUD API.
The public fields and operations belong in [Users and groups](../reference/rest-api/users-and-groups.md),
and credential endpoints belong in [Authentication](../reference/rest-api/authentication.md).

This page explains how initialization, protected schemas, hooks, and identity
reads fit together. The overall composition sequence is in
[Architecture](architecture.md#composition-and-lifecycle).

## Responsibility split

| Component | Responsibility |
| --- | --- |
| `core/users/schemas.py` | Build the initial user and group schemas and name their protected fields. |
| `core/users/bootstrap.py` | Ensure the initial schemas, bootstrap identities, and module metadata exist. |
| `core/users/hooks.py` | Normalize ordinary identity writes, derive password hashes, maintain group membership, and reject unsafe identity deletion. |
| `EntityService` | Protect built-in field definitions during schema replacement. |
| `NodeService` | Apply generic node ACL, field write modes, hierarchy, candidate validation, and transient Password removal. |
| `AuthService` and `IdentityRepository` | Verify credentials against raw active identities and build the authenticated actor. |
| `SecurityService` | Supply username normalization, secret generation, hashing, and verification primitives. |

Keep these boundaries when extending users. For example, the password hook
derives a hash, but it neither owns the generic transient-field mechanism nor
implements password-pattern validation itself.

## Initial database setup

`build_container()` constructs repositories and services, registers the
built-in user/group hooks, calls `ensure_users_module()`, and only then
constructs `AuthService`. Configured integration hook modules are loaded by
the Flask app afterwards, not by this initialization function.

For an empty database, the important sequence inside `ensure_users_module()`
is:

```text
ensure_users_module(...)
    ├── initialize users node-collection indexes
    ├── store group and user schemas
    ├── generate IDs for the initial user and default group
    ├── insert the user with that primary group ID
    ├── insert the default group with that user as owner
    └── create users module metadata pointing to both identities
```

The initial user owns itself and belongs to the default group; the group is
owned by that user and uses its own ID as its node group. Both nodes are at
the module root. The user is active with the `superuser` role, and the group
has `is_default: true`. The module's virtual root uses them as `root_owner`
and `root_group`. Index definitions and their construction points are in
[Storage](storage.md#index-ownership).

These references explain why bootstrap is a controlled repository-write
exception. No existing caller identity can authorize the first ordinary
create, and the first user and group refer to each other before both exist.
Bootstrap preallocates their IDs and constructs their system fields directly
instead of routing the inserts through `NodeService` or temporarily relaxing
ordinary ACL and reference checks.

Bootstrap validates the configured initial username and password against the
corresponding user-schema fields, then hashes the password before insertion.
It does not run the full ordinary node-create lifecycle or integration hooks.
Contributors changing the fixed seed shapes must therefore preserve their
schema and identity invariants explicitly, not assume the normal service path
will fill or validate them later.

### Repeated startup preserves stored state

Initialization ensures missing records rather than overwriting existing
schemas or resetting identity values on every container build. A non-null
resolved `ROOT_USERNAME` selects the username to look for; when it is `None`,
bootstrap looks for a non-deleted, active superuser. A non-null resolved
`DEFAULT_GROUP_GROUPNAME` selects that group by name; when it is `None`,
bootstrap looks for a non-deleted group marked `is_default`.

Those selectors are not rename commands. Reusing existing records does not
reset their password, role, membership, or the module root ACL.
`ROOT_PASSWORD` is needed when creating the bootstrap user, not when an
existing bootstrap identity is reused. Normal password changes go through the
ordinary user PATCH flow.

Initialization spans several writes without a transaction. An exception fails
container construction but does not roll back earlier schema or identity
inserts. Do not confuse repeated-startup behavior with atomic initialization.

## Credential policy is stored in the schema

When `users/user` does not yet have a stored schema, `user_schema(config)`
places the username length bounds and pattern, plus the password minimum
length and pattern, into their field definitions. The same stored constraints
then apply to ordinary node candidates and to validation of bootstrap
credential values.

Once that schema exists, bootstrap reuses it instead of rebuilding it from
the current `AUTH_USERNAME_*` and `AUTH_PASSWORD_*` settings. Changing those
configuration values does not update stored policy. Authentication also does
not regenerate the schema or rerun assignment constraints when checking a
password against its stored hash.

`SecurityService.normalize_username()` handles non-empty string normalization
and lowercasing; it does not read that schema's pattern or length bounds.
The hook normalizes first, and `NodeService` validates the completed candidate
afterwards. This keeps the policy visible in the schema rather than hiding a
second copy in the hash or login code. Configuration keys and defaults are
listed in [Configuration](../reference/configuration.md#users-bootstrap-and-password-policy).

## Protected schemas remain extensible

`USER_PROTECTED_FIELDS` and `GROUP_PROTECTED_FIELDS` identify definitions
required by the built-in implementation. During schema replacement,
`EntityService` compares those fields and their requiredness against the
stored schema before validating existing nodes.

The structural comparison recursively ignores `description` values, allowing
descriptive edits without allowing a type, visibility, write mode, reference
target, pattern, or length bound to change. Importantly, comparison is against
the stored definition, not a newly generated schema based on today's
configuration.

Integrators can add fields while preserving the protected definitions. The
normal schema-replacement checks still validate all existing nodes, including
soft-deleted ones. Do not turn protected-field comparison into a blanket ban
on extending either entity, or bypass it in a special REST route. See
[Validation and schema evolution](validation-and-schema-evolution.md#built-in-user-and-group-schemas).

## Ordinary user and group writes

Built-in handlers participate in `NodeHookRegistry` with the same scope and
ordering rules as integration handlers. They receive the raw write contexts
described in [Node hooks](node-hooks.md), not caller-visible projections.
The initial field write checks remain in `NodeService`; normalization by a
trusted hook is not permission for the caller to submit restricted fields.

For users, the hooks normalize usernames and optional email addresses, check
uniqueness, normalize roles, and maintain group membership. Email validation
is a hook rule: its stored schema is a nullable String, while the normalizer
checks the address and converts its domain to the canonical IDNA form.
The username and non-null email uniqueness checks include soft-deleted users
and exclude the current user when patching. Database indexes enforce the
same uniqueness boundary under concurrent writes; see
[User identity indexes](storage.md#user-identity-indexes).

On create, an omitted primary group is resolved through `is_default: true`,
not through the group's display name. The hooks ensure that the primary group
appears in the deduplicated `groups` list and that every selected group exists
and is not soft-deleted. On patch, changing either membership field rebuilds
and checks the pair together. The hook also rejects assigning `admin` or
`superuser` unless its actor is a superuser; this is additional to the ordinary
field-mode and node-ACL checks.

For groups, `before_create` forces `is_default` to false and `before_patch`
removes that attribute from the patch. The default marker therefore cannot
be assigned through ordinary group writes. Group names are labels, not unique
identity keys.

### Password derivation and transient input

An absent password on user creation produces no password hash. A supplied
password must be a non-empty string even if the field's `minLength` is zero;
the hook derives its hash through `SecurityService`. The completed candidate
then passes schema validation, including the Password field's constraints,
before `NodeService` removes transient values and writes the node.

For PATCH, an empty password string is removed from the payload as a no-op.
A non-empty string derives a replacement hash; `null` is not a request to
remove the credential. Client-supplied `password_hash` is blocked by its
write mode and explicitly rejected by the built-in hooks.

Do not move generic Password cleanup into these user hooks: the semantic type
is also available in integrators' entities. Conversely, cleanup alone does
not derive a credential; the user hook supplies that behavior. After-hook
payload snapshots can retain submitted secrets, even though candidate and
stored result snapshots have had transient values removed. The lifecycle is
described in [Validation and schema evolution](validation-and-schema-evolution.md#node-candidate-validation).

### Anonymous registration uses an operation-local actor

`ALLOW_ANONYMOUS_USER_REGISTRATION` is checked by the user-create hook at
runtime; unlike schema-policy settings, it is not stored in a field schema.
The ordinary API's original field-write checks prevent an anonymous caller
from supplying privileged role or membership fields.

For accepted registration, the hook sets owner to the proposed new user ID,
sets the node group to the primary group, and supplies an effective actor
representing that new identity and its membership. This lets subsequent
generic create checks verify self-ownership and group selection without an
already persisted caller identity.

The remaining root or parent populate check uses that effective actor,
including its group membership, not the original anonymous actor. Enabling
registration does not bypass the selected location's populate permission or
entity child rules. This actor change is local to the node operation: it does
not create an authentication session or issue a PAT.

## Identity deletion uses targeted integrity checks

Deletion hooks read raw repository state rather than query-hook results.
An identity cannot become safe to delete merely because a read policy hides
one of its dependencies from the caller.

User deletion rejects self-deletion and ownership references from active
nodes or module virtual roots. Group deletion protects the default group and
checks active node-group references, module root groups, and users' primary
and secondary membership. The reference queries exclude the identity's own
node and descendants; they do not exclude every node in an arbitrary larger
delete request.

The last-active-superuser guard is module-scoped on `users` rather than
entity-scoped on `user`. It can therefore reject deletion of a non-user
ancestor whose subtree contains the last active superuser. This guard belongs
to deletion; it is not a general postcondition applied to every role or
`active` update.

These are targeted identity rules, not generic foreign-key constraints or a
cascade across arbitrary user-defined links. Ordinary links can still become
dangling. Hook failures precede the subtree's bulk soft delete, as described
in [Recursive writes](node-hooks.md#recursive-writes-are-service-orchestration).
Public error codes and dependency details belong in
[Users and groups](../reference/rest-api/users-and-groups.md#errors).

## Authentication state is not the returned user profile

`AuthService` reads identities through `IdentityRepository`, not through
`NodeService.query()`. Password login requires a non-deleted active user and
verification against a stored password hash; a user without a hash cannot
authenticate with a local password. PAT and session authentication verify
their own credentials and load the current non-deleted active user instead.
The user's password hash is not required for those authentication methods.

The authenticated actor contains `user_id`, `primary_group`, `groups`, `role`,
and `auth_type`. It is neither the full user document nor the user's
caller-visible profile. Custom schema fields are not automatically copied
into it. Because credential checks load current identity state, later
requests reflect role, membership, and activation changes without rebuilding
the actor from a public profile. Changing a password does not itself revoke
separate PAT or session records.

The REST login and current-user routes obtain their profile separately through
`NodeService.get()`. That response follows node ACL, field visibility, default
resolution, and query hooks. The actor can contain group and role information
that the profile omits, and the profile may contain resolved objects where
the actor needs stored IDs. Never construct authorization state from that
response projection.

When changing users or authentication, review schema factories and protected
fields, bootstrap construction, user/group hooks, identity indexes, credential
verification, actor construction, and profile reads together. Keep ordinary
identity writes on the node-service path, initialization explicit, and
authentication independent from caller-visible field projection.
