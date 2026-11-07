# Users and authentication

Sandala includes a built-in `users` module with two entities: `user` and
`group`. They are ordinary nodes for the purposes of links, trees, and node
ACL, but Sandala protects their core schemas and installs hooks that preserve
identity and authentication invariants.

Users and groups are created, read, patched, and soft-deleted through the
ordinary node APIs. Their special behavior comes from their protected schemas
and built-in hooks, rather than from a separate kind of record.

Users and groups provide the IDs used by node `owner`, `group`, and module
`root_owner` and `root_group` fields. Authentication turns an active user into
an actor; ACL and field modes then decide what that actor may do.

## Users, groups, and roles

Each user has a `username`, an optional `email`, a `primary_group`, a `groups`
list, a global `role`, and an `active` flag. The primary group is always a
member of `groups`. If a new user does not specify a primary group, Sandala
assigns the built-in default group and adds it to the membership list.

| Role | Meaning |
| --- | --- |
| `all` | Ordinary authenticated user. |
| `admin` | May list and read modules and entity schemas, and may read or write fields whose mode is `admin`. It does not bypass node ACL; changing modules or schemas still requires `superuser`. |
| `superuser` | Highest global role. It bypasses node ACL, except that field modes set to `none` remain inaccessible. |

Global roles and node ACL are separate. For example, an admin is still treated
as owner, group member, or other when Sandala evaluates a node's `perm`.
[Permissions and ACL](permissions-and-acl.md) explains the interaction in
detail.

The built-in schemas define the identity fields, but an integrator may add
application-specific fields to `user` or `group`. Sandala does not permit
structural changes to the core fields through the entity-schema APIs, although
their human-readable `description` values may be edited.

### Identity rules

Sandala normalizes usernames and email addresses to lowercase before storing
them. A username and every non-empty email address are unique across all
`users/user` nodes, including soft-deleted users. Deleting a user therefore
does not make their former username or email available to a different identity.

The `groupname` field identifies a group for people, but it is not a unique
identity key. One group is created as the default group. It cannot be deleted,
and other groups cannot be made default through ordinary node operations.

Changing group membership requires superuser access. A non-superuser cannot
assign the `admin` or `superuser` role. User and group deletion also protects
referential integrity: Sandala refuses to delete an identity that is still used
as a node owner, a module root owner or group, or a user's group membership.
It also refuses an operation that would remove the last active superuser.

## Local passwords

The `password` field of `users/user` uses the transient `Password` semantic
type. When a non-empty password is supplied during create or patch, the users
hook derives an Argon2id `password_hash`; Sandala then removes the clear-text
`password` before writing the user node. `password_hash` is never exposed or
accepted through the ordinary node API.

A user may be created without `password`. Such a user is a valid identity but
cannot use local password login until a non-empty password is set later. An
empty password in a user PATCH means no password change; it does not remove an
existing local password.

The password and username constraints stored in the initial `users/user`
schema come from bootstrap configuration. See [Configuration](../reference/configuration.md)
for `AUTH_PASSWORD_*` and `AUTH_USERNAME_*` settings.

## Bootstrap and registration

When Sandala starts against a database without the `users` module, it creates
the module, a default group, and the bootstrap superuser. `ROOT_USERNAME`,
`ROOT_PASSWORD`, and `DEFAULT_GROUP_GROUPNAME` configure those initial
identities. Bootstrap does not reset existing records on later starts.

Anonymous creation of `users/user` nodes is disabled by default. Enabling
`ALLOW_ANONYMOUS_USER_REGISTRATION` activates the built-in self-registration
behavior: Sandala assigns the new user as its own node owner and assigns the
default group when no primary group is supplied. An anonymously registered
user always receives the ordinary `all` role. Creating a user with a higher
role is a separate operation that requires a superuser.

## Authentication creates an actor

Sandala supports two first-party authentication mechanisms:

| Mechanism | Intended use | Credential sent with requests |
| --- | --- | --- |
| Auth session | Browser-based first-party UI | Configured HTTP cookie. |
| Personal access token (PAT) | Scripts, automation, and server-to-server integrations | `Authorization: Bearer <id>.<secret>` header. |

Both mechanisms authenticate an active, non-deleted `users/user` node and
produce the same kind of actor:

```json
{
  "user_id": "…",
  "primary_group": "…",
  "groups": ["…"],
  "role": "all",
  "auth_type": "session"
}
```

The actor is evaluated on each authenticated request, so the user's current
role and group membership determine ACL decisions. When a request supplies
both a Bearer token and an auth-session cookie, the Bearer token takes
precedence.

Successful authentication is not authorization. It establishes the actor; node
ACL, field modes, and any relevant service rules still apply to the requested
operation.

## Browser sessions

Local login accepts a username or email address plus a password and issues an
opaque auth-session ID in a cookie. Sandala stores only a hash of that ID.
The cookie is configured as `HttpOnly`, `Secure`, and `SameSite=Lax` by default;
all cookie attributes are configurable.

A session has an idle expiry and an absolute maximum lifetime. Optional renewal
extends the idle expiry only on authenticated session requests and never beyond
the absolute limit. Logout revokes the current session and clears its cookie.
The exact endpoint contracts and lifetime settings belong in the authentication
reference and [Configuration](../reference/configuration.md).

## Personal access tokens

A PAT is a bearer credential shaped as `<id>.<secret>`. Sandala stores the
public ID and a hash of the secret; the complete token is returned only when it
is created or rotated. Store it as a secret, because it cannot be retrieved
again.

A PAT belongs to one active user and produces that user's actor. A superuser
may manage PATs for any user; other users may manage only their own. PATs can
have a configured default expiry, an explicit expiry, or no expiry, and they
can be revoked or rotated independently of browser sessions.

Session records and PAT records live in dedicated system collections rather
than in user nodes. The REST API reference defines their management endpoints
and response payloads. The [Users and groups](../reference/rest-api/users-and-groups.md)
reference defines the built-in node schemas, ordinary node operations, and
their special errors.
